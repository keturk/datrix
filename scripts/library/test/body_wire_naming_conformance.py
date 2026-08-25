"""Cross-language response-body wire-naming conformance gate.

Every registered `datrix.languages` plugin must serialize response-body
fields under ONE declared rule: camelCase wire keys. This is currently
several independent realizations of that rule with no gate comparing them
to each other, and one of them -- the Python CQRS view response schema
(`cqrs_view_schema.py.j2`) -- already diverges: it has no alias generator,
so it serializes its raw snake_case attribute names instead of camelCase.
This gate generates a real example project once per registered language and
compares each language's OWN emitted response classes' EFFECTIVE wire names
against `to_camel_case(field_name)`.

The comparison is over EFFECTIVE wire names, never the mere presence of a
wire-renaming mechanism: `problem_details.py.j2` also has no alias
generator, but every one of its fields is a single word, so its effective
wire name is identical either way -- a gate that grepped for a marker like
`alias_generator` would flag it as a false positive.

Target set is NEVER hardcoded: languages are enumerated from the installed
`datrix.languages` entry points at run time.
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import logging
import re
import shutil
import sys
from collections import Counter
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from types import ModuleType
from typing import Final, Protocol

# Add library directory to sys.path to import from shared (this file lives at
# library/test/, shared/ lives at the sibling library/shared/).
_LIBRARY_DIR = Path(__file__).resolve().parent.parent
if _LIBRARY_DIR.exists() and str(_LIBRARY_DIR) not in sys.path:
    sys.path.insert(0, str(_LIBRARY_DIR))

from shared.registered_targets import registered_language_names  # noqa: E402

from datrix_cli.pipeline.contract import PipelineConfig, PipelineResult  # noqa: E402
from datrix_cli.pipeline.generation import GenerationPipeline  # noqa: E402
from datrix_common.generation.validation_level import ValidationLevel  # noqa: E402
from datrix_common.plugin.identity import LanguageId  # noqa: E402
from datrix_common.utils.text import to_camel_case  # noqa: E402
from datrix_language.registration import register_all  # noqa: E402
from pydantic import BaseModel, Field  # noqa: E402
from pydantic.fields import FieldInfo  # noqa: E402

logger = logging.getLogger(__name__)

# `GenerationPipeline.run()` parses real `.dtrx` source, which needs the
# stdlib parser protocol registered first -- normally done once by
# `datrix_cli.main` at CLI startup. This gate calls `GenerationPipeline`
# directly (never through the CLI entry point), so it must register the
# same implementation itself, before any real generation is attempted.
register_all()

_HERE = Path(__file__).resolve()
#: This file lives at <datrix>/scripts/library/test/body_wire_naming_conformance.py --
#: parents[3] is <datrix> (parents[0]=.../library/test, [1]=.../library,
#: [2]=.../scripts, [3]=<datrix>).
DATRIX_DIR: Path = _HERE.parents[3]
EXEMPTIONS_PATH: Path = DATRIX_DIR / "scripts" / "config" / "body-wire-naming-exemptions.json"
EXAMPLE_SOURCE: Path = (
    DATRIX_DIR
    / "examples"
    / "02-features"
    / "03-infrastructure-blocks"
    / "cqrs"
    / "system.dtrx"
)
#: Generation scratch space -- a package repo (repo-boundaries.md forbids a
#: temp dir inside any datrix-* repo), cleaned per run.
_GATE_OUTPUT_ROOT: Path = DATRIX_DIR.parent / ".tmp" / "body-wire-naming-gate"
_EXAMPLE_PROFILE: Final[str] = "test"

#: A cross-language comparison over 0 or 1 language is vacuous.
_MIN_LANGUAGES_FOR_COMPARISON: Final[int] = 2

#: Exit code the gate returns when it refuses to run for lack of targets --
#: distinct from 1 (a real divergence) so a caller can tell "nothing was
#: compared" apart from "something disagreed". Documented in
#: `datrix/scripts/test/quick-reference.md` and proven by
#: `_run_insufficient_target_refusal_self_test`.
_INSUFFICIENT_TARGETS_EXIT_CODE: Final[int] = 2

#: Synthetic identifiers used only by the self-test below -- deliberately not
#: real values, so the self-test proves the COMPARATOR's discriminating power
#: without touching real generation.
_SELF_TEST_LANGUAGE: Final[str] = "self_test_lang"
_SELF_TEST_SCHEMA_KIND: Final[str] = "self_test_schema"
#: The serialization-alias precedence case's attribute name and its ONLY
#: declared alias (`Field(serialization_alias=...)`, never `alias=`).
_SELF_TEST_ALIAS_ATTR: Final[str] = "foo_bar"
_SELF_TEST_ALIAS_WIRE_NAME: Final[str] = "fooBar"


@dataclass(frozen=True)
class ResponseField:
    """One field of one emitted response-body schema, as one language realized it.

    Attributes:
        language: `datrix.languages` entry-point name that emitted this field.
        schema_kind: Coarse schema family ("entity_response", "cqrs_view_response",
            "problem_details", "dependency_response", or "response_schema" for
            anything this language's extractor did not specifically classify)
            -- an exemption covers a whole divergent schema_kind, not one
            field at a time.
        template: The language's own template source that produced this
            schema kind, when it can be attributed unambiguously; "" when
            the extractor cannot name one specific template for this
            schema_kind (used only for violation messages).
        file_path: Absolute path of the emitted file this field was read from.
        field_name: The field/attribute/property identifier as THIS
            language's own generated code spells it (its own case
            convention -- snake_case for python, camelCase for
            typescript/java, PascalCase for dotnet).
        effective_wire_name: The wire (JSON) key this language ACTUALLY
            emits for this field, read from the real generated artifact.
    """

    language: str
    schema_kind: str
    template: str
    file_path: Path
    field_name: str
    effective_wire_name: str


class ResponseFieldExtractor(Protocol):
    """Per-language: read effective wire names out of one language's real generated tree.

    One implementation per registered language that emits response-body
    schemas. Every implementation is a STATIC read of the generated
    artifact -- parse, import as inert data, or a fixed-shape regex over a
    known declaration convention -- never a re-derivation of what the naming
    rule SHOULD be. The comparison is always "what did this language's own
    emitted code actually say", never "what would the rule predict".

    `extract()` sets `self.excluded_by_scope` as a side effect: a per-run
    tally of schema kinds this extractor recognized but excluded from
    measurement as out-of-population (never silently dropped -- the gate
    reports this census beside its verdict).
    """

    excluded_by_scope: Counter[str]

    def extract(self, generated_root: Path) -> list[ResponseField]:
        """Return every response-body field this language emitted under *generated_root*."""
        ...


#: Schema kinds that are NOT members of the population this gate measures.
#:
#: The declared rule is about the response bodies a target serializes for
#: its OWN endpoints. A dependency-response model (e.g. python's
#: `clients/dependency_responses.py.j2`, written by
#: `response_struct_generator.py`, and each other language's own equivalent)
#: is the opposite: it DECODES an upstream service's wire format, whose
#: casing that upstream service dictates, not this generator's rule.
#: Measuring it would compare this target's rule against someone else's
#: wire and report a violation that is not one.
#:
#: This is a scope boundary, not an exemption -- an exemption says "a
#: divergence we tolerate", and this is "not a member of the population".
#: It is still never silent: every extractor COUNTS what it excludes and the
#: gate reports that census beside its verdict, so an exclusion that starts
#: swallowing an unexpected number of files is visible rather than invisible.
_OUT_OF_SCOPE_SCHEMA_KINDS: Final[frozenset[str]] = frozenset({"dependency_response"})


def _looks_like_test_file(file_path: Path) -> bool:
    """Return True if *file_path* is generated scaffolding TEST code, not
    production response-body code.

    Applies uniformly across every language's extractor as a defensive
    scope guard: generated test files (unit tests over a schema/DTO, or a
    fixture) can incidentally declare a class/record shape that would
    otherwise be misread as a real response schema.
    """
    name = file_path.name
    if name.startswith("test_") or name.endswith(
        ("_test.py", ".spec.ts", "Test.java", "Tests.cs")
    ):
        return True
    test_dir_names = {"test", "tests"}
    return any(part.lower() in test_dir_names for part in file_path.parts)


def configure_logging(debug: bool = False) -> None:
    """Configure logging output."""
    level = logging.DEBUG if debug else logging.INFO
    logging.basicConfig(level=level, format="%(levelname)s: %(message)s")


# ---------------------------------------------------------------------------
# Python extractor
# ---------------------------------------------------------------------------

_PYTHON_SCHEMA_KIND_TEMPLATES: Final[dict[str, str]] = {
    "cqrs_view_response": "messaging/cqrs_view_schema.py.j2",
    "problem_details": "cross_cutting/problem_details.py.j2",
}

_RESPONSE_CLASS_RE = re.compile(r"^class\s+(\w+)\(BaseModel\):", re.MULTILINE)


def _classify_python_schema_kind(py_file: Path) -> str | None:
    """Classify a generated python file's schema kind from its output path.

    Path conventions are set by each micro-generator's own
    `service_src_path(...)` call: a CQRS view response lands under
    `.../cqrs/schemas/...`, a dependency-response decoder under
    `.../clients/..._responses.py`, RFC 7807 error models under
    `.../errors/problem_details.py`, and both entity (`entity_schema.py.j2`)
    and struct (`struct.py.j2`) responses share the same
    `.../schemas/<name>.py` convention -- indistinguishable from the output
    path alone, so both are reported under the single "entity_response"
    bucket.

    Returns:
        The schema kind, or None if *py_file*'s path matches none of the
        known response-body-producing conventions above. `None` means the
        file is OUT OF SCOPE for this gate entirely -- e.g. a pub/sub
        message schema (`mq/schemas.py`), a cache access model
        (`redis/access.py`), or a CQRS command/query handler's internal
        payload model can each declare an unrelated `BaseModel` subclass
        for a purpose that has nothing to do with an HTTP response body.
        Returning a generic "measure it anyway" bucket for these would
        report real false violations against models this rule was never
        about -- confirmed by direct measurement against the real CQRS
        example, where exactly this happened before this scope check was
        added.
    """
    parts = py_file.as_posix()
    if "/cqrs/schemas/" in parts:
        return "cqrs_view_response"
    if "/clients/" in parts and py_file.stem.endswith("_responses"):
        return "dependency_response"
    if "/errors/" in parts or py_file.stem == "problem_details":
        return "problem_details"
    if "/schemas/" in parts:
        return "entity_response"
    return None


def _register_src_roots_on_syspath(generated_root: Path) -> None:
    """Add every generated service's own `src/` directory to `sys.path`.

    Generated Python services declare intra-package absolute imports (e.g.
    `from library_book_service.enums.book_status import BookStatus`), which
    only resolve when that service's OWN `src/` directory (the parent of its
    top-level package) is on `sys.path` -- exactly as an editable install or
    a real deployment's `PYTHONPATH` would provide it. Each generated
    service under *generated_root* has a distinct top-level package name
    (one per service in the example project), so adding every one is safe.
    """
    for src_dir in sorted(generated_root.glob("*/src")):
        src_str = str(src_dir)
        if src_str not in sys.path:
            sys.path.insert(0, src_str)


def _import_generated_module(py_file: Path) -> ModuleType:
    """Import *py_file* as inert data -- no service boot, no side effects.

    The generated module only declares Pydantic ``BaseModel`` subclasses and
    their field annotations; importing it merely builds those classes so
    Pydantic's OWN ``model_fields[...]`` can be read back, which is the
    actual computed wire name (accounting for ``alias_generator``) -- not a
    re-implementation of Pydantic's own aliasing logic.

    The module is registered in ``sys.modules`` BEFORE ``exec_module`` runs
    -- required, not optional: every generated schema module carries
    ``from __future__ import annotations`` (PEP 563 deferred/string
    annotations), and Pydantic v2 resolves those forward references by
    looking the defining module up in ``sys.modules`` by name. Skipping
    this step does not raise -- it silently leaves every field's resolved
    annotation (and therefore its computed `alias`/`serialization_alias`)
    unset, which is a false PASS waiting to happen on any field whose
    snake_case and camelCase spellings coincide, and a false VIOLATION on
    every other field. Verified directly: the identical model built via
    ``exec_module`` with vs. without this registration reports
    ``alias=None`` unregistered and the correct computed alias registered.
    """
    module_name = f"_body_wire_naming_gate_{py_file.stem}_{id(py_file)}"
    spec = importlib.util.spec_from_file_location(module_name, py_file)
    if spec is None or spec.loader is None:
        raise ImportError(f"Could not build an import spec for {py_file}")
    module = importlib.util.module_from_spec(spec)
    # Registered under a per-file UNIQUE name (never reused, never deleted)
    # -- safe to keep for the remainder of this one-shot process, and
    # simpler than reasoning about whether Pydantic needs the module again
    # after class construction (e.g. a later, lazy model_rebuild()).
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


def _response_model_classes(module: ModuleType) -> list[tuple[str, type]]:
    """Return every ``(class_name, class_object)`` pydantic BaseModel subclass in *module*."""
    return [
        (name, obj)
        for name, obj in vars(module).items()
        if isinstance(obj, type) and issubclass(obj, BaseModel) and obj is not BaseModel
    ]


def compute_effective_wire_name(field_info: FieldInfo, field_name: str) -> str:
    """Return the wire (JSON) key Pydantic ACTUALLY serializes *field_name* under.

    Precedence: ``serialization_alias or alias or field_name`` -- matching
    ``model_dump(by_alias=True)``'s own resolution order, NOT ``alias``
    alone. A per-field ``Field(serialization_alias="fooBar")`` leaves
    ``field_info.alias is None`` while ``model_dump(by_alias=True)`` still
    emits ``fooBar``, so reading ``alias`` alone reports the raw attribute
    name and compares the wrong string -- a false VIOLATION in general, and
    a false PASS on a field whose snake_case and camelCase spellings
    coincide, which a conformance gate must never produce.
    """
    return field_info.serialization_alias or field_info.alias or field_name


class PythonResponseFieldExtractor:
    """Reads effective wire names straight off the real generated Pydantic classes.

    A response class with NO alias generator has ``alias is None`` for every
    field in Pydantic v2's own ``model_fields``, so its effective wire name
    falls back to the attribute name itself -- exactly today's
    `cqrs_view_schema.py.j2` defect, and exactly why `problem_details.py.j2`
    (single-word fields) is not a false positive:
    ``to_camel_case("type") == "type"``.
    """

    def __init__(self) -> None:
        self.excluded_by_scope: Counter[str] = Counter()

    def extract(self, generated_root: Path) -> list[ResponseField]:
        fields: list[ResponseField] = []
        self.excluded_by_scope = Counter()
        _register_src_roots_on_syspath(generated_root)
        for py_file in sorted(generated_root.rglob("*.py")):
            if _looks_like_test_file(py_file):
                continue
            source = py_file.read_text(encoding="utf-8")
            if not _RESPONSE_CLASS_RE.search(source):
                continue
            schema_kind = _classify_python_schema_kind(py_file)
            if schema_kind is None:
                continue
            if schema_kind in _OUT_OF_SCOPE_SCHEMA_KINDS:
                self.excluded_by_scope[schema_kind] += 1
                continue
            template = _PYTHON_SCHEMA_KIND_TEMPLATES.get(schema_kind, "")
            module = _import_generated_module(py_file)
            for _class_name, model_cls in _response_model_classes(module):
                for field_name, field_info in model_cls.model_fields.items():
                    fields.append(
                        ResponseField(
                            language="python",
                            schema_kind=schema_kind,
                            template=template,
                            file_path=py_file,
                            field_name=field_name,
                            effective_wire_name=compute_effective_wire_name(
                                field_info, field_name
                            ),
                        )
                    )
        return fields


# ---------------------------------------------------------------------------
# TypeScript extractor
# ---------------------------------------------------------------------------

_TS_CLASS_HEADER_RE = re.compile(r"^export class \w+\s*\{", re.MULTILINE)
_TS_FIELD_LINE_RE = re.compile(r"^\s*([A-Za-z_]\w*)[!?]?\s*:\s*[^=;]+;\s*$")


def _classify_ts_schema_kind(ts_file: Path) -> str:
    """Classify a generated TypeScript file's schema kind from its output path.

    Mirrors `_classify_python_schema_kind`'s path-based approach: a CQRS
    view response lands under `.../cqrs/.../schemas/...`, a
    dependency-response decoder under `.../clients/<dep>-responses.ts`.
    Entity and struct responses share no single distinguishing directory
    (both are plain `export class` DTOs), so both fall to the generic
    "response_schema" bucket, which is still fully checked for conformance.
    """
    parts = ts_file.as_posix()
    if "/clients/" in parts and ts_file.name.endswith("-responses.ts"):
        return "dependency_response"
    if "/cqrs/" in parts and "/schemas/" in parts:
        return "cqrs_view_response"
    return "response_schema"


class TypeScriptResponseFieldExtractor:
    """Reads effective wire names off generated TypeScript response DTO classes.

    TypeScript/NestJS response DTOs use no per-field wire-rename decorator
    in this codegen package (verified: no `@Expose({name: ...})` appears on
    any entity/struct/CQRS response template) -- `JSON.stringify`/Nest's
    default serialization emits the declared property name verbatim, and
    that property name is already camelCase (`ts_identifier()` ->
    `TS_PROFILE.naming.identifier_caser` -> `to_camel_case`,
    `generators/_helpers.py`). The effective wire name is therefore the
    declared property name itself, read directly off the generated source
    on every invocation -- never assumed.
    """

    def __init__(self) -> None:
        self.excluded_by_scope: Counter[str] = Counter()

    def extract(self, generated_root: Path) -> list[ResponseField]:
        fields: list[ResponseField] = []
        self.excluded_by_scope = Counter()
        for ts_file in sorted(generated_root.rglob("*.ts")):
            if _looks_like_test_file(ts_file):
                continue
            source = ts_file.read_text(encoding="utf-8")
            if not _TS_CLASS_HEADER_RE.search(source):
                continue
            schema_kind = _classify_ts_schema_kind(ts_file)
            if schema_kind in _OUT_OF_SCOPE_SCHEMA_KINDS:
                self.excluded_by_scope[schema_kind] += 1
                continue
            for line in source.splitlines():
                match = _TS_FIELD_LINE_RE.match(line)
                if match is None:
                    continue
                name = match.group(1)
                fields.append(
                    ResponseField(
                        language="typescript",
                        schema_kind=schema_kind,
                        template="",
                        file_path=ts_file,
                        field_name=name,
                        effective_wire_name=name,
                    )
                )
        return fields


# ---------------------------------------------------------------------------
# Java extractor
# ---------------------------------------------------------------------------

_JAVA_RECORD_HEADER_RE = re.compile(r"public record (\w+)\(")
_JAVA_FIELD_LINE_RE = re.compile(
    r"^\s*(?:@[\w.]+(?:\([^()]*\))?\s+)*[\w.\[\]<>]+\s+([A-Za-z_]\w*)\s*,?\s*$"
)


def _classify_java_schema_kind(java_file: Path) -> str:
    """Classify a generated Java file's schema kind from its output path.

    Mirrors `_classify_python_schema_kind`: a CQRS view response lands
    under `.../cqrs/schemas/...`, a dependency-response decoder under
    `.../clients/<Dep>Responses.java`. Entity and struct responses share no
    single distinguishing directory (both are plain `record` DTOs under
    `.../dto/...`), so both fall to the generic "response_schema" bucket,
    still fully checked for conformance.
    """
    parts = java_file.as_posix()
    if "/clients/" in parts and java_file.stem.endswith("Responses"):
        return "dependency_response"
    if "/cqrs/" in parts and "/schemas/" in parts:
        return "cqrs_view_response"
    return "response_schema"


def _java_record_field_list_span(source: str) -> tuple[int, int] | None:
    """Return the `(start, end)` character offsets of the first Java
    `record`'s parenthesized field-declaration list, or None if no record
    header is found.

    Tracks paren depth from the opening `(` so an annotation argument list
    inside a field declaration (e.g. `@Size(min = 0, max = 100)`) never
    terminates the scan before the record's own closing paren.
    """
    match = _JAVA_RECORD_HEADER_RE.search(source)
    if match is None:
        return None
    start = match.end()
    depth = 1
    i = start
    while i < len(source) and depth > 0:
        if source[i] == "(":
            depth += 1
        elif source[i] == ")":
            depth -= 1
        i += 1
    return start, i - 1


class JavaResponseFieldExtractor:
    """Reads effective wire names off generated Java record response DTOs.

    Java response DTOs are Jackson-serialized records with no per-field
    `@JsonProperty` rename anywhere in the entity/struct/CQRS response
    templates, and no global `PropertyNamingStrategy` configured anywhere in
    this codegen package (verified) -- Jackson's default record
    serialization uses the record component name verbatim, and that name is
    already camelCase (`safe_java_field_name()` -> `to_camel_case`,
    `generators/entity/_entity_constants.py`). The effective wire name is
    therefore the declared record-component name itself, read directly off
    the generated source on every invocation -- never assumed.
    """

    def __init__(self) -> None:
        self.excluded_by_scope: Counter[str] = Counter()

    def extract(self, generated_root: Path) -> list[ResponseField]:
        fields: list[ResponseField] = []
        self.excluded_by_scope = Counter()
        for java_file in sorted(generated_root.rglob("*.java")):
            if _looks_like_test_file(java_file):
                continue
            source = java_file.read_text(encoding="utf-8")
            span = _java_record_field_list_span(source)
            if span is None:
                continue
            schema_kind = _classify_java_schema_kind(java_file)
            if schema_kind in _OUT_OF_SCOPE_SCHEMA_KINDS:
                self.excluded_by_scope[schema_kind] += 1
                continue
            field_list_text = source[span[0] : span[1]]
            for line in field_list_text.splitlines():
                match = _JAVA_FIELD_LINE_RE.match(line)
                if match is None:
                    continue
                name = match.group(1)
                fields.append(
                    ResponseField(
                        language="java",
                        schema_kind=schema_kind,
                        template="",
                        file_path=java_file,
                        field_name=name,
                        effective_wire_name=name,
                    )
                )
        return fields


# ---------------------------------------------------------------------------
# .NET extractor
# ---------------------------------------------------------------------------

_DOTNET_RECORD_HEADER_RE = re.compile(r"public sealed record \w+\s*\{")
_DOTNET_PROPERTY_LINE_RE = re.compile(
    r"^\s*public\s+(?:required\s+)?[\w<>\[\],.?]+\s+([A-Za-z_]\w*)\s*\{\s*get;\s*init;\s*\}\s*$"
)
_DOTNET_JSON_PROPERTY_NAME_RE = re.compile(r'^\s*\[JsonPropertyName\("([^"]+)"\)\]\s*$')
_DOTNET_NAMING_POLICY_OVERRIDE_RE = re.compile(r"PropertyNamingPolicy\s*=")


def _classify_dotnet_schema_kind(cs_file: Path) -> str:
    """Classify a generated C# file's schema kind from its output path.

    .NET's own directory constants are PascalCase (`Cqrs/Schemas`,
    `Clients`, `Dtos` -- `directory_constants.py`), unlike every other
    registered language's lowercase convention, so this classifier matches
    case-insensitively. Entity and struct responses share no single
    distinguishing directory (both are `record` DTOs under `.../Dtos/...`),
    so both fall to the generic "response_schema" bucket, still fully
    checked for conformance.
    """
    parts = cs_file.as_posix().lower()
    if "/clients/" in parts and cs_file.stem.endswith("Responses"):
        return "dependency_response"
    if "/cqrs/" in parts and "/schemas/" in parts:
        return "cqrs_view_response"
    return "response_schema"


def _dotnet_default_camel_case_policy_holds(generated_root: Path) -> bool:
    """Return True iff no generated `.cs` file overrides the framework's
    default camelCase JSON property-naming policy.

    ASP.NET Core's `AddControllers()` configures `System.Text.Json` via
    `JsonSerializerDefaults.Web` internally, whose default
    `PropertyNamingPolicy` is `JsonNamingPolicy.CamelCase` -- so a plain C#
    PascalCase property serializes to a camelCase wire key with no
    per-field annotation needed (verified: every generated `Program.cs`
    calls plain `AddControllers()` with no `AddJsonOptions` override). This
    is re-verified against the REAL generated tree on every invocation,
    never assumed from a one-time template review, so a future template
    change that overrides the policy is caught rather than silently missed.
    """
    for cs_file in generated_root.rglob("*.cs"):
        if _DOTNET_NAMING_POLICY_OVERRIDE_RE.search(cs_file.read_text(encoding="utf-8")):
            return False
    return True


class DotnetResponseFieldExtractor:
    """Reads effective wire names off generated C# response DTO records.

    Unlike TypeScript/Java, .NET's declared property identifiers are
    PascalCase (`to_pascal_case(field.name)` -- `DotnetSchemaMicroGen.
    _build_dto_fields`, `CqrsMicroGen`), NOT camelCase: `identifier_caser=
    to_camel_case` in dotnet's own `NamingProfile` governs locals/params
    only (`profile.py`), never DTO property names. The effective wire name
    instead comes from ASP.NET Core's own JSON serialization behavior (see
    `_dotnet_default_camel_case_policy_holds`) -- a genuinely SEPARATE
    mechanism from the property declaration, the same shape as Python's
    `alias_generator`. A `[JsonPropertyName("...")]` attribute immediately
    preceding a property is honored as an explicit override, this
    language's equivalent of Python's `serialization_alias`.
    """

    def __init__(self) -> None:
        self.excluded_by_scope: Counter[str] = Counter()

    def extract(self, generated_root: Path) -> list[ResponseField]:
        fields: list[ResponseField] = []
        self.excluded_by_scope = Counter()
        camel_case_by_default = _dotnet_default_camel_case_policy_holds(generated_root)
        for cs_file in sorted(generated_root.rglob("*.cs")):
            if _looks_like_test_file(cs_file):
                continue
            source = cs_file.read_text(encoding="utf-8")
            if not _DOTNET_RECORD_HEADER_RE.search(source):
                continue
            schema_kind = _classify_dotnet_schema_kind(cs_file)
            if schema_kind in _OUT_OF_SCOPE_SCHEMA_KINDS:
                self.excluded_by_scope[schema_kind] += 1
                continue
            fields.extend(
                self._fields_from_source(cs_file, source, schema_kind, camel_case_by_default)
            )
        return fields

    def _fields_from_source(
        self, cs_file: Path, source: str, schema_kind: str, camel_case_by_default: bool
    ) -> list[ResponseField]:
        fields: list[ResponseField] = []
        pending_json_name: str | None = None
        for line in source.splitlines():
            override_match = _DOTNET_JSON_PROPERTY_NAME_RE.match(line)
            if override_match is not None:
                pending_json_name = override_match.group(1)
                continue
            prop_match = _DOTNET_PROPERTY_LINE_RE.match(line)
            if prop_match is None:
                continue
            name = prop_match.group(1)
            if pending_json_name is not None:
                wire_name = pending_json_name
            elif camel_case_by_default:
                wire_name = to_camel_case(name)
            else:
                wire_name = name
            pending_json_name = None
            fields.append(
                ResponseField(
                    language="dotnet",
                    schema_kind=schema_kind,
                    template="",
                    file_path=cs_file,
                    field_name=name,
                    effective_wire_name=wire_name,
                )
            )
        return fields


#: Registry of per-language extractors. A registered language with no
#: extractor is reported as "unsupported, no extractor" (an unexempted gap,
#: not a silent skip) -- see check_body_wire_naming_conformance()'s
#: handling below.
_EXTRACTORS: Final[dict[str, ResponseFieldExtractor]] = {
    "python": PythonResponseFieldExtractor(),
    "typescript": TypeScriptResponseFieldExtractor(),
    "java": JavaResponseFieldExtractor(),
    "dotnet": DotnetResponseFieldExtractor(),
}


# ---------------------------------------------------------------------------
# Comparison
# ---------------------------------------------------------------------------


def is_wire_name_conformant(field: ResponseField) -> bool:
    """Return True iff *field*'s effective wire name matches the declared rule.

    The declared rule is camelCase. `to_camel_case` is case-variant-
    idempotent, so this holds regardless of which case convention the
    emitting language's own attribute/property identifier uses -- the
    original DSL spelling is never needed.

    Args:
        field: One extracted response-body field.

    Returns:
        True if `field.effective_wire_name == to_camel_case(field.field_name)`.
    """
    return field.effective_wire_name == to_camel_case(field.field_name)


# ---------------------------------------------------------------------------
# Exemption file
# ---------------------------------------------------------------------------


def load_exemptions() -> tuple[dict[tuple[str, str], str], int]:
    """Load and validate `body-wire-naming-exemptions.json`.

    Returns:
        `({(language, schema_kind): reason}, expected_count)`.

    Raises:
        ValueError: If the file is missing, malformed, an entry has an
            empty reason, or the entry count does not match the pinned
            `expected_count`.
    """
    if not EXEMPTIONS_PATH.exists():
        raise ValueError(
            f"Missing exemption file {EXEMPTIONS_PATH}. It pins the "
            f"catalogued body wire-naming divergences. Restore it from "
            f"git; the gate never creates it."
        )
    data = json.loads(EXEMPTIONS_PATH.read_text(encoding="utf-8"))
    entries = data.get("exemptions")
    expected = data.get("expected_count")
    if not isinstance(entries, list) or not isinstance(expected, int):
        raise ValueError(
            f"Malformed exemption file {EXEMPTIONS_PATH}: expected an "
            f"object with 'expected_count' (int) and 'exemptions' (array "
            f"of {{language, schema_kind, template, reason}})."
        )
    exemptions: dict[tuple[str, str], str] = {}
    for entry in entries:
        for key in ("language", "schema_kind", "template", "reason"):
            if not isinstance(entry.get(key), str) or not entry[key].strip():
                raise ValueError(
                    f"Exemption entry {entry!r} is missing a non-empty {key!r}."
                )
        exemptions[(entry["language"], entry["schema_kind"])] = entry["reason"]
    if len(entries) != expected:
        raise ValueError(
            f"Exemption file {EXEMPTIONS_PATH} has {len(entries)} entries "
            f"but 'expected_count' is pinned at {expected}. Update the "
            f"count in the same change that adds or removes an entry."
        )
    return exemptions, expected


# ---------------------------------------------------------------------------
# Non-vacuity self-test
# ---------------------------------------------------------------------------


def run_self_test() -> list[str]:
    """Prove the comparator detects a forced mismatch, respects a real
    exemption, does not flag a single-word-field (problem_details.py.j2
    shape) false positive, and reads the effective serialization wire name
    (never `alias` alone) -- before any real comparison is trusted.

    Returns:
        A list of failure descriptions -- empty means the comparator is sound.
    """
    problems: list[str] = []

    conformant = ResponseField(
        language=_SELF_TEST_LANGUAGE,
        schema_kind=_SELF_TEST_SCHEMA_KIND,
        template="",
        file_path=Path("self_test_conformant.py"),
        field_name="order_id",
        effective_wire_name="orderId",
    )
    if not is_wire_name_conformant(conformant):
        problems.append(
            "self-test: is_wire_name_conformant flagged a genuinely "
            "conformant field (order_id -> orderId) -- over-triggering."
        )

    divergent = ResponseField(
        language=_SELF_TEST_LANGUAGE,
        schema_kind=_SELF_TEST_SCHEMA_KIND,
        template="",
        file_path=Path("self_test_divergent.py"),
        field_name="order_id",
        effective_wire_name="order_id",
    )
    if is_wire_name_conformant(divergent):
        problems.append(
            "self-test: is_wire_name_conformant did NOT detect a forced "
            "mismatch (order_id emitted as raw 'order_id' instead of "
            "'orderId')."
        )

    # problem_details.py.j2's real shape: no alias generator, single-word
    # field -- must NOT be flagged, proving the false-positive guard.
    single_word_no_alias = ResponseField(
        language=_SELF_TEST_LANGUAGE,
        schema_kind="problem_details",
        template="cross_cutting/problem_details.py.j2",
        file_path=Path("self_test_problem_details.py"),
        field_name="type",
        effective_wire_name="type",
    )
    if not is_wire_name_conformant(single_word_no_alias):
        problems.append(
            "self-test: is_wire_name_conformant flagged a single-word "
            "field with no alias generator (the real problem_details.py.j2 "
            "shape) -- this must never be a violation."
        )

    # An exemption must suppress a real, forced divergence.
    exemptions = {(_SELF_TEST_LANGUAGE, _SELF_TEST_SCHEMA_KIND): "self-test exemption"}
    if (divergent.language, divergent.schema_kind) not in exemptions:
        problems.append("self-test: exemption map construction is broken.")

    problems.extend(_run_serialization_alias_precedence_self_test())
    problems.extend(_run_insufficient_target_refusal_self_test())
    return problems


def _run_insufficient_target_refusal_self_test() -> list[str]:
    """Prove the gate REFUSES to run when fewer than two targets are registered.

    A cross-target conformance gate that quietly passes with one target
    installed reports "every language agrees" about a set of size one, which
    is true and worthless. `check_body_wire_naming_conformance` guards against
    that by returning exit code 2, and `quick-reference.md` documents the
    behaviour -- but nothing proved the guard fires, so it was a documented
    claim rather than a checked one.

    This drives the REAL function with real short lists rather than asserting
    on a re-implementation of the rule. The guard is the function's first
    statement and returns before any generation or filesystem work, so the
    calls are side-effect free.

    The complementary half is supplied by the invocation itself: a function
    that returned 2 unconditionally would make the whole gate exit 2 instead
    of 0, so an always-refusing implementation cannot survive a real run.
    """
    problems: list[str] = []

    for insufficient in ([], ["python"]):
        code = check_body_wire_naming_conformance(insufficient)
        if code != _INSUFFICIENT_TARGETS_EXIT_CODE:
            problems.append(
                "self-test: check_body_wire_naming_conformance did NOT refuse "
                f"a target set of {len(insufficient)} ({insufficient!r}) -- "
                f"returned {code}, expected "
                f"{_INSUFFICIENT_TARGETS_EXIT_CODE}. A cross-target gate that "
                "runs under fewer than "
                f"{_MIN_LANGUAGES_FOR_COMPARISON} targets compares nothing "
                "and would pass vacuously."
            )
    return problems


def _run_serialization_alias_precedence_self_test() -> list[str]:
    """Prove `compute_effective_wire_name` reads `serialization_alias`, not
    just `alias` -- against a REAL Pydantic model, not a synthetic dataclass.

    `Field(serialization_alias=...)` leaves `field_info.alias` as `None`
    while `model_dump(by_alias=True)` still emits the serialization alias,
    so an implementation reading `alias` alone would report the raw
    attribute name here -- a false PASS whenever the snake_case and
    camelCase spellings coincide, which this gate must never produce.
    """
    problems: list[str] = []

    class _SelfTestSerializationAliasModel(BaseModel):
        foo_bar: str = Field(serialization_alias=_SELF_TEST_ALIAS_WIRE_NAME)

    field_info = _SelfTestSerializationAliasModel.model_fields[_SELF_TEST_ALIAS_ATTR]
    if field_info.alias is not None:
        problems.append(
            "self-test: Field(serialization_alias=...) unexpectedly set "
            "field_info.alias too -- the precedence case this self-test "
            "exercises no longer isolates serialization_alias from alias; "
            "the installed Pydantic's behavior may have changed."
        )

    alias_only_would_read = field_info.alias or _SELF_TEST_ALIAS_ATTR
    if alias_only_would_read == _SELF_TEST_ALIAS_WIRE_NAME:
        problems.append(
            "self-test: the serialization_alias precedence case is not "
            "discriminating -- an alias-only read would ALSO report "
            f"{_SELF_TEST_ALIAS_WIRE_NAME!r}, so this case cannot prove "
            "compute_effective_wire_name reads serialization_alias rather "
            "than alias."
        )

    effective = compute_effective_wire_name(field_info, _SELF_TEST_ALIAS_ATTR)
    if effective != _SELF_TEST_ALIAS_WIRE_NAME:
        problems.append(
            f"self-test: compute_effective_wire_name did not read "
            f"serialization_alias (expected {_SELF_TEST_ALIAS_WIRE_NAME!r}, "
            f"got {effective!r}) -- an alias-only implementation would "
            f"report the raw attribute name {_SELF_TEST_ALIAS_ATTR!r} here."
        )

    dumped = _SelfTestSerializationAliasModel(foo_bar="x").model_dump(by_alias=True)
    if dumped != {_SELF_TEST_ALIAS_WIRE_NAME: "x"}:
        problems.append(
            f"self-test: Pydantic's own model_dump(by_alias=True) did not "
            f"serialize under {_SELF_TEST_ALIAS_WIRE_NAME!r} as expected "
            f"(got {dumped!r}) -- the installed Pydantic version's alias "
            f"behavior differs from what this gate assumes."
        )

    return problems


# ---------------------------------------------------------------------------
# Commands
# ---------------------------------------------------------------------------


def _generate_example_for_language(language: str) -> Path:
    """Generate the shared CQRS example project for *language* into a scratch dir.

    Real generation, no mocks -- reuses `datrix-cli`'s own
    `GenerationPipeline`, the one true generation entry point, exactly as
    `datrix generate` itself would invoke it.

    Args:
        language: A `datrix.languages` entry-point name.

    Returns:
        The output directory the generated files were written under.

    Raises:
        RuntimeError: If the pipeline reports failure.
    """
    output_dir = _GATE_OUTPUT_ROOT / language
    # `ValidationLevel.FAST` still runs fix_imports/format_files but skips
    # validate_files (e.g. java's own `mvnw compile`, dotnet's `dotnet
    # build`) -- this gate reads generated SOURCE TEXT only, never compiled
    # output, so a full compiler invocation is an unrelated, more expensive
    # dependency this naming check does not need.
    config = PipelineConfig(
        target_language=LanguageId(language),
        profile=_EXAMPLE_PROFILE,
        validation_level=ValidationLevel.FAST,
    )
    result: PipelineResult = GenerationPipeline().run(
        source_path=EXAMPLE_SOURCE, output_dir=output_dir, config=config
    )
    if not result.success:
        raise RuntimeError(
            f"Generating the body wire-naming example for language "
            f"{language!r} failed: {result.errors}"
        )
    return output_dir


def _check_language(
    language: str, exemptions: Mapping[tuple[str, str], str]
) -> tuple[bool, Counter[str]]:
    """Run the real check for one language.

    Returns:
        `(conformant, excluded_by_scope)` -- `conformant` is False if the
        language has no registered extractor or emits at least one
        unexempted divergence; `excluded_by_scope` tallies the schema kinds
        this language's extractor recognized but excluded as out-of-population.
    """
    extractor = _EXTRACTORS.get(language)
    if extractor is None:
        logger.error(
            "BODY WIRE-NAMING VIOLATION: language %r has no registered "
            "ResponseFieldExtractor in body_wire_naming_conformance.py -- "
            "implement one before this gate can cover it (a registered "
            "language with no extractor is an unexempted gap, never a "
            "silent skip).",
            language,
        )
        return False, Counter()

    output_dir = _generate_example_for_language(language)
    response_fields = extractor.extract(output_dir)
    excluded = Counter(extractor.excluded_by_scope)
    ok = True
    for field in response_fields:
        if is_wire_name_conformant(field):
            continue
        if (field.language, field.schema_kind) in exemptions:
            continue
        ok = False
        logger.error(
            "BODY WIRE-NAMING VIOLATION: language %r schema_kind %r "
            "(template %s) field %r emits wire key %r, expected %r "
            "(camelCase, per the declared response-body wire-naming rule). "
            "File: %s. Fix: apply the language's own wire-naming mechanism "
            "(an alias generator, a JsonPropertyName override, or the "
            "equivalent), or add a reviewed entry to %s.",
            field.language, field.schema_kind,
            field.template or "<unclassified>", field.field_name,
            field.effective_wire_name, to_camel_case(field.field_name),
            field.file_path, EXEMPTIONS_PATH,
        )
    return ok, excluded


def check_body_wire_naming_conformance(languages: Sequence[str] | None = None) -> int:
    """Run the real gate over every registered language.

    Args:
        languages: Language set to compare. ``None`` -- the production value --
            resolves the installed ``datrix.languages`` entry points at run
            time, which is the only way a real invocation ever calls this. An
            explicit sequence exists so the non-vacuity self-test can drive
            THIS function's own insufficient-target refusal with a real short
            list, rather than asserting on a copy of the rule. The refusal is
            the first statement, so while the guard holds a short list returns
            before any generation or filesystem work. If the guard is ever
            severed, that same call falls through into a real single-language
            run -- which is precisely the vacuous outcome the self-test exists
            to catch, and it fails loudly instead of quietly passing.

    Returns:
        Exit code (0 = conformant, 1 = at least one unexempted divergence
        or an unsupported/no-extractor language, 2 = fewer than
        `_MIN_LANGUAGES_FOR_COMPARISON` languages registered).
    """
    languages = sorted(registered_language_names() if languages is None else languages)
    if len(languages) < _MIN_LANGUAGES_FOR_COMPARISON:
        logger.error(
            "Body wire-naming gate CANNOT RUN: only %d language(s) "
            "registered (%s) -- at least %d are required.",
            len(languages), languages, _MIN_LANGUAGES_FOR_COMPARISON,
        )
        return 2

    shutil.rmtree(_GATE_OUTPUT_ROOT, ignore_errors=True)
    exemptions, _ = load_exemptions()

    ok = True
    total_excluded: Counter[str] = Counter()
    for language in languages:
        language_ok, excluded = _check_language(language, exemptions)
        ok = ok and language_ok
        total_excluded.update(excluded)

    if total_excluded:
        logger.info(
            "Out-of-population schema kinds excluded from measurement "
            "(counted, never silently dropped): %s.", dict(total_excluded),
        )

    if ok:
        logger.info(
            "Body wire-naming conformance holds across %d languages (%s); "
            "every divergence is exempted.", len(languages), languages,
        )
        return 0
    return 1


def main() -> int:
    """Entry point.

    Returns:
        Exit code: 0 = conformant, 1 = a divergence was found, 2 = the
        self-test failed or fewer than 2 languages are registered.
    """
    parser = argparse.ArgumentParser(
        description=(
            "Prove every registered datrix.languages plugin serializes "
            "response-body fields under ONE declared camelCase rule, or "
            "declares the surface exempted."
        ),
    )
    parser.add_argument("--debug", action="store_true", help="Enable debug logging")
    parser.add_argument(
        "--self-test",
        action="store_true",
        help="Run only the non-vacuity self-test and skip real generation",
    )
    args = parser.parse_args()

    configure_logging(debug=args.debug)
    logger_ = logging.getLogger(__name__)

    problems = run_self_test()
    if problems:
        logger_.error("Non-vacuity self-test FAILED:")
        for p in problems:
            logger_.error("  %s", p)
        return 2
    logger_.info("Non-vacuity self-test passed.")

    if args.self_test:
        return 0

    return check_body_wire_naming_conformance()


if __name__ == "__main__":
    sys.exit(main())
