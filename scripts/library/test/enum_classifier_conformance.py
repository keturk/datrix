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

How a language renders its enum file belongs to the language: each registered language declares
a `LanguageConformanceProbes` (`LanguagePlugin.conformance_probes`,
`datrix_codegen_kernel.parity.conformance_probes`) whose `render_enum_classifier` renders the
fixture enum through that language's own enum generation. How the classifier definitions are
SPELLED in that source is data on the language's capability declaration
(`LanguageCapabilityDeclaration.enum_classifier_idioms`). The exception a miss must raise is read
from the language's own transpiler profile -- never from the probe, so a probe cannot choose what
it is checked against. This gate holds the comparison and the fixture and NEVER names a language;
its self-test proves that first (`shared.registered_targets.target_references_in_module`).

The gate is a hard zero: every enum-emitting language must be fully conformant, and a language
that is not fails the gate naming the missing classifier behaviour. No exemption of any kind
exists. A language with no probes or no declared idioms fails loud, never a silent skip.

Run with `--self-test` to verify the comparator is non-vacuous before trusting a real run.
"""

from __future__ import annotations

import argparse
import logging
import re
import sys
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Final

# library/test/ -> library/ -> sibling library/shared/
_LIBRARY_DIR = Path(__file__).resolve().parent.parent
if _LIBRARY_DIR.exists() and str(_LIBRARY_DIR) not in sys.path:
    sys.path.insert(0, str(_LIBRARY_DIR))

from shared.registered_targets import (  # noqa: E402
    registered_language_names,
    self_test_gate_names_no_target,
)

from datrix_common.datrix_model.enums import Enum, EnumValue  # noqa: E402
from datrix_common.errors.plugin import PluginValidationError  # noqa: E402
from datrix_common.paths import ServicePaths  # noqa: E402
from datrix_common.plugin.capability_resolution import declaration_for_language  # noqa: E402
from datrix_common.plugin.language_capability import (  # noqa: E402
    EnumClassifierIdioms,
    LanguageCapabilityDeclaration,
)
from datrix_codegen_kernel.generation.discovery import get_language_plugin  # noqa: E402
from datrix_codegen_kernel.generation.gendsl_ir import DomainDefinition  # noqa: E402
from datrix_codegen_kernel.generation.registry import SubGeneratorSpec  # noqa: E402
from datrix_codegen_kernel.parity.conformance_probes import (  # noqa: E402
    DocumentationSurfaces,
    EnumClassifierRender,
    LanguageConformanceProbes,
    ResponseBodyWireField,
    RouteWireContract,
    conformance_probes_of_language_plugin,
    language_conformance_probes,
)

logger = logging.getLogger(__name__)

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
#: can resolve a per-service import/using/package line for the declared exception.
_FIXTURE_SERVICE_NAME: Final[str] = "catalog"

#: The GenDSL domain id every enum-emitting language plugin registers its `EnumGenerator`
#: sub-generator under (`_declare_structural("enum", EnumGenerator)` in each language's own gendsl
#: definitions module). This is deliberately NOT a structural-parity declaration in
#: `plugin.domain_declarations` -- that declaration carries a structural glob pattern for the
#: cross-language STRUCTURAL parity surface, which a language's `EnumGenerator` does not need in
#: order to emit real enum files. The SUB-GENERATOR REGISTRATION, not the structural-parity
#: declaration, is the true capability signal "this language emits enum types."
_ENUM_DOMAIN_NAME: Final[str] = "enum"

#: The no-match throw's message shape every language's enum template emits (a compile-time
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
            (case/spelling per that language's own convention).
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
    `datrix_testing.conformance.domain_self_consistency.registered_orchestrator_domains`
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

    Every currently registered language emits enum types. This function exists so a future
    non-enum-emitting LANGUAGE plugin (if one is ever added) is excluded rather than silently
    required to conform.

    The capability signal is each plugin's own sub-generator registration -- does it register a
    sub-generator under the `"enum"` GenDSL domain (`_registered_domain_names`) -- never a
    hardcoded language-name list, and never a structural-parity declaration in
    `domain_declarations` (see `_ENUM_DOMAIN_NAME`'s own docstring for why that is the wrong
    signal).

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


def _single_rendered_content(sources: Sequence[str], language: str) -> str:
    """Return the sole rendered source, or raise loud on an unexpected count.

    Args:
        sources: The sources a language's probe rendered for exactly one fixture enum.
        language: The language under render, for the error message.

    Returns:
        `sources[0]`.

    Raises:
        RuntimeError: If *sources* does not contain exactly one entry.
    """
    if len(sources) != 1:
        raise RuntimeError(
            f"{language}'s conformance probe rendered {len(sources)} source(s) for the single "
            f"fixture enum {_FIXTURE_ENUM_NAME!r}, expected exactly 1. This is a harder failure "
            f"than a conformance gap -- investigate {language}'s render_enum_classifier for an "
            f"unexpected extra or missing emission."
        )
    return sources[0]


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
            declares -- every isolated raise must name exactly this type.
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
# Rendering through each language's own probe
# ---------------------------------------------------------------------------


def require_enum_classifier_idioms(language: str, declaration: LanguageCapabilityDeclaration) -> EnumClassifierIdioms:
    """The enum-classifier idioms *declaration* carries.

    Raises:
        RuntimeError: *declaration* declares no enum-classifier idioms.
    """
    idioms = declaration.enum_classifier_idioms
    if idioms is None:
        raise RuntimeError(
            f"Language {language!r} declares no enum-classifier idioms: its "
            f"LanguageCapabilityDeclaration.enum_classifier_idioms is None. The gate cannot "
            f"recognize the classifier definitions in {language}'s rendered enum source. Fix: "
            f"declare an EnumClassifierIdioms (equals/contains definition patterns and the "
            f"two-group no-match raise pattern) on {language}'s capability declaration."
        )
    return idioms


def facts_from_probe(
    language: str,
    fixture: Enum,
    probes: LanguageConformanceProbes,
    idioms: EnumClassifierIdioms,
    expected_exception: str,
) -> ClassifierConformanceFacts:
    """Render *fixture* through *probes* and observe its classifier facts, read with *idioms*.

    Raises:
        RuntimeError: The probe did not render exactly one source.
    """
    render: EnumClassifierRender = probes.render_enum_classifier(fixture, ServicePaths(_FIXTURE_SERVICE_NAME))
    content = _single_rendered_content(render.sources, language)
    return _facts_from_render(
        content,
        has_equals_keyword=re.search(idioms.equals_keyword_definition, content) is not None,
        has_contains_keyword=re.search(idioms.contains_keyword_definition, content) is not None,
        raise_pattern=re.compile(idioms.no_match_raise),
        expected_exception=expected_exception,
        enum_name=str(fixture.name),
    )


def collect_conformance_facts(language: str, fixture: Enum) -> ClassifierConformanceFacts:
    """Render *fixture*'s enum file for *language* and observe its classifier facts.

    The probe is the language's own (`LanguagePlugin.conformance_probes`), the idioms are its
    declared data, and the expected exception is read from its own transpiler profile.

    Args:
        language: A `datrix.languages` entry-point name.
        fixture: The shared fixture `Enum` from `build_fixture_enum`.

    Returns:
        The observed `ClassifierConformanceFacts` for *language*.

    Raises:
        PluginValidationError: *language* declares no (or incomplete) conformance probes.
        RuntimeError: *language* declares no enum-classifier idioms, or its probe cannot render an
            enum at all (a harder failure than a conformance gap -- surfaced distinctly so it is
            never miscounted as "renders but violates one property").
    """
    probes = language_conformance_probes(language)
    idioms = require_enum_classifier_idioms(language, declaration_for_language(language))
    expected_exception = get_language_plugin(language).transpiler_profile.language_profile.errors.unrecognized_value_exception
    try:
        return facts_from_probe(language, fixture, probes, idioms, expected_exception)
    except RuntimeError:
        raise
    except Exception as exc:
        raise RuntimeError(
            f"{language}'s conformance probe could not render the fixture enum "
            f"{_FIXTURE_ENUM_NAME!r}: {exc}. This is a harder failure than a conformance gap -- "
            f"{language}'s enum generator itself is broken, not merely non-conformant."
        ) from exc


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


def conformance_exit_code(violations: Mapping[str, ClassifierConformanceFacts]) -> int:
    """The gate verdict over the non-conformant subset `compare_classifier_conformance` returns.

    Any non-conformant language fails the gate. The verdict takes no exemption input, so no
    language can be excused.

    Returns:
        0 when *violations* is empty, 1 otherwise.
    """
    return 1 if violations else 0


# ---------------------------------------------------------------------------
# Non-vacuity self-test
# ---------------------------------------------------------------------------

#: The idioms and exception of the self-test's fixture language.
_SELF_TEST_IDIOMS: Final[EnumClassifierIdioms] = EnumClassifierIdioms(
    equals_keyword_definition=r"function equals\(",
    contains_keyword_definition=r"function contains\(",
    no_match_raise=r"raise (\w+)\('([^']*)'\)",
)
_SELF_TEST_EXCEPTION: Final[str] = "FixtureUnrecognized"
#: A `LanguageCapabilityDeclaration.name_tokens` entry must be a lowercase alphanumeric segment.
_SELF_TEST_NAME_TOKEN: Final[str] = "selftestlang"
_SELF_TEST_MESSAGE: Final[str] = _EXPECTED_MESSAGE_TEMPLATE.format(enum_name=_FIXTURE_ENUM_NAME)


class _FixtureEnumProbes:
    """An in-process fixture language whose probe renders a fixed set of sources."""

    def __init__(self, sources: tuple[str, ...]) -> None:
        self._sources = sources

    def response_body_wire_fields(self, generated_root: Path) -> tuple[ResponseBodyWireField, ...]:
        return ()

    def route_wire_contracts(self, generated_root: Path) -> tuple[RouteWireContract, ...]:
        return ()

    def documentation_surfaces(self, generated_root: Path, files: Sequence[Path]) -> DocumentationSurfaces:
        return DocumentationSurfaces(frozenset(), frozenset())

    def render_enum_classifier(self, enum: Enum, paths: ServicePaths) -> EnumClassifierRender:
        return EnumClassifierRender(self._sources)


class _FixturePluginWithoutProbes:
    """A fixture language plugin with no `conformance_probes` member."""


def _fixture_source(*, contains: bool = True, message: str = _SELF_TEST_MESSAGE) -> str:
    lines = ["function equals(value) {}"]
    if contains:
        lines.append("function contains(value) {}")
    lines.append(f"raise {_SELF_TEST_EXCEPTION}('{message}')")
    return "\n".join(lines)


def _fixture_facts(*sources: str) -> ClassifierConformanceFacts:
    return facts_from_probe(
        _SELF_TEST_LANGUAGE_A,
        build_fixture_enum(),
        _FixtureEnumProbes(sources),  # type: ignore[arg-type]  # a fixture satisfying the probe members the gate calls
        _SELF_TEST_IDIOMS,
        _SELF_TEST_EXCEPTION,
    )


def _run_probe_dispatch_self_test() -> None:
    """Drive the gate's real render-and-read path with in-process fixture probes.

    The fixture language's name is not a registered one: a conformant render passes, a planted
    divergence (a missing classifier, a disclosing message) fails, a probe returning no source or
    two sources fails loud, a declaration with no idioms fails loud, and a plugin with no probe
    member fails with the accessor's message.

    Raises:
        AssertionError: Any case does not produce the expected result.
    """
    if not _fixture_facts(_fixture_source()).is_fully_conformant():
        raise AssertionError("a conformant fixture render was reported as non-conformant -- over-triggering")
    if _fixture_facts(_fixture_source(contains=False)).is_fully_conformant():
        raise AssertionError("a fixture render with no containsKeyword definition was not reported")
    disclosing = _fixture_source(message=f"{_SELF_TEST_MESSAGE} {_FIXTURE_KEYWORD_HIT}")
    if _fixture_facts(disclosing).is_fully_conformant():
        raise AssertionError("a fixture render whose raise message discloses a keyword was not reported")
    wrong_exception = _fixture_source().replace(_SELF_TEST_EXCEPTION, "SomeOtherError")
    if _fixture_facts(wrong_exception).is_fully_conformant():
        raise AssertionError("a fixture render raising an undeclared exception was not reported")
    for sources in ((), (_fixture_source(), _fixture_source())):
        try:
            _fixture_facts(*sources)
        except RuntimeError as exc:
            if _SELF_TEST_LANGUAGE_A not in str(exc):
                raise AssertionError(f"the refusal of {len(sources)} rendered source(s) did not name the language") from exc
        else:
            raise AssertionError(f"a probe rendering {len(sources)} source(s) was not refused -- exactly one is required")

    bare_declaration = LanguageCapabilityDeclaration(
        language_label=_SELF_TEST_LANGUAGE_A,
        name_tokens=frozenset({_SELF_TEST_NAME_TOKEN}),
        response_body_transform_idioms=(r"\bfixtureTransform\(",),
    )
    try:
        require_enum_classifier_idioms(_SELF_TEST_LANGUAGE_A, bare_declaration)
    except RuntimeError as exc:
        if "declares no enum-classifier idioms" not in str(exc) or _SELF_TEST_LANGUAGE_A not in str(exc):
            raise AssertionError(f"the refusal of a declaration with no idioms was not named ({exc})") from exc
    else:
        raise AssertionError("a declaration with no enum-classifier idioms was not refused")

    try:
        conformance_probes_of_language_plugin(_SELF_TEST_LANGUAGE_A, _FixturePluginWithoutProbes())
    except PluginValidationError as exc:
        if _SELF_TEST_LANGUAGE_A not in str(exc) or "declares no conformance probes" not in str(exc):
            raise AssertionError(f"a plugin with no probe member failed without the accessor's message ({exc})") from exc
    else:
        raise AssertionError("a plugin with no probe member was not refused")


def run_self_test() -> None:
    """Prove this gate names no target and the comparator detects a forced conformance gap
    before any real run is trusted.

    Feeds `compare_classifier_conformance` a synthetic FULLY-CONFORMANT pair (both synthetic
    languages have every `ClassifierConformanceFacts` field True -- must report zero violations)
    and a synthetic PARTIALLY-BROKEN pair (one language has `has_contains_keyword=False` -- must
    report exactly that language as non-conformant, and must NOT report the other language).
    The verdict over each result must pass the first pair and fail the second, and
    `conformance_exit_code` takes no exemption input, so a non-conformant language has no path
    to a pass. Then drives the real render path with fixture probes
    (`_run_probe_dispatch_self_test`).

    Raises:
        AssertionError: Either synthetic case does not produce the expected result.
    """
    names_a_target = self_test_gate_names_no_target(__file__)
    if names_a_target:
        raise AssertionError("\n".join(names_a_target))

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
    if conformance_exit_code(matching_result) != 0 or conformance_exit_code(mismatched_result) != 1:
        raise AssertionError(
            f"Non-vacuity self-test FAILED: conformance_exit_code must pass a fully-conformant "
            f"pair and fail a pair with a non-conformant language, with no exemption input to "
            f"turn that failure into a pass (got {conformance_exit_code(matching_result)} and "
            f"{conformance_exit_code(mismatched_result)})."
        )
    _run_probe_dispatch_self_test()


def check_enum_classifier_conformance() -> int:
    """Run the real cross-target comparison and report the result.

    Returns:
        Exit code (0 = every enum-emitting registered language is fully conformant, 1 = a
        conformance gap was found, 2 = fewer than `_MIN_LANGUAGES_FOR_COMPARISON` enum-emitting
        languages are registered).
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

    for language in emitting:
        facts = violations.get(language)
        if facts is None:
            continue
        logger.error(
            "G10 VIOLATION: %s does not fully realize equalsKeyword/containsKeyword conformance "
            "for the fixture enum %r: %s. Fix: implement the missing classifier behavior in "
            "%s's EnumGenerator/templates.",
            language, _FIXTURE_ENUM_NAME, facts, language,
        )

    exit_code = conformance_exit_code(violations)
    if exit_code == 0:
        logger.info(
            "G10 holds: all %d enum-emitting registered languages (%s) fully realize "
            "equalsKeyword/containsKeyword conformance for the fixture enum %r.",
            len(emitting), emitting, _FIXTURE_ENUM_NAME,
        )
    return exit_code


def main() -> int:
    """CLI entry point. Runs the non-vacuity self-test first, always."""
    parser = argparse.ArgumentParser(
        description="Prove every registered enum-emitting datrix.languages plugin realizes "
        "equalsKeyword/containsKeyword identically for a fixture enum."
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
