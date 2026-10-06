"""Cross-language domain-universe closure and declaration-presence gate.

Every registered ``datrix.languages`` entry point declares, for each shared
structural domain it realizes, the glob its generator emits to
(``DomainDeclaration.structural_pattern``). This gate proves two properties
about those declarations, never that the languages' declarations agree with one
another:

**Language set is never hardcoded.** ``registered_language_names`` derives
the comparison universe from ``importlib.metadata.entry_points(group=
"datrix.languages")`` at runtime, so a future ``datrix-codegen-<lang>``
package is picked up automatically with no edit to this script.

**Property 1: domain-universe closure.** ``check_domain_universe_closure``
computes the union of every registered language's COMPILED GenDSL IR domain
ids (``get_definitions(<lang>)``, independent of any declaration a plugin
commits) and asserts it equals ``SHARED_CONTEXT_TYPES.keys()`` exactly: a
domain id some language's compiled IR declares but the registry omits fails
naming the declaring language(s); a registry id no registered language's
compiled IR declares fails as a dead entry (Decision 28 invariant 6 -- dead
surfaces are deleted, not deprecated). Zero tolerance, no exemption file.
This closure check runs first and short-circuits everything after it on
failure -- a wrong universe makes every later check meaningless.

**Property 2: per-language declaration presence.**
``check_declaration_presence`` proves every registered language declares every
STRUCTURAL domain id (the kernel's ``STRUCTURAL_DOMAIN_IDS``), and declares
nothing outside the full registration universe (``SHARED_CONTEXT_TYPES``). A
structural id a language does not declare, or an id a language declares that is
not (or no longer) part of the universe, is a fail-loud
``DECLARATION PRESENCE VIOLATION`` naming the language and the id -- a domain a
language does not realize is counted here and never excused. ``discovery`` and
``resilience`` keep their GenDSL registration and so stay in the registration
universe, but carry no structural-pattern obligation: no language is required to
declare either, and a language that declares one is not reported
out-of-universe. The gate reads only membership (``domain_id in
plugin.domain_declarations``) and a declaration's ``structural_pattern``.

**The declaration report is diagnostic, not a gate.**
``print_declaration_report`` prints, for every STRUCTURAL domain id, each
registered language's declared ``structural_pattern`` (or ``no structural
pattern``), then a divergence block for every structural id some language
declares with no structural pattern or does not declare at all, listing those
languages. It never fails the gate on its own; only ``check_declaration_presence``
does.

**The MariaDB engine boundary needs no special-case code.** The
MariaDB engine boundary is an ENGINE CHOICE inside the ``rdbms``/migration
domains, not a withheld domain -- it never shows up as a domain-set diff at
this script's grain. This script compares by ``domain_id`` (a coarser grain
than per-engine), so MariaDB is naturally never a domain-id-level diff. Do
not add a per-engine special case here.

**Built-in non-vacuity self-test, every invocation.** Before any real
comparison is trusted, ``run_self_test`` feeds ``check_declaration_presence``
a complete synthetic declaration table covering the structural ids only (must
report zero findings, a language omitting the non-structural id included), a
synthetic language omitting one structural id (must be reported, naming that
language and id), a synthetic language declaring an id outside the registration
universe (must be reported, naming that language and id), and a synthetic
language declaring the non-structural id (must be neither reported nor
required); and ``run_universe_closure_self_test`` feeds
``check_domain_universe_closure`` a synthetic matching registry/compiled-IR
pair (must report zero divergence), a synthetic compiled id absent from the
registry (must be reported, naming the declaring language), and a synthetic
registry id no synthetic language declares (must be reported as a dead entry).
A parity gate that cannot detect a real divergence is worthless -- this
mirrors the self-test pattern already used by ``artifact-role-parity-gate.ps1``,
``check-generated-file-ratchet.ps1``, and ``check-docs-conformance.ps1``.

**Fails loud on an empty/single-target discovery.** Fewer than 2 registered
languages makes a cross-language comparison vacuous; ``check_supported_domain_parity``
refuses to silently "pass" that case and exits 2 instead.

Usage:
    python supported_domain_parity.py
    python supported_domain_parity.py --debug
    python supported_domain_parity.py --self-test
"""

from __future__ import annotations

import argparse
import logging
import sys
from collections.abc import Iterable, Mapping, Sequence
from importlib.metadata import entry_points
from typing import Final, cast

from datrix_codegen_common.parity.domain_registry import SHARED_CONTEXT_TYPES
from datrix_codegen_kernel.generation.discovery import get_language_plugin
from datrix_codegen_kernel.parity.domain_declaration import DomainDeclaration
from datrix_codegen_kernel.parity.domain_ids import STRUCTURAL_DOMAIN_IDS
from datrix_common.plugin.registry import LANGUAGES_GROUP
from datrix_testing.conformance.domain_self_consistency import (
    DomainDeclaringPlugin,
)

#: A cross-language parity comparison over 0 or 1 language is vacuous (there
#: is nothing to compare against) -- discovery returning fewer than this many
#: registered languages is a fail-loud condition, never a silent "pass".
_MIN_LANGUAGES_FOR_COMPARISON: Final[int] = 2

