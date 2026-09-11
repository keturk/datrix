"""Cross-language domain-universe closure and stance-completeness gate.

Every registered ``datrix.languages`` entry point declares its own stance --
``supported`` or ``unsupported(reason)`` -- over the full shared domain
universe. This gate proves two properties about that stance-taking, never
that the stances themselves agree: a per-language `supported`/
`unsupported(reason)` split is the DESIGNED state, not a gap awaiting work --
most `unsupported` stances are permanent "realized elsewhere on this target"
facts (e.g. a domain folded into another domain, or architecturally
inapplicable to one target's runtime), not capability holes.

**Language set is never hardcoded.** ``registered_language_names`` derives
the comparison universe from ``importlib.metadata.entry_points(group=
"datrix.languages")`` at runtime, so a future ``datrix-codegen-<lang>``
package is picked up automatically with no edit to this script.

**Property 1: domain-universe closure.** ``check_domain_universe_closure``
computes the union of every registered language's COMPILED GenDSL IR domain
ids (``get_definitions(<lang>)``, independent of any supported/unsupported
stance) and asserts it equals ``SHARED_CONTEXT_TYPES.keys()`` exactly: a
domain id some language's compiled IR declares but the registry omits fails
naming the declaring language(s); a registry id no registered language's
compiled IR declares fails as a dead entry (Decision 28 invariant 6 -- dead
surfaces are deleted, not deprecated). Zero tolerance, no exemption file.
This closure check runs first and short-circuits everything after it on
failure -- a wrong universe makes every later check meaningless.

**Property 2: per-language stance completeness.** ``check_stance_completeness``
proves every registered language declares SOME stance -- ``supported`` or
``unsupported(reason)`` -- for every id in the closed universe, and declares
no stance for an id outside it. A language silently missing a stance for a
universe id, or declaring a stance for an id that is not (or no longer) part
of the universe, is a fail-loud ``STANCE COMPLETENESS VIOLATION``. This is a
COMPLETENESS check, never an agreement check: two languages are free to take
opposite stances on the same domain id -- python may support ``graphql``
while java declares it ``unsupported(reason=...)`` -- as long as each
language HAS declared one.

**The stance report is diagnostic, not a gate.** ``print_stance_report``
prints every registered language's full stance table (one row per universe
id) and then a divergence report for every id whose declared status is not
unanimous across languages -- including unanimous ``unsupported`` -- quoting
each unsupported language's declared reason verbatim. Divergence-with-a-reason
is the designed per-target-realization state; the report exists so a reader
can see WHY languages diverge, never to fail the gate on its own.

**The MariaDB engine boundary needs no special-case code.** The
MariaDB engine boundary is an ENGINE CHOICE inside the ``rdbms``/migration
domains, not a withheld domain -- it never shows up as a domain-set diff at
this script's grain. This script compares by ``domain_id`` (a coarser grain
than per-engine), so MariaDB is naturally never a domain-id-level diff. Do
not add a per-engine special case here.

**Built-in non-vacuity self-test, every invocation.** Before any real
comparison is trusted, ``run_self_test`` feeds ``check_stance_completeness``
a complete synthetic stance table (must report zero findings), a synthetic
language missing one universe id's stance (must be reported, naming that
language and id), and a synthetic language declaring a stance for an
out-of-universe id (must be reported, naming that language and id); and
``run_universe_closure_self_test`` feeds ``check_domain_universe_closure`` a
synthetic matching registry/compiled-IR pair (must report zero divergence),
a synthetic compiled id absent from the registry (must be reported, naming
the declaring language), and a synthetic registry id no synthetic language
declares (must be reported as a dead entry). A parity gate that cannot
detect a real divergence is worthless -- this mirrors the self-test pattern
already used by ``reference-example-parity-gate.ps1``,
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
from collections.abc import Iterable, Mapping
from importlib.metadata import entry_points
from typing import Final, cast

from datrix_codegen_common.parity.domain_declaration import DomainDeclaration
from datrix_codegen_common.parity.domain_registry import SHARED_CONTEXT_TYPES
from datrix_codegen_common.testkit.gates.domain_self_consistency import (
    DomainDeclaringPlugin,
)
from datrix_common.generation.discovery import get_language_plugin
from datrix_common.plugin.registry import LANGUAGES_GROUP

#: A cross-language parity comparison over 0 or 1 language is vacuous (there
#: is nothing to compare against) -- discovery returning fewer than this many
#: registered languages is a fail-loud condition, never a silent "pass".
_MIN_LANGUAGES_FOR_COMPARISON: Final[int] = 2

#: Synthetic language names used only by the self-test below. Deliberately
#: NOT real registered language names (`python`/`dotnet`/`java`/`typescript`)
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

#: A fourth synthetic domain id, used only by the stance-completeness
#: self-test below, standing in for a stance a synthetic language declares
#: for an id that is not (or no longer) part of the synthetic universe.
_SELF_TEST_DOMAIN_OUT_OF_UNIVERSE: Final[str] = "self_test_returns"


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


def stance_table_by_language(
    language_names: Iterable[str],
) -> dict[str, Mapping[str, DomainDeclaration]]:
    """Every domain id's declared STANCE for each language.

    Reads each language plugin's full ``domain_declarations`` -- the
    ``supported``/``unsupported(reason)`` stance a plugin commits for a
    domain id, not just the ones it supports. Callers use this both to
    check completeness (``check_stance_completeness``) and to print the
    full stance table (``print_stance_report``).

    Args:
        language_names: `datrix.languages` entry-point names.

    Returns:
        `{language_name: {domain_id: DomainDeclaration}}`, one entry per
        language for every domain id that language's plugin declares a
        stance for.
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


