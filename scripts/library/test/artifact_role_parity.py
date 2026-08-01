"""Cross-language artifact-role parity gate (D7): the G-A closure.

Detects a language silently emitting nothing for a construct another
language realizes, WITHOUT GENERATING ANYTHING -- it reads the blessed
baseline manifests that reference-example-parity-gate.ps1 already writes
under datrix/scripts/config/parity-baselines/<example_id>/<language>.sha256.

For every example with >= 2 blessed language baselines:
  1. Load each blessed language's manifest (a path list, ignoring hashes).
  2. Classify each path by domain ROLE using that language's OWN derived
     DomainDeclaration.structural_pattern set (derive_domain_declarations
     over the plugin's own registered specs -- the same fnmatch globs the
     domain self-consistency gate uses). A path matching no pattern goes to
     an "unclassified" bucket, reported but never compared (template-level
     naming differs by design across languages; the ROLE set is the
     contract, not the literal path shape).
  3. The set of roles with >= 1 matching path must be IDENTICAL across the
     example's blessed languages. A difference must carry an entry in
     artifact-role-exemptions.json (coordinates + reason, pinned count).

Relationship to the byte gate: replaces nothing. reference-example-parity-gate.ps1
still pins CONTENT per (example, language) pair; this gate pins PRESENCE
across languages. Its coverage grows automatically as later phases bless
more of the (example, language) matrix -- no code change needed here when
that happens.

Built-in non-vacuity self-test, every invocation: proves compare_role_sets
detects a forced mismatch and does not false-positive a matching pair, and
proves classify_paths correctly buckets a synthetic manifest against
synthetic declarations (including the unclassified bucket). Refuses to pass
vacuously: zero examples with >= 2 blessed languages is exit 2, never a
silent 0-example pass.

Usage:
    python artifact_role_parity.py
    python artifact_role_parity.py --debug
    python artifact_role_parity.py --self-test
"""

from __future__ import annotations

import argparse
import fnmatch
import json
import logging
import sys
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Final, cast

from datrix_codegen_common.parity.derived_declarations import DerivationError
from datrix_codegen_common.parity.domain_declaration import (
    DomainDeclaration,
    DomainDeclarations,
)

# Add scripts/library to sys.path to import shared.registered_targets --
# mirrors reference_example_parity.py's own shim (this file lives at
# library/test/, shared/ lives at the sibling library/shared/).
_LIBRARY_DIR = Path(__file__).resolve().parent.parent
if _LIBRARY_DIR.exists() and str(_LIBRARY_DIR) not in sys.path:
    sys.path.insert(0, str(_LIBRARY_DIR))

from shared.registered_targets import registered_language_names  # noqa: E402

logger = logging.getLogger(__name__)

# This file: datrix/scripts/library/test/artifact_role_parity.py
# parents[3] -> datrix/ ; parents[4] -> the monorepo root. Mirrors
# reference_example_parity.py's own identical-depth path math.
_HERE = Path(__file__).resolve()
DATRIX_DIR: Path = _HERE.parents[3]

BASELINES_ROOT: Path = DATRIX_DIR / "scripts" / "config" / "parity-baselines"
EXEMPTIONS_PATH: Path = DATRIX_DIR / "scripts" / "config" / "artifact-role-exemptions.json"

_MIN_LANGUAGES_FOR_COMPARISON: Final[int] = 2
_MANIFEST_SEP = "  "  # matches reference_example_parity.py's _SEP

EXIT_OK = 0
EXIT_FAIL = 1
EXIT_USAGE = 2

_SELF_TEST_LANGUAGE_A: Final[str] = "self_test_lang_a"
_SELF_TEST_LANGUAGE_B: Final[str] = "self_test_lang_b"
_SELF_TEST_DOMAIN_SHARED: Final[str] = "self_test_order"
_SELF_TEST_DOMAIN_FORCED_GAP: Final[str] = "self_test_shipment"


@dataclass(frozen=True)
class ExemptionEntry:
    """One reviewed hole in artifact-role-exemptions.json."""

    example: str
    domain: str
    language: str
    reason: str