#: What the report prints for a declaration that names no structural glob.
_NO_STRUCTURAL_PATTERN: Final[str] = "no structural pattern"

#: Synthetic language names used only by the self-test below. Deliberately
#: NOT real registered language names
#: -- the self-test proves the COMPARATOR's discriminating power, it must
#: never influence which real languages get compared.
_SELF_TEST_LANGUAGE_A: Final[str] = "self_test_lang_a"
_SELF_TEST_LANGUAGE_B: Final[str] = "self_test_lang_b"

#: Synthetic domain ids (neutral e-commerce domain, per repo domain-isolation
#: rules) used only by the self-test below.
_SELF_TEST_DOMAIN_SHARED: Final[str] = "self_test_order"
_SELF_TEST_DOMAIN_FORCED_GAP: Final[str] = "self_test_shipment"

#: A third synthetic domain id, used only by the universe-closure self-test
#: below, standing in for a registry entry no synthetic language declares.
_SELF_TEST_DOMAIN_DEAD_ENTRY: Final[str] = "self_test_backorder"

#: A fourth synthetic domain id, used only by the declaration-presence
#: self-test below, standing in for a declaration a synthetic language makes
#: for an id that is not (or no longer) part of the synthetic universe.
_SELF_TEST_DOMAIN_OUT_OF_UNIVERSE: Final[str] = "self_test_returns"

#: A fifth synthetic domain id, in the synthetic registration universe but not
#: in the synthetic structural ids: standing in for ``discovery``/``resilience``,
#: which no language is required to declare and any language may.
_SELF_TEST_DOMAIN_NON_STRUCTURAL: Final[str] = "self_test_lookup"


def configure_logging(debug: bool = False) -> None:
    """Configure logging output."""
    level = logging.DEBUG if debug else logging.INFO
    logging.basicConfig(level=level, format="%(levelname)s: %(message)s")


def registered_language_names() -> frozenset[str]:
    """Return every language name registered under the ``datrix.languages`` group.

    Derived from the installed entry points -- never a hardcoded literal --
    so a future language package is picked up automatically with no edit here.

    Returns:
        The frozenset of every installed ``datrix.languages`` entry-point name.

    Raises:
        RuntimeError: If entry-point discovery itself fails (queryable
            ``importlib.metadata`` failure, not a plugin-load failure).
    """
    try:
        eps = list(entry_points(group=LANGUAGES_GROUP))
    except Exception as e:
        raise RuntimeError(
            f"Failed to discover '{LANGUAGES_GROUP}' entry points: {e}. "
            f"Expected the 'datrix.languages' entry-point group to be "
            f"queryable via importlib.metadata.entry_points(). Fix: verify "
            f"at least one datrix-codegen-<lang> package is installed into "
            f"the active environment (D:\\datrix\\.venv)."
        ) from e
    return frozenset(ep.name for ep in eps)


def declarations_by_language(
    language_names: Iterable[str],
) -> dict[str, Mapping[str, DomainDeclaration]]:
    """Every domain declaration each language's plugin commits.

    Reads each language plugin's full ``domain_declarations``. Callers use this
    both to check presence (``check_declaration_presence``) and to print the
    declaration table (``print_declaration_report``).

    Args:
        language_names: `datrix.languages` entry-point names.

    Returns:
        `{language_name: {domain_id: DomainDeclaration}}`, one entry per
        language for every domain id that language's plugin declares.
    """
    result: dict[str, Mapping[str, DomainDeclaration]] = {}
    for name in language_names:
        plugin = get_language_plugin(name)
        # `get_language_plugin` returns the base `LanguagePlugin` protocol,
        # which deliberately does not list `domain_declarations` (see
        # `DomainDeclaringPlugin`'s own docstring). Every concrete language
        # plugin class attaches `domain_declarations` regardless; this cast
        # asserts that structural fact without importing any concrete
        # `datrix-codegen-<lang>` package.
        declaring_plugin = cast(DomainDeclaringPlugin, plugin)
        result[name] = declaring_plugin.domain_declarations
    return result


_DOMAIN_GAP_PREFIX = "domain:"


def domain_gap_rows_by_language(
    language_names: Iterable[str],
) -> dict[str, frozenset[str]]:
    """The structural domain ids each language carries as a tracked ``domain:<id>`` gap row.

    Args:
        language_names: `datrix.languages` entry-point names.

    Returns:
        `{language_name: domain ids named by that language's domain gap rows}`.
    """
    return {
        name: frozenset(
            gap.surface[len(_DOMAIN_GAP_PREFIX):]
            for gap in get_language_plugin(name).capability.capability_gaps
            if gap.surface.startswith(_DOMAIN_GAP_PREFIX)
        )
        for name in language_names
    }


