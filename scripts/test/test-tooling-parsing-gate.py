#!/usr/bin/env python3
"""Repo-level gate absorbing 2 orphaned pytest files from `scripts/library/test/tests/`.

`datrix/scripts/library/test/tests/` held pytest files that no runner ever executed (the
`datrix` showcase repo hosts no test suite of any kind -- see CLAUDE.md "Datrix Showcase Repo
Boundaries"). This gate absorbs the valuable, non-vacuous coverage from 2 of those 4 files as a
plain-Python check harness (the other 2 -- test_check_generated_file_ratchet.py,
test_check_docs_conformance.py -- are owned by a separate conversion effort) and re-expresses
each file's distinct behavioral classes as named ``_check_*`` functions:

  - test_compare_tests.py     -> test/compare_tests.py (find_runs, build_service_comparisons,
    parse_unit_run: direct-child-only run discovery, service change classification, the
    flat-log fallback parser, and unit/deploy population separation)
  - test_status_tests_index.py -> test/status_tests.py (TestResult, _format_result_row,
    _read_index_json, find_latest_log_file, parse_pytest_summary, parse_timestamp_from_log_file)

Repo-level validation script, not a pytest suite (per the datrix showcase boundary). Uses only
``assert`` + a small harness that catches ``AssertionError`` per check and prints [OK]/[FAIL] --
no pytest, no mocks/fakes, real ``tempfile.TemporaryDirectory()`` fixtures for every filesystem
case.

Exit codes: 0 = every check passed, 1 = at least one check (or the harness self-test) failed.
"""

from __future__ import annotations

import argparse
import json
import sys
import tempfile
from collections.abc import Callable
from pathlib import Path

_SCRIPT_DIR = Path(__file__).resolve().parent
_LIBRARY_DIR = _SCRIPT_DIR.parent / "library"
if str(_LIBRARY_DIR) not in sys.path:
    sys.path.insert(0, str(_LIBRARY_DIR))

from test.compare_tests import (  # noqa: E402
    build_service_comparisons,
    find_runs,
    parse_unit_run,
)
from test.status_tests import (  # noqa: E402
    TestResult,
    _format_result_row,
    _read_index_json,
    find_latest_log_file,
    parse_pytest_summary,
    parse_timestamp_from_log_file,
)

_GREEN = "\033[92m"
_RED = "\033[91m"
_CYAN = "\033[96m"
_RESET = "\033[0m"


def _ok(msg: str) -> None:
    print(f"{_GREEN}[OK]{_RESET} {msg}")


def _fail(msg: str) -> None:
    print(f"{_RED}[FAIL]{_RESET} {msg}")


def _step(msg: str) -> None:
    print(f"\n{_CYAN}=== {msg}{_RESET}")


# ---------------------------------------------------------------------------
# test/compare_tests.py -- find_runs, build_service_comparisons, parse_unit_run
# ---------------------------------------------------------------------------


def _write_junit(
    run_dir: Path,
    service: str,
    *,
    tests: int,
    failures: int = 0,
    errors: int = 0,
    skipped: int = 0,
) -> None:
    service_dir = run_dir / "services" / service
    service_dir.mkdir(parents=True)
    (service_dir / "junit.xml").write_text(
        (
            '<?xml version="1.0" encoding="utf-8"?>'
            "<testsuites>"
            f'<testsuite name="pytest" tests="{tests}" failures="{failures}" '
            f'errors="{errors}" skipped="{skipped}">'
            "</testsuite>"
            "</testsuites>"
        ),
        encoding="utf-8",
    )


