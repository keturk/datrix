"""Cross-language response-body wire-naming conformance gate.

Every registered `datrix.languages` plugin must serialize response-body
fields under ONE declared rule: camelCase wire keys. This gate generates a
real example project once per registered language and compares each
language's OWN emitted response classes' EFFECTIVE wire names against
`datrix_codegen_common.generation.wire_naming.body_wire_name(field_name)` --
the one home of the declared rule, called rather than restated, so the gate
and the frontend client contract that computes body wire keys can never be
measuring two different rules.

How a language's emitted response classes are read belongs to the language:
each registered language declares a `LanguageConformanceProbes`
(`LanguagePlugin.conformance_probes`,
`datrix_codegen_kernel.parity.conformance_probes`) whose
`response_body_wire_fields(generated_root)` returns every classified response
field with the JSON key the artifact actually emits. Reading Pydantic's
computed aliases needs Pydantic, reading a TypeScript DTO needs its declaration
convention -- neither can live in a shared script without naming a language.
This gate holds the comparison, the population rule and the exemptions, and
NEVER names a language; its self-test proves that first
(`shared.registered_targets.target_references_in_module`).

The comparison is over EFFECTIVE wire names, never the mere presence of a
wire-renaming mechanism: a response class with no alias generator whose
fields are all single words has the same effective wire name either way, so a
gate that grepped for a marker like `alias_generator` would flag it as a
false positive.

A probe that returns no in-population field for the generated CQRS example
fails the gate: a census that finds nothing proves nothing.

A second census covers what that comparison cannot see: a transform applied
AFTER serialization. A framework-level response transform (a global
interceptor, a response-model setting that changes how field names are
serialized) rewrites every outgoing body, so it is invisible to a comparison
over the emitted response classes. Each language declares the regular
expressions that spell such a transform in its own framework
(`LanguageCapabilityDeclaration.response_body_transform_idioms`); this gate
greps the generated tree for them and every hit must be a typed entry in the
exemption file's `transform_exemptions` (language, path suffix, matched text,
reason). An exemption that matches no hit is stale and fails too.

Target set is NEVER hardcoded: languages are enumerated from the installed
`datrix.languages` entry points at run time.
"""

from __future__ import annotations

import argparse
import json
import logging
import re
import shutil
import sys
from collections import Counter
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Final

# Add library directory to sys.path to import from shared (this file lives at
# library/test/, shared/ lives at the sibling library/shared/).
_LIBRARY_DIR = Path(__file__).resolve().parent.parent
if _LIBRARY_DIR.exists() and str(_LIBRARY_DIR) not in sys.path:
    sys.path.insert(0, str(_LIBRARY_DIR))

from shared.registered_targets import (  # noqa: E402
    registered_language_names,
    self_test_gate_names_no_target,
)

from datrix_cli.pipeline.contract import PipelineConfig, PipelineResult  # noqa: E402
from datrix_cli.pipeline.generation import GenerationPipeline  # noqa: E402
from datrix_cli.generation.validation_level import ValidationLevel  # noqa: E402
from datrix_codegen_common.generation.wire_naming import body_wire_name  # noqa: E402
from datrix_codegen_kernel.parity.conformance_probes import (  # noqa: E402
    DocumentationSurfaces,
    EnumClassifierRender,
    LanguageConformanceProbes,
    ResponseBodyWireField,
    conformance_probes_of_language_plugin,
    language_conformance_probes,
)
from datrix_common.errors.plugin import PluginNotFoundError, PluginValidationError  # noqa: E402
from datrix_common.plugin.capability_resolution import declaration_for_language  # noqa: E402
from datrix_common.plugin.identity import LanguageId  # noqa: E402
from datrix_language.registration import register_all  # noqa: E402

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