def compiled_domain_ids_by_language(
    language_names: Iterable[str],
) -> dict[str, frozenset[str]]:
    """Every domain id each language's COMPILED GenDSL IR declares.

    Unlike ``declarations_by_language`` (which reads a plugin's derived
    ``domain_declarations``), this reads ``get_definitions(name)`` directly:
    the compiled IR is the raw fact of what a language's GenDSL source
    declares, independent of any declaration a plugin later commits. The
    domain-universe closure check measures the universe against THIS raw
    compiled fact, never against the registry's own idea of itself.

    Args:
        language_names: `datrix.languages` entry-point names.

    Returns:
        `{language_name: frozenset of every DomainDefinition.name the
        compiled IR reports for that language}`.
    """
    from datrix_codegen_kernel.gendsl.compiler import get_definitions

    return {
        name: frozenset(
            domain.name
            for definition in get_definitions(name)
            for domain in definition.domains
        )
        for name in language_names
    }


def check_domain_universe_closure(
    per_language_compiled: Mapping[str, frozenset[str]],
    *,
    registry_ids: frozenset[str] | None = None,
) -> tuple[dict[str, frozenset[str]], frozenset[str]]:
    """Compare the compiled-IR union against the shared registry.

    Args:
        per_language_compiled: `{language_name: compiled_domain_ids}` from
            `compiled_domain_ids_by_language`.
        registry_ids: The registry's id set to compare against. Defaults to
            the real `SHARED_CONTEXT_TYPES`; a test passes a synthetic set
            to prove this function's discriminating power without touching
            real state.

    Returns:
        `(declaring_languages_by_missing_id, dead_registry_ids)`.
        `declaring_languages_by_missing_id` maps each domain id present in
        the compiled union but ABSENT from the registry to the set of
        languages that declare it (empty dict iff none). `dead_registry_ids`
        is every registry id no registered language's compiled IR declares
        (empty frozenset iff none). Both empty is the domain-universe
        closure property holding: the registry equals the compiled-IR union
        exactly.
    """
    ids = registry_ids if registry_ids is not None else frozenset(SHARED_CONTEXT_TYPES)
    union_ids: frozenset[str] = frozenset[str]().union(*per_language_compiled.values())
    missing_from_registry = union_ids - ids
    dead_registry_ids = ids - union_ids
    declaring_by_missing_id = {
        domain_id: frozenset(
            lang for lang, ids_for_lang in per_language_compiled.items()
            if domain_id in ids_for_lang
        )
        for domain_id in missing_from_registry
    }
    return declaring_by_missing_id, dead_registry_ids


def check_declaration_presence(
    per_language: Mapping[str, Mapping[str, DomainDeclaration]],
    *,
    registry_ids: frozenset[str] | None = None,
    structural_ids: frozenset[str] | None = None,
    gap_rows: Mapping[str, frozenset[str]] | None = None,
) -> tuple[dict[str, frozenset[str]], dict[str, frozenset[str]]]:
    """Prove every language realizes or tracks every structural domain id, and declares nothing outside the universe.

    This is a PRESENCE check, never an agreement check: a language MAY declare
    a registered non-structural id (``discovery``, ``resilience``) and is never
    required to, and two languages are free to emit a domain to different globs.
    A structural id a language does not declare is accounted for only by that
    language's own ``domain:<id>`` gap row (``gap_rows``); the ledger gate counts
    the rows, this check only requires that an absent domain is tracked.

    Args:
        per_language: `{language_name: {domain_id: DomainDeclaration}}`
            from `declarations_by_language`.
        registry_ids: The full registration universe a declaration must stay
            inside. Defaults to the real `SHARED_CONTEXT_TYPES`; a test passes a
            synthetic set to prove this function's discriminating power
            without touching real state.
        structural_ids: The ids every language must declare. Defaults to the
            kernel's real `STRUCTURAL_DOMAIN_IDS`; a test passes a synthetic set.

    Returns:
        `(undeclared_by_language, out_of_universe_by_language)`.
        `undeclared_by_language` maps each language that does not declare one
        or more structural ids to the frozenset of those ids (a language that
        declares every structural id is simply absent from this dict).
        `out_of_universe_by_language` maps each language that declares an id
        outside the registration universe to the frozenset of those ids. Both
        empty for every language is the presence property holding.
    """
    universe = registry_ids if registry_ids is not None else frozenset(SHARED_CONTEXT_TYPES)
    required = structural_ids if structural_ids is not None else frozenset(STRUCTURAL_DOMAIN_IDS)
    undeclared_by_language: dict[str, frozenset[str]] = {}
    out_of_universe_by_language: dict[str, frozenset[str]] = {}
    for language, declarations in per_language.items():
        declared = frozenset(declarations)
        tracked = gap_rows.get(language, frozenset()) if gap_rows is not None else frozenset()
        undeclared = required - declared - tracked
        out_of_universe = declared - universe
        if undeclared:
            undeclared_by_language[language] = undeclared
        if out_of_universe:
            out_of_universe_by_language[language] = out_of_universe
    return undeclared_by_language, out_of_universe_by_language