def compiled_domain_ids_by_language(
    language_names: Iterable[str],
) -> dict[str, frozenset[str]]:
    """Every domain id each language's COMPILED GenDSL IR declares.

    Unlike ``stance_table_by_language`` (which reads a plugin's derived
    ``domain_declarations`` -- supported/unsupported STANCES), this reads
    ``get_definitions(name)`` directly: the compiled IR is the raw fact of
    what a language's GenDSL source declares, independent of any stance a
    plugin later commits. The domain-universe closure check measures the
    universe against THIS raw compiled fact, never against the registry's
    own idea of itself.

    Args:
        language_names: `datrix.languages` entry-point names.

    Returns:
        `{language_name: frozenset of every DomainDefinition.name the
        compiled IR reports for that language}`.
    """
    from datrix_codegen_common.gendsl.compiler import get_definitions

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


def check_stance_completeness(
    per_language_stances: Mapping[str, Mapping[str, DomainDeclaration]],
    *,
    registry_ids: frozenset[str] | None = None,
) -> tuple[dict[str, frozenset[str]], dict[str, frozenset[str]]]:
    """Prove every language declares a stance for every universe id, and no other.

    This is a COMPLETENESS check, never an agreement check: two languages
    are free to take opposite stances (``supported`` vs.
    ``unsupported(reason)``) on the same domain id, as long as each language
    HAS declared one.

    Args:
        per_language_stances: `{language_name: {domain_id: DomainDeclaration}}`
            from `stance_table_by_language`.
        registry_ids: The universe to check completeness against. Defaults
            to the real `SHARED_CONTEXT_TYPES`; a test passes a synthetic
            set to prove this function's discriminating power without
            touching real state.

    Returns:
        `(undeclared_by_language, out_of_universe_by_language)`.
        `undeclared_by_language` maps each language that is missing a
        stance for one or more universe ids to the frozenset of those ids
        (a language with a complete stance table is simply absent from this
        dict). `out_of_universe_by_language` maps each language that
        declares a stance for an id outside the universe to the frozenset
        of those ids. Both empty for every language is the stance-
        completeness property holding.
    """
    universe = registry_ids if registry_ids is not None else frozenset(SHARED_CONTEXT_TYPES)
    undeclared_by_language: dict[str, frozenset[str]] = {}
    out_of_universe_by_language: dict[str, frozenset[str]] = {}
    for language, stances in per_language_stances.items():
        declared = frozenset(stances)
        undeclared = universe - declared
        out_of_universe = declared - universe
        if undeclared:
            undeclared_by_language[language] = undeclared
        if out_of_universe:
            out_of_universe_by_language[language] = out_of_universe
    return undeclared_by_language, out_of_universe_by_language


