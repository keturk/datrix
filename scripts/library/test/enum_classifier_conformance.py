"""Cross-target enum-classifier conformance gate.

Every registered `datrix.languages` plugin that emits enum types must realize
`equalsKeyword`/`containsKeyword` identically for a fixture keyword-bearing enum: a hit returns
the correct member, a miss without fallback raises the plugin's declared unrecognized-value
exception with a message naming only the enum type (no input/keyword disclosure), and
a miss with fallback returns the fallback. This gate is the coverage the closed `BUILTIN_REGISTRY`
normally provides -- these classifiers are deliberately NOT registry entries (the registry is
keyed by fixed category names and a user enum is never one of those categories), so nothing else
in the framework compares them cross-language.

Target set is NEVER hardcoded: languages are enumerated from the installed `datrix.languages`
entry points at runtime via `shared.registered_targets.registered_language_names`, so a future
`datrix-codegen-<lang>` package is covered automatically with no edit to this gate.
`enum_emitting_language_names` further narrows that set from each plugin's own registered
sub-generator domain (`"enum"`), never from a language-name literal.

`collect_conformance_facts` alone carries per-language rendering mechanics, keyed by language
name -- this is the one place this deliberately sanctions that, because each of
python/typescript/java/dotnet emits its classifier through a genuinely different
template/context-builder shape (classmethods, a merged namespace, enum-hosted statics, a
companion static class) with no shared render interface to call generically.
The TARGET SET this gate evaluates never comes from that dispatch table's keys -- only from
`enum_emitting_language_names(registered_language_names())` -- and a registered enum-emitting
language absent from the dispatch table is a loud `RuntimeError`, never a silent skip.

A known, reviewed gap is a typed, counted entry in
`d:\\datrix\\datrix\\scripts\\config\\enum-classifier-conformance-exemptions.json` with a written
reason -- never silence (D11's own wording).

Run with `--self-test` to verify the comparator is non-vacuous before trusting a real run.
"""

from __future__ import annotations

import argparse
import json
import logging
import re
import sys
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Final

# library/test/ -> library/ -> sibling library/shared/
_LIBRARY_DIR = Path(__file__).resolve().parent.parent
if _LIBRARY_DIR.exists() and str(_LIBRARY_DIR) not in sys.path:
    sys.path.insert(0, str(_LIBRARY_DIR))

from shared.registered_targets import registered_language_names  # noqa: E402

from datrix_codegen_common.templates import shared_template_dir  # noqa: E402
from datrix_common.datrix_model.enums import Enum, EnumValue  # noqa: E402
from datrix_common.generation.discovery import get_language_plugin  # noqa: E402
from datrix_common.generation.gendsl_ir import DomainDefinition  # noqa: E402
from datrix_common.generation.generator import GeneratedFile  # noqa: E402
from datrix_common.generation.plugin_helpers import template_dir_for  # noqa: E402
from datrix_common.generation.registry import SubGeneratorSpec  # noqa: E402
from datrix_common.generation.template_generator import TemplateGenerator  # noqa: E402
from datrix_common.paths import ServicePaths  # noqa: E402

logger = logging.getLogger(__name__)

_HERE = Path(__file__).resolve()
#: <datrix>/scripts/library/test/enum_classifier_conformance.py -- parents[3] is <datrix>.
DATRIX_DIR: Path = _HERE.parents[3]
EXEMPTIONS_PATH: Path = DATRIX_DIR / "scripts" / "config" / "enum-classifier-conformance-exemptions.json"

#: A cross-language comparison over 0 or 1 language is vacuous.
_MIN_LANGUAGES_FOR_COMPARISON: Final[int] = 2

#: Synthetic language names used only by the self-test -- deliberately not real registered names.
_SELF_TEST_LANGUAGE_A: Final[str] = "self_test_lang_a"
_SELF_TEST_LANGUAGE_B: Final[str] = "self_test_lang_b"

#: Fixture enum used for the REAL (non-self-test) comparison: two keyword-bearing values plus one
#: value with no keywords, matching the shape ENUM003 requires (>=1 keyword-bearing value) while
#: also exercising "not every value need carry keywords."
_FIXTURE_ENUM_NAME: Final[str] = "EnumClassifierConformanceFixture"
_FIXTURE_KEYWORD_HIT: Final[str] = "ALPHA"
_FIXTURE_KEYWORD_MISS: Final[str] = "ZULU-UNRECOGNIZED"

