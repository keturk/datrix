"""Cross-language builtin-claims parity gate, reading each language's realized set.

Two things are checked over every registered `datrix.languages` plugin's
`LanguageCapabilityDeclaration`:

1. CLAIM ACCOUNTING. A language's `realized_builtin_groups` names only real
   BuiltinGroup members; every group a language is obligated to realize (derived from
   the group's own `axis` by `obligated_groups`, never from a list here and never from
   the language's own claim) is either in its realized set or carried as a
   `builtin_group:<id>` row in its `capability_gaps`; and no group is both realized and
   rowed (a stale row). The rows are read only to say which obligated groups are
   accounted for -- they excuse nothing the mapper check below measures.
2. REALIZED-GROUP-VS-MAPPER COHERENCE. Every BUILTIN_REGISTRY row whose group the
   language realizes is mapped by that language's profile. Re-derives, as an independent
   backstop, the same judgment
   `datrix_codegen_common.transpiler.parity_checker.register_builtin_capability` already
   enforces at each language's own plugin import -- as pure, dependency-injected
   comparators over frozensets (never a full LanguageProfile construction), so this
   repo-level gate is testable with synthetic data and is not a call-through to the
   registration-time raise.

Every obligated group a language carries as a gap row is logged on a live run (one INFO
line per `builtin_group:<id>` surface); the count belongs to the capability-gap ledger
gate.

Target set is NEVER hardcoded: languages are enumerated from the installed
`datrix.languages` entry points at run time.
"""

from __future__ import annotations

import argparse
import logging
import sys
from typing import Final, cast

from datrix_codegen_common.transpiler.builtin_registry import (
    BUILTIN_REGISTRY,
    BuiltinGroup,
    obligated_groups,
)
from datrix_codegen_common.transpiler.profile import TranspilerProfile
from datrix_codegen_kernel.generation.discovery import get_language_plugin

from datrix_scripts.registered_targets import registered_language_names

logger = logging.getLogger(__name__)

_MIN_LANGUAGES_FOR_COMPARISON: Final[int] = 2

#: The `capability_gaps` surface prefix a builtin group's tracked gap is recorded under.
_GROUP_GAP_PREFIX: Final[str] = "builtin_group:"

#: The obligation axis a `LanguageCapabilityDeclaration` is measured on.
_LANGUAGE_AXIS: Final[str] = "language"


def configure_logging(debug: bool = False) -> None:
    """Configure logging output."""
    level = logging.DEBUG if debug else logging.INFO
    logging.basicConfig(level=level, format="%(levelname)s: %(message)s")


def group_vocabulary() -> frozenset[str]:
    """Every BuiltinGroup value -- the closed vocabulary a realized name must belong to."""
    return frozenset(group.value for group in BuiltinGroup)


def obligated_group_names() -> frozenset[str]:
    """The group names a language is obligated to realize, derived from each group's axis."""
    return frozenset(group.value for group in obligated_groups(axis=_LANGUAGE_AXIS))


# ---------------------------------------------------------------------------
# Surface 1: claim accounting
# ---------------------------------------------------------------------------


def realized_group_names(language: str) -> frozenset[str]:
    """Return the group names *language* realizes."""
    plugin = get_language_plugin(language)
    return plugin.capability.realized_builtin_groups


def gap_group_names(language: str) -> frozenset[str]:
    """Return the group ids of *language*'s `builtin_group:<id>` capability gap rows."""
    plugin = get_language_plugin(language)
    return frozenset(
        gap.surface.removeprefix(_GROUP_GAP_PREFIX)
        for gap in plugin.capability.capability_gaps
        if gap.surface.startswith(_GROUP_GAP_PREFIX)
    )