def _stances_for_domain(
    domain_id: str,
    per_language_stances: Mapping[str, Mapping[str, DomainDeclaration]],
    languages: list[str],
) -> dict[str, DomainDeclaration]:
    """Every language's declaration for one domain id, for languages that hold one."""
    return {
        language: per_language_stances[language][domain_id]
        for language in languages
        if domain_id in per_language_stances[language]
    }


def _is_divergent_stance(by_language: Mapping[str, DomainDeclaration]) -> bool:
    """True if a universe id's stance is not unanimous ``supported`` across languages.

    Unanimous ``unsupported`` counts as divergent too -- surfaced in the
    report even though no language supports the domain, since that is worth
    a reader's attention (nobody realizes this domain on any target) without
    being a gate failure on its own.
    """
    statuses = {declaration.status for declaration in by_language.values()}
    return len(statuses) > 1 or statuses == {"unsupported"}


def print_stance_report(
    per_language_stances: Mapping[str, Mapping[str, DomainDeclaration]],
) -> None:
    """Log the full per-language stance table, then a divergence report.

    One INFO row per universe id per language: ``STANCE: <lang>.<id> =
    <status>`` (with the declared reason parenthesized for ``unsupported``).
    Then, for every universe id whose declared status is not unanimous
    across every language that holds a stance for it -- including the case
    where every language agrees on ``unsupported`` -- a divergence block
    quoting each unsupported language's reason verbatim.

    Divergence here is the DESIGNED state, not a failure list: per-language
    ``supported``/``unsupported(reason)`` stances are expected to diverge
    when a domain is realized differently (or not at all) on different
    targets -- e.g. a domain folded into another domain on one target, or
    architecturally inapplicable to one target's runtime. Reporting
    divergence never fails the gate on its own; only
    ``check_stance_completeness`` (a missing or out-of-universe stance)
    does.

    Args:
        per_language_stances: `{language_name: {domain_id: DomainDeclaration}}`
            from `stance_table_by_language`.
    """
    logger = logging.getLogger(__name__)
    languages = sorted(per_language_stances)
    universe_ids = sorted(
        frozenset[str]().union(*(frozenset(stances) for stances in per_language_stances.values()))
    )

    for domain_id in universe_ids:
        for language, declaration in _stances_for_domain(
            domain_id, per_language_stances, languages
        ).items():
            suffix = f" ({declaration.reason})" if declaration.status == "unsupported" else ""
            logger.info(
                "STANCE: %s.%s = %s%s", language, domain_id, declaration.status, suffix
            )

    divergent_ids = [
        domain_id
        for domain_id in universe_ids
        if _is_divergent_stance(_stances_for_domain(domain_id, per_language_stances, languages))
    ]
    if not divergent_ids:
        return

    logger.info(
        "STANCE DIVERGENCE REPORT (%d domain id(s) -- divergence-with-a-reason is "
        "the designed per-target-realization state, not a gate failure):",
        len(divergent_ids),
    )
    for domain_id in divergent_ids:
        by_language = _stances_for_domain(domain_id, per_language_stances, languages)
        for language, declaration in by_language.items():
            if declaration.status != "unsupported":
                continue
            logger.info("  %s: %s unsupported -- %s", domain_id, language, declaration.reason)