def _check_find_runs_compares_direct_child_unit_runs_only() -> None:
    with tempfile.TemporaryDirectory(prefix="tooling-gate-findruns-") as tmp:
        root = Path(tmp) / ".test_results"
        first = root / "unit-tests-20260511-100000"
        second = root / "unit-tests-20260511-110000"
        nested = root / "archive" / "unit-tests-20260511-120000"

        _write_junit(first, "orders_service", tests=10)
        _write_junit(second, "orders_service", tests=10, failures=2)
        _write_junit(nested, "orders_service", tests=10, failures=9)

        unit_runs = find_runs(root, "unit")
        comparisons = build_service_comparisons(unit_runs)

        run_names = [run.folder.name for run in unit_runs]
        assert run_names == [
            "unit-tests-20260511-100000",
            "unit-tests-20260511-110000",
        ], f"nested/archived run dirs must be excluded from direct-child discovery, got {run_names}"
        assert len(comparisons) == 1
        assert comparisons[0].service == "orders_service"
        assert comparisons[0].change == "REGRESSED"
        assert comparisons[0].history == ["OK", "FAIL"]


def _check_unit_summary_log_fallback_parses_service_rows() -> None:
    with tempfile.TemporaryDirectory(prefix="tooling-gate-summaryfallback-") as tmp:
        run_dir = Path(tmp) / ".test_results" / "unit-tests-20260511-100000"
        run_dir.mkdir(parents=True)
        (run_dir / "unit-tests-summary.log").write_text(
            "\n".join(
                [
                    "Project: D:\\example",
                    "Testing: passed_service",
                    "  Running unit tests...",
                    "  PASSED: 3 tests (1 skipped)",
                    "Testing: failed_service",
                    "  Running unit tests...",
                    "ERROR:   FAILED: 7 passed, 2 failed",
                    "Testing: error_service",
                    "ERROR:   COLLECTION ERRORS: 4 collection errors",
                ]
            ),
            encoding="utf-8",
        )

        run = parse_unit_run(run_dir, find_runs(run_dir.parent, "unit")[0].timestamp)

        assert run.services["passed_service"].status == "PASSED"
        assert run.services["passed_service"].counts.passed == 3
        assert run.services["passed_service"].counts.skipped == 1
        assert run.services["failed_service"].status == "FAILED"
        assert run.services["failed_service"].counts.failed == 2
        assert run.services["error_service"].counts.errors == 4


def _check_deploy_runs_are_discovered_and_compared_separately() -> None:
    with tempfile.TemporaryDirectory(prefix="tooling-gate-deploysep-") as tmp:
        project_root = Path(tmp)
        root = project_root / ".test_results"
        unit_run = root / "unit-tests-20260511-100000"
        deploy_run = root / "deploy-test-20260511-100000"
        _write_junit(unit_run, "orders_service", tests=4)
        deploy_run.mkdir(parents=True)
        (deploy_run / "index.json").write_text(
            json.dumps(
                {
                    "project_path": str(project_root),
                    "services": [
                        {
                            "name": "orders_service",
                            "spec_result": "PASSED",
                            "integration_result": "FAILED",
                            "docker_healthy": True,
                            "health_check_passed": True,
                            "db_connectivity_passed": True,
                            "counts": {"passed": 8, "failed": 1, "errors": 0},
                        }
                    ],
                }
            ),
            encoding="utf-8",
        )

        unit_runs = find_runs(root, "unit")
        deploy_runs = find_runs(root, "deploy")

        assert len(unit_runs) == 1
        assert unit_runs[0].services["orders_service"].status == "PASSED"
        assert len(deploy_runs) == 1
        assert deploy_runs[0].services["orders_service"].status == "FAILED"
        assert deploy_runs[0].services["orders_service"].counts.failed == 1


# ---------------------------------------------------------------------------
# test/status_tests.py -- _read_index_json
# ---------------------------------------------------------------------------


def _make_run_dir(root: Path, timestamp: str = "20260503-191002") -> Path:
    """Create a project/.test_results/test-results-TIMESTAMP/ structure."""
    project = root / "datrix-example"
    run_dir = project / ".test_results" / f"test-results-{timestamp}"
    run_dir.mkdir(parents=True)
    return run_dir


def _write_index(run_dir: Path, data: dict[str, object]) -> Path:
    index_path = run_dir / "index.json"
    index_path.write_text(json.dumps(data), encoding="utf-8")
    return index_path


def _write_full_log(run_dir: Path, content: str = "") -> Path:
    full_log = run_dir / "full.log"
    full_log.write_text(content, encoding="utf-8")
    return full_log