def check_domain_gap_rows(
    per_language: Mapping[str, Mapping[str, DomainDeclaration]],
    gap_rows: Mapping[str, frozenset[str]],
    *,
    structural_ids: frozenset[str] | None = None,
) -> tuple[dict[str, frozenset[str]], dict[str, frozenset[str]]]:
    """Prove every ``domain:<id>`` gap row names a structural domain the language really lacks.

    A row is stale when its language also declares the domain (the domain is
    realized, so the row records a gap that no longer exists), and unknown when
    it names an id outside the structural set (a typo or a retired id would
    otherwise account for nothing and never be noticed).

    Args:
        per_language: `{language_name: {domain_id: DomainDeclaration}}`.
        gap_rows: `{language_name: domain ids named by its domain gap rows}`.
        structural_ids: The structural ids a row may name. Defaults to the
            kernel's real `STRUCTURAL_DOMAIN_IDS`; a test passes a synthetic set.

    Returns:
        `(stale_by_language, unknown_by_language)`, each mapping a language to
        the offending ids; a language with none is absent.
    """
    allowed = structural_ids if structural_ids is not None else frozenset(STRUCTURAL_DOMAIN_IDS)
    stale_by_language: dict[str, frozenset[str]] = {}
    unknown_by_language: dict[str, frozenset[str]] = {}
    for language, rows in gap_rows.items():
        stale = rows & frozenset(per_language.get(language, {}))
        unknown = rows - allowed
        if stale:
            stale_by_language[language] = stale
        if unknown:
            unknown_by_language[language] = unknown
    return stale_by_language, unknown_by_language


def _declarations_for_domain(
    domain_id: str,
    per_language: Mapping[str, Mapping[str, DomainDeclaration]],
    languages: Sequence[str],
) -> dict[str, DomainDeclaration]:
    """Every language's declaration for one domain id, for languages that hold one."""
    return {
        language: per_language[language][domain_id]
        for language in languages
        if domain_id in per_language[language]
    }


def _undeclaring_languages(
    domain_id: str,
    per_language: Mapping[str, Mapping[str, DomainDeclaration]],
    languages: Sequence[str],
) -> list[str]:
    """The languages that hold no declaration for one domain id."""
    return [language for language in languages if domain_id not in per_language[language]]


def _has_unpatterned_language(by_language: Mapping[str, DomainDeclaration]) -> bool:
    """True if any language's declaration for a domain names no structural pattern."""
    return any(declaration.structural_pattern is None for declaration in by_language.values())


def print_declaration_report(
    per_language: Mapping[str, Mapping[str, DomainDeclaration]],
    structural_ids: Sequence[str],
) -> None:
    """Log the per-language declaration table, then a divergence block.

    One INFO row per STRUCTURAL domain id per language holding a declaration:
    ``DECLARATION: <lang>.<id> = <structural_pattern>`` (``no structural
    pattern`` when the declaration names none). Then, for every structural id
    some language declares with no structural pattern or does not declare at
    all, a divergence block listing those languages. A non-structural id
    (``discovery``, ``resilience``) appears nowhere in the report.

    The report is diagnostic: it never quotes a reason (none exists) and never
    fails the gate on its own; only ``check_declaration_presence`` does.

    Args:
        per_language: `{language_name: {domain_id: DomainDeclaration}}`
            from `declarations_by_language`.
        structural_ids: The structural domain ids to report, in report order.
    """
    languages = sorted(per_language)
    _log_declaration_table(per_language, structural_ids, languages)
    _log_divergence_block(per_language, structural_ids, languages)


def _log_declaration_table(
    per_language: Mapping[str, Mapping[str, DomainDeclaration]],
    structural_ids: Sequence[str],
    languages: Sequence[str],
) -> None:
    """Log one ``DECLARATION:`` row per structural domain id per declaring language."""
    logger = logging.getLogger(__name__)
    for domain_id in structural_ids:
        for language, declaration in _declarations_for_domain(domain_id, per_language, languages).items():
            pattern = (
                _NO_STRUCTURAL_PATTERN
                if declaration.structural_pattern is None
                else declaration.structural_pattern
            )
            logger.info("DECLARATION: %s.%s = %s", language, domain_id, pattern)


def _log_divergence_block(
    per_language: Mapping[str, Mapping[str, DomainDeclaration]],
    structural_ids: Sequence[str],
    languages: Sequence[str],
) -> None:
    """Log the divergence block: every structural id some language declares without a pattern or omits."""
    logger = logging.getLogger(__name__)
    divergent_ids = [
        domain_id
        for domain_id in structural_ids
        if _has_unpatterned_language(_declarations_for_domain(domain_id, per_language, languages))
        or _undeclaring_languages(domain_id, per_language, languages)
    ]
    if not divergent_ids:
        return

    logger.info(
        "DECLARATION DIVERGENCE REPORT (%d structural domain id(s) some language declares "
        "with no structural pattern or does not declare):",
        len(divergent_ids),
    )
    for domain_id in divergent_ids:
        by_language = _declarations_for_domain(domain_id, per_language, languages)
        for language, declaration in by_language.items():
            if declaration.structural_pattern is None:
                logger.info("  %s: %s declares %s", domain_id, language, _NO_STRUCTURAL_PATTERN)
        for language in _undeclaring_languages(domain_id, per_language, languages):
            logger.info("  %s: %s does not declare it", domain_id, language)