@dataclass(frozen=True)
class ResponseField:
    """One field of one emitted response-body schema, as one language realized it.

    Attributes:
        language: `datrix.languages` entry-point name that emitted this field.
        schema_kind: Coarse schema family ("entity_response", "cqrs_view_response",
            "problem_details", "dependency_response", or "response_schema" for
            anything this language's probe did not specifically classify)
            -- an exemption covers a whole divergent schema_kind, not one
            field at a time.
        template: The language's own template source that produced this
            schema kind, when it can be attributed unambiguously; "" when
            the probe cannot name one specific template for this
            schema_kind (used only for violation messages).
        file_path: Absolute path of the emitted file this field was read from.
        field_name: The field/attribute/property identifier as THIS
            language's own generated code spells it (its own case
            convention -- snake_case for python, camelCase for
            typescript).
        effective_wire_name: The wire (JSON) key this language ACTUALLY
            emits for this field, read from the real generated artifact.
    """

    language: str
    schema_kind: str
    template: str
    file_path: Path
    field_name: str
    effective_wire_name: str


#: Schema kinds that are NOT members of the population this gate measures.
#:
#: The declared rule is about the response bodies a target serializes for
#: its OWN endpoints. A dependency-response model is the opposite: it DECODES
#: an upstream service's wire format, whose casing that upstream service
#: dictates, not this generator's rule. Measuring it would compare this
#: target's rule against someone else's wire and report a violation that is
#: not one.
#:
#: This is a scope boundary, not an exemption -- an exemption says "a
#: divergence we tolerate", and this is "not a member of the population".
#: It is still never silent: the gate COUNTS the files it excludes per kind
#: and reports that census beside its verdict, so an exclusion that starts
#: swallowing an unexpected number of files is visible rather than invisible.
_OUT_OF_SCOPE_SCHEMA_KINDS: Final[frozenset[str]] = frozenset({"dependency_response"})


def configure_logging(debug: bool = False) -> None:
    """Configure logging output."""
    level = logging.DEBUG if debug else logging.INFO
    logging.basicConfig(level=level, format="%(levelname)s: %(message)s")


# ---------------------------------------------------------------------------
# Comparison
# ---------------------------------------------------------------------------


def is_wire_name_conformant(field: ResponseField) -> bool:
    """Return True iff *field*'s effective wire name matches the declared rule.

    The declared rule is `datrix_codegen_common.generation.wire_naming.body_wire_name`
    -- camelCase -- and this gate calls THAT function rather than restating
    the rule, so a gate that passes and a contract that computes a wire key
    can never be measuring two different rules. It is case-variant-idempotent,
    so this holds regardless of which case convention the emitting language's
    own attribute/property identifier uses -- the original DSL spelling is
    never needed.

    Args:
        field: One extracted response-body field.

    Returns:
        True if `field.effective_wire_name == body_wire_name(field.field_name)`.
    """
    return field.effective_wire_name == body_wire_name(field.field_name)


def measured_population(
    language: str, probe_fields: Sequence[ResponseBodyWireField]
) -> tuple[list[ResponseField], Counter[str]]:
    """Split a probe's fields into the measured population and the counted exclusions.

    Args:
        language: The language whose probe returned *probe_fields*.
        probe_fields: Every classified field the probe returned.

    Returns:
        `(measured, excluded_files_by_kind)` -- the fields of every in-population
        schema kind, and, per out-of-population kind, the number of distinct
        files excluded.
    """
    measured: list[ResponseField] = []
    excluded_files: dict[str, set[Path]] = {}
    for item in probe_fields:
        if item.schema_kind in _OUT_OF_SCOPE_SCHEMA_KINDS:
            excluded_files.setdefault(item.schema_kind, set()).add(item.file_path)
            continue
        measured.append(
            ResponseField(
                language=language,
                schema_kind=item.schema_kind,
                template=item.template,
                file_path=item.file_path,
                field_name=item.field_name,
                effective_wire_name=item.effective_wire_name,
            )
        )
    return measured, Counter({kind: len(files) for kind, files in excluded_files.items()})


# ---------------------------------------------------------------------------
# Exemption file
# ---------------------------------------------------------------------------