def claim_issues(
    language: str,
    *,
    realized: frozenset[str],
    obligated: frozenset[str],
    gap_groups: frozenset[str],
    vocabulary: frozenset[str],
) -> list[str]:
    """Every way *language*'s realized-group claim is unsound.

    Mirrors the registration-time judgment as an independent backstop: a realized name
    outside the group vocabulary denies; an obligated group that is neither realized nor
    carried as a tracked gap is unaccounted for; a group that is both realized and
    carried as a gap row is a stale row. The gap rows are read only to say which
    obligated groups are accounted for -- they excuse nothing the mapper check below
    measures.

    Args:
        language: Language name, used in issue messages only.
        realized: The group names the language realizes.
        obligated: The group names the language is obligated to realize.
        gap_groups: The group ids the language carries as `builtin_group:<id>` rows.
        vocabulary: Every valid BuiltinGroup value.

    Returns:
        Human-readable issue descriptions; empty means the claim is sound.
    """
    issues: list[str] = []
    unknown_realized = sorted(realized - vocabulary)
    if unknown_realized:
        issues.append(
            f"{language!r} realizes unknown builtin group(s) {unknown_realized}. "
            f"Valid groups: {sorted(vocabulary)}. Fix: remove the name from "
            f"realized_builtin_groups or correct its spelling."
        )
    unknown_gapped = sorted(gap_groups - vocabulary)
    if unknown_gapped:
        issues.append(
            f"{language!r} carries a 'builtin_group:<id>' gap row naming unknown "
            f"group(s) {unknown_gapped}. Valid groups: {sorted(vocabulary)}. Fix: "
            f"correct the row's group id."
        )
    unaccounted = sorted(obligated - realized - gap_groups)
    if unaccounted:
        issues.append(
            f"{language!r} neither realizes obligated builtin group(s) {unaccounted} "
            f"nor carries a tracked gap for them. Fix: add each name to "
            f"realized_builtin_groups, or add CapabilityGap(surface="
            f"'builtin_group:<id>', detail=<the missing runtime capability>) to "
            f"capability_gaps."
        )
    stale = sorted(realized & gap_groups)
    if stale:
        issues.append(
            f"{language!r} both realizes builtin group(s) {stale} and carries a "
            f"'builtin_group:<id>' gap row for them (a stale row). Fix: delete the "
            f"gap row, since the group is realized."
        )
    return issues


# ---------------------------------------------------------------------------
# Surface 2: realized-group-vs-mapper coherence
# ---------------------------------------------------------------------------


def mapped_builtin_keys(language: str) -> frozenset[tuple[str, str]]:
    """Return the `(category, method)` keys *language*'s profile actually maps."""
    plugin = get_language_plugin(language)
    transpiler_profile = cast(TranspilerProfile, plugin.transpiler_profile)
    return frozenset(transpiler_profile.language_profile.builtins.mapper.mappings.keys())


def mapping_issues(
    language: str,
    *,
    realized: frozenset[str],
    mapped_keys: frozenset[tuple[str, str]],
) -> list[str]:
    """Pure comparator: every BUILTIN_REGISTRY row whose group is in *realized* is in
    *mapped_keys*.

    Dependency-injected on purpose (never reads a live plugin itself) so this repo-level
    gate's OWN comparator is testable with synthetic data, independent of
    `register_builtin_capability`. It applies to every realized group regardless of any
    gap row the language carries.

    Args:
        language: Language name, used in issue messages only.
        realized: The group names the language realizes.
        mapped_keys: The `(category, method)` keys this language's profile maps.

    Returns:
        Human-readable issue descriptions; empty means every realized group is fully
        mapped.
    """
    return [
        f"{language!r} realizes group {decl.group.value!r} but does not map {key!r}."
        for key, decl in BUILTIN_REGISTRY.items()
        if decl.group.value in realized and key not in mapped_keys
    ]


# ---------------------------------------------------------------------------
# Non-vacuity self-test
# ---------------------------------------------------------------------------


def _self_test_claim_cases() -> list[str]:
    """Plant each claim shape as plain frozensets and check the verdict."""
    problems: list[str] = []
    vocabulary = group_vocabulary()
    obligated = obligated_group_names()
    client_only = sorted(vocabulary - obligated)
    if not obligated or not client_only:
        return [
            "self-test: the BuiltinGroup axes yield no obligated group or no non-obligated "
            "group, so the claim cases cannot be planted."
        ]
    one_obligated = sorted(obligated)[0]
    unknown = "self_test_unknown_group"
    no_rows: frozenset[str] = frozenset()
    rowed = frozenset({one_obligated})
    # (label, realized set, gap-row groups, must the comparator flag it?)
    cases: list[tuple[str, frozenset[str], frozenset[str], bool]] = [
        ("complete language, no client-axis group realized: clean", obligated, no_rows, False),
        ("realized name outside the vocabulary: flagged", obligated | {unknown}, no_rows, True),
        (
            "obligated group neither realized nor rowed: flagged",
            obligated - {one_obligated},
            no_rows,
            True,
        ),
        (
            "obligated group rowed instead of realized: clean",
            obligated - {one_obligated},
            rowed,
            False,
        ),
        ("group both realized and rowed (stale row): flagged", obligated, rowed, True),
        (
            "client-axis group extra in the realized set: clean",
            (obligated - {one_obligated}) | {client_only[0]},
            rowed,
            False,
        ),
    ]
    for label, realized, gaps, must_flag in cases:
        issues = claim_issues(
            "self_test",
            realized=realized,
            obligated=obligated,
            gap_groups=gaps,
            vocabulary=vocabulary,
        )
        logger.info("self-test case: %s -> %s", label, "flagged" if issues else "clean")
        if bool(issues) != must_flag:
            problems.append(
                f"self-test: claim_issues {'did not flag' if must_flag else 'flagged'} "
                f"the case '{label}' (issues: {issues})."
            )
    return problems