# ---------------------------------------------------------------------------
# Baseline discovery + manifest reading
# ---------------------------------------------------------------------------


def blessed_language_baselines(example_id: str) -> dict[str, Path]:
    """Return {language: baseline_path} for every REGISTERED language that has
    a blessed .sha256 manifest for *example_id*.

    Args:
        example_id: An example id as used by parity-baselines/ directory names
            (kebab-joined path segments, e.g. "01-foundation").

    Returns:
        Mapping of registered language name -> its baseline file, for
        languages that actually have one blessed. Never raises for a missing
        manifest -- an unblessed language for this example is simply absent.
    """
    example_dir = BASELINES_ROOT / example_id
    if not example_dir.is_dir():
        return {}
    found: dict[str, Path] = {}
    for language in sorted(registered_language_names()):
        candidate = example_dir / f"{language}.sha256"
        if candidate.is_file():
            found[language] = candidate
    return found


def discover_multi_language_examples() -> dict[str, dict[str, Path]]:
    """Every example id under BASELINES_ROOT with >= 2 blessed language baselines.

    Returns:
        {example_id: {language: baseline_path}}, only for examples meeting
        the >= 2 threshold. Sorted by example id for deterministic output.
    """
    result: dict[str, dict[str, Path]] = {}
    if not BASELINES_ROOT.is_dir():
        return result
    for example_dir in sorted(p for p in BASELINES_ROOT.iterdir() if p.is_dir()):
        languages = blessed_language_baselines(example_dir.name)
        if len(languages) >= _MIN_LANGUAGES_FOR_COMPARISON:
            result[example_dir.name] = languages
    return result


def manifest_paths(baseline_path: Path) -> list[str]:
    """The relative-path column of one blessed .sha256 manifest (hashes ignored).

    Args:
        baseline_path: A `<example_id>/<language>.sha256` file.

    Returns:
        Every path recorded in the manifest, in file order.

    Raises:
        ValueError: On a malformed line (not "path<2sp>sha256hex").
    """
    paths: list[str] = []
    for raw in baseline_path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line:
            continue
        parts = line.split(_MANIFEST_SEP, 1)
        if len(parts) != 2:
            raise ValueError(
                f"Malformed manifest line in {baseline_path} (expected "
                f"'path{_MANIFEST_SEP}sha256hex'): {line!r}"
            )
        paths.append(parts[0])
    return paths


# ---------------------------------------------------------------------------
# Role classification
# ---------------------------------------------------------------------------


def language_domain_declarations(language: str) -> DomainDeclarations:
    """Fresh, derived DomainDeclarations for *language*.

    Computed independently of whatever mechanism the plugin's OWN
    `.domain_declarations` attribute currently uses in production -- calling
    `derive_domain_declarations` directly guarantees one consistent
    structural-pattern basis across all four languages for this gate, rather
    than trusting each package's own wiring to already route through it.

    Args:
        language: A registered `datrix.languages` entry-point name.

    Returns:
        `domain_id -> DomainDeclaration`, derived fresh from the plugin's
        registered sub-generator specs.
    """
    from datrix_codegen_common.parity.derived_declarations import (
        derive_domain_declarations,
    )
    from datrix_codegen_common.testkit.gates.domain_self_consistency import (
        DomainDeclaringPlugin,
    )
    from datrix_common.generation.discovery import get_language_plugin

    plugin = cast(DomainDeclaringPlugin, get_language_plugin(language))
    specs = plugin.generator.get_sub_generators()
    return derive_domain_declarations(
        specs,
        unsupported_reason=lambda domain_id: (
            f"{language} registers no sub-generator for domain {domain_id!r} "
            f"(artifact-role-parity gate probe -- not a committed exemption reason)."
        ),
    )