#: Neutral e-commerce service name the fixture enum is rendered under. Never a real registered
#: service -- purely a `ServicePaths` anchor so each language's `ErrorProfile.import_statement`
#: (D9) can resolve a per-service import/using/package line for the declared exception.
_FIXTURE_SERVICE_NAME: Final[str] = "catalog"

#: The GenDSL domain id every enum-emitting language plugin registers its `EnumGenerator`
#: sub-generator under (`_declare_structural("enum", EnumGenerator)`, identical across
#: python/typescript/java/dotnet's own gendsl definitions modules -- verified by reading all
#: four). This is deliberately NOT `plugin.domain_declarations["enum"].status` -- java legitimately
#: declares that "unsupported" for an unrelated reason (no committed structural glob pattern for
#: the cross-language STRUCTURAL parity surface; `EnumGenerator` still emits real, compiling
#: `.java` files regardless -- see that package's own `enum_generator.py` docstring). The
#: SUB-GENERATOR REGISTRATION, not the structural-parity declaration, is the true capability
#: signal "this language emits enum types."
_ENUM_DOMAIN_NAME: Final[str] = "enum"

#: The no-match throw's message shape every one of the four templates emits today (a compile-time
#: constant naming only the enum type, by deliberate security decision). Interpolated with the fixture enum's
#: own name at comparison time; used to prove `message_discloses_nothing` rather than merely
#: "the keyword literal is absent from the whole file" (which would false-negative against the
#: keyword lookup tables the same file legitimately carries -- see this module's own
#: `_facts_from_render` docstring).
_EXPECTED_MESSAGE_TEMPLATE: Final[str] = "Unrecognized {enum_name} value."


@dataclass(frozen=True)
class ClassifierConformanceFacts:
    """Per-language observed facts about the fixture enum's generated classifiers.

    Every field must be independently checkable from the language's rendered enum source
    (or, once available, from actually exercising the generated code) -- this dataclass is the
    single comparison unit `compare_classifier_conformance` operates on, so it must carry exactly
    the properties D11/G10 require and nothing implementation-specific to one language.

    Attributes:
        has_equals_keyword: The generated source declares an `equalsKeyword`-family classifier
            (case/spelling per that language's own convention, e.g. `EqualsKeyword` for the
            dotnet companion class).
        has_contains_keyword: As above, for `containsKeyword`.
        declared_exception_referenced: The language's `LanguageProfile` exception sub-profile
            (41-05) names a type, and that type name appears in the generated classifier's
            no-match path.
        message_discloses_nothing: The no-match throw's message argument is a fixed string
            naming only the enum type -- neither the received value nor any declared keyword
            literal appears in it (D3.2, D9, G4).
    """

    has_equals_keyword: bool
    has_contains_keyword: bool
    declared_exception_referenced: bool
    message_discloses_nothing: bool

    def is_fully_conformant(self) -> bool:
        """Return whether every required property holds for this language."""
        return (
            self.has_equals_keyword
            and self.has_contains_keyword
            and self.declared_exception_referenced
            and self.message_discloses_nothing
        )


def configure_logging(debug: bool = False) -> None:
    """Configure logging output."""
    level = logging.DEBUG if debug else logging.INFO
    logging.basicConfig(level=level, format="%(levelname)s: %(message)s")


def build_fixture_enum() -> Enum:
    """Build the real, in-memory keyword-bearing fixture `Enum` AST object.

    No `.dtrx` parsing is needed -- this constructs the same `Enum`/`EnumValue` model objects the
    transformer (41-02) would produce, directly, following the pattern
    `datrix-codegen-python/tests/unit/entity/test_enum_value_documentation.py` already uses for
    real (non-mocked) `Enum`/`EnumValue` objects in a unit test.

    Returns:
        An `Enum` named `EnumClassifierConformanceFixture` with one value carrying
        `keywords=(_FIXTURE_KEYWORD_HIT,)` and one value with no keywords, in declaration order.
    """
    fixture = Enum(name=_FIXTURE_ENUM_NAME)
    fixture.add_value(EnumValue(name="Alpha", keywords=(_FIXTURE_KEYWORD_HIT,)))
    fixture.add_value(EnumValue(name="Untagged"))
    return fixture