def _self_test_mapping_cases() -> list[str]:
    """Plant a fully-mapped and a one-key-removed realized language."""
    problems: list[str] = []
    realized = group_vocabulary()
    fully_mapped = frozenset(BUILTIN_REGISTRY.keys())
    logger.info(
        "self-test case: realized groups fully mapped -> %s",
        "flagged" if mapping_issues("self_test", realized=realized, mapped_keys=fully_mapped) else "clean",
    )
    if mapping_issues("self_test", realized=realized, mapped_keys=fully_mapped):
        problems.append(
            "self-test: mapping_issues flagged a fully-mapped synthetic language "
            "-- over-triggering."
        )
    some_key = next(iter(BUILTIN_REGISTRY))
    logger.info(
        "self-test case: realized group with one registry key unmapped -> %s",
        "flagged"
        if mapping_issues("self_test", realized=realized, mapped_keys=fully_mapped - {some_key})
        else "clean",
    )
    if not mapping_issues("self_test", realized=realized, mapped_keys=fully_mapped - {some_key}):
        problems.append(
            f"self-test: mapping_issues did not detect a realized group's unmapped "
            f"builtin ({some_key!r} removed)."
        )
    unrealized_group = BUILTIN_REGISTRY[some_key].group.value
    if mapping_issues(
        "self_test",
        realized=realized - {unrealized_group},
        mapped_keys=fully_mapped - {some_key},
    ):
        problems.append(
            f"self-test: mapping_issues flagged an unmapped builtin of group "
            f"{unrealized_group!r}, which this synthetic language does not realize "
            f"-- over-triggering."
        )
    return problems


def run_self_test() -> list[str]:
    """Prove both comparators detect a planted defect before any real comparison is trusted.

    Returns:
        A list of failure descriptions -- empty means both comparators are sound.
    """
    return _self_test_claim_cases() + _self_test_mapping_cases()


# ---------------------------------------------------------------------------
# Commands
# ---------------------------------------------------------------------------


def check_builtin_claims_parity() -> int:
    """Run the real gate over every registered language.

    Returns:
        Exit code (0 = both surfaces hold, 1 = at least one defect, 2 = fewer than
        `_MIN_LANGUAGES_FOR_COMPARISON` languages registered).
    """
    languages = sorted(registered_language_names())
    if len(languages) < _MIN_LANGUAGES_FOR_COMPARISON:
        logger.error(
            "D2 CANNOT RUN: only %d language(s) registered (%s) -- at least %d are "
            "required.", len(languages), languages, _MIN_LANGUAGES_FOR_COMPARISON,
        )
        return 2

    vocabulary = group_vocabulary()
    obligated = obligated_group_names()
    ok = True
    for name in languages:
        realized = realized_group_names(name)
        gap_groups = gap_group_names(name)
        for group in sorted(gap_groups & obligated):
            logger.info("TRACKED GAP language=%s surface=%s%s", name, _GROUP_GAP_PREFIX, group)
        issues = claim_issues(
            name,
            realized=realized,
            obligated=obligated,
            gap_groups=gap_groups,
            vocabulary=vocabulary,
        ) + mapping_issues(name, realized=realized, mapped_keys=mapped_builtin_keys(name))
        for issue in issues:
            ok = False
            logger.error("D2 VIOLATION: %s", issue)

    if ok:
        logger.info(
            "D2 holds: every obligated builtin group is realized or tracked as a gap, and "
            "every realized group is fully mapped, across %d languages (%s).",
            len(languages), languages,
        )
        return 0
    return 1


def main() -> int:
    """Entry point.

    Returns:
        Exit code: 0 = D2 holds, 1 = a defect was found, 2 = the self-test failed
        or fewer than 2 languages are registered.
    """
    parser = argparse.ArgumentParser(
        description=(
            "Prove every registered datrix.languages plugin accounts for every builtin "
            "group it is obligated to realize (realized or tracked as a gap) and fully "
            "maps every group it realizes."
        ),
    )
    parser.add_argument("--debug", action="store_true", help="Enable debug logging")
    parser.add_argument(
        "--self-test",
        action="store_true",
        help="Run only the non-vacuity self-test and skip the real comparison",
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
    logger_.info("Non-vacuity self-test passed (claim accounting and mapping coherence).")

    if args.self_test:
        return 0

    return check_builtin_claims_parity()


if __name__ == "__main__":
    sys.exit(main())