def run_self_test() -> None:
    """Prove check_stance_completeness detects both incompleteness directions
    before any real stance-completeness check is trusted (non-vacuity
    requirement).

    Feeds :func:`check_stance_completeness` a complete synthetic stance
    table (both synthetic languages declare a stance for every synthetic
    universe id -- must report zero findings), a synthetic table where one
    language is missing a stance for one universe id (must be reported,
    naming that language and id), and a synthetic table where one language
    declares a stance for an id outside the synthetic universe (must be
    reported, naming that language and id). A comparator that either
    false-positives on the complete table or fails to detect either forced
    gap cannot be trusted for the real check that follows.

    Every input here is synthetic (never a real language name, domain id, or
    mutation of real state).

    Raises:
        AssertionError: If any of the three synthetic cases does not
            produce the expected result.
    """
    synthetic_universe = frozenset({_SELF_TEST_DOMAIN_SHARED, _SELF_TEST_DOMAIN_FORCED_GAP})
    complete_stances: Mapping[str, DomainDeclaration] = {
        _SELF_TEST_DOMAIN_SHARED: DomainDeclaration(
            domain_id=_SELF_TEST_DOMAIN_SHARED,
            status="supported",
            structural_pattern="*/self_test/*.txt",
        ),
        _SELF_TEST_DOMAIN_FORCED_GAP: DomainDeclaration(
            domain_id=_SELF_TEST_DOMAIN_FORCED_GAP,
            status="unsupported",
            reason="self-test synthetic reason -- never a real capability gap",
        ),
    }

    complete_table = {
        _SELF_TEST_LANGUAGE_A: complete_stances,
        _SELF_TEST_LANGUAGE_B: complete_stances,
    }
    undeclared, out_of_universe = check_stance_completeness(
        complete_table, registry_ids=synthetic_universe
    )
    if undeclared or out_of_universe:
        raise AssertionError(
            f"Non-vacuity self-test FAILED: check_stance_completeness "
            f"reported a finding for a synthetic COMPLETE stance table "
            f"(undeclared={undeclared}, out_of_universe={out_of_universe}) "
            f"-- the comparator is over-triggering and cannot be trusted to "
            f"judge a real comparison."
        )

    incomplete_table = {
        _SELF_TEST_LANGUAGE_A: {_SELF_TEST_DOMAIN_SHARED: complete_stances[_SELF_TEST_DOMAIN_SHARED]},
        _SELF_TEST_LANGUAGE_B: complete_stances,
    }
    undeclared, out_of_universe = check_stance_completeness(
        incomplete_table, registry_ids=synthetic_universe
    )
    missing_for_a = undeclared.get(_SELF_TEST_LANGUAGE_A, frozenset())
    if _SELF_TEST_DOMAIN_FORCED_GAP not in missing_for_a:
        raise AssertionError(
            f"Non-vacuity self-test FAILED: check_stance_completeness did "
            f"not detect {_SELF_TEST_LANGUAGE_A!r}'s missing stance for "
            f"{_SELF_TEST_DOMAIN_FORCED_GAP!r} (got undeclared={undeclared}) "
            f"-- a completeness gate that cannot detect a real gap is "
            f"worthless."
        )

    extra_stances = dict(complete_stances)
    extra_stances[_SELF_TEST_DOMAIN_OUT_OF_UNIVERSE] = DomainDeclaration(
        domain_id=_SELF_TEST_DOMAIN_OUT_OF_UNIVERSE,
        status="unsupported",
        reason="self-test synthetic out-of-universe reason",
    )
    out_of_universe_table = {
        _SELF_TEST_LANGUAGE_A: extra_stances,
        _SELF_TEST_LANGUAGE_B: complete_stances,
    }
    undeclared, out_of_universe = check_stance_completeness(
        out_of_universe_table, registry_ids=synthetic_universe
    )
    extra_for_a = out_of_universe.get(_SELF_TEST_LANGUAGE_A, frozenset())
    if _SELF_TEST_DOMAIN_OUT_OF_UNIVERSE not in extra_for_a:
        raise AssertionError(
            f"Non-vacuity self-test FAILED: check_stance_completeness did "
            f"not detect {_SELF_TEST_LANGUAGE_A!r}'s out-of-universe stance "
            f"for {_SELF_TEST_DOMAIN_OUT_OF_UNIVERSE!r} (got "
            f"out_of_universe={out_of_universe})."
        )