def _synthetic_declaration(domain_id: str) -> DomainDeclaration:
    """A realized synthetic declaration -- always carries a structural pattern."""
    return DomainDeclaration(
        domain_id=domain_id,
        structural_pattern=f"*/self_test/{domain_id}/*.txt",
    )


def run_self_test() -> None:
    """Prove check_declaration_presence detects both directions, and narrows
    its required set to the structural ids, before any real presence check is
    trusted (non-vacuity requirement).

    Feeds :func:`check_declaration_presence` a complete synthetic declaration
    table over the structural ids only (both synthetic languages declare every
    structural id and neither declares the non-structural one -- must report
    zero findings), a synthetic table where one language omits one structural
    id (must be reported undeclared, naming that language and id), a synthetic
    table where one language declares an id outside the registration universe
    (must be reported, naming that language and id), and a synthetic table
    where one language declares the non-structural id (must be neither
    reported out-of-universe nor make the other language undeclared). A
    comparator that either false-positives on the complete table or fails to
    detect either forced gap cannot be trusted for the real check that follows.

    Every input here is synthetic (never a real language name, domain id, or
    mutation of real state).

    Raises:
        AssertionError: If any of the synthetic cases does not produce the
            expected result.
    """
    structural_ids = frozenset({_SELF_TEST_DOMAIN_SHARED, _SELF_TEST_DOMAIN_FORCED_GAP})
    synthetic_universe = structural_ids | {_SELF_TEST_DOMAIN_NON_STRUCTURAL}
    complete_declarations: Mapping[str, DomainDeclaration] = {
        domain_id: _synthetic_declaration(domain_id) for domain_id in sorted(structural_ids)
    }

    complete_table = {
        _SELF_TEST_LANGUAGE_A: complete_declarations,
        _SELF_TEST_LANGUAGE_B: complete_declarations,
    }
    undeclared, out_of_universe = check_declaration_presence(
        complete_table, registry_ids=synthetic_universe, structural_ids=structural_ids
    )
    if undeclared or out_of_universe:
        raise AssertionError(
            f"Non-vacuity self-test FAILED: check_declaration_presence "
            f"reported a finding for a synthetic COMPLETE declaration table "
            f"(undeclared={undeclared}, out_of_universe={out_of_universe}) "
            f"-- the comparator is over-triggering and cannot be trusted to "
            f"judge a real comparison."
        )

    incomplete_table = {
        _SELF_TEST_LANGUAGE_A: {
            _SELF_TEST_DOMAIN_SHARED: complete_declarations[_SELF_TEST_DOMAIN_SHARED]
        },
        _SELF_TEST_LANGUAGE_B: complete_declarations,
    }
    undeclared, out_of_universe = check_declaration_presence(
        incomplete_table, registry_ids=synthetic_universe, structural_ids=structural_ids
    )
    if (
        undeclared.get(_SELF_TEST_LANGUAGE_A) != frozenset({_SELF_TEST_DOMAIN_FORCED_GAP})
        or _SELF_TEST_LANGUAGE_B in undeclared
        or out_of_universe
    ):
        raise AssertionError(
            f"Non-vacuity self-test FAILED: check_declaration_presence did "
            f"not report exactly {_SELF_TEST_LANGUAGE_A!r}'s omitted structural id "
            f"{_SELF_TEST_DOMAIN_FORCED_GAP!r} (got undeclared={undeclared}, "
            f"out_of_universe={out_of_universe}) -- a presence gate that cannot "
            f"detect a real gap is worthless."
        )
    omitting = _undeclaring_languages(
        _SELF_TEST_DOMAIN_FORCED_GAP, incomplete_table, sorted(incomplete_table)
    )
    if omitting != [_SELF_TEST_LANGUAGE_A]:
        raise AssertionError(
            f"Non-vacuity self-test FAILED: the declaration report did not name "
            f"{_SELF_TEST_LANGUAGE_A!r} as the only language omitting "
            f"{_SELF_TEST_DOMAIN_FORCED_GAP!r} (got {omitting})."
        )

    extra_declarations = dict(complete_declarations)
    extra_declarations[_SELF_TEST_DOMAIN_OUT_OF_UNIVERSE] = _synthetic_declaration(
        _SELF_TEST_DOMAIN_OUT_OF_UNIVERSE
    )
    out_of_universe_table = {
        _SELF_TEST_LANGUAGE_A: extra_declarations,
        _SELF_TEST_LANGUAGE_B: complete_declarations,
    }
    undeclared, out_of_universe = check_declaration_presence(
        out_of_universe_table, registry_ids=synthetic_universe, structural_ids=structural_ids
    )
    if out_of_universe != {_SELF_TEST_LANGUAGE_A: frozenset({_SELF_TEST_DOMAIN_OUT_OF_UNIVERSE})} or undeclared:
        raise AssertionError(
            f"Non-vacuity self-test FAILED: check_declaration_presence did "
            f"not report exactly {_SELF_TEST_LANGUAGE_A!r}'s out-of-universe "
            f"declaration {_SELF_TEST_DOMAIN_OUT_OF_UNIVERSE!r} (got "
            f"out_of_universe={out_of_universe}, undeclared={undeclared})."
        )

    undeclared, out_of_universe = check_declaration_presence(
        incomplete_table,
        registry_ids=synthetic_universe,
        structural_ids=structural_ids,
        gap_rows={_SELF_TEST_LANGUAGE_A: frozenset({_SELF_TEST_DOMAIN_FORCED_GAP})},
    )
    if undeclared or out_of_universe:
        raise AssertionError(
            f"Non-vacuity self-test FAILED: check_declaration_presence reported "
            f"{_SELF_TEST_LANGUAGE_A!r}'s omitted structural id "
            f"{_SELF_TEST_DOMAIN_FORCED_GAP!r} although the language carries a "
            f"'domain:{_SELF_TEST_DOMAIN_FORCED_GAP}' gap row for it "
            f"(undeclared={undeclared}, out_of_universe={out_of_universe}) -- a tracked "
            f"gap is the one accounting for an absent domain."
        )

    optional_declarations = dict(complete_declarations)
    optional_declarations[_SELF_TEST_DOMAIN_NON_STRUCTURAL] = _synthetic_declaration(
        _SELF_TEST_DOMAIN_NON_STRUCTURAL
    )
    optional_table = {
        _SELF_TEST_LANGUAGE_A: optional_declarations,
        _SELF_TEST_LANGUAGE_B: complete_declarations,
    }
    undeclared, out_of_universe = check_declaration_presence(
        optional_table, registry_ids=synthetic_universe, structural_ids=structural_ids
    )
    if undeclared or out_of_universe:
        raise AssertionError(
            f"Non-vacuity self-test FAILED: check_declaration_presence reported a "
            f"finding for a language declaring the non-structural id "
            f"{_SELF_TEST_DOMAIN_NON_STRUCTURAL!r} beside the structural ids "
            f"(undeclared={undeclared}, out_of_universe={out_of_universe}) -- a "
            f"non-structural id is optional: never required, never out-of-universe."
        )