def load_exemptions() -> dict[tuple[str, str], str]:
    """Load and validate `body-wire-naming-exemptions.json`.

    Returns:
        `{(language, schema_kind): reason}`.

    Raises:
        ValueError: If the file is missing, malformed, or an entry has an
            empty reason.
    """
    if not EXEMPTIONS_PATH.exists():
        raise ValueError(
            f"Missing exemption file {EXEMPTIONS_PATH}. It pins the "
            f"catalogued body wire-naming divergences. Restore it from "
            f"git; the gate never creates it."
        )
    data = json.loads(EXEMPTIONS_PATH.read_text(encoding="utf-8"))
    entries = data.get("exemptions")
    if not isinstance(entries, list):
        raise ValueError(
            f"Malformed exemption file {EXEMPTIONS_PATH}: expected an "
            f"object with 'exemptions' (array of "
            f"{{language, schema_kind, template, reason}})."
        )
    exemptions: dict[tuple[str, str], str] = {}
    for entry in entries:
        for key in ("language", "schema_kind", "template", "reason"):
            if not isinstance(entry.get(key), str) or not entry[key].strip():
                raise ValueError(
                    f"Exemption entry {entry!r} is missing a non-empty {key!r}."
                )
        exemptions[(entry["language"], entry["schema_kind"])] = entry["reason"]
    return exemptions


# ---------------------------------------------------------------------------
# Response-body transform census
# ---------------------------------------------------------------------------

#: Directories a census never descends into: dependency and VCS trees, not
#: generated source.
_TRANSFORM_SCAN_SKIP_DIRS: Final[frozenset[str]] = frozenset(
    {"node_modules", ".git", "__pycache__", ".venv"}
)

#: A generated file larger than this is data (a lockfile, a bundle), not
#: handwritten-shaped source a framework idiom could appear in.
_TRANSFORM_SCAN_MAX_BYTES: Final[int] = 2_000_000


@dataclass(frozen=True)
class TransformHit:
    """One place a generated tree spells a response-body transform idiom.

    Attributes:
        language: `datrix.languages` entry-point name whose tree holds the hit.
        relative_path: The file, relative to the generated root, in POSIX form.
        line: 1-based line number of the match.
        matched_text: The exact text the idiom matched.
    """

    language: str
    relative_path: str
    line: int
    matched_text: str


@dataclass(frozen=True)
class TransformExemption:
    """A reviewed generated-tree hit that does not transform a response body.

    Attributes:
        language: The language whose tree holds the hit.
        path_suffix: Trailing path segments of the file (POSIX), e.g.
            ``src/app.module.ts`` -- a service's own directory differs, so the
            coordinate is the suffix.
        matched_text: The exact text the idiom matched.
        reason: Why this hit leaves every response body untouched.
    """

    language: str
    path_suffix: str
    matched_text: str
    reason: str

    def covers(self, hit: TransformHit) -> bool:
        """True when *hit* is the hit this entry reviewed."""
        return (
            hit.language == self.language
            and hit.matched_text == self.matched_text
            and hit.relative_path.endswith(self.path_suffix)
        )


def load_transform_exemptions() -> tuple[TransformExemption, ...]:
    """Load and validate the ``transform_exemptions`` of `body-wire-naming-exemptions.json`.

    Raises:
        ValueError: If the file or its ``transform_exemptions`` array is missing
            or malformed, or an entry lacks a non-empty field.
    """
    if not EXEMPTIONS_PATH.exists():
        raise ValueError(
            f"Missing exemption file {EXEMPTIONS_PATH}. It pins the reviewed "
            f"response-body transform hits. Restore it from git; the gate never creates it."
        )
    data = json.loads(EXEMPTIONS_PATH.read_text(encoding="utf-8"))
    entries = data.get("transform_exemptions")
    if not isinstance(entries, list):
        raise ValueError(
            f"Malformed exemption file {EXEMPTIONS_PATH}: expected 'transform_exemptions' "
            f"(array of {{language, path_suffix, matched_text, reason}})."
        )
    exemptions: list[TransformExemption] = []
    for entry in entries:
        for key in ("language", "path_suffix", "matched_text", "reason"):
            if not isinstance(entry.get(key), str) or not entry[key].strip():
                raise ValueError(
                    f"Transform exemption entry {entry!r} is missing a non-empty {key!r}."
                )
        exemptions.append(
            TransformExemption(
                language=entry["language"],
                path_suffix=entry["path_suffix"],
                matched_text=entry["matched_text"],
                reason=entry["reason"],
            )
        )
    return tuple(exemptions)


