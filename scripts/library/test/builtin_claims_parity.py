"""Cross-language builtin-claims parity gate (D2).

Two independent surfaces, both required:

1. CLAIM-SET IDENTITY. Every registered `datrix.languages` plugin's
   generator declares CLAIMED_BUILTIN_GROUPS -- the authoritative set of
   BuiltinGroup capability clusters that generator implements. Today all
   four hand-typed literals happen to agree; nothing has ever compared them
   to each other. This surface does so, with NO exemption path (a claim-set
   divergence is always a real defect, never a reviewed exception).
2. PER-BUILTIN MAPPED-SET COMPARISON, over the FULL BUILTIN_REGISTRY --
   including `group=None` ("optional everywhere") members, which the
   existing per-package `validate_builtin_coverage` structurally never
   reports (parity_checker.py:191-192,208-211). A builtin mapped by >=1
   language and unmapped by another needs a reviewed entry in
   builtin-mapping-exemptions.json, or the gate fails.

Target set is NEVER hardcoded: languages are enumerated from the installed
`datrix.languages` entry points at run time.
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from collections.abc import Mapping
from pathlib import Path
from typing import Final, cast

# Add library directory to sys.path to import from shared (this file lives at
# library/test/, shared/ lives at the sibling library/shared/).
_LIBRARY_DIR = Path(__file__).resolve().parent.parent
if _LIBRARY_DIR.exists() and str(_LIBRARY_DIR) not in sys.path:
    sys.path.insert(0, str(_LIBRARY_DIR))

from shared.registered_targets import registered_language_names  # noqa: E402

from datrix_codegen_common.transpiler.builtin_registry import BUILTIN_REGISTRY  # noqa: E402
from datrix_codegen_common.transpiler.profile import TranspilerProfile  # noqa: E402
from datrix_common.generation.discovery import get_language_plugin  # noqa: E402

logger = logging.getLogger(__name__)

_HERE = Path(__file__).resolve()
#: This file lives at <datrix>/scripts/library/test/builtin_claims_parity.py --
#: parents[3] is <datrix> (the datrix package root: parents[0]=.../library/test,
#: [1]=.../library, [2]=.../scripts, [3]=<datrix>).
DATRIX_DIR: Path = _HERE.parents[3]
EXEMPTIONS_PATH: Path = DATRIX_DIR / "scripts" / "config" / "builtin-mapping-exemptions.json"

#: A cross-language comparison over 0 or 1 language is vacuous.
_MIN_LANGUAGES_FOR_COMPARISON: Final[int] = 2

#: Synthetic language/group/builtin identifiers used only by the self-test
#: below. Deliberately not real values, so the self-test proves the
#: COMPARATOR's discriminating power without influencing which real
#: languages/builtins get compared.
_SELF_TEST_LANGUAGE_A: Final[str] = "self_test_lang_a"
_SELF_TEST_LANGUAGE_B: Final[str] = "self_test_lang_b"
_SELF_TEST_GROUP_SHARED: Final[str] = "self_test_group_shared"
_SELF_TEST_GROUP_FORCED_GAP: Final[str] = "self_test_group_forced_gap"
_SELF_TEST_BUILTIN_SHARED: Final[tuple[str, str]] = ("SelfTestCategory", "sharedMethod")
_SELF_TEST_BUILTIN_FORCED_GAP: Final[tuple[str, str]] = ("SelfTestCategory", "forcedGapMethod")


def configure_logging(debug: bool = False) -> None:
    """Configure logging output."""
    level = logging.DEBUG if debug else logging.INFO
    logging.basicConfig(level=level, format="%(levelname)s: %(message)s")


# ---------------------------------------------------------------------------
# Surface 1: claim-set identity (no exemption path)
# ---------------------------------------------------------------------------


def claimed_builtin_group_names(language: str) -> frozenset[str]:
    """Return *language*'s declared CLAIMED_BUILTIN_GROUPS, as group-name strings.

    Args:
        language: A `datrix.languages` entry-point name.

    Returns:
        The frozenset of group-name strings (e.g. {"text", "numeric", ...})
        the language's generator claims.
    """
    plugin = get_language_plugin(language)
    return plugin.generator.claimed_builtin_group_names  # type: ignore[attr-defined,no-any-return]


def compare_claim_sets(
    per_language: Mapping[str, frozenset[str]],
) -> dict[str, frozenset[str]]:
    """Compare every language's claim set against the union of all.

    Mirrors `supported_domain_parity.compare_supported_domain_sets` exactly
    -- deliberately: claim-set identity is the SAME shape of "every set
    must equal the union" comparison, just over builtin-capability-group
    names instead of domain ids.

    Args:
        per_language: `{language_name: claimed_group_names}`.

    Returns:
        `{language_name: missing_group_names}` -- empty for every language
        iff every claim set is identical.

    Raises:
        ValueError: If *per_language* has fewer than
            `_MIN_LANGUAGES_FOR_COMPARISON` entries.
    """
    if len(per_language) < _MIN_LANGUAGES_FOR_COMPARISON:
        raise ValueError(
            f"compare_claim_sets requires at least "
            f"{_MIN_LANGUAGES_FOR_COMPARISON} languages, got "
            f"{len(per_language)} ({sorted(per_language)})."
        )
    union: frozenset[str] = frozenset[str]().union(*per_language.values())
    return {name: union - groups for name, groups in per_language.items()}


# ---------------------------------------------------------------------------
# Surface 2: per-builtin mapped-set comparison (exemption path)
# ---------------------------------------------------------------------------


def mapped_builtin_keys(language: str) -> frozenset[tuple[str, str]]:
    """Return the `(category, method)` keys *language*'s profile actually maps.

    This is the mapped SET, not the CLAIMED groups -- a builtin can be
    mapped whether or not its `BUILTIN_REGISTRY` group (if any) is claimed;
    `group=None` builtins ("optional everywhere") are mapped-or-not on
    exactly this same basis, with no group gate at all.

    Args:
        language: A `datrix.languages` entry-point name.

    Returns:
        The frozenset of `(category, method)` keys present in
        `profile.builtins.mapper.mappings`.
    """
    plugin = get_language_plugin(language)
    # `LanguagePlugin.transpiler_profile` is typed `object` at the
    # datrix-common layer (datrix-common cannot import datrix-codegen-common);
    # at runtime every language's plugin assigns a real `TranspilerProfile`
    # (core_factory + language_profile) -- NOT a bare `LanguageProfile`
    # directly, verified by reading all four `language_plugin.py` files.
    transpiler_profile = cast(TranspilerProfile, plugin.transpiler_profile)
    return frozenset(transpiler_profile.language_profile.builtins.mapper.mappings.keys())


def compare_builtin_mapped_sets(
    per_language: Mapping[str, frozenset[tuple[str, str]]],
) -> dict[str, frozenset[tuple[str, str]]]:
    """Compare every language's mapped-builtin set, WITHOUT assuming every
    builtin should eventually be mapped everywhere.

    A `(category, method)` key mapped by ZERO languages is never flagged
    (nothing to compare -- neither language has made a decision the other
    lacks). A key mapped by SOME but not ALL registered languages IS
    flagged for every language that lacks it -- this is D2's literal
    "mapped by >=1 language and unmapped by another" rule, deliberately
    different from `compare_claim_sets`'s pure union-vs-each-set shape.

    Args:
        per_language: `{language_name: mapped_(category,method)_keys}`.

    Returns:
        `{language_name: hole_keys}` -- the `(category, method)` keys at
        least one OTHER language maps that this language does not.

    Raises:
        ValueError: If *per_language* has fewer than
            `_MIN_LANGUAGES_FOR_COMPARISON` entries.
    """
    if len(per_language) < _MIN_LANGUAGES_FOR_COMPARISON:
        raise ValueError(
            f"compare_builtin_mapped_sets requires at least "
            f"{_MIN_LANGUAGES_FOR_COMPARISON} languages, got "
            f"{len(per_language)} ({sorted(per_language)})."
        )
    all_keys: set[tuple[str, str]] = set()
    for keys in per_language.values():
        all_keys |= keys

    holes: dict[str, set[tuple[str, str]]] = {name: set() for name in per_language}
    total_languages = len(per_language)
    for key in all_keys:
        mapped_by = {name for name, keys in per_language.items() if key in keys}
        if 0 < len(mapped_by) < total_languages:
            for name in per_language:
                if name not in mapped_by:
                    holes[name].add(key)
    return {name: frozenset(keys) for name, keys in holes.items()}


# ---------------------------------------------------------------------------
# Exemption file (surface 2 only)
# ---------------------------------------------------------------------------


def load_exemptions() -> tuple[dict[tuple[str, str, str], str], int]:
    """Load and validate `builtin-mapping-exemptions.json`.

    Returns:
        `({(language, category, method): reason}, expected_count)`.

    Raises:
        ValueError: If the file is missing, malformed, an entry has an
            empty reason, or the entry count does not match the pinned
            `expected_count`.
    """
    if not EXEMPTIONS_PATH.exists():
        raise ValueError(
            f"Missing exemption file {EXEMPTIONS_PATH}. It pins the "
            f"catalogued per-builtin mapped-set holes. Restore it from "
            f"git; the gate never creates it."
        )
    data = json.loads(EXEMPTIONS_PATH.read_text(encoding="utf-8"))
    entries = data.get("exemptions")
    expected = data.get("expected_count")
    if not isinstance(entries, list) or not isinstance(expected, int):
        raise ValueError(
            f"Malformed exemption file {EXEMPTIONS_PATH}: expected an "
            f"object with 'expected_count' (int) and 'exemptions' (array "
            f"of {{language, category, method, reason}})."
        )
    exemptions: dict[tuple[str, str, str], str] = {}
    for entry in entries:
        for key in ("language", "category", "method", "reason"):
            if not isinstance(entry.get(key), str) or not entry[key].strip():
                raise ValueError(
                    f"Exemption entry {entry!r} is missing a non-empty {key!r}."
                )
        exemptions[(entry["language"], entry["category"], entry["method"])] = entry["reason"]
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
    """Prove both comparators detect a forced mismatch before any real
    comparison is trusted.

    Returns:
        A list of failure descriptions -- empty means both comparators are sound.
    """
    problems: list[str] = []

    # --- Surface 1: claim-set identity ---
    matching_claims = {
        _SELF_TEST_LANGUAGE_A: frozenset({_SELF_TEST_GROUP_SHARED}),
        _SELF_TEST_LANGUAGE_B: frozenset({_SELF_TEST_GROUP_SHARED}),
    }
    if any(compare_claim_sets(matching_claims).values()):
        problems.append(
            "self-test: compare_claim_sets reported a divergence for a "
            "synthetic MATCHING pair -- over-triggering."
        )
    mismatched_claims = {
        _SELF_TEST_LANGUAGE_A: frozenset({_SELF_TEST_GROUP_SHARED, _SELF_TEST_GROUP_FORCED_GAP}),
        _SELF_TEST_LANGUAGE_B: frozenset({_SELF_TEST_GROUP_SHARED}),
    }
    claim_result = compare_claim_sets(mismatched_claims)
    if _SELF_TEST_GROUP_FORCED_GAP not in claim_result.get(_SELF_TEST_LANGUAGE_B, frozenset()):
        problems.append(
            f"self-test: compare_claim_sets did not detect the forced claim "
            f"mismatch (expected {_SELF_TEST_GROUP_FORCED_GAP!r} missing for "
            f"{_SELF_TEST_LANGUAGE_B!r}, got {claim_result})."
        )
    if claim_result.get(_SELF_TEST_LANGUAGE_A):
        problems.append(
            f"self-test: compare_claim_sets flagged {_SELF_TEST_LANGUAGE_A!r} "
            f"(the language that DECLARED the extra group) as missing "
            f"something -- asymmetric/wrong: {claim_result[_SELF_TEST_LANGUAGE_A]}"
        )

    # --- Surface 2: per-builtin mapped-set comparison ---
    matching_mapped = {
        _SELF_TEST_LANGUAGE_A: frozenset({_SELF_TEST_BUILTIN_SHARED}),
        _SELF_TEST_LANGUAGE_B: frozenset({_SELF_TEST_BUILTIN_SHARED}),
    }
    if any(compare_builtin_mapped_sets(matching_mapped).values()):
        problems.append(
            "self-test: compare_builtin_mapped_sets reported a divergence "
            "for a synthetic MATCHING pair -- over-triggering."
        )
    mismatched_mapped = {
        _SELF_TEST_LANGUAGE_A: frozenset(
            {_SELF_TEST_BUILTIN_SHARED, _SELF_TEST_BUILTIN_FORCED_GAP}
        ),
        _SELF_TEST_LANGUAGE_B: frozenset({_SELF_TEST_BUILTIN_SHARED}),
    }
    mapped_result = compare_builtin_mapped_sets(mismatched_mapped)
    if _SELF_TEST_BUILTIN_FORCED_GAP not in mapped_result.get(_SELF_TEST_LANGUAGE_B, frozenset()):
        problems.append(
            f"self-test: compare_builtin_mapped_sets did not detect the "
            f"forced mapped-set mismatch (expected "
            f"{_SELF_TEST_BUILTIN_FORCED_GAP!r} missing for "
            f"{_SELF_TEST_LANGUAGE_B!r}, got {mapped_result})."
        )
    if mapped_result.get(_SELF_TEST_LANGUAGE_A):
        problems.append(
            f"self-test: compare_builtin_mapped_sets flagged "
            f"{_SELF_TEST_LANGUAGE_A!r} as missing something it itself "
            f"maps -- asymmetric/wrong: {mapped_result[_SELF_TEST_LANGUAGE_A]}"
        )
    # A builtin mapped by NEITHER language must never appear as a hole for
    # either -- proves the "0 < len(mapped_by) < total" guard, not just the
    # "some but not all" case above.
    unmapped_everywhere = {
        _SELF_TEST_LANGUAGE_A: frozenset({_SELF_TEST_BUILTIN_SHARED}),
        _SELF_TEST_LANGUAGE_B: frozenset({_SELF_TEST_BUILTIN_SHARED}),
    }
    never_mapped_key = ("SelfTestCategory", "neverMappedByAnyone")
    if any(
        never_mapped_key in holes
        for holes in compare_builtin_mapped_sets(unmapped_everywhere).values()
    ):
        problems.append(
            "self-test: compare_builtin_mapped_sets flagged a builtin "
            "mapped by NEITHER language -- must never be flagged (nothing "
            "to compare)."
        )

    return problems


# ---------------------------------------------------------------------------
# Commands
# ---------------------------------------------------------------------------


def check_builtin_claims_parity() -> int:
    """Run the real gate over every registered language.

    Returns:
        Exit code (0 = both surfaces hold, 1 = at least one unexempted
        divergence, 2 = fewer than `_MIN_LANGUAGES_FOR_COMPARISON`
        languages registered).
    """
    languages = sorted(registered_language_names())
    if len(languages) < _MIN_LANGUAGES_FOR_COMPARISON:
        logger.error(
            "D2 CANNOT RUN: only %d language(s) registered (%s) -- at "
            "least %d are required.", len(languages), languages,
            _MIN_LANGUAGES_FOR_COMPARISON,
        )
        return 2

    ok = True

    # Surface 1: claim-set identity -- no exemption path.
    per_language_claims = {name: claimed_builtin_group_names(name) for name in languages}
    claim_holes = compare_claim_sets(per_language_claims)
    for name in languages:
        missing = claim_holes[name]
        if missing:
            ok = False
            logger.error(
                "D2 SURFACE 1 VIOLATION: %s's CLAIMED_BUILTIN_GROUPS is "
                "missing %s (claimed by at least one other registered "
                "language). %s.claims=%s",
                name, sorted(missing), name, sorted(per_language_claims[name]),
            )

    # Surface 2: per-builtin mapped-set comparison -- exemption path.
    per_language_mapped = {name: mapped_builtin_keys(name) for name in languages}
    mapped_holes = compare_builtin_mapped_sets(per_language_mapped)
    exemptions, _ = load_exemptions()
    for name in languages:
        for category, method in sorted(mapped_holes[name]):
            if (name, category, method) in exemptions:
                continue
            ok = False
            decl = BUILTIN_REGISTRY.get((category, method))
            group_label = decl.group.value if decl and decl.group else "None (optional everywhere)"
            logger.error(
                "D2 SURFACE 2 VIOLATION: %s does not map %s.%s (registry "
                "group=%s), which at least one other registered language "
                "maps, and no exemption entry covers it. Fix: implement "
                "the mapping, or add a reviewed entry to %s.",
                name, category, method, group_label, EXEMPTIONS_PATH,
            )

    if ok:
        logger.info(
            "D2 holds: claim sets identical across %d languages (%s); "
            "every cross-language mapped-set hole is exempted.",
            len(languages), languages,
        )
        return 0
    return 1


def main() -> int:
    """Entry point.

    Returns:
        Exit code: 0 = D2 holds, 1 = a divergence was found, 2 = the
        self-test failed or fewer than 2 languages are registered.
    """
    parser = argparse.ArgumentParser(
        description=(
            "Prove every registered datrix.languages plugin's "
            "CLAIMED_BUILTIN_GROUPS are identical, and that every "
            "cross-language builtin mapped-set hole (including group=None "
            "members) is reviewed and exempted (D2)."
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