def run_gap_row_self_test() -> None:
    """Prove check_domain_gap_rows reports a stale row and an unknown row, and
    stays silent for a row that tracks a genuinely absent structural domain.

    Every input is synthetic (never a real language name or domain id).

    Raises:
        AssertionError: If any of the synthetic cases does not produce the
            expected result.
    """
    structural_ids = frozenset({_SELF_TEST_DOMAIN_SHARED, _SELF_TEST_DOMAIN_FORCED_GAP})
    complete_declarations: Mapping[str, DomainDeclaration] = {
        domain_id: _synthetic_declaration(domain_id) for domain_id in sorted(structural_ids)
    }
    absent_declarations: Mapping[str, DomainDeclaration] = {
        _SELF_TEST_DOMAIN_SHARED: complete_declarations[_SELF_TEST_DOMAIN_SHARED]
    }
    table = {
        _SELF_TEST_LANGUAGE_A: absent_declarations,
        _SELF_TEST_LANGUAGE_B: complete_declarations,
    }

    stale, unknown = check_domain_gap_rows(
        table,
        {
            _SELF_TEST_LANGUAGE_A: frozenset({_SELF_TEST_DOMAIN_FORCED_GAP}),
            _SELF_TEST_LANGUAGE_B: frozenset(),
        },
        structural_ids=structural_ids,
    )
    if stale or unknown:
        raise AssertionError(
            f"Non-vacuity self-test FAILED: check_domain_gap_rows reported a finding for a row "
            f"tracking a domain the language really lacks (stale={stale}, unknown={unknown})."
        )

    stale, unknown = check_domain_gap_rows(
        table,
        {_SELF_TEST_LANGUAGE_B: frozenset({_SELF_TEST_DOMAIN_FORCED_GAP})},
        structural_ids=structural_ids,
    )
    if stale != {_SELF_TEST_LANGUAGE_B: frozenset({_SELF_TEST_DOMAIN_FORCED_GAP})} or unknown:
        raise AssertionError(
            f"Non-vacuity self-test FAILED: check_domain_gap_rows did not report exactly "
            f"{_SELF_TEST_LANGUAGE_B!r}'s stale row for the domain it declares "
            f"(stale={stale}, unknown={unknown})."
        )

    stale, unknown = check_domain_gap_rows(
        table,
        {_SELF_TEST_LANGUAGE_A: frozenset({_SELF_TEST_DOMAIN_OUT_OF_UNIVERSE})},
        structural_ids=structural_ids,
    )
    if unknown != {_SELF_TEST_LANGUAGE_A: frozenset({_SELF_TEST_DOMAIN_OUT_OF_UNIVERSE})} or stale:
        raise AssertionError(
            f"Non-vacuity self-test FAILED: check_domain_gap_rows did not report exactly "
            f"{_SELF_TEST_LANGUAGE_A!r}'s row naming the non-structural id "
            f"{_SELF_TEST_DOMAIN_OUT_OF_UNIVERSE!r} (stale={stale}, unknown={unknown})."
        )