#: Package-init marker basenames: language package-structure boilerplate
#: (e.g. Python's `__init__.py`, created wherever a package directory exists
#: for ANY reason) rather than domain-specific generated content. A trailing
#: `*.py`-shaped structural_pattern trivially matches this marker for every
#: domain whose files happen to share that directory, manufacturing a false
#: "domain present" signal with no bearing on what the DSL actually declared.
#: Excluded from classification entirely (routed to "unclassified") rather
#: than credited to any domain.
_PACKAGE_MARKER_BASENAMES: Final[frozenset[str]] = frozenset({"__init__.py"})


def _pattern_specificity(pattern: str) -> int:
    """Number of '/'-separated segments in a structural_pattern glob.

    `fnmatch.fnmatch`'s `*` spans `/` (by design -- the leading `*/` absorbs
    a variable-depth service-directory prefix). A side effect: when one
    domain's pattern is a strict directory-shallower generalization of a
    sibling domain's pattern (e.g. struct's `*/src/*/schemas/*.py` vs
    schema's `*/src/*/schemas/*/*.py`), the shallower pattern also matches
    files that structurally belong to the deeper, more specific sibling.
    Segment count is the tie-break: the pattern requiring more path segments
    is the more specific match for a path both patterns accept.
    """
    return pattern.count("/")


def classify_paths(
    paths: list[str], declarations: Mapping[str, DomainDeclaration]
) -> tuple[frozenset[str], list[str]]:
    """Classify each manifest path by domain role via fnmatch against every
    SUPPORTED declaration's structural_pattern -- the same glob shape
    `domain_self_consistency._pattern_mismatch_violations` uses.

    When a path matches more than one domain's pattern, only the most
    SPECIFIC match (see `_pattern_specificity`) is credited -- this is a
    property of this gate's own aggregation, not a different fnmatch rule:
    each candidate is still tested with the exact same `fnmatch.fnmatch`
    call domain_self_consistency uses. A package-init marker basename (see
    `_PACKAGE_MARKER_BASENAMES`) is routed to `unclassified` before any
    pattern is even tried -- it is package-structure boilerplate, never
    domain-specific content.

    Args:
        paths: Relative paths from one blessed manifest.
        declarations: `domain_id -> DomainDeclaration`.

    Returns:
        `(role_set, unclassified_paths)`. `role_set` is every domain id with
        >= 1 matching path (after the most-specific tie-break).
        `unclassified_paths` is reported by the caller but never compared --
        template-level naming legitimately differs by language; the role set
        is the contract, not the literal path shape.
    """
    supported: list[tuple[str, str]] = [
        (domain_id, decl.structural_pattern)
        for domain_id, decl in declarations.items()
        if decl.status == "supported" and decl.structural_pattern is not None
    ]
    roles: set[str] = set()
    unclassified: list[str] = []
    for path in paths:
        if PurePosixPath(path).name in _PACKAGE_MARKER_BASENAMES:
            unclassified.append(path)
            continue
        matches = [
            (domain_id, pattern)
            for domain_id, pattern in supported
            if fnmatch.fnmatch(path, pattern)
        ]
        if not matches:
            unclassified.append(path)
            continue
        most_specific = max(_pattern_specificity(pattern) for _, pattern in matches)
        for domain_id, pattern in matches:
            if _pattern_specificity(pattern) == most_specific:
                roles.add(domain_id)
    return frozenset(roles), unclassified


def compare_role_sets(
    per_language: Mapping[str, frozenset[str]],
) -> dict[str, frozenset[str]]:
    """Compare every language's role set against the union of all, for one example.

    Mirrors `supported_domain_parity.compare_supported_domain_sets` exactly
    (same union-minus-own shape) -- reuse that reasoning rather than
    reinventing a comparison rule.

    Args:
        per_language: {language: role_set} for one example's blessed languages.

    Returns:
        {language: missing_role_ids} -- empty per language iff every
        language's role set is identical (D7's POSITIVE acceptance property
        for that example).

    Raises:
        ValueError: If *per_language* has fewer than
            `_MIN_LANGUAGES_FOR_COMPARISON` entries.
    """
    if len(per_language) < _MIN_LANGUAGES_FOR_COMPARISON:
        raise ValueError(
            f"compare_role_sets requires at least {_MIN_LANGUAGES_FOR_COMPARISON} "
            f"languages to compare, got {len(per_language)} ({sorted(per_language)})."
        )
    union_ids: frozenset[str] = frozenset[str]().union(*per_language.values())
    return {name: union_ids - ids for name, ids in per_language.items()}