def _registered_domain_names(specs: list[SubGeneratorSpec]) -> frozenset[str]:
    """Domain ids a plugin's sub-generator specs register.

    Mirrors the two sanctioned registration shapes documented by
    `datrix_codegen_common.testkit.gates.domain_self_consistency.registered_orchestrator_domains`
    (a string `cls.DOMAIN` class attribute, or a GenDSL-compiled `DomainDefinition` under
    `spec.extras["domain"]`) -- WITHOUT that gate's `SHARED_CONTEXT_TYPES` scoping, since `"enum"`
    is deliberately outside that 39-domain shared-context-type registry (it is not one of the rich
    cross-language domains that registry exists to compare) yet is exactly the domain id every
    enum-emitting language's `EnumGenerator` registers.

    Args:
        specs: Sub-generator specs from `plugin.generator.get_sub_generators()`.

    Returns:
        The frozenset of every domain id at least one spec registers.
    """
    names: set[str] = set()
    for spec in specs:
        cls_domain = getattr(spec.cls, "DOMAIN", None)
        if isinstance(cls_domain, str):
            names.add(cls_domain)
            continue
        extras_domain = spec.extras.get("domain") if spec.extras else None
        if isinstance(extras_domain, DomainDefinition):
            names.add(extras_domain.name)
    return frozenset(names)


def enum_emitting_language_names(languages: frozenset[str]) -> frozenset[str]:
    """Return the subset of *languages* whose plugin emits enum types.

    Per the design's target table (§2), every CURRENTLY registered language emits enum types
    (python/typescript/java/dotnet); sql/docker/aws/azure/common do not register under
    `datrix.languages` as enum-emitting targets in the first place (they are not
    `datrix.languages` entry points at all -- sql/docker are platform/db targets, not languages).
    This function exists so a future non-enum-emitting LANGUAGE plugin (if one is ever added)
    is excluded rather than silently required to conform.

    The capability signal is each plugin's own sub-generator registration -- does it register a
    sub-generator under the `"enum"` GenDSL domain (`_registered_domain_names`) -- never a
    hardcoded language-name list, and never `domain_declarations["enum"].status` (see
    `_ENUM_DOMAIN_NAME`'s own docstring for why that status is the wrong signal).

    Args:
        languages: Every registered `datrix.languages` entry-point name.

    Returns:
        The subset that emits enum types, per each plugin's own declared capability.
    """
    emitting: set[str] = set()
    for language in languages:
        plugin = get_language_plugin(language)
        specs = plugin.generator.get_sub_generators()
        if _ENUM_DOMAIN_NAME in _registered_domain_names(specs):
            emitting.add(language)
    return frozenset(emitting)


#: Per-language `TemplateGenerator` is expensive to build (walks the template tree) and stateless
#: once built -- cached by language name for the lifetime of one gate invocation.
_TEMPLATE_GEN_CACHE: dict[str, TemplateGenerator] = {}


def _template_generator_for(language: str, plugin_module_file: str) -> TemplateGenerator:
    """Build (once, cached) *language*'s own real `TemplateGenerator`.

    Uses the SAME production resolution every language's own `plugin.py` uses elsewhere in that
    package (`template_dir_for(<package>.plugin.__file__)` -- verified against
    `datrix_codegen_python`'s own `http_contract_overlay_generator.py`/`runtime_requirements.py`
    call sites; every one of the four packages keeps its `templates/` directory as a direct
    sibling of its own `plugin.py`, so `levels_up=0` resolves correctly for all four).

    Args:
        language: The `datrix.languages` entry-point name (also the Jinja `target_language`).
        plugin_module_file: `__file__` of that language's own `plugin` module.

    Returns:
        The cached (or newly built) `TemplateGenerator`.
    """
    cached = _TEMPLATE_GEN_CACHE.get(language)
    if cached is not None:
        return cached
    template_gen = TemplateGenerator(
        template_dir=template_dir_for(plugin_module_file),
        target_language=language,
        shared_template_dir=shared_template_dir(),
    )
    _TEMPLATE_GEN_CACHE[language] = template_gen
    return template_gen