def run_universe_closure_self_test() -> None:
    """Prove check_domain_universe_closure detects both divergence directions
    before any real closure check is trusted.

    Every input here is synthetic (never a real language name or a mutation
    of real state) -- this proves the COMPARATOR's discriminating power, the
    same non-vacuity discipline `run_self_test` already applies to
    `check_stance_completeness`.

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
    """Prove domain-universe closure and per-language stance completeness.

    Runs, in order:
    1. Domain-universe closure -- the union of every registered language's
       COMPILED GenDSL IR domain ids must equal ``SHARED_CONTEXT_TYPES.keys()``
       exactly. A domain id declared by some language's compiled IR but
       absent from the registry, or a registry id no registered language's
       compiled IR declares, fails loud and short-circuits before anything
       downstream runs (a wrong universe makes every later check meaningless).
    2. Per-language stance completeness -- every registered language must
       declare a stance (``supported`` or ``unsupported(reason)``) for every
       id in the closed universe, and no stance for an id outside it. Fails
       loud and short-circuits before the stance report runs.
    3. The full per-language stance table and divergence report are printed
       (diagnostic only -- never itself a failure condition).

    Returns:
        Exit code (0 = the universe closure holds and every registered
        language's stance table is complete, 1 = a closure violation or a
        stance-completeness violation was found, 2 = fewer than
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
            "datrix_common.generation.registry.COMMON_GENERATOR_REGISTRATIONS.",
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
        "Comparing %d registered languages: %s (full %d-domain shared "
        "universe: %s)",
        len(languages), languages, len(SHARED_CONTEXT_TYPES), sorted(SHARED_CONTEXT_TYPES),
    )
    per_language_stances = stance_table_by_language(languages)
    undeclared_by_language, out_of_universe_by_language = check_stance_completeness(
        per_language_stances
    )

    completeness_ok = True
    for name in languages:
        undeclared = undeclared_by_language.get(name, frozenset())
        if undeclared:
            completeness_ok = False
            logger.error(
                "STANCE COMPLETENESS VIOLATION: %s has no stance for %s",
                name, sorted(undeclared),
            )
        out_of_universe = out_of_universe_by_language.get(name, frozenset())
        if out_of_universe:
            completeness_ok = False
            logger.error(
                "STANCE COMPLETENESS VIOLATION: %s declares out-of-universe %s",
                name, sorted(out_of_universe),
            )
    if not completeness_ok:
        return 1

    logger.info(
        "Stance completeness holds: all %d registered languages' (%s) "
        "stance tables cover the full shared domain universe with no "
        "out-of-universe stance.",
        len(languages), languages,
    )
    print_stance_report(per_language_stances)

    return 0


def main() -> int:
    """Main entry point.

    Returns:
        Exit code (0 = domain-universe closure and stance completeness both
        hold, 1 = a closure or stance-completeness violation was found, 2 =
        the non-vacuity self-test failed or fewer than 2 languages are
        registered).
    """
    parser = argparse.ArgumentParser(
        description=(
            "Prove domain-universe closure (the registry equals the union "
            "of every registered datrix.languages plugin's compiled GenDSL "
            "IR) and per-language stance completeness (every registered "
            "language declares a supported/unsupported(reason) stance for "
            "every id in that closed universe, and no stance outside it)."
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
        run_universe_closure_self_test()
    except AssertionError as e:
        logger.error(
            "Non-vacuity self-test FAILED -- aborting before any real "
            "comparison is trusted: %s", e,
        )
        return 2
    logger.info(
        "Non-vacuity self-test passed: check_stance_completeness reports "
        "zero findings for a synthetic complete stance table and correctly "
        "detects both a synthetic missing stance and a synthetic "
        "out-of-universe stance, and check_domain_universe_closure "
        "correctly detects both a synthetic missing-from-registry id and a "
        "synthetic dead registry entry."
    )

    if args.self_test:
        return 0

    return check_supported_domain_parity()


if __name__ == "__main__":
    sys.exit(main())