def response_transform_idioms(language: str) -> tuple[re.Pattern[str], ...]:
    """The compiled response-transform idioms *language* declares.

    Raises:
        ValueError: *language* has no capability declaration to read them from;
            the message names the language and the underlying cause.
    """
    try:
        declaration = declaration_for_language(language)
    except (PluginNotFoundError, PluginValidationError) as exc:
        raise ValueError(
            f"language {language!r} declares no LanguageCapabilityDeclaration, so its "
            f"response_body_transform_idioms cannot be read ({exc}). Fix: add the "
            f"declaration to the language package."
        ) from exc
    return declaration.compiled_response_body_transform_idioms()


def census_response_transforms(
    language: str, generated_root: Path, idioms: Sequence[re.Pattern[str]]
) -> list[TransformHit]:
    """Every line of the generated tree under *generated_root* that spells an idiom.

    Args:
        language: The language whose tree this is (carried onto each hit).
        generated_root: The generated project directory.
        idioms: The language's compiled response-transform idioms.

    Returns:
        One hit per match, ordered by path then line.
    """
    hits: list[TransformHit] = []
    for path in sorted(generated_root.rglob("*")):
        if not path.is_file() or any(part in _TRANSFORM_SCAN_SKIP_DIRS for part in path.parts):
            continue
        if path.stat().st_size > _TRANSFORM_SCAN_MAX_BYTES:
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        relative = path.relative_to(generated_root).as_posix()
        for line_number, line in enumerate(text.splitlines(), start=1):
            for idiom in idioms:
                hits.extend(
                    TransformHit(language, relative, line_number, match.group(0))
                    for match in idiom.finditer(line)
                )
    return hits


def unexempted_transform_hits(
    hits: Sequence[TransformHit], exemptions: Sequence[TransformExemption]
) -> list[TransformHit]:
    """The hits no exemption reviewed."""
    return [hit for hit in hits if not any(entry.covers(hit) for entry in exemptions)]


def stale_transform_exemptions(
    language: str, hits: Sequence[TransformHit], exemptions: Sequence[TransformExemption]
) -> list[TransformExemption]:
    """The *language* exemptions that cover no hit -- they no longer review anything."""
    return [
        entry
        for entry in exemptions
        if entry.language == language and not any(entry.covers(hit) for hit in hits)
    ]


# ---------------------------------------------------------------------------
# Non-vacuity self-test
# ---------------------------------------------------------------------------


class _FixtureProbes:
    """An in-process fixture language whose probe returns a fixed field list."""

    def __init__(self, fields: Sequence[ResponseBodyWireField]) -> None:
        self._fields = tuple(fields)

    def response_body_wire_fields(self, generated_root: Path) -> tuple[ResponseBodyWireField, ...]:
        return self._fields

    def documentation_surfaces(self, generated_root: Path, files: Sequence[Path]) -> DocumentationSurfaces:
        return DocumentationSurfaces(frozenset(), frozenset())

    def render_enum_classifier(self, enum: object, paths: object) -> EnumClassifierRender:
        return EnumClassifierRender(())


class _FixturePluginWithoutProbes:
    """A fixture language plugin with no `conformance_probes` member."""


def _fixture_field(
    kind: str, field_name: str, wire_name: str, file_name: str = "fixture.py"
) -> ResponseBodyWireField:
    return ResponseBodyWireField(
        schema_kind=kind,  # type: ignore[arg-type]  # a fixture kind the comparator treats generically
        template="",
        file_path=Path(file_name),
        field_name=field_name,
        effective_wire_name=wire_name,
    )


def run_self_test() -> list[str]:
    """Prove this gate names no target, the comparator detects a forced mismatch,
    respects a real exemption, does not flag a single-word-field false positive,
    and drives its real dispatch with fixture probes -- before any real
    comparison is trusted.

    Returns:
        A list of failure descriptions -- empty means the comparator is sound.
    """
    problems: list[str] = list(self_test_gate_names_no_target(__file__))
    if problems:
        return problems

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

    # A single-word field with no alias generator -- must NOT be flagged,
    # proving the false-positive guard.
    single_word_no_alias = ResponseField(
        language=_SELF_TEST_LANGUAGE,
        schema_kind="problem_details",
        template="",
        file_path=Path("self_test_problem_details.py"),
        field_name="type",
        effective_wire_name="type",
    )
    if not is_wire_name_conformant(single_word_no_alias):
        problems.append(
            "self-test: is_wire_name_conformant flagged a single-word "
            "field with no alias generator -- this must never be a violation."
        )

    problems.extend(_run_probe_dispatch_self_test())
    problems.extend(_run_transform_census_self_test())
    problems.extend(_run_insufficient_target_refusal_self_test())
    return problems