def _single_rendered_content(files: list[GeneratedFile], language: str) -> str:
    """Return the sole rendered file's content, or raise loud on an unexpected count.

    Args:
        files: The `GeneratedFile`s a language's `EnumGenerator.generate_enums` produced for
            exactly one fixture enum.
        language: The language under render, for the error message.

    Returns:
        `files[0].content`.

    Raises:
        RuntimeError: If *files* does not contain exactly one entry.
    """
    if len(files) != 1:
        raise RuntimeError(
            f"{language}'s EnumGenerator rendered {len(files)} file(s) for the single fixture "
            f"enum {_FIXTURE_ENUM_NAME!r}, expected exactly 1. This is a harder failure than a "
            f"conformance gap -- investigate {language}'s EnumGenerator.generate_enums for an "
            f"unexpected extra or missing emission."
        )
    return files[0].content


def _facts_from_render(
    content: str,
    *,
    has_equals_keyword: bool,
    has_contains_keyword: bool,
    raise_pattern: re.Pattern[str],
    expected_exception: str,
    enum_name: str,
) -> ClassifierConformanceFacts:
    """Derive `ClassifierConformanceFacts` from one language's rendered enum source.

    `declared_exception_referenced`/`message_discloses_nothing` are derived from *raise_pattern*
    ISOLATING the no-match throw/raise statement(s) (exception name + message-literal capture
    groups) -- never from "is the keyword literal absent from the whole file", which would
    false-negative constantly: the keyword lookup tables the same file legitimately emits (for the
    hit path) also contain the keyword literal, just outside the throw statement.

    Args:
        content: The language's rendered enum file text.
        has_equals_keyword: Whether the language's own method/function-signature convention for
            `equalsKeyword` was found (checked by the caller, per that language's own casing).
        has_contains_keyword: As above, for `containsKeyword`.
        raise_pattern: A 2-group regex isolating each no-match throw/raise statement in this
            language's shape: group 1 is the raised exception's type name, group 2 is its message
            string-literal body.
        expected_exception: The exception type name this language's `LanguageProfile.errors`
            declares (D9) -- every isolated raise must name exactly this type.
        enum_name: The fixture enum's own name, to build the expected constant message.

    Returns:
        The observed `ClassifierConformanceFacts`.
    """
    matches = raise_pattern.findall(content)
    expected_message = _EXPECTED_MESSAGE_TEMPLATE.format(enum_name=enum_name)
    exception_referenced = bool(matches) and all(name == expected_exception for name, _ in matches)
    message_clean = bool(matches) and all(
        message == expected_message
        and _FIXTURE_KEYWORD_HIT not in message
        and _FIXTURE_KEYWORD_MISS not in message
        for _, message in matches
    )
    return ClassifierConformanceFacts(
        has_equals_keyword=has_equals_keyword,
        has_contains_keyword=has_contains_keyword,
        declared_exception_referenced=exception_referenced,
        message_discloses_nothing=message_clean,
    )


# ---------------------------------------------------------------------------
# Per-language rendering mechanics (see this module's own docstring for why
# this is the one sanctioned place that special-cases by language name).
# ---------------------------------------------------------------------------

_PYTHON_RAISE_RE: Final[re.Pattern[str]] = re.compile(r'raise\s+(\w+)\(\[\s*"([^"]*)"\s*\]\)')
_TS_THROW_RE: Final[re.Pattern[str]] = re.compile(r"throw new (\w+)\('([^']*)'\);")
_JAVA_THROW_RE: Final[re.Pattern[str]] = re.compile(r'throw new (\w+)\(List\.of\("([^"]*)"\)\);')
_DOTNET_THROW_RE: Final[re.Pattern[str]] = re.compile(r'throw new (\w+)\("([^"]*)"\);')

