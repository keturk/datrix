"""Cross-language builtin-claims parity gate (D2), reading per-group stances.

Two things are checked over every registered `datrix.languages` plugin's
`LanguageCapabilityDeclaration.builtin_group_stances`:

1. STANCE KEY-SET IDENTITY. Every language declares a stance for exactly the same set
   of BuiltinGroup names -- guaranteed identical by construction for any language whose
   plugin loaded at all (the per-language, registration-time completeness check in
   `register_builtin_capability` already enforces it, at plugin import).
   Kept here as a non-vacuity proof, not because it can fail for
   an installed set: a future change that decoupled per-language enforcement from this
   repo-level check would be caught here first.
2. PER-GROUP STANCE-VS-MAPPER COHERENCE. For every group, a language is 'supported' (and
   maps every BUILTIN_REGISTRY row in that group) or 'unsupported' with a non-empty
   reason. Re-derives the SAME completeness/coverage judgment
   `datrix_codegen_common.transpiler.parity_checker.register_builtin_capability` already
   enforces at each language's own plugin import -- as a pure, dependency-injected
   comparator over stance dicts and mapped-key frozensets (never a full LanguageProfile
   construction), so this repo-level gate is testable with synthetic data and does not
   duplicate the registration-time raise -- it is the belt-and-suspenders backstop.

The per-method reviewed-gap file this gate previously read is DELETED outright: a
`supported` stance is fully mapped by construction (enforced at plugin import), so
there is no more "mapped by some languages, not all" state left to catalogue.

Target set is NEVER hardcoded: languages are enumerated from the installed
`datrix.languages` entry points at run time.
"""

from __future__ import annotations

import argparse
import logging
import sys
from collections.abc import Mapping
from pathlib import Path
from typing import Final, cast

_LIBRARY_DIR = Path(__file__).resolve().parent.parent
if _LIBRARY_DIR.exists() and str(_LIBRARY_DIR) not in sys.path:
    sys.path.insert(0, str(_LIBRARY_DIR))

from shared.registered_targets import registered_language_names  # noqa: E402

from datrix_codegen_common.transpiler.builtin_registry import (  # noqa: E402
    BUILTIN_REGISTRY,
    BuiltinGroup,
)
from datrix_codegen_common.transpiler.profile import TranspilerProfile  # noqa: E402
from datrix_common.generation.discovery import get_language_plugin  # noqa: E402
from datrix_common.plugin.language_capability import BuiltinGroupStance  # noqa: E402

logger = logging.getLogger(__name__)

_MIN_LANGUAGES_FOR_COMPARISON: Final[int] = 2

_SELF_TEST_LANGUAGE_A: Final[str] = "self_test_lang_a"
_SELF_TEST_LANGUAGE_B: Final[str] = "self_test_lang_b"
_SELF_TEST_GROUP_SHARED: Final[str] = "self_test_group_shared"
_SELF_TEST_GROUP_FORCED_GAP: Final[str] = "self_test_group_forced_gap"


def configure_logging(debug: bool = False) -> None:
    """Configure logging output."""
    level = logging.DEBUG if debug else logging.INFO
    logging.basicConfig(level=level, format="%(levelname)s: %(message)s")


# ---------------------------------------------------------------------------
# Surface 1: stance key-set identity
# ---------------------------------------------------------------------------


def stance_key_set(language: str) -> frozenset[str]:
    """Return *language*'s declared builtin_group_stances key set (group names)."""
    plugin = get_language_plugin(language)
    return frozenset(plugin.capability.builtin_group_stances)


def compare_stance_key_sets(
    per_language: Mapping[str, frozenset[str]],
) -> dict[str, frozenset[str]]:
    """Compare every language's stance key set against the union of all.

    Kept as a non-vacuity proof (see module docstring) -- this can only ever
    return all-empty for a set of languages whose plugins all loaded, since
    `register_builtin_capability` already enforces per-language completeness
    against the same BuiltinGroup member set at import.

    Raises:
        ValueError: If *per_language* has fewer than
            `_MIN_LANGUAGES_FOR_COMPARISON` entries.
    """
    if len(per_language) < _MIN_LANGUAGES_FOR_COMPARISON:
        raise ValueError(
            f"compare_stance_key_sets requires at least "
            f"{_MIN_LANGUAGES_FOR_COMPARISON} languages, got "
            f"{len(per_language)} ({sorted(per_language)})."
        )
    union: frozenset[str] = frozenset[str]().union(*per_language.values())
    return {name: union - keys for name, keys in per_language.items()}


# ---------------------------------------------------------------------------
# Surface 2: per-group stance-vs-mapper coherence
# ---------------------------------------------------------------------------


def mapped_builtin_keys(language: str) -> frozenset[tuple[str, str]]:
    """Return the `(category, method)` keys *language*'s profile actually maps."""
    plugin = get_language_plugin(language)
    transpiler_profile = cast(TranspilerProfile, plugin.transpiler_profile)
    return frozenset(transpiler_profile.language_profile.builtins.mapper.mappings.keys())