def _run_probe_dispatch_self_test() -> list[str]:
    """Drive the gate's real per-language evaluation with fixture probes.

    The fixture language's name is not a registered one: a conformant probe
    passes, a planted divergence fails, an exemption suppresses a divergence, an
    empty result fails, a dependency-only result fails (and is counted), an
    out-of-population divergence is excluded and counted, and a plugin with no
    probe member fails with the accessor's message.
    """
    problems: list[str] = []
    no_exemptions: dict[tuple[str, str], str] = {}

    def evaluate(fields: Sequence[ResponseBodyWireField], exemptions: Mapping[tuple[str, str], str] = no_exemptions):
        return evaluate_probe_fields(_SELF_TEST_LANGUAGE, _FixtureProbes(fields), Path("."), exemptions)

    ok, _ = evaluate([_fixture_field("entity_response", "order_id", "orderId")])
    if not ok:
        problems.append("self-test: a conformant fixture probe was reported as a violation.")

    ok, _ = evaluate([_fixture_field("entity_response", "order_id", "order_id")])
    if ok:
        problems.append("self-test: a fixture probe emitting 'order_id' for order_id was not reported.")

    ok, _ = evaluate(
        [_fixture_field("entity_response", "order_id", "order_id")],
        {(_SELF_TEST_LANGUAGE, "entity_response"): "self-test exemption"},
    )
    if not ok:
        problems.append("self-test: a divergence covered by an exemption was still reported.")

    ok, _ = evaluate([])
    if ok:
        problems.append("self-test: a fixture probe returning no field passed -- a census that finds nothing proves nothing.")

    ok, excluded = evaluate([_fixture_field("dependency_response", "order_id", "order_id")])
    if ok or excluded != Counter({"dependency_response": 1}):
        problems.append(
            "self-test: a probe returning only dependency responses must fail (nothing in population) "
            f"and count the excluded file (got ok={ok}, excluded={dict(excluded)})."
        )

    ok, excluded = evaluate(
        [
            _fixture_field("entity_response", "order_id", "orderId"),
            _fixture_field("dependency_response", "order_id", "order_id", "a.py"),
            _fixture_field("dependency_response", "item_id", "item_id", "a.py"),
            _fixture_field("dependency_response", "item_id", "item_id", "b.py"),
        ]
    )
    if not ok or excluded != Counter({"dependency_response": 2}):
        problems.append(
            "self-test: out-of-population divergences must not fail the language and must be counted "
            f"once per distinct file (got ok={ok}, excluded={dict(excluded)})."
        )

    try:
        conformance_probes_of_language_plugin(_SELF_TEST_LANGUAGE, _FixturePluginWithoutProbes())
    except PluginValidationError as exc:
        if _SELF_TEST_LANGUAGE not in str(exc) or "declares no conformance probes" not in str(exc):
            problems.append(
                f"self-test: a plugin with no probe member failed without the accessor's message ({exc})."
            )
    else:
        problems.append("self-test: a plugin with no probe member was not refused.")
    return problems


#: The planted interceptor line the transform census self-test must report, and
#: the idiom (a language's own declared spelling of it) that matches it.
_SELF_TEST_INTERCEPTOR_LINE: Final[str] = "app.useGlobalInterceptors(new KeyRewriteInterceptor());"
_SELF_TEST_INTERCEPTOR_IDIOM: Final[str] = r"\buseGlobalInterceptors\("
_SELF_TEST_INTERCEPTOR_MATCH: Final[str] = "useGlobalInterceptors("
_SELF_TEST_TREE_DIR: Final[str] = "self-test-transform-census"