_JAVA_EQUALS_SIG_RE: Final[re.Pattern[str]] = re.compile(r"\bstatic\s+\S+\s+equalsKeyword\s*\(")
_JAVA_CONTAINS_SIG_RE: Final[re.Pattern[str]] = re.compile(r"\bstatic\s+\S+\s+containsKeyword\s*\(")
_DOTNET_EQUALS_SIG_RE: Final[re.Pattern[str]] = re.compile(r"\bstatic\s+\S+\s+EqualsKeyword\s*\(")
_DOTNET_CONTAINS_SIG_RE: Final[re.Pattern[str]] = re.compile(r"\bstatic\s+\S+\s+ContainsKeyword\s*\(")


def _python_facts(fixture: Enum, paths: ServicePaths) -> ClassifierConformanceFacts:
    """Render *fixture* through python's real `EnumGenerator` and observe its classifier facts."""
    import datrix_codegen_python.plugin as _plugin_module
    from datrix_codegen_python.generators.entity.enum_generator import EnumGenerator
    from datrix_codegen_python.profile import PYTHON_PROFILE

    template_gen = _template_generator_for("python", _plugin_module.__file__)
    files = EnumGenerator(template_gen).generate_enums(paths, {str(fixture.name): fixture})
    content = _single_rendered_content(files, "python")
    return _facts_from_render(
        content,
        has_equals_keyword="def equalsKeyword(" in content,
        has_contains_keyword="def containsKeyword(" in content,
        raise_pattern=_PYTHON_RAISE_RE,
        expected_exception=PYTHON_PROFILE.errors.unrecognized_value_exception,
        enum_name=str(fixture.name),
    )


def _typescript_facts(fixture: Enum, paths: ServicePaths) -> ClassifierConformanceFacts:
    """Render *fixture* through typescript's real context-builder + template render."""
    import datrix_codegen_typescript.plugin as _plugin_module
    from datrix_codegen_typescript.file_helpers import render_ts_file
    from datrix_codegen_typescript.generators.entity.enum_generator import (
        build_enum_template_context,
    )
    from datrix_codegen_typescript.profile import TS_PROFILE
    from datrix_codegen_typescript.validation import validate_typescript_syntax

    template_gen = _template_generator_for("typescript", _plugin_module.__file__)
    context = build_enum_template_context(fixture, paths)
    generated = render_ts_file(
        template_gen,
        "entity/enum.ts.j2",
        Path(f"{fixture.name}.enum.ts"),
        format_fn=validate_typescript_syntax,
        **context,
    )
    content = generated.content
    return _facts_from_render(
        content,
        has_equals_keyword="export function equalsKeyword(" in content,
        has_contains_keyword="export function containsKeyword(" in content,
        raise_pattern=_TS_THROW_RE,
        expected_exception=TS_PROFILE.errors.unrecognized_value_exception,
        enum_name=str(fixture.name),
    )


def _java_facts(fixture: Enum, paths: ServicePaths) -> ClassifierConformanceFacts:
    """Render *fixture* through java's real `EnumGenerator` and observe its classifier facts."""
    import datrix_codegen_java.plugin as _plugin_module
    from datrix_codegen_java.generators.entity.enum_generator import EnumGenerator
    from datrix_codegen_java.profile import JAVA_PROFILE

    template_gen = _template_generator_for("java", _plugin_module.__file__)
    files = EnumGenerator(template_gen).generate_enums(paths, {str(fixture.name): fixture})
    content = _single_rendered_content(files, "java")
    return _facts_from_render(
        content,
        has_equals_keyword=bool(_JAVA_EQUALS_SIG_RE.search(content)),
        has_contains_keyword=bool(_JAVA_CONTAINS_SIG_RE.search(content)),
        raise_pattern=_JAVA_THROW_RE,
        expected_exception=JAVA_PROFILE.errors.unrecognized_value_exception,
        enum_name=str(fixture.name),
    )


def _dotnet_facts(fixture: Enum, paths: ServicePaths) -> ClassifierConformanceFacts:
    """Render *fixture* through dotnet's real `EnumGenerator` and observe its classifier facts."""
    import datrix_codegen_dotnet.plugin as _plugin_module
    from datrix_codegen_dotnet.generators.entity.enum_generator import EnumGenerator
    from datrix_codegen_dotnet.profile import DOTNET_PROFILE

    template_gen = _template_generator_for("dotnet", _plugin_module.__file__)
    files = EnumGenerator(template_gen).generate_enums(paths, {str(fixture.name): fixture})
    content = _single_rendered_content(files, "dotnet")
    return _facts_from_render(
        content,
        has_equals_keyword=bool(_DOTNET_EQUALS_SIG_RE.search(content)),
        has_contains_keyword=bool(_DOTNET_CONTAINS_SIG_RE.search(content)),
        raise_pattern=_DOTNET_THROW_RE,
        expected_exception=DOTNET_PROFILE.errors.unrecognized_value_exception,
        enum_name=str(fixture.name),
    )