def _check_read_index_json_valid_counts() -> None:
    with tempfile.TemporaryDirectory(prefix="tooling-gate-index-valid-") as tmp:
        run_dir = _make_run_dir(Path(tmp))
        _write_full_log(run_dir)
        index_path = _write_index(
            run_dir,
            {
                "schema_version": 1,
                "result": "FAILED",
                "counts": {"passed": 42, "failed": 3, "errors": 1, "skipped": 5, "warnings": 2},
            },
        )

        result = _read_index_json(index_path)

        assert result is not None
        assert result.status == "FAILED"
        assert result.total_passed == 42
        assert result.total_failed == 3
        assert result.total_errors == 1
        assert result.total_skipped == 5
        assert result.total_warnings == 2
        assert result.project_name == "datrix-example"
        assert result.timestamp == "2026-05-03 19:10:02"


def _check_read_index_json_passed_result() -> None:
    with tempfile.TemporaryDirectory(prefix="tooling-gate-index-passed-") as tmp:
        run_dir = _make_run_dir(Path(tmp))
        _write_full_log(run_dir)
        index_path = _write_index(
            run_dir,
            {
                "schema_version": 1,
                "result": "PASSED",
                "counts": {"passed": 100, "failed": 0, "errors": 0, "skipped": 2, "warnings": 0},
            },
        )

        result = _read_index_json(index_path)

        assert result is not None
        assert result.status == "PASSED"
        assert result.total_passed == 100


def _check_read_index_json_incomplete_returns_none() -> None:
    with tempfile.TemporaryDirectory(prefix="tooling-gate-index-incomplete-") as tmp:
        run_dir = _make_run_dir(Path(tmp))
        index_path = _write_index(
            run_dir,
            {"schema_version": 1, "result": "INCOMPLETE", "counts": None, "note": "No JUnit XML produced"},
        )

        assert _read_index_json(index_path) is None


def _check_read_index_json_no_counts_returns_none() -> None:
    with tempfile.TemporaryDirectory(prefix="tooling-gate-index-nocounts-") as tmp:
        run_dir = _make_run_dir(Path(tmp))
        index_path = _write_index(run_dir, {"schema_version": 1, "result": "INCOMPLETE"})

        assert _read_index_json(index_path) is None


def _check_read_index_json_corrupt_returns_none() -> None:
    with tempfile.TemporaryDirectory(prefix="tooling-gate-index-corrupt-") as tmp:
        run_dir = _make_run_dir(Path(tmp))
        index_path = run_dir / "index.json"
        index_path.write_text("not valid json {{{", encoding="utf-8")

        assert _read_index_json(index_path) is None


# ---------------------------------------------------------------------------
# test/status_tests.py -- find_latest_log_file
# ---------------------------------------------------------------------------


def _check_find_latest_log_file_prefers_index_json() -> None:
    with tempfile.TemporaryDirectory(prefix="tooling-gate-latest-index-") as tmp:
        run_dir = _make_run_dir(Path(tmp))
        index_path = _write_index(run_dir, {"counts": {"passed": 1}})
        test_results_dir = run_dir.parent

        result = find_latest_log_file(test_results_dir)

        assert result is not None
        assert result == index_path


def _check_find_latest_log_file_falls_back_to_full_log() -> None:
    with tempfile.TemporaryDirectory(prefix="tooling-gate-latest-fulllog-") as tmp:
        run_dir = _make_run_dir(Path(tmp))
        full_log = _write_full_log(run_dir, "====== 5 passed in 1.0s ======\n")
        test_results_dir = run_dir.parent

        result = find_latest_log_file(test_results_dir)

        assert result is not None
        assert result == full_log


def _check_find_latest_log_file_empty_dir_returns_none() -> None:
    with tempfile.TemporaryDirectory(prefix="tooling-gate-latest-empty-") as tmp:
        test_results_dir = Path(tmp) / ".test_results"
        test_results_dir.mkdir()

        assert find_latest_log_file(test_results_dir) is None


# ---------------------------------------------------------------------------
# test/status_tests.py -- parse_timestamp_from_log_file
# ---------------------------------------------------------------------------


