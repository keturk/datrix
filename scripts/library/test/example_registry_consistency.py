"""Example-universe consistency gate (D9).

The reference-example parity gate's example corpus and test-projects.json's
test-set union are two independently-maintained registries of "the examples
under datrix/examples/" -- and they drift. This gate is the standing proof
they agree: every system.dtrx on disk must appear in >= 1 named test set of
test-projects.json, or carry a reviewed entry in test-set-exclusions.json.

An unregistered example is not a cosmetic gap: generate.ps1 -All and
run-complete.ps1 -All select their corpus FROM test-projects.json's test
sets, so an unregistered example is never built by ANY full-corpus run --
exactly how two whole-example parked defects (config-store,
replayable-ingestion) went unnoticed for a full generation cycle.

Three violation classes, all fail-loud (never silently narrowed to "just
missing" or "just extra"):
  - unregistered: on disk, in no test set, no exclusion entry.
  - stale_exclusions: an exclusion entry names an example no longer on disk
    (a park entry that outlived what it was protecting).
  - redundant_exclusions: an example is BOTH excluded and registered in a
    test set -- a contradictory, unreviewable state.

Built-in non-vacuity self-test, every invocation: proves the pure comparator
(compute_registry_violations) detects each of the three violation classes on
synthetic ids and reports a clean state as clean -- entirely without file
I/O, before any real comparison against the live tree is trusted.

Usage:
    python example_registry_consistency.py
    python example_registry_consistency.py --debug
    python example_registry_consistency.py --self-test
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path

logger = logging.getLogger(__name__)

# This file: datrix/scripts/library/test/example_registry_consistency.py
# parents[3] -> datrix/ ; parents[4] -> the monorepo root (unused here, kept
# for symmetry with the other repo-level gates in this package).
_HERE = Path(__file__).resolve()
DATRIX_DIR: Path = _HERE.parents[3]

EXAMPLES_ROOT: Path = DATRIX_DIR / "examples"
TEST_PROJECTS_PATH: Path = DATRIX_DIR / "scripts" / "config" / "test-projects.json"
EXCLUSIONS_PATH: Path = DATRIX_DIR / "scripts" / "config" / "test-set-exclusions.json"

EXIT_OK = 0
EXIT_FAIL = 1
EXIT_USAGE = 2

_SELF_TEST_KNOWN = "self_test_known_example"
_SELF_TEST_UNREGISTERED = "self_test_unregistered_example"
_SELF_TEST_STALE = "self_test_stale_excluded_example"
_SELF_TEST_REDUNDANT = "self_test_redundant_excluded_example"


# ---------------------------------------------------------------------------
# Disk discovery
# ---------------------------------------------------------------------------


def example_id_from_system_dtrx(system_dtrx: Path) -> str:
    """The SAME dash-joined example id
    `reference_example_parity.example_id()` computes -- both gates must agree
    on identity for the same disk example.

    Args:
        system_dtrx: Absolute path to a `system.dtrx` under `EXAMPLES_ROOT`.

    Returns:
        The example directory's path relative to `EXAMPLES_ROOT`, path
        separators replaced with `-`.
    """
    return "-".join(system_dtrx.parent.relative_to(EXAMPLES_ROOT).parts)


def discover_disk_example_ids() -> set[str]:
    """Every example id with a real `system.dtrx` under `EXAMPLES_ROOT`."""
    return {example_id_from_system_dtrx(p) for p in EXAMPLES_ROOT.rglob("system.dtrx")}


# ---------------------------------------------------------------------------
# test-projects.json
# ---------------------------------------------------------------------------


def _project_path_to_example_id(project_relpath: str) -> str:
    """Convert a `test-projects.json` project path (relative to `DATRIX_DIR`,
    e.g. "examples/02-features/.../system.dtrx") into the same example id
    `example_id_from_system_dtrx` computes for the corresponding disk file.
    """
    system_dtrx = (DATRIX_DIR / project_relpath).resolve()
    return example_id_from_system_dtrx(system_dtrx)


def load_test_projects() -> tuple[dict[str, str], dict[str, list[str]]]:
    """Load `test-projects.json`.

    Returns:
        `(name_to_path, test_sets)` -- `name_to_path` is every registered
        project's `name -> path`; `test_sets` is `testSetName -> [names]`.

    Raises:
        ValueError: If the file is missing or malformed.
    """
    if not TEST_PROJECTS_PATH.exists():
        raise ValueError(f"Missing {TEST_PROJECTS_PATH}. Restore it from git.")
    data = json.loads(TEST_PROJECTS_PATH.read_text(encoding="utf-8"))
    projects = data.get("projects")
    test_sets = data.get("testSets")
    if not isinstance(projects, dict) or not isinstance(test_sets, dict):
        raise ValueError(
            f"Malformed {TEST_PROJECTS_PATH}: expected 'projects' (object of "
            f"groups) and 'testSets' (object of name -> [project names])."
        )
    name_to_path: dict[str, str] = {}
    for group_name, entries in projects.items():
        if not isinstance(entries, list):
            raise ValueError(f"projects.{group_name} is not a list in {TEST_PROJECTS_PATH}.")
        for entry in entries:
            name_to_path[entry["name"]] = entry["path"]
    return name_to_path, {k: list(v) for k, v in test_sets.items()}


def registered_example_ids() -> set[str]:
    """Every example id reachable from >= 1 named test set in `test-projects.json`.

    A project name listed under `"projects"` but referenced by NO `testSets`
    entry does not count as registered -- D9's invariant is "appears in >= 1
    test set", not merely "has a projects entry" (a projects-only entry is
    never actually selected by any `-TestSet`/`-All` run).

    Returns:
        The set of example ids covered by the union of every `testSets` value.

    Raises:
        ValueError: If a `testSets` entry names a project with no `projects` entry.
    """
    name_to_path, test_sets = load_test_projects()
    names_in_some_set: set[str] = set()
    for names in test_sets.values():
        names_in_some_set.update(names)

    ids: set[str] = set()
    for name in sorted(names_in_some_set):
        path = name_to_path.get(name)
        if path is None:
            raise ValueError(
                f"{TEST_PROJECTS_PATH}: testSets reference project name {name!r}, "
                f"which has no entry under 'projects'. Fix the typo or add the "
                f"missing project entry."
            )
        ids.add(_project_path_to_example_id(path))
    return ids


# ---------------------------------------------------------------------------
# Exclusions
# ---------------------------------------------------------------------------


def load_exclusions() -> tuple[dict[str, str], int]:
    """Load and validate `test-set-exclusions.json`.

    Returns:
        `(example_id -> reason, expected_count)`.

    Raises:
        ValueError: If the file is missing, malformed, has an empty reason,
            or its entry count does not match the pinned `expected_count`.
    """
    if not EXCLUSIONS_PATH.exists():
        raise ValueError(
            f"Missing {EXCLUSIONS_PATH}. It pins the examples deliberately excluded "
            f"from every test set, each with a reviewed reason. Restore it from git; "
            f"the gate never creates it."
        )
    data = json.loads(EXCLUSIONS_PATH.read_text(encoding="utf-8"))
    expected = data.get("expected_count")
    exclusions = data.get("exclusions")
    if not isinstance(exclusions, dict) or not isinstance(expected, int):
        raise ValueError(
            f"Malformed {EXCLUSIONS_PATH}: expected an object with 'expected_count' "
            f"(int) and 'exclusions' (object of example_id -> reason)."
        )
    for example_id, reason in exclusions.items():
        if not isinstance(reason, str) or not reason.strip():
            raise ValueError(
                f"Exclusion entry {example_id!r} has an empty reason. Every entry "
                f"must state why the example is permanently excluded."
            )
    if len(exclusions) != expected:
        raise ValueError(
            f"{EXCLUSIONS_PATH} has {len(exclusions)} entries but 'expected_count' "
            f"is pinned at {expected}. Update the count in the same change that "
            f"adds or removes an entry."
        )
    return {str(k): str(v) for k, v in exclusions.items()}, expected


# ---------------------------------------------------------------------------
# Pure comparator (self-tested without any file I/O)
# ---------------------------------------------------------------------------


def compute_registry_violations(
    disk_ids: set[str], registered_ids: set[str], exclusions: dict[str, str]
) -> dict[str, list[str]]:
    """Pure comparison -- no file I/O -- so the self-test can exercise it
    directly against synthetic ids.

    Args:
        disk_ids: Every example id with a real `system.dtrx` on disk.
        registered_ids: Every example id reachable from >= 1 test set.
        exclusions: `example_id -> reason` from `test-set-exclusions.json`.

    Returns:
        `{"unregistered": [...], "stale_exclusions": [...],
        "redundant_exclusions": [...]}`, each sorted; every list empty iff
        the registry is fully consistent.
    """
    excluded_ids = set(exclusions)
    return {
        "unregistered": sorted(disk_ids - registered_ids - excluded_ids),
        "stale_exclusions": sorted(excluded_ids - disk_ids),
        "redundant_exclusions": sorted(excluded_ids & registered_ids),
    }


def run_self_test() -> list[str]:
    """Prove `compute_registry_violations` detects each violation class and
    reports a clean state as clean -- entirely with synthetic ids.

    Returns:
        Problem descriptions; empty means the comparator is sound.
    """
    problems: list[str] = []

    clean = compute_registry_violations(
        disk_ids={_SELF_TEST_KNOWN}, registered_ids={_SELF_TEST_KNOWN}, exclusions={}
    )
    if any(clean.values()):
        problems.append(f"self-test: clean state reported violations: {clean}")

    unregistered = compute_registry_violations(
        disk_ids={_SELF_TEST_KNOWN, _SELF_TEST_UNREGISTERED},
        registered_ids={_SELF_TEST_KNOWN},
        exclusions={},
    )
    if unregistered["unregistered"] != [_SELF_TEST_UNREGISTERED]:
        problems.append(f"self-test: unregistered example not detected: {unregistered}")

    excluded_clean = compute_registry_violations(
        disk_ids={_SELF_TEST_KNOWN, _SELF_TEST_UNREGISTERED},
        registered_ids={_SELF_TEST_KNOWN},
        exclusions={_SELF_TEST_UNREGISTERED: "reviewed reason"},
    )
    if excluded_clean["unregistered"]:
        problems.append(
            f"self-test: a reviewed exclusion should silence the unregistered "
            f"finding: {excluded_clean}"
        )

    stale = compute_registry_violations(
        disk_ids={_SELF_TEST_KNOWN},
        registered_ids={_SELF_TEST_KNOWN},
        exclusions={_SELF_TEST_STALE: "reason"},
    )
    if stale["stale_exclusions"] != [_SELF_TEST_STALE]:
        problems.append(f"self-test: stale exclusion not detected: {stale}")

    redundant = compute_registry_violations(
        disk_ids={_SELF_TEST_KNOWN, _SELF_TEST_REDUNDANT},
        registered_ids={_SELF_TEST_KNOWN, _SELF_TEST_REDUNDANT},
        exclusions={_SELF_TEST_REDUNDANT: "reason"},
    )
    if redundant["redundant_exclusions"] != [_SELF_TEST_REDUNDANT]:
        problems.append(f"self-test: redundant exclusion not detected: {redundant}")

    return problems


# ---------------------------------------------------------------------------
# Commands
# ---------------------------------------------------------------------------


def check_example_registry_consistency() -> int:
    """Run the gate against the real tree.

    Returns:
        Exit code (0 = fully consistent, 1 = at least one violation,
        2 = zero examples discovered on disk -- a vacuous check).
    """
    disk_ids = discover_disk_example_ids()
    if not disk_ids:
        logger.error(
            "EXAMPLE-REGISTRY GATE CANNOT RUN: zero system.dtrx found under %s -- "
            "an empty corpus would make this check vacuously pass.",
            EXAMPLES_ROOT,
        )
        return EXIT_USAGE

    registered_ids = registered_example_ids()
    exclusions, expected_count = load_exclusions()
    violations = compute_registry_violations(disk_ids, registered_ids, exclusions)

    ok = True
    for example_id in violations["unregistered"]:
        ok = False
        logger.error(
            "UNREGISTERED EXAMPLE example=%s -- appears in no testSets entry of "
            "%s and has no test-set-exclusions.json entry. Register it into an "
            "existing test set, or add a reviewed exclusion.",
            example_id, TEST_PROJECTS_PATH.name,
        )
    for example_id in violations["stale_exclusions"]:
        ok = False
        logger.error(
            "STALE EXCLUSION example=%s -- test-set-exclusions.json names an "
            "example with no system.dtrx on disk. Remove the entry and "
            "decrement expected_count.",
            example_id,
        )
    for example_id in violations["redundant_exclusions"]:
        ok = False
        logger.error(
            "REDUNDANT EXCLUSION example=%s -- both excluded AND registered in "
            ">= 1 test set. Remove the exclusion entry and decrement "
            "expected_count.",
            example_id,
        )

    if ok:
        logger.info(
            "EXAMPLE-REGISTRY GATE PASSED: %d example(s) on disk, %d registered, "
            "%d reviewed exclusion(s).",
            len(disk_ids), len(registered_ids), expected_count,
        )
        return EXIT_OK
    return EXIT_FAIL


def _parse_args(argv: list[str]) -> argparse.Namespace:
    """Parse CLI arguments."""
    parser = argparse.ArgumentParser(
        description=(
            "Example-universe consistency gate (D9): every system.dtrx under "
            "datrix/examples/ must appear in >= 1 test-projects.json test set, "
            "or carry a reviewed test-set-exclusions.json entry."
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
        Process exit code: 0 = consistent (or a successful `--self-test`),
        1 = at least one violation, 2 = self-test failure, zero disk
        examples, or a malformed config file.
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
        return check_example_registry_consistency()
    except ValueError as exc:
        logger.error("ERROR: %s", exc)
        return EXIT_USAGE


if __name__ == "__main__":
    sys.exit(main())