#: Rendering mechanics for each language known to this gate today. NEVER the source of the target
#: SET under comparison (that is always `enum_emitting_language_names(registered_language_names())`
#: -- see this module's own docstring). A registered enum-emitting language absent from this table
#: is a loud `RuntimeError` from `collect_conformance_facts`, never a silently skipped language.
_LANGUAGE_COLLECTORS: Final[dict[str, Callable[[Enum, ServicePaths], ClassifierConformanceFacts]]] = {
    "python": _python_facts,
    "typescript": _typescript_facts,
    "java": _java_facts,
    "dotnet": _dotnet_facts,
}


def collect_conformance_facts(language: str, fixture: Enum) -> ClassifierConformanceFacts:
    """Render *fixture*'s enum file for *language* and observe its classifier facts.

    Uses the SAME in-process context-builder + template-render call each language's own unit
    tests use (see `enum_generator.py`'s `build_enum_template_context` for each of the four
    packages, and the render helper each package exposes alongside it -- e.g.
    `datrix_codegen_python.generators._helpers.render_python_file` for python). No `.dtrx` file is
    written to disk and no subprocess/CLI generation is invoked.

    Args:
        language: A `datrix.languages` entry-point name.
        fixture: The shared fixture `Enum` from `build_fixture_enum`.

    Returns:
        The observed `ClassifierConformanceFacts` for *language*.

    Raises:
        RuntimeError: If *language*'s plugin cannot render an enum file at all (a harder failure
            than a conformance gap -- surfaced distinctly so it is never miscounted as "renders
            but violates one property"), or if *language* is not one this gate knows how to
            render at all (no dispatch entry in `_LANGUAGE_COLLECTORS`).
    """
    collector = _LANGUAGE_COLLECTORS.get(language)
    if collector is None:
        raise RuntimeError(
            f"No enum-classifier rendering mechanics are registered in this gate for language "
            f"{language!r} (registered mechanics: {sorted(_LANGUAGE_COLLECTORS)}). "
            f"enum_emitting_language_names() derived {language!r} as enum-emitting from its own "
            f"plugin registration, but each language's classifier template/context-builder shape "
            f"differs enough per language that this gate cannot render it generically. Fix: "
            f"add a _{language}_facts collector mirroring the existing four (see "
            f"_python_facts/_typescript_facts/_java_facts/_dotnet_facts) and register it in "
            f"_LANGUAGE_COLLECTORS. This is a loud, fail-closed gap -- never a silent skip."
        )
    paths = ServicePaths(_FIXTURE_SERVICE_NAME)
    try:
        return collector(fixture, paths)
    except RuntimeError:
        raise
    except Exception as exc:
        raise RuntimeError(
            f"{language}'s EnumGenerator could not render the fixture enum "
            f"{_FIXTURE_ENUM_NAME!r}: {exc}. This is a harder failure than a conformance gap -- "
            f"{language}'s enum generator itself is broken, not merely non-conformant."
        ) from exc