def _check_parse_timestamp_directory_name() -> None:
    result = parse_timestamp_from_log_file("test-results-20260503-191002")
    assert result is not None
    assert result.year == 2026
    assert result.month == 5
    assert result.day == 3
    assert result.hour == 19
    assert result.minute == 10
    assert result.second == 2


def _check_parse_timestamp_invalid_name_returns_none() -> None:
    assert parse_timestamp_from_log_file("not-a-test-result") is None


# ---------------------------------------------------------------------------
# test/status_tests.py -- parse_pytest_summary
# ---------------------------------------------------------------------------


def _check_parse_pytest_summary_from_index_json() -> None:
    with tempfile.TemporaryDirectory(prefix="tooling-gate-summary-index-") as tmp:
        run_dir = _make_run_dir(Path(tmp))
        _write_full_log(run_dir)
        index_path = _write_index(
            run_dir,
            {
                "schema_version": 1,
                "result": "PASSED",
                "counts": {"passed": 50, "failed": 0, "errors": 0, "skipped": 1, "warnings": 0},
            },
        )

        result = parse_pytest_summary(index_path)

        assert result.status == "PASSED"
        assert result.total_passed == 50
        assert result.total_skipped == 1
        assert result.project_name == "datrix-example"


def _check_parse_pytest_summary_index_json_incomplete_falls_back_to_full_log() -> None:
    with tempfile.TemporaryDirectory(prefix="tooling-gate-summary-fallback-") as tmp:
        run_dir = _make_run_dir(Path(tmp))
        _write_full_log(run_dir, "====== 8 passed, 2 failed in 3.0s ======\n")
        _write_index(run_dir, {"schema_version": 1, "result": "INCOMPLETE", "counts": None})

        index_path = run_dir / "index.json"
        result = parse_pytest_summary(index_path)

        assert result.status == "FAILED"
        assert result.total_passed == 8
        assert result.total_failed == 2


def _check_parse_pytest_summary_full_log_in_directory() -> None:
    with tempfile.TemporaryDirectory(prefix="tooling-gate-summary-fulllog-") as tmp:
        run_dir = _make_run_dir(Path(tmp))
        full_log = _write_full_log(run_dir, "====== 15 passed in 1.5s ======\n")

        result = parse_pytest_summary(full_log)

        assert result.status == "PASSED"
        assert result.total_passed == 15
        assert result.project_name == "datrix-example"


def _check_parse_pytest_summary_extracts_progress_for_running_log() -> None:
    with tempfile.TemporaryDirectory(prefix="tooling-gate-summary-progress-") as tmp:
        run_dir = _make_run_dir(Path(tmp))
        full_log = _write_full_log(
            run_dir,
            (
                "Phase 1: Parallel tests (excluding serial)\n"
                "[gw2] [  7%] PASSED tests/test_a.py::test_one\n"
                "[gw1] [ 37%] PASSED tests/test_b.py::test_two\n"
            ),
        )

        result = parse_pytest_summary(full_log)

        assert result.status == "UNKNOWN"
        assert result.progress_percent == 37


# ---------------------------------------------------------------------------
# test/status_tests.py -- _format_result_row
# ---------------------------------------------------------------------------


def _check_format_result_row_shows_progress_in_tests_column_for_unknown() -> None:
    row = _format_result_row(
        TestResult(
            project_path="D:/tmp/datrix-example",
            project_name="datrix-example",
            status="UNKNOWN",
            total_passed=0,
            total_failed=0,
            total_errors=0,
            total_skipped=0,
            total_warnings=0,
            timestamp="",
            log_file="",
            phases={},
            progress_percent=42,
        ),
        name_width=len("datrix-example"),
        use_colors=False,
    )

    assert "42%" in row


# ---------------------------------------------------------------------------
# Harness
# ---------------------------------------------------------------------------