def _run_transform_census_self_test() -> list[str]:
    """Prove the transform census reports a planted hit, honours an exemption,
    flags a stale one, ignores a clean file, and refuses an undeclared language.

    The planted ``useGlobalInterceptors(`` line is the exact shape of a
    response transform a backend could install; the census must report it
    at its coordinates before any real tree is trusted.
    """
    problems: list[str] = []
    root = _GATE_OUTPUT_ROOT / _SELF_TEST_TREE_DIR
    shutil.rmtree(root, ignore_errors=True)
    (root / "src").mkdir(parents=True)
    try:
        (root / "src" / "main.ts").write_text(
            f"bootstrap();\n{_SELF_TEST_INTERCEPTOR_LINE}\n", encoding="utf-8"
        )
        (root / "src" / "clean.ts").write_text(
            "app.useGlobalPipes(new ValidationPipe());\n", encoding="utf-8"
        )
        hits = census_response_transforms(
            _SELF_TEST_LANGUAGE, root, (re.compile(_SELF_TEST_INTERCEPTOR_IDIOM),)
        )
        planted = TransformHit(_SELF_TEST_LANGUAGE, "src/main.ts", 2, _SELF_TEST_INTERCEPTOR_MATCH)
        if hits != [planted]:
            problems.append(
                f"self-test: the transform census did not report exactly the planted "
                f"{_SELF_TEST_INTERCEPTOR_MATCH!r} hit at src/main.ts:2 (got {hits!r}); a clean "
                "useGlobalPipes( line must never match."
            )
        exemption = TransformExemption(
            _SELF_TEST_LANGUAGE, "src/main.ts", _SELF_TEST_INTERCEPTOR_MATCH, "self-test exemption"
        )
        if unexempted_transform_hits([planted], []) != [planted]:
            problems.append("self-test: an unexempted transform hit was not reported.")
        if unexempted_transform_hits([planted], [exemption]):
            problems.append("self-test: a transform hit covered by an exemption was still reported.")
        if stale_transform_exemptions(_SELF_TEST_LANGUAGE, [], [exemption]) != [exemption]:
            problems.append("self-test: an exemption that matches no hit was not reported as stale.")
        if stale_transform_exemptions(_SELF_TEST_LANGUAGE, [planted], [exemption]):
            problems.append("self-test: an exemption that covers a hit was reported as stale.")
    finally:
        shutil.rmtree(root, ignore_errors=True)

    try:
        response_transform_idioms(_SELF_TEST_LANGUAGE)
    except ValueError as exc:
        if _SELF_TEST_LANGUAGE not in str(exc):
            problems.append(
                "self-test: the refusal of a language with no declaration did not name it."
            )
    else:
        problems.append(
            "self-test: a language with no capability declaration was not refused -- the "
            "census would silently count nothing for it."
        )
    return problems


def _run_insufficient_target_refusal_self_test() -> list[str]:
    """Prove the gate REFUSES to run when fewer than two targets are registered.

    A cross-target conformance gate that quietly passes with one target
    installed reports "every language agrees" about a set of size one, which
    is true and worthless. `check_body_wire_naming_conformance` guards against
    that by returning exit code 2, and `quick-reference.md` documents the
    behaviour -- but nothing proved the guard fires, so it was a documented
    claim rather than a checked one.

    This drives the REAL function with real short lists (the empty list and one
    registered language) rather than asserting on a re-implementation of the
    rule. The guard is the function's first statement and returns before any
    generation or filesystem work, so the calls are side-effect free.

    The complementary half is supplied by the invocation itself: a function
    that returned 2 unconditionally would make the whole gate exit 2 instead
    of 0, so an always-refusing implementation cannot survive a real run.
    """
    problems: list[str] = []

    for insufficient in ([], sorted(registered_language_names())[:1]):
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
    # validate_files (a language's own toolchain compile step) -- this gate
    # reads generated SOURCE TEXT only, never compiled output, so a full
    # compiler invocation is an unrelated, more expensive dependency this
    # naming check does not need.
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