def load_exemptions() -> tuple[list[dict[str, str]], int]:
    """Return reviewed exemption entries and the pinned count they must match.

    Mirrors `builtin_claims_parity.load_exemptions` exactly: a typed, counted, reason-carrying
    entry is the only sanctioned way a known gap survives this gate. An empty exemptions file
    (pinned count 0, empty list) is the default/expected state today -- every currently registered
    language is expected to be fully conformant.

    Returns:
        `(exemption_entries, pinned_count)`. Each entry carries at least `"language"` and
        `"reason"` (both non-empty strings).

    Raises:
        ValueError: The exemptions file is missing or malformed, the pinned count disagrees with
            the entry list length, or an entry is missing a required field (`language`, `reason`)
            -- both mean the file stopped describing what it claims to and nothing in it can be
            trusted.
    """
    if not EXEMPTIONS_PATH.exists():
        raise ValueError(
            f"Missing exemption file {EXEMPTIONS_PATH}. It pins the catalogued per-language "
            f"enum-classifier conformance holes. Restore it from git; the gate never creates it."
        )
    data = json.loads(EXEMPTIONS_PATH.read_text(encoding="utf-8"))
    entries = data.get("exemptions")
    pinned_count = data.get("pinned_count")
    if not isinstance(entries, list) or not isinstance(pinned_count, int):
        raise ValueError(
            f"Malformed exemption file {EXEMPTIONS_PATH}: expected an object with "
            f"'pinned_count' (int) and 'exemptions' (array of {{language, reason}})."
        )
    for entry in entries:
        for key in ("language", "reason"):
            if not isinstance(entry, dict) or not isinstance(entry.get(key), str) or not entry[key].strip():
                raise ValueError(f"Exemption entry {entry!r} is missing a non-empty {key!r}.")
    if len(entries) != pinned_count:
        raise ValueError(
            f"Exemption file {EXEMPTIONS_PATH} has {len(entries)} entries but 'pinned_count' is "
            f"pinned at {pinned_count}. Update the count in the same change that adds or removes "
            f"an entry."
        )
    return entries, pinned_count


def compare_classifier_conformance(
    per_language: Mapping[str, ClassifierConformanceFacts],
) -> dict[str, ClassifierConformanceFacts]:
    """Return the subset of *per_language* whose facts are NOT fully conformant.

    Args:
        per_language: `{language_name: ClassifierConformanceFacts}` for every enum-emitting
            language under comparison.

    Returns:
        `{language_name: facts}` for every language where `facts.is_fully_conformant()` is
        False. Empty iff every language fully conforms (G10's positive acceptance property).

    Raises:
        ValueError: If *per_language* has fewer than `_MIN_LANGUAGES_FOR_COMPARISON` entries.
    """
    if len(per_language) < _MIN_LANGUAGES_FOR_COMPARISON:
        raise ValueError(
            f"compare_classifier_conformance requires at least "
            f"{_MIN_LANGUAGES_FOR_COMPARISON} languages to compare, got "
            f"{len(per_language)} ({sorted(per_language)})."
        )
    return {
        name: facts for name, facts in per_language.items() if not facts.is_fully_conformant()
    }


def run_self_test() -> None:
    """Prove the comparator detects a forced conformance gap before any real run is trusted.

    Feeds `compare_classifier_conformance` a synthetic FULLY-CONFORMANT pair (both synthetic
    languages have every `ClassifierConformanceFacts` field True -- must report zero violations)
    and a synthetic PARTIALLY-BROKEN pair (one language has `has_contains_keyword=False` -- must
    report exactly that language as non-conformant, and must NOT report the other language).
    Mirrors `supported_domain_parity.run_self_test`'s matching/forced-mismatch shape.

    Raises:
        AssertionError: Either synthetic case does not produce the expected result.
    """
    fully_conformant = ClassifierConformanceFacts(
        has_equals_keyword=True,
        has_contains_keyword=True,
        declared_exception_referenced=True,
        message_discloses_nothing=True,
    )
    matching_pair = {
        _SELF_TEST_LANGUAGE_A: fully_conformant,
        _SELF_TEST_LANGUAGE_B: fully_conformant,
    }
    matching_result = compare_classifier_conformance(matching_pair)
    if matching_result:
        raise AssertionError(
            f"Non-vacuity self-test FAILED: compare_classifier_conformance reported a violation "
            f"for a synthetic FULLY-CONFORMANT pair ({matching_result}) -- the comparator is "
            f"over-triggering and cannot be trusted to judge a real comparison."
        )

    broken_facts = ClassifierConformanceFacts(
        has_equals_keyword=True,
        has_contains_keyword=False,  # forced gap
        declared_exception_referenced=True,
        message_discloses_nothing=True,
    )
    mismatched_pair = {
        _SELF_TEST_LANGUAGE_A: fully_conformant,
        _SELF_TEST_LANGUAGE_B: broken_facts,
    }
    mismatched_result = compare_classifier_conformance(mismatched_pair)
    if _SELF_TEST_LANGUAGE_B not in mismatched_result:
        raise AssertionError(
            f"Non-vacuity self-test FAILED: compare_classifier_conformance did not detect the "
            f"forced conformance gap (expected {_SELF_TEST_LANGUAGE_B!r} reported non-conformant, "
            f"got {mismatched_result}) -- a conformance gate that cannot detect a real divergence "
            f"is worthless."
        )
    if _SELF_TEST_LANGUAGE_A in mismatched_result:
        raise AssertionError(
            f"Non-vacuity self-test FAILED: compare_classifier_conformance flagged "
            f"{_SELF_TEST_LANGUAGE_A!r} (the language that IS fully conformant) as "
            f"non-conformant -- asymmetric/wrong: {mismatched_result[_SELF_TEST_LANGUAGE_A]}"
        )