def stance_coverage_issues(
    language: str,
    stances: Mapping[str, BuiltinGroupStance],
    mapped_keys: frozenset[tuple[str, str]],
) -> list[str]:
    """Pure comparator: every BuiltinGroup member has a stance, and every group whose
    stance is 'supported' has every one of its BUILTIN_REGISTRY rows in *mapped_keys*.

    Dependency-injected on purpose (never reads a live plugin itself) so this repo-level
    gate's OWN comparator is testable with synthetic data, independent of
    `register_builtin_capability` -- the belt-and-suspenders backstop this gate exists
    to provide, not a call-through to the same function.

    Args:
        language: Language name, used in issue messages only.
        stances: `{group name: BuiltinGroupStance}`.
        mapped_keys: The `(category, method)` keys this language's profile maps.

    Returns:
        Human-readable issue descriptions; empty means this language's stances are
        complete and every 'supported' group is fully mapped.
    """
    issues: list[str] = []
    required_names = frozenset(group.value for group in BuiltinGroup)
    missing = sorted(required_names - frozenset(stances))
    if missing:
        issues.append(
            f"{language!r} declares no builtin_group_stances entry for group(s) "
            f"{missing}."
        )
    for key, decl in BUILTIN_REGISTRY.items():
        stance = stances.get(decl.group.value)
        if stance is not None and stance.status == "supported" and key not in mapped_keys:
            issues.append(
                f"{language!r} declares group {decl.group.value!r} supported but "
                f"does not map {key!r}."
            )
    return issues


# ---------------------------------------------------------------------------
# Non-vacuity self-test
# ---------------------------------------------------------------------------


def run_self_test() -> list[str]:
    """Prove both comparators detect a forced mismatch before any real comparison is trusted.

    Returns:
        A list of failure descriptions -- empty means both comparators are sound.
    """
    problems: list[str] = []

    # --- Surface 1: stance key-set identity ---
    matching_keys = {
        _SELF_TEST_LANGUAGE_A: frozenset({_SELF_TEST_GROUP_SHARED}),
        _SELF_TEST_LANGUAGE_B: frozenset({_SELF_TEST_GROUP_SHARED}),
    }
    if any(compare_stance_key_sets(matching_keys).values()):
        problems.append(
            "self-test: compare_stance_key_sets reported a divergence for a "
            "synthetic MATCHING pair -- over-triggering."
        )
    mismatched_keys = {
        _SELF_TEST_LANGUAGE_A: frozenset({_SELF_TEST_GROUP_SHARED, _SELF_TEST_GROUP_FORCED_GAP}),
        _SELF_TEST_LANGUAGE_B: frozenset({_SELF_TEST_GROUP_SHARED}),
    }
    key_result = compare_stance_key_sets(mismatched_keys)
    if _SELF_TEST_GROUP_FORCED_GAP not in key_result.get(_SELF_TEST_LANGUAGE_B, frozenset()):
        problems.append(
            "self-test: compare_stance_key_sets did not detect the forced key-set "
            f"mismatch (got {key_result})."
        )

    # --- Surface 2: per-group stance-vs-mapper coherence ---
    complete_stances = {
        group.value: BuiltinGroupStance(status="supported") for group in BuiltinGroup
    }
    fully_mapped = frozenset(BUILTIN_REGISTRY.keys())
    if stance_coverage_issues("self_test", complete_stances, fully_mapped):
        problems.append(
            "self-test: stance_coverage_issues flagged a fully-supported, "
            "fully-mapped synthetic language -- over-triggering."
        )

    some_key = next(iter(BUILTIN_REGISTRY))
    broken_mapped = fully_mapped - {some_key}
    if not stance_coverage_issues("self_test", complete_stances, broken_mapped):
        problems.append(
            f"self-test: stance_coverage_issues did not detect a supported group's "
            f"unmapped builtin ({some_key!r} removed)."
        )

    incomplete_stances = dict(complete_stances)
    del incomplete_stances[next(iter(incomplete_stances))]
    if not stance_coverage_issues("self_test", incomplete_stances, fully_mapped):
        problems.append(
            "self-test: stance_coverage_issues did not detect a missing group stance."
        )

    return problems


# ---------------------------------------------------------------------------
# Commands
# ---------------------------------------------------------------------------


def check_builtin_claims_parity() -> int:
    """Run the real gate over every registered language.

    Returns:
        Exit code (0 = both surfaces hold, 1 = at least one divergence, 2 = fewer than
        `_MIN_LANGUAGES_FOR_COMPARISON` languages registered).
    """
    languages = sorted(registered_language_names())
    if len(languages) < _MIN_LANGUAGES_FOR_COMPARISON:
        logger.error(
            "D2 CANNOT RUN: only %d language(s) registered (%s) -- at least %d are "
            "required.", len(languages), languages, _MIN_LANGUAGES_FOR_COMPARISON,
        )
        return 2

    ok = True

    per_language_keys = {name: stance_key_set(name) for name in languages}
    key_holes = compare_stance_key_sets(per_language_keys)
    for name in languages:
        missing = key_holes[name]
        if missing:
            ok = False
            logger.error(
                "D2 SURFACE 1 VIOLATION: %s's builtin_group_stances is missing key(s) "
                "%s (declared by at least one other registered language).",
                name, sorted(missing),
            )

    for name in languages:
        plugin = get_language_plugin(name)
        stances = plugin.capability.builtin_group_stances
        mapped = mapped_builtin_keys(name)
        issues = stance_coverage_issues(name, stances, mapped)
        if issues:
            ok = False
            for issue in issues:
                logger.error("D2 SURFACE 2 VIOLATION: %s", issue)

    if ok:
        logger.info(
            "D2 holds: stance key sets identical and every 'supported' group is "
            "fully mapped, across %d languages (%s).", len(languages), languages,
        )
        return 0
    return 1


def main() -> int:
    """Entry point.

    Returns:
        Exit code: 0 = D2 holds, 1 = a divergence was found, 2 = the self-test failed
        or fewer than 2 languages are registered.
    """
    parser = argparse.ArgumentParser(
        description=(
            "Prove every registered datrix.languages plugin's builtin_group_stances "
            "are complete and that every 'supported' group is fully mapped (D2)."
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
    logger_.info("Non-vacuity self-test passed (both surfaces).")

    if args.self_test:
        return 0

    return check_builtin_claims_parity()


if __name__ == "__main__":
    sys.exit(main())