_CHECKS: list[tuple[str, Callable[[], None]]] = [
    ("find_runs_compares_direct_child_unit_runs_only", _check_find_runs_compares_direct_child_unit_runs_only),
    ("unit_summary_log_fallback_parses_service_rows", _check_unit_summary_log_fallback_parses_service_rows),
    ("deploy_runs_are_discovered_and_compared_separately", _check_deploy_runs_are_discovered_and_compared_separately),
    ("read_index_json_valid_counts", _check_read_index_json_valid_counts),
    ("read_index_json_passed_result", _check_read_index_json_passed_result),
    ("read_index_json_incomplete_returns_none", _check_read_index_json_incomplete_returns_none),
    ("read_index_json_no_counts_returns_none", _check_read_index_json_no_counts_returns_none),
    ("read_index_json_corrupt_returns_none", _check_read_index_json_corrupt_returns_none),
    ("find_latest_log_file_prefers_index_json", _check_find_latest_log_file_prefers_index_json),
    ("find_latest_log_file_falls_back_to_full_log", _check_find_latest_log_file_falls_back_to_full_log),
    ("find_latest_log_file_empty_dir_returns_none", _check_find_latest_log_file_empty_dir_returns_none),
    ("parse_timestamp_directory_name", _check_parse_timestamp_directory_name),
    ("parse_timestamp_invalid_name_returns_none", _check_parse_timestamp_invalid_name_returns_none),
    ("parse_pytest_summary_from_index_json", _check_parse_pytest_summary_from_index_json),
    ("parse_pytest_summary_index_json_incomplete_falls_back_to_full_log", _check_parse_pytest_summary_index_json_incomplete_falls_back_to_full_log),
    ("parse_pytest_summary_full_log_in_directory", _check_parse_pytest_summary_full_log_in_directory),
    ("parse_pytest_summary_extracts_progress_for_running_log", _check_parse_pytest_summary_extracts_progress_for_running_log),
    ("format_result_row_shows_progress_in_tests_column_for_unknown", _check_format_result_row_shows_progress_in_tests_column_for_unknown),
]


def _dummy_intentionally_failing_check() -> None:
    """Registered ONLY under --harness-self-test.

    Always fails on purpose -- this is the proof that run_checks() actually
    detects and reports a failing check, rather than vacuously swallowing
    every AssertionError and reporting green regardless of what the checks do.
    """
    raise AssertionError("intentional harness self-test failure (expected -- proves non-vacuity)")


def run_checks(checks: list[tuple[str, Callable[[], None]]]) -> bool:
    """Run every (name, check_fn) pair, printing [OK]/[FAIL] per check.

    Args:
        checks: Named zero-argument callables; each raises AssertionError on
            failure and returns normally on success.

    Returns:
        True iff every check passed.
    """
    all_passed = True
    for name, fn in checks:
        try:
            fn()
        except AssertionError as e:
            _fail(f"{name}: {e}")
            all_passed = False
        else:
            _ok(name)
    return all_passed


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Repo-level gate absorbing 2 orphaned test/tests/*.py pytest files "
            "(compare_tests.py run discovery/comparison, status_tests.py index.json/log parsing)."
        )
    )
    parser.add_argument(
        "--harness-self-test",
        action="store_true",
        help=(
            "Demonstration mode: run one intentionally-failing dummy check through "
            "the harness and report the result. Always reports [FAIL] and exits 1 -- "
            "this is the proof that the harness's pass/fail detection is not vacuous."
        ),
    )
    args = parser.parse_args()

    if args.harness_self_test:
        _step("Harness self-test: intentionally-failing dummy check (must report FAIL, exit 1)")
        harness_ok = run_checks(
            [("dummy_intentionally_failing_check", _dummy_intentionally_failing_check)]
        )
        return 0 if harness_ok else 1

    _step("test-tooling-parsing-gate: compare_tests.py, status_tests.py")
    passed = run_checks(_CHECKS)

    print()
    if passed:
        print(
            f"{_GREEN}GATE PASSED{_RESET}: all {len(_CHECKS)} absorbed test-tooling-parsing checks passed."
        )
        return 0
    print(f"{_RED}GATE FAILED{_RESET}: see failures above.")
    return 1


if __name__ == "__main__":
    sys.exit(main())