def _check_response_transforms(
    language: str, output_dir: Path, exemptions: Sequence[TransformExemption]
) -> bool:
    """Run the response-transform census over *language*'s generated tree.

    Returns:
        False when the language declares no idioms, a hit is not covered by a
        reviewed exemption, or an exemption for the language covers no hit.
    """
    try:
        idioms = response_transform_idioms(language)
    except ValueError as exc:
        logger.error("BODY WIRE-NAMING VIOLATION: %s", exc)
        return False
    hits = census_response_transforms(language, output_dir, idioms)
    ok = True
    for hit in unexempted_transform_hits(hits, exemptions):
        ok = False
        logger.error(
            "BODY WIRE-NAMING VIOLATION: language %r spells a response-body transform at "
            "%s:%d (%r). A transform applied to every outgoing body changes the wire names "
            "the response classes declare. Fix: delete the transform, or add a reviewed "
            "entry to 'transform_exemptions' in %s if it leaves the body untouched.",
            hit.language, hit.relative_path, hit.line, hit.matched_text, EXEMPTIONS_PATH,
        )
    for entry in stale_transform_exemptions(language, hits, exemptions):
        ok = False
        logger.error(
            "BODY WIRE-NAMING VIOLATION: the transform exemption for language %r "
            "(%s, %r) matches nothing in the generated tree. Fix: delete it from %s.",
            entry.language, entry.path_suffix, entry.matched_text, EXEMPTIONS_PATH,
        )
    return ok


def evaluate_probe_fields(
    language: str,
    probes: LanguageConformanceProbes,
    output_dir: Path,
    exemptions: Mapping[tuple[str, str], str],
) -> tuple[bool, Counter[str]]:
    """Read *language*'s response fields through *probes* and compare them with the declared rule.

    Returns:
        `(conformant, excluded_by_scope)` -- `conformant` is False when the probe
        finds no in-population field or any field diverges without an exemption;
        `excluded_by_scope` counts the files excluded per out-of-population kind.
    """
    measured, excluded = measured_population(language, probes.response_body_wire_fields(output_dir))
    if not measured:
        logger.error(
            "BODY WIRE-NAMING VIOLATION: probe for %r found no response-body fields in the "
            "generated CQRS example; a census that finds nothing proves nothing. Expected "
            "at least one in-population response class. Fix: make the language's "
            "response_body_wire_fields read the response classes its generator emits.",
            language,
        )
        return False, excluded
    ok = True
    for field in measured:
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
            field.effective_wire_name, body_wire_name(field.field_name),
            field.file_path, EXEMPTIONS_PATH,
        )
    return ok, excluded


def _check_language(
    language: str,
    exemptions: Mapping[tuple[str, str], str],
    transform_exemptions: Sequence[TransformExemption],
) -> tuple[bool, Counter[str]]:
    """Run the real checks for one language over one generated example.

    Returns:
        `(conformant, excluded_by_scope)` -- `conformant` is False if the
        language declares no probes, emits at least one unexempted divergence,
        or fails the response-transform census; `excluded_by_scope` tallies the
        files its probe returned for kinds outside the measured population.
    """
    output_dir = _generate_example_for_language(language)
    transforms_ok = _check_response_transforms(language, output_dir, transform_exemptions)
    try:
        probes = language_conformance_probes(language)
    except PluginValidationError as exc:
        logger.error("BODY WIRE-NAMING VIOLATION: %s", exc)
        return False, Counter()
    fields_ok, excluded = evaluate_probe_fields(language, probes, output_dir, exemptions)
    return transforms_ok and fields_ok, excluded


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
        or a language with no conformance probes, 2 = fewer than
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
    exemptions = load_exemptions()
    transform_exemptions = load_transform_exemptions()

    ok = True
    total_excluded: Counter[str] = Counter()
    for language in languages:
        language_ok, excluded = _check_language(language, exemptions, transform_exemptions)
        ok = ok and language_ok
        total_excluded.update(excluded)

    if total_excluded:
        logger.info(
            "Out-of-population schema kinds excluded from measurement "
            "(counted per file, never silently dropped): %s.", dict(total_excluded),
        )

    if ok:
        logger.info(
            "Body wire-naming conformance holds across %d languages (%s); every "
            "divergence is exempted and no unreviewed response-body transform exists.",
            len(languages), languages,
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