# ---------------------------------------------------------------------------
# Exemptions
# ---------------------------------------------------------------------------


def load_exemptions() -> tuple[list[ExemptionEntry], int]:
    """Load and validate artifact-role-exemptions.json.

    Returns:
        `(entries, expected_count)`.

    Raises:
        ValueError: If the file is missing, malformed, has an empty field on
            any entry, or its entry count does not match the pinned
            `expected_count`.
    """
    if not EXEMPTIONS_PATH.exists():
        raise ValueError(
            f"Missing exemption file {EXEMPTIONS_PATH}. Restore it from git; "
            f"the gate never creates it."
        )
    data = json.loads(EXEMPTIONS_PATH.read_text(encoding="utf-8"))
    expected = data.get("expected_count")
    raw_entries = data.get("exemptions")
    if not isinstance(raw_entries, list) or not isinstance(expected, int):
        raise ValueError(
            f"Malformed {EXEMPTIONS_PATH}: expected an object with "
            f"'expected_count' (int) and 'exemptions' (array of "
            f"{{example, domain, language, reason}})."
        )
    entries: list[ExemptionEntry] = []
    for i, raw in enumerate(raw_entries):
        if not isinstance(raw, dict):
            raise ValueError(f"exemptions[{i}] is not an object: {raw!r}")
        example = raw.get("example")
        domain = raw.get("domain")
        language = raw.get("language")
        reason = raw.get("reason")
        if (
            not isinstance(example, str) or not example.strip()
            or not isinstance(domain, str) or not domain.strip()
            or not isinstance(language, str) or not language.strip()
            or not isinstance(reason, str) or not reason.strip()
        ):
            raise ValueError(
                f"exemptions[{i}] must have non-empty string 'example', 'domain', "
                f"'language', and 'reason' fields; got {raw!r}."
            )
        entries.append(ExemptionEntry(example, domain, language, reason))
    if len(entries) != expected:
        raise ValueError(
            f"{EXEMPTIONS_PATH} has {len(entries)} entries but 'expected_count' is "
            f"pinned at {expected}. Update the count in the same change that adds "
            f"or removes an entry."
        )
    return entries, expected


def _is_exempt(
    exemptions: list[ExemptionEntry], example: str, domain: str, language: str
) -> bool:
    """Whether (example, domain, language) has a reviewed exemption entry."""
    return any(
        e.example == example and e.domain == domain and e.language == language
        for e in exemptions
    )


# ---------------------------------------------------------------------------
# Non-vacuity self-test
# ---------------------------------------------------------------------------