def check_enum_classifier_conformance() -> int:
    """Run the real cross-target comparison and report the result.

    Returns:
        Exit code (0 = every enum-emitting registered language is fully conformant or has a valid
        exemption, 1 = an unexempted conformance gap was found, 2 = fewer than
        `_MIN_LANGUAGES_FOR_COMPARISON` enum-emitting languages are registered).
    """
    languages = registered_language_names()
    emitting = sorted(enum_emitting_language_names(languages))

    if len(emitting) < _MIN_LANGUAGES_FOR_COMPARISON:
        logger.error(
            "G10 CANNOT RUN: only %d enum-emitting language(s) registered under "
            "'datrix.languages' (%s, out of %d registered total: %s) -- at least %d are required "
            "for a cross-target conformance comparison. Fix: install another enum-emitting "
            "datrix-codegen-<lang> package into D:\\datrix\\.venv (editable install).",
            len(emitting), emitting, len(languages), sorted(languages),
            _MIN_LANGUAGES_FOR_COMPARISON,
        )
        return 2

    fixture = build_fixture_enum()
    per_language = {language: collect_conformance_facts(language, fixture) for language in emitting}
    violations = compare_classifier_conformance(per_language)

    exemptions, _ = load_exemptions()
    exempted_reasons = {entry["language"]: entry["reason"] for entry in exemptions}

    ok = True
    for language in emitting:
        facts = violations.get(language)
        if facts is None:
            continue
        if language in exempted_reasons:
            logger.warning(
                "G10 EXEMPTED: %s does not fully realize equalsKeyword/containsKeyword "
                "conformance (%s) -- reviewed exemption: %s",
                language, facts, exempted_reasons[language],
            )
            continue
        ok = False
        logger.error(
            "G10 VIOLATION: %s does not fully realize equalsKeyword/containsKeyword conformance "
            "for the fixture enum %r: %s. Fix: implement the missing classifier behavior in "
            "%s's EnumGenerator/templates, or add a reviewed entry to %s.",
            language, _FIXTURE_ENUM_NAME, facts, language, EXEMPTIONS_PATH,
        )

    if ok:
        logger.info(
            "G10 holds: all %d enum-emitting registered languages (%s) fully realize "
            "equalsKeyword/containsKeyword conformance for the fixture enum %r.",
            len(emitting), emitting, _FIXTURE_ENUM_NAME,
        )
        return 0
    return 1


def main() -> int:
    """CLI entry point. Runs the non-vacuity self-test first, always."""
    parser = argparse.ArgumentParser(
        description="Prove every registered enum-emitting datrix.languages plugin realizes "
        "equalsKeyword/containsKeyword identically for a fixture enum (G10)."
    )
    parser.add_argument("--debug", action="store_true", help="Enable debug logging")
    parser.add_argument(
        "--self-test", action="store_true", help="Run only the non-vacuity self-test"
    )
    args = parser.parse_args()

    configure_logging(debug=args.debug)
    logger = logging.getLogger(__name__)

    try:
        run_self_test()
    except AssertionError as e:
        logger.error("Non-vacuity self-test FAILED -- aborting: %s", e)
        return 2
    logger.info("Non-vacuity self-test passed.")

    if args.self_test:
        return 0

    return check_enum_classifier_conformance()


if __name__ == "__main__":
    sys.exit(main())