def run_universe_closure_self_test() -> None:
    """Prove check_domain_universe_closure detects both divergence directions
    before any real closure check is trusted.

    Every input here is synthetic (never a real language name or a mutation
    of real state) -- this proves the COMPARATOR's discriminating power, the
    same non-vacuity discipline `run_self_test` already applies to
    `check_declaration_presence`.

    Raises:
        AssertionError: If any of the three synthetic cases does not produce
            the expected result.
    """
    matching_registry = frozenset({_SELF_TEST_DOMAIN_SHARED})
    matching_compiled = {_SELF_TEST_LANGUAGE_A: frozenset({_SELF_TEST_DOMAIN_SHARED})}
    missing, dead = check_domain_universe_closure(
        matching_compiled, registry_ids=matching_registry
    )
    if missing or dead:
        raise AssertionError(
            f"Non-vacuity self-test FAILED: check_domain_universe_closure "
            f"reported a divergence for a synthetic MATCHING registry/"
            f"compiled pair (missing={missing}, dead={dead})."
        )

    forced_missing_compiled = {
        _SELF_TEST_LANGUAGE_A: frozenset(
            {_SELF_TEST_DOMAIN_SHARED, _SELF_TEST_DOMAIN_FORCED_GAP}
        ),
    }
    missing, dead = check_domain_universe_closure(
        forced_missing_compiled, registry_ids=matching_registry
    )
    if _SELF_TEST_DOMAIN_FORCED_GAP not in missing:
        raise AssertionError(
            f"Non-vacuity self-test FAILED: check_domain_universe_closure "
            f"did not detect a compiled domain id absent from the registry: "
            f"{missing}"
        )
    if _SELF_TEST_LANGUAGE_A not in missing[_SELF_TEST_DOMAIN_FORCED_GAP]:
        raise AssertionError(
            f"Non-vacuity self-test FAILED: {_SELF_TEST_LANGUAGE_A!r} was "
            f"not named as a declaring language for the forced-missing id: "
            f"{missing}"
        )

    forced_dead_registry = frozenset(
        {_SELF_TEST_DOMAIN_SHARED, _SELF_TEST_DOMAIN_DEAD_ENTRY}
    )
    missing, dead = check_domain_universe_closure(
        matching_compiled, registry_ids=forced_dead_registry
    )
    if _SELF_TEST_DOMAIN_DEAD_ENTRY not in dead:
        raise AssertionError(
            f"Non-vacuity self-test FAILED: check_domain_universe_closure "
            f"did not detect a dead registry entry: {dead}"
        )