def run_self_test() -> list[str]:
    """Prove the comparator and classifier are non-vacuous before any real
    comparison is trusted.

    Returns:
        Problem descriptions; empty means the gate is sound.
    """
    problems: list[str] = []

    matching = {
        _SELF_TEST_LANGUAGE_A: frozenset({_SELF_TEST_DOMAIN_SHARED}),
        _SELF_TEST_LANGUAGE_B: frozenset({_SELF_TEST_DOMAIN_SHARED}),
    }
    matching_result = compare_role_sets(matching)
    if any(matching_result.values()):
        problems.append(
            f"self-test: compare_role_sets reported a divergence for a synthetic "
            f"MATCHING pair: {matching_result}"
        )

    mismatched = {
        _SELF_TEST_LANGUAGE_A: frozenset({_SELF_TEST_DOMAIN_SHARED, _SELF_TEST_DOMAIN_FORCED_GAP}),
        _SELF_TEST_LANGUAGE_B: frozenset({_SELF_TEST_DOMAIN_SHARED}),
    }
    mismatched_result = compare_role_sets(mismatched)
    if _SELF_TEST_DOMAIN_FORCED_GAP not in mismatched_result.get(_SELF_TEST_LANGUAGE_B, frozenset()):
        problems.append(
            f"self-test: compare_role_sets did not detect the forced mismatch: "
            f"{mismatched_result}"
        )
    if mismatched_result.get(_SELF_TEST_LANGUAGE_A):
        problems.append(
            f"self-test: compare_role_sets reported {_SELF_TEST_LANGUAGE_A!r} as "
            f"missing domains it actually declares: {mismatched_result}"
        )

    declarations: DomainDeclarations = {
        _SELF_TEST_DOMAIN_SHARED: DomainDeclaration(
            domain_id=_SELF_TEST_DOMAIN_SHARED,
            status="supported",
            structural_pattern="*/orders/*.txt",
        ),
    }
    roles, unclassified = classify_paths(
        ["svc/orders/order.txt", "svc/unrelated/readme.md"], declarations
    )
    if roles != frozenset({_SELF_TEST_DOMAIN_SHARED}):
        problems.append(f"self-test: classify_paths role mismatch: {roles}")
    if unclassified != ["svc/unrelated/readme.md"]:
        problems.append(f"self-test: classify_paths unclassified mismatch: {unclassified}")

    # Package-init marker exclusion: __init__.py sitting in a domain's own
    # matching directory is package-structure boilerplate, never credited,
    # even though its bare name would otherwise satisfy a trailing `*` glob.
    marker_declarations: DomainDeclarations = {
        _SELF_TEST_DOMAIN_SHARED: DomainDeclaration(
            domain_id=_SELF_TEST_DOMAIN_SHARED,
            status="supported",
            structural_pattern="*/orders/*.py",
        ),
    }
    marker_roles, marker_unclassified = classify_paths(
        ["svc/orders/__init__.py"], marker_declarations
    )
    if marker_roles != frozenset():
        problems.append(
            f"self-test: classify_paths credited a package-init marker to a "
            f"domain: {marker_roles}"
        )
    if marker_unclassified != ["svc/orders/__init__.py"]:
        problems.append(
            f"self-test: classify_paths did not route the package-init marker to "
            f"unclassified: {marker_unclassified}"
        )

    # Most-specific-wins tie-break: a shallow pattern that also matches a
    # sibling's deeper, more specific path must NOT be credited for that path.
    _SELF_TEST_DOMAIN_SHALLOW = "self_test_order_shallow"
    _SELF_TEST_DOMAIN_DEEP = "self_test_order_deep"
    overlap_declarations: DomainDeclarations = {
        _SELF_TEST_DOMAIN_SHALLOW: DomainDeclaration(
            domain_id=_SELF_TEST_DOMAIN_SHALLOW,
            status="supported",
            structural_pattern="*/orders/*.txt",
        ),
        _SELF_TEST_DOMAIN_DEEP: DomainDeclaration(
            domain_id=_SELF_TEST_DOMAIN_DEEP,
            status="supported",
            structural_pattern="*/orders/*/*.txt",
        ),
    }
    overlap_roles, _ = classify_paths(
        ["svc/orders/archive/order.txt", "svc/orders/order.txt"], overlap_declarations
    )
    if overlap_roles != frozenset({_SELF_TEST_DOMAIN_SHALLOW, _SELF_TEST_DOMAIN_DEEP}):
        problems.append(
            f"self-test: classify_paths most-specific tie-break failed: expected both "
            f"domains credited (one per path, at its own most-specific match), got "
            f"{overlap_roles}"
        )

    try:
        compare_role_sets({_SELF_TEST_LANGUAGE_A: frozenset()})
        problems.append("self-test: compare_role_sets accepted a single-language mapping")
    except ValueError:
        pass

    return problems


# ---------------------------------------------------------------------------
# Commands
# ---------------------------------------------------------------------------