def check_supported_domain_parity() -> int:
    """Prove domain-universe closure and per-language declaration presence.

    Runs, in order:
    1. Domain-universe closure -- the union of every registered language's
       COMPILED GenDSL IR domain ids must equal ``SHARED_CONTEXT_TYPES.keys()``
       exactly. A domain id declared by some language's compiled IR but
       absent from the registry, or a registry id no registered language's
       compiled IR declares, fails loud and short-circuits before anything
       downstream runs (a wrong universe makes every later check meaningless).
    2. Per-language declaration presence -- every registered language must
       declare every structural domain id, and no id outside the registration
       universe. Fails loud and short-circuits before the declaration report
       runs.
    3. The per-language declaration table and divergence block are printed
       (diagnostic only -- never itself a failure condition).

    Returns:
        Exit code (0 = the universe closure holds and every registered
        language declares every structural domain id, 1 = a closure violation
        or a declaration-presence violation was found, 2 = fewer than
        ``_MIN_LANGUAGES_FOR_COMPARISON`` languages are registered -- a
        cross-language comparison over 0 or 1 language is vacuous and must
        fail loud rather than silently "pass").
    """
    logger = logging.getLogger(__name__)
    languages = sorted(registered_language_names())

    if len(languages) < _MIN_LANGUAGES_FOR_COMPARISON:
        logger.error(
            "PARITY GATE CANNOT RUN: only %d language(s) registered under "
            "'%s' (%s) -- at least %d are required for a cross-language "
            "comparison. Expected: 2+ installed datrix-codegen-<lang> "
            "packages, each registering a 'datrix.languages' entry point in "
            "its own pyproject.toml. Fix: install the missing language "
            "package(s) into D:\\datrix\\.venv (editable install), or "
            "verify entry-point registration if a package is installed but "
            "not appearing here.",
            len(languages), LANGUAGES_GROUP, languages, _MIN_LANGUAGES_FOR_COMPARISON,
        )
        return 2

    per_language_compiled = compiled_domain_ids_by_language(languages)
    missing_from_registry, dead_registry_ids = check_domain_universe_closure(
        per_language_compiled
    )
    closure_ok = True
    for domain_id, declaring_languages in sorted(missing_from_registry.items()):
        closure_ok = False
        logger.error(
            "DOMAIN UNIVERSE CLOSURE VIOLATION: domain %r is declared by "
            "%s's compiled GenDSL IR but is not a member of "
            "SHARED_CONTEXT_TYPES. Fix: add it to "
            "datrix_codegen_kernel.generation.registry.COMMON_GENERATOR_REGISTRATIONS.",
            domain_id, sorted(declaring_languages),
        )
    if dead_registry_ids:
        closure_ok = False
        logger.error(
            "DOMAIN UNIVERSE CLOSURE VIOLATION: %d registry id(s) are "
            "declared by NO registered language's compiled GenDSL IR (dead "
            "entries -- delete them per Decision 28 invariant 6, never "
            "deprecate in place): %s",
            len(dead_registry_ids), sorted(dead_registry_ids),
        )
    if not closure_ok:
        return 1

    logger.info(
        "Comparing %d registered languages: %s (%d structural domain ids of the full "
        "%d-domain registration universe: %s)",
        len(languages), languages, len(STRUCTURAL_DOMAIN_IDS), len(SHARED_CONTEXT_TYPES),
        list(STRUCTURAL_DOMAIN_IDS),
    )
    per_language = declarations_by_language(languages)
    gap_rows = domain_gap_rows_by_language(languages)
    undeclared_by_language, out_of_universe_by_language = check_declaration_presence(
        per_language, gap_rows=gap_rows
    )
    stale_by_language, unknown_by_language = check_domain_gap_rows(per_language, gap_rows)
    for name, stale in sorted(stale_by_language.items()):
        logger.error(
            "STALE DOMAIN GAP ROW: %s declares %s and also carries a 'domain:<id>' gap row "
            "for it. Fix: delete the gap row (the domain is realized).",
            name, sorted(stale),
        )
    for name, unknown in sorted(unknown_by_language.items()):
        logger.error(
            "UNKNOWN DOMAIN GAP ROW: %s carries a 'domain:<id>' gap row for %s, which is not a "
            "structural domain id (valid ids: %s). Fix: correct the surface on the language's "
            "capability_gaps row, or delete it.",
            name, sorted(unknown), list(STRUCTURAL_DOMAIN_IDS),
        )
    if stale_by_language or unknown_by_language:
        return 1
    for name in languages:
        for domain_id in sorted(gap_rows[name]):
            logger.info("TRACKED GAP language=%s surface=domain:%s", name, domain_id)

    presence_ok = True
    for name in languages:
        undeclared = undeclared_by_language.get(name, frozenset())
        if undeclared:
            presence_ok = False
            logger.error(
                "DECLARATION PRESENCE VIOLATION: %s declares no structural domain %s and carries "
                "no 'domain:<id>' gap row for it. Every registered language is obligated to "
                "realize every structural domain id; one it realizes by no implementation must be "
                "a tracked gap row on its own capability declaration. "
                "Fix: realize the domain and declare its structural_pattern, or record the gap row.",
                name, sorted(undeclared),
            )
        out_of_universe = out_of_universe_by_language.get(name, frozenset())
        if out_of_universe:
            presence_ok = False
            logger.error(
                "DECLARATION PRESENCE VIOLATION: %s declares out-of-universe %s. Fix: remove "
                "the declaration, or register the domain id in "
                "datrix_codegen_kernel.generation.registry.COMMON_GENERATOR_REGISTRATIONS.",
                name, sorted(out_of_universe),
            )
    if not presence_ok:
        return 1

    logger.info(
        "Declaration presence holds: all %d registered languages' (%s) "
        "declaration tables cover every structural domain id with no "
        "out-of-universe declaration.",
        len(languages), languages,
    )
    print_declaration_report(per_language, STRUCTURAL_DOMAIN_IDS)

    return 0


def main() -> int:
    """Main entry point.

    Returns:
        Exit code (0 = domain-universe closure and declaration presence both
        hold, 1 = a closure or declaration-presence violation was found, 2 =
        the non-vacuity self-test failed or fewer than 2 languages are
        registered).
    """
    parser = argparse.ArgumentParser(
        description=(
            "Prove domain-universe closure (the registry equals the union "
            "of every registered datrix.languages plugin's compiled GenDSL "
            "IR) and per-language declaration presence (every registered "
            "language declares every structural domain id in that closed "
            "universe, and nothing outside it)."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--debug", action="store_true", help="Enable debug logging")
    parser.add_argument(
        "--self-test",
        action="store_true",
        help="Run only the non-vacuity self-test and skip the real comparison",
    )
    args = parser.parse_args()

    configure_logging(debug=args.debug)
    logger = logging.getLogger(__name__)

    try:
        run_self_test()
        run_gap_row_self_test()
        run_universe_closure_self_test()
    except AssertionError as e:
        logger.error(
            "Non-vacuity self-test FAILED -- aborting before any real "
            "comparison is trusted: %s", e,
        )
        return 2
    logger.info(
        "Non-vacuity self-test passed: check_declaration_presence reports "
        "zero findings for a synthetic complete declaration table, correctly "
        "detects both a synthetic omitted structural id and a synthetic "
        "out-of-universe declaration, and neither requires nor rejects a "
        "non-structural id; check_domain_gap_rows reports a stale 'domain:<id>' row (the "
        "language declares the domain) and an unknown one (not a structural id) and "
        "accepts a row for a domain the language really lacks; check_domain_universe_closure "
        "correctly detects both a synthetic missing-from-registry id and a "
        "synthetic dead registry entry."
    )

    if args.self_test:
        return 0

    return check_supported_domain_parity()


if __name__ == "__main__":
    sys.exit(main())