def check_artifact_role_parity() -> int:
    """Run the gate over every example with >= 2 blessed language baselines.

    Returns:
        Exit code (0 = every example's role sets agree modulo exemptions,
        1 = an un-exempted divergence was found, 2 = zero examples have
        >= 2 blessed language baselines -- a vacuous comparison).
    """
    multi_language_examples = discover_multi_language_examples()
    if not multi_language_examples:
        logger.error(
            "ARTIFACT-ROLE GATE CANNOT RUN: no example has >= 2 blessed language "
            "baselines under %s -- a cross-language comparison over < 2 languages "
            "is vacuous.",
            BASELINES_ROOT,
        )
        return EXIT_USAGE

    exemptions, expected_count = load_exemptions()
    logger.info(
        "artifact_role_parity_start examples=%d exemptions=%d",
        len(multi_language_examples), expected_count,
    )

    ok = True
    for example_id, language_baselines in multi_language_examples.items():
        per_language_roles: dict[str, frozenset[str]] = {}
        for language, baseline_path in sorted(language_baselines.items()):
            declarations = language_domain_declarations(language)
            paths = manifest_paths(baseline_path)
            roles, unclassified = classify_paths(paths, declarations)
            per_language_roles[language] = roles
            if unclassified:
                logger.info(
                    "artifact_role_unclassified example=%s language=%s count=%d "
                    "(reported, not compared): %s",
                    example_id, language, len(unclassified), unclassified[:5],
                )
        missing_by_language = compare_role_sets(per_language_roles)
        example_clean = True
        for language, missing in sorted(missing_by_language.items()):
            for domain_id in sorted(missing):
                if _is_exempt(exemptions, example_id, domain_id, language):
                    continue
                ok = False
                example_clean = False
                logger.error(
                    "ARTIFACT-ROLE DRIFT example=%s language=%s missing_domain=%s "
                    "(present in >= 1 other blessed language for this example; "
                    "%s's blessed manifest matches no file to this domain's "
                    "structural_pattern)",
                    example_id, language, domain_id, language,
                )
        if example_clean:
            logger.info(
                "artifact_role_example_clean example=%s languages=%s",
                example_id, sorted(language_baselines),
            )

    if ok:
        logger.info(
            "ARTIFACT-ROLE GATE PASSED: %d example(s) with >= 2 blessed languages, "
            "role sets identical modulo %d reviewed exemption(s).",
            len(multi_language_examples), expected_count,
        )
        return EXIT_OK
    return EXIT_FAIL


def _parse_args(argv: list[str]) -> argparse.Namespace:
    """Parse CLI arguments."""
    parser = argparse.ArgumentParser(
        description=(
            "Cross-language artifact-role parity gate (D7): for every example "
            "with >= 2 blessed language baselines, the set of domain roles with "
            ">= 1 matching file must be identical across languages. Reads blessed "
            "manifests only -- generates nothing."
        ),
    )
    parser.add_argument("--debug", action="store_true", help="Enable DEBUG logging")
    parser.add_argument(
        "--self-test",
        action="store_true",
        help="Run only the non-vacuity self-test and skip the real comparison",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    """Entry point.

    Returns:
        Process exit code: 0 = gate passed (or a successful `--self-test`),
        1 = an un-exempted role drift was found, 2 = self-test failure, zero
        comparable examples, a malformed exemption file, or an underivable
        domain declaration.
    """
    args = _parse_args(argv if argv is not None else sys.argv[1:])
    logging.basicConfig(
        level=logging.DEBUG if args.debug else logging.INFO,
        format="%(levelname)s: %(message)s",
    )

    problems = run_self_test()
    if problems:
        logger.error("NON-VACUITY SELF-TEST FAILED -- aborting before any real comparison:")
        for problem in problems:
            logger.error("  %s", problem)
        return EXIT_USAGE
    logger.info("non-vacuity self-test: PASS")

    if args.self_test:
        return EXIT_OK

    try:
        return check_artifact_role_parity()
    except (ValueError, DerivationError) as exc:
        logger.error("ERROR: %s", exc)
        return EXIT_USAGE


if __name__ == "__main__":
    sys.exit(main())
