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

It additionally covers test/run_complete.py's Java generated-project handling (which no orphaned
pytest file ever exercised): _find_java_service_dirs/_is_java_project service detection -- Maven
modules with src/test/java, with the project-level deployment-tests module excluded because
deploy tests run in Step 4 -- and _merge_surefire_reports/_count_junit_testcases, including the
adversarial cases where a build never reached surefire and so must NOT read as a clean run.

It also covers shared/logging_utils.py's quiet-mode stream liveness: under quiet mode the
subprocess stream reaches the log file and never the console, so a long phase printed nothing
at all and read as a hang. The checks hold the liveness line to what the stream actually
reported -- pytest's per-test progress lines only, never the closing short-summary repeats --
and prove verbose mode gains no extra line, since it already echoes the stream.

Repo-level validation script, not a pytest suite (per the datrix showcase boundary). Uses only
``assert`` + a small harness that catches ``AssertionError`` per check and prints [OK]/[FAIL] --
no pytest, no mocks/fakes, real ``tempfile.TemporaryDirectory()`` fixtures for every filesystem
case.

Exit codes: 0 = every check passed, 1 = at least one check (or the harness self-test) failed.
"""

from __future__ import annotations

import argparse
import io
import json
import re
import subprocess
import sys
import tempfile
import xml.etree.ElementTree as ET
from collections.abc import Callable
from contextlib import redirect_stdout
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
from shared.logging_utils import (  # noqa: E402
    _PROGRESS_INTERVAL_SECONDS,
    LogConfig,
    TeeLogger,
    _StreamProgress,
)
from shared.node_test_runner import _format_summary, merge_junit_xml  # noqa: E402
from shared.package_suites import testable_package_names  # noqa: E402
from shared.structured_log_writer import StructuredLogWriter  # noqa: E402
from shared.venv import get_datrix_root  # noqa: E402
from test.post_process_test_results import post_process_results  # noqa: E402
from test.run_complete import (  # noqa: E402
    _count_junit_testcases,
    _derive_generated_project_metadata,
    _find_java_service_dirs,
    _is_java_project,
    _merge_surefire_reports,
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


def _check_failed_phase_renders_as_failed() -> None:
    """A failed phase must reach the report's phase column as a failure.

    ``phases`` is a map of DICTS carrying ``status`` (1 = passed, 2 = failed).
    The pytest runner used to hand the writer bare return codes instead, so every
    phase parsed as status 0 and rendered OK even on a red run -- the failure was
    visible only in the row's overall symbol and its Failed count.
    """
    with tempfile.TemporaryDirectory(prefix="tooling-gate-index-phase-") as tmp:
        run_dir = _make_run_dir(Path(tmp))
        _write_full_log(run_dir)
        index_path = _write_index(
            run_dir,
            {
                "schema_version": 1,
                "result": "FAILED",
                "counts": {"passed": 10, "failed": 2, "errors": 0, "skipped": 0},
                "phases": {
                    "Parallel": {"status": 1, "items": 8},
                    "Serial": {"status": 2, "items": 4},
                },
            },
        )

        result = _read_index_json(index_path)

        assert result is not None
        assert result.phases["Parallel"].status == "PASSED", result.phases["Parallel"]
        assert result.phases["Serial"].status == "FAILED", result.phases["Serial"]
        assert result.phases["Serial"].failed == 2, result.phases["Serial"]

        row = _format_result_row(result, name_width=20, use_colors=False)
        assert "2F" in row, f"failed phase must show its failure count in the row: {row!r}"


def _check_legacy_returncode_phase_shape_is_read_correctly() -> None:
    """Runs recorded before the dict encoding carry the phase's RETURN CODE.

    A `.test_results` tree holds runs from both encodings, so the older one is
    read rather than discarded -- and reading it is what applies the fix to those
    runs too: a non-zero code is a FAILED phase, where the previous reader turned
    every int into PASSED.
    """
    with tempfile.TemporaryDirectory(prefix="tooling-gate-index-legacyphase-") as tmp:
        run_dir = _make_run_dir(Path(tmp))
        _write_full_log(run_dir)
        index_path = _write_index(
            run_dir,
            {
                "schema_version": 1,
                "result": "FAILED",
                "counts": {"passed": 10, "failed": 2, "errors": 0, "skipped": 0},
                "phases": {"Parallel": 0, "Serial": 1},
            },
        )

        result = _read_index_json(index_path)

        assert result is not None
        assert result.phases["Parallel"].status == "PASSED", result.phases["Parallel"]
        assert result.phases["Serial"].status == "FAILED", result.phases["Serial"]
        row = _format_result_row(result, name_width=20, use_colors=False)
        assert "2F" in row, f"legacy non-zero return code must render as a failure: {row!r}"


def _check_uninterpretable_phase_shape_is_not_reported_as_passed() -> None:
    """Adversarial: a phase in neither encoding must not read as green.

    Defaulting an unreadable phase to PASSED is what let a producer writing the
    wrong shape render every phase column OK on red runs. Such a phase is now
    omitted -- the column shows "-" ("no information"), which is what the
    artifact actually establishes.
    """
    with tempfile.TemporaryDirectory(prefix="tooling-gate-index-badphase-") as tmp:
        run_dir = _make_run_dir(Path(tmp))
        _write_full_log(run_dir)
        index_path = _write_index(
            run_dir,
            {
                "schema_version": 1,
                "result": "FAILED",
                "counts": {"passed": 10, "failed": 2, "errors": 0, "skipped": 0},
                "phases": {"Parallel": "green", "Serial": {"items": 4}},
            },
        )

        result = _read_index_json(index_path)

        assert result is not None
        assert result.phases == {}, (
            f"a phases map the reader cannot interpret must yield NO phase entries, "
            f"never entries defaulted to PASSED; got {result.phases}"
        )
        row = _format_result_row(result, name_width=20, use_colors=False)
        assert "OK" not in row, f"an uninterpretable phase must not render OK: {row!r}"


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
# test/run_complete.py -- Java generated-project detection and surefire merging
# ---------------------------------------------------------------------------

_SUREFIRE_PASSING = (
    '<?xml version="1.0" encoding="UTF-8"?>'
    '<testsuite name="a.OrderTest" tests="2" failures="0" errors="0" skipped="0">'
    '<testcase classname="a.OrderTest" name="creates"/>'
    '<testcase classname="a.OrderTest" name="updates"/>'
    "</testsuite>"
)

_SUREFIRE_MIXED = (
    '<?xml version="1.0" encoding="UTF-8"?>'
    '<testsuite name="a.ProductTest" tests="3" failures="1" errors="1" skipped="1">'
    '<testcase classname="a.ProductTest" name="fails">'
    '<failure type="AssertionError" message="expected 1">stack</failure>'
    "</testcase>"
    '<testcase classname="a.ProductTest" name="errors">'
    '<error type="IllegalStateException" message="boom">stack</error>'
    "</testcase>"
    '<testcase classname="a.ProductTest" name="ignored"><skipped/></testcase>'
    "</testsuite>"
)


def _make_java_service(project: Path, name: str, *, with_tests: bool = True) -> None:
    """Create a minimal generated Java service module under *project*."""
    service = project / name
    (service / "src" / "main" / "java").mkdir(parents=True)
    (service / "pom.xml").write_text("<project/>", encoding="utf-8")
    if with_tests:
        (service / "src" / "test" / "java").mkdir(parents=True)


def _check_java_service_dirs_are_the_unit_test_targets() -> None:
    with tempfile.TemporaryDirectory(prefix="tooling-gate-java-services-") as tmp:
        project = Path(tmp) / "logistics"
        _make_java_service(project, "logistics_fleet_service")
        _make_java_service(project, "logistics_route_service")

        assert [d.name for d in _find_java_service_dirs(project)] == [
            "logistics_fleet_service",
            "logistics_route_service",
        ]
        assert _is_java_project(project) is True


def _check_java_deployment_tests_module_excluded() -> None:
    with tempfile.TemporaryDirectory(prefix="tooling-gate-java-deploy-") as tmp:
        project = Path(tmp) / "logistics"
        _make_java_service(project, "logistics_fleet_service")
        # The project-level deploy suite is also a Maven module with tests; it
        # belongs to Step 4, so Step 3 must not pick it up as a service.
        _make_java_service(project, "deployment-tests")

        assert [d.name for d in _find_java_service_dirs(project)] == [
            "logistics_fleet_service"
        ]


def _check_java_service_without_test_sources_is_not_a_target() -> None:
    with tempfile.TemporaryDirectory(prefix="tooling-gate-java-notests-") as tmp:
        project = Path(tmp) / "logistics"
        _make_java_service(project, "logistics_fleet_service", with_tests=False)

        assert _find_java_service_dirs(project) == []
        assert _is_java_project(project) is False


def _check_non_java_project_is_not_detected_as_java() -> None:
    with tempfile.TemporaryDirectory(prefix="tooling-gate-java-none-") as tmp:
        project = Path(tmp) / "ecommerce"
        (project / "product_service").mkdir(parents=True)

        assert _is_java_project(project) is False


def _check_surefire_reports_merge_into_one_countable_junit() -> None:
    with tempfile.TemporaryDirectory(prefix="tooling-gate-surefire-merge-") as tmp:
        reports = Path(tmp) / "surefire-reports"
        reports.mkdir()
        (reports / "TEST-a.OrderTest.xml").write_text(_SUREFIRE_PASSING, encoding="utf-8")
        (reports / "TEST-a.ProductTest.xml").write_text(_SUREFIRE_MIXED, encoding="utf-8")

        junit = Path(tmp) / "services" / "fleet" / "junit.xml"
        assert _merge_surefire_reports(reports, junit) is True
        assert _count_junit_testcases(junit) == {
            "passed": 2,
            "failed": 1,
            "errors": 1,
            "skipped": 1,
        }


def _check_missing_surefire_dir_reports_no_results() -> None:
    with tempfile.TemporaryDirectory(prefix="tooling-gate-surefire-missing-") as tmp:
        junit = Path(tmp) / "junit.xml"

        # A build that failed before surefire ran must not read as a clean run.
        assert _merge_surefire_reports(Path(tmp) / "surefire-reports", junit) is False
        assert not junit.exists()


def _check_empty_surefire_dir_reports_no_results() -> None:
    with tempfile.TemporaryDirectory(prefix="tooling-gate-surefire-empty-") as tmp:
        reports = Path(tmp) / "surefire-reports"
        reports.mkdir()
        junit = Path(tmp) / "junit.xml"

        assert _merge_surefire_reports(reports, junit) is False
        assert not junit.exists()


def _check_surefire_merge_ignores_non_result_files() -> None:
    with tempfile.TemporaryDirectory(prefix="tooling-gate-surefire-noise-") as tmp:
        reports = Path(tmp) / "surefire-reports"
        reports.mkdir()
        (reports / "a.OrderTest.txt").write_text("plain text summary", encoding="utf-8")
        (reports / "TEST-a.OrderTest.xml").write_text(_SUREFIRE_PASSING, encoding="utf-8")

        junit = Path(tmp) / "junit.xml"
        assert _merge_surefire_reports(reports, junit) is True
        assert _count_junit_testcases(junit)["passed"] == 2


# ---------------------------------------------------------------------------
# Structured-output seam: every service the runner attempted gets a verdict
# ---------------------------------------------------------------------------

_GATE_JUNIT_PASSING = """<?xml version="1.0" encoding="utf-8"?>
<testsuites>
  <testsuite name="svc" tests="2" failures="0" errors="0" skipped="0">
    <testcase classname="a.OrderTest" name="test_one" time="0.01"/>
    <testcase classname="a.OrderTest" name="test_two" time="0.01"/>
  </testsuite>
</testsuites>
"""


def _write_service_run_dir(run_dir: Path, *, reporting: list[str], silent: list[str]) -> None:
    """Build a results dir where *reporting* services wrote a junit.xml and *silent* did not.

    ``silent`` reproduces the real shape exactly: the runner creates
    ``services/{name}/`` and writes ``service.log`` BEFORE running the build, so a
    build that dies at ``testCompile`` leaves the directory and the log behind with
    no test report beside them.
    """
    for name in reporting:
        svc = run_dir / "services" / name
        svc.mkdir(parents=True, exist_ok=True)
        (svc / "junit.xml").write_text(_GATE_JUNIT_PASSING, encoding="utf-8")
        (svc / "service.log").write_text("BUILD SUCCESS\n", encoding="utf-8")
    for name in silent:
        svc = run_dir / "services" / name
        svc.mkdir(parents=True, exist_ok=True)
        (svc / "service.log").write_text(
            "[ERROR] COMPILATION ERROR :\n[ERROR] cannot find symbol\n[INFO] BUILD FAILURE\n",
            encoding="utf-8",
        )


def _post_process_index(run_dir: Path) -> dict[str, object]:
    """Run the standalone post-processor over *run_dir* and return its index.json."""
    exit_code = post_process_results(
        run_dir,
        project_name="gate/project",
        source_dtrx="datrix/examples/gate/system.dtrx",
        language="java",
        platform="docker",
    )
    assert exit_code == 0, f"post_process_results returned {exit_code}, expected 0"
    index_path = run_dir / "index.json"
    assert index_path.is_file(), f"no index.json written to {run_dir}"
    return json.loads(index_path.read_text(encoding="utf-8"))


def _check_service_without_test_report_is_recorded_as_failed() -> None:
    """A service that produced no test report must FAIL the run, never vanish.

    The defect this pins: a Java service whose ``testCompile`` failed wrote a
    ``service.log`` and no ``junit.xml``, the walk skipped it with no ``else``
    branch, and the verdict was then computed over the SURVIVING services only --
    ``"result": "PASSED"`` for a run whose own ``unit-tests-summary.log`` said
    ``Total Errors: 1`` / ``Tests FAILED!``.
    """
    with tempfile.TemporaryDirectory(prefix="tooling-gate-unreported-svc-") as tmp:
        run_dir = Path(tmp) / "unit-tests-20260101-000000"
        run_dir.mkdir(parents=True)
        _write_service_run_dir(
            run_dir, reporting=["ingestion_service"], silent=["order_service"]
        )
        index = _post_process_index(run_dir)

        names = [s["name"] for s in index["services"]]  # type: ignore[index]
        assert "order_service" in names, (
            f"the service that produced no report was dropped from index.json: {names}"
        )
        assert index["result"] == "FAILED", (
            f"index reported {index['result']!r} for a run in which a service never "
            f"produced a test report"
        )
        assert index["counts"]["errors"] >= 1, index["counts"]  # type: ignore[index]


def _check_all_services_reporting_still_passes() -> None:
    """Non-vacuity for the check above: the same walk must still report PASSED.

    Without this, a walk hardcoded to emit FAILED would satisfy the previous check
    while destroying every green run.
    """
    with tempfile.TemporaryDirectory(prefix="tooling-gate-all-reported-") as tmp:
        run_dir = Path(tmp) / "unit-tests-20260101-000000"
        run_dir.mkdir(parents=True)
        _write_service_run_dir(
            run_dir, reporting=["ingestion_service", "order_service"], silent=[]
        )
        index = _post_process_index(run_dir)

        assert index["result"] == "PASSED", index["result"]
        assert index["counts"]["errors"] == 0, index["counts"]  # type: ignore[index]
        assert len(index["services"]) == 2, index["services"]  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# Structured-output metadata: the .dtrx pointer must resolve
# ---------------------------------------------------------------------------


def _any_real_example_relpath() -> str:
    """Return a real example path under ``datrix/examples`` carrying a system.dtrx.

    Discovered rather than hardcoded: this gate must not start failing because one
    named example was renamed, and a check built on a non-existent example would
    prove nothing about a derivation whose whole job is resolving to a real file.
    """
    examples_root = get_datrix_root() / "datrix" / "examples"
    for dtrx in sorted(examples_root.rglob("system.dtrx")):
        return dtrx.parent.relative_to(examples_root).as_posix()
    raise AssertionError(f"no system.dtrx found under {examples_root}")


def _check_dtrx_source_resolves_to_a_real_file() -> None:
    """The derived ``dtrx_source`` must name a file that exists.

    The defect this pins: the example was derived positionally from a
    caller-supplied base, and single-project mode passes the project's own parent
    as that base so the relative path collapses to the leaf name. A nested example
    then produced ``datrix/examples/serverless/system.dtrx`` -- which does not
    exist -- instead of
    ``datrix/examples/02-features/02-service-architecture/serverless/system.dtrx``.
    """
    datrix_root = get_datrix_root()
    example = _any_real_example_relpath()
    project = datrix_root / ".generated" / "java" / "docker-compose" / "local" / example

    project_name, derived_example, dtrx_source = _derive_generated_project_metadata(project)

    assert derived_example == example, f"{derived_example!r} != {example!r}"
    assert (datrix_root / dtrx_source).is_file(), (
        f"derived dtrx_source {dtrx_source!r} does not resolve to a real file"
    )
    assert project_name.startswith("java/docker-compose/local/"), project_name


def _check_collapsed_project_path_is_rejected() -> None:
    """A project path that cannot name an example must raise, never guess.

    This is the single-project-mode trap in its pure form: given only the leaf
    directory there is no category to build an example path from, and the old
    ``else`` branch silently emitted ``datrix/examples/{leaf}/system.dtrx`` anyway.
    """
    collapsed = get_datrix_root() / ".generated" / "serverless"
    try:
        _derive_generated_project_metadata(collapsed)
    except ValueError:
        pass
    else:
        raise AssertionError(
            "a project path with too few segments to name an example was accepted; "
            "it must raise rather than emit a guessed .dtrx pointer"
        )


def _check_project_matching_no_example_is_rejected() -> None:
    """A project path naming no real example must raise, never guess a pointer."""
    with tempfile.TemporaryDirectory(prefix="tooling-gate-no-example-") as tmp:
        try:
            _derive_generated_project_metadata(Path(tmp) / "some-project")
        except ValueError:
            return
    raise AssertionError(
        "a project path matching no example under datrix/examples was accepted; "
        "it must raise rather than emit a guessed .dtrx pointer"
    )


def _check_example_resolves_under_a_custom_output_base() -> None:
    """The example must resolve outside ``.generated`` too.

    ``generate.ps1 -OutputBase`` is a documented flow. Counting a fixed
    ``{language}/{runtime}/{provider}`` prefix off the path only works under
    ``.generated``; matching from the tail against a real ``system.dtrx`` makes the
    number of leading segments irrelevant, which is what keeps a custom output base
    from turning into either a wrong pointer or a crashed run.
    """
    datrix_root = get_datrix_root()
    example = _any_real_example_relpath()
    project = datrix_root / ".generated2" / "java" / "docker-compose" / "local" / example

    _project_name, derived_example, dtrx_source = _derive_generated_project_metadata(project)

    assert derived_example == example, f"{derived_example!r} != {example!r}"
    assert (datrix_root / dtrx_source).is_file(), dtrx_source


# ---------------------------------------------------------------------------
# shared/structured_log_writer.py -- stack-frame parsing across both producers
# ---------------------------------------------------------------------------

_PYTEST_TRACEBACK = """\
tests/unit/test_widget.py:41: in test_builds_a_widget
    result = build_widget(spec)
src/datrix_common/widgets/builder.py:117: in build_widget
    raise ValueError("no such kind")
E   ValueError: no such kind
"""

_V8_URL_STACK = """\
[Error [ERR_TEST_FAILURE]: helper exploded] {
  cause: TypeError [Error]: helper exploded
      at boom (file:///C:/work/pkg/helper.mjs:2:9)
      at TestContext.<anonymous> (file:///C:/work/pkg/b.test.mjs:10:3)
      at Test.runInAsyncScope (node:async_hooks:211:14)
      at Test.run (node:internal/test_runner/test:931:25)
}
"""

_V8_PLAIN_PATH_STACK = """\
AssertionError [ERR_ASSERTION]: Expected values to be strictly equal
    at Object.resolveThing (D:\\work\\pkg\\src\\resolution.ts:28:52)
    at TestContext.<anonymous> (D:\\work\\pkg\\src\\test\\resolution.test.ts:9:10)
    at async startSubtestAfterBootstrap (node:internal/test_runner/harness:296:3)
"""

_V8_ENGINE_ONLY_STACK = """\
[Error [ERR_TEST_FAILURE]: test timed out] {
    at Test.run (node:internal/test_runner/test:931:25)
    at listOnTimeout (node:internal/timers:594:17)
    at [eval]:1:63
}
"""


def _writer() -> StructuredLogWriter:
    return StructuredLogWriter(project_name="probe", run_dir=Path("."))


def _check_pytest_traceback_still_resolves_to_the_project_frame() -> None:
    """The Python path must be byte-for-byte what it was before Node support.

    A pytest traceback lists the OUTERMOST frame first, a V8 stack the innermost.
    Normalizing the two orders is the change most able to silently invert which
    frame a Python failure is attributed to, so it is pinned here.
    """
    location = _writer()._extract_source_location(_PYTEST_TRACEBACK)
    assert str(location) == "src/datrix_common/widgets/builder.py:117", location


def _check_v8_url_stack_resolves_to_the_project_frame() -> None:
    location = _writer()._extract_source_location(_V8_URL_STACK)
    assert str(location) == "C:/work/pkg/helper.mjs:2", location


def _check_v8_plain_path_stack_resolves_to_the_project_frame() -> None:
    location = _writer()._extract_source_location(_V8_PLAIN_PATH_STACK)
    assert str(location) == "D:/work/pkg/src/resolution.ts:28", location


def _check_v8_engine_only_stack_resolves_to_unknown() -> None:
    """Adversarial: a stack with no source file must yield unknown:0.

    Without the file-extension filter, ``node:internal/test_runner/test:931:25``
    parses as a perfectly well-formed frame, and every timed-out Node test would
    be clustered under an engine path no author can open.
    """
    location = _writer()._extract_source_location(_V8_ENGINE_ONLY_STACK)
    assert str(location) == "unknown:0", location


def _check_pytest_classname_still_becomes_a_python_path() -> None:
    element = ET.fromstring(
        '<testcase classname="tests.unit.test_widget.TestWidget" name="test_ok" time="0.1"/>'
    )
    result = _writer()._parse_testcase_element(element, None)
    assert result.file == "tests/unit/test_widget.py", result.file


def _check_declared_file_attribute_wins_over_classname() -> None:
    element = ET.fromstring(
        '<testcase classname="src/test/a.test.ts" file="src/test/a.test.ts" '
        'name="does a thing" time="0.1"/>'
    )
    result = _writer()._parse_testcase_element(element, None)
    assert result.file == "src/test/a.test.ts", result.file


# ---------------------------------------------------------------------------
# shared/node_test_runner.py -- merging Node's junit output
# ---------------------------------------------------------------------------

_NODE_JUNIT_XML = """\
<?xml version="1.0" encoding="utf-8"?>
<testsuites>
\t<testcase name="passing one" time="0.000420" classname="test"/>
\t<testcase name="failing one" time="0.000471" classname="test" failure="boom">
\t\t<failure type="testCodeFailure" message="boom">stack text</failure>
\t</testcase>
\t<testcase name="skipped one" time="0.000065" classname="test">
\t\t<skipped type="skipped" message="true"/>
\t</testcase>
\t<!-- tests 3 -->
</testsuites>
"""


def _check_node_junit_merge_counts_and_attributes_every_case() -> None:
    """Node emits cases directly under <testsuites> with classname="test".

    StructuredLogWriter reads <testsuite> elements, so unmerged Node output
    parses to ZERO results -- a suite that ran would report as an empty run.
    """
    with tempfile.TemporaryDirectory(prefix="tooling-gate-nodemerge-") as tmp:
        root = Path(tmp)
        raw = root / "junit-node-001.xml"
        raw.write_text(_NODE_JUNIT_XML, encoding="utf-8")
        merged = root / "junit-node.xml"

        counts = merge_junit_xml([("src/test/a.test.ts", raw)], merged, 1.25)

        assert counts == {"passed": 1, "failed": 1, "error": 0, "skipped": 1}, counts

        tree = ET.parse(merged)
        suites = list(tree.getroot().iter("testsuite"))
        assert len(suites) == 1, f"expected exactly one <testsuite>, got {len(suites)}"
        assert suites[0].get("time") == "1.250000", suites[0].get("time")
        cases = list(suites[0].iter("testcase"))
        assert len(cases) == 3, len(cases)
        for case in cases:
            assert case.get("classname") == "src/test/a.test.ts", case.get("classname")
            assert case.get("file") == "src/test/a.test.ts", case.get("file")
            assert case.get("failure") is None, "redundant failure attribute not stripped"


def _check_node_summary_line_matches_the_shape_test_ps1_parses() -> None:
    """test.ps1 scans the runner's stdout for a pytest-shaped summary line.

    It requires outcome counts AND an ``in <n>.<n>s`` timing on one line, and it
    reads the last two matching lines as two phases. A line that fails to match
    would report the run as zero tests in the repo-wide summary.
    """
    line = _format_summary({"passed": 33, "failed": 0, "error": 0, "skipped": 1}, 6.512)
    assert line == "33 passed, 1 skipped in 6.51s", line
    assert re.search(r"\bin\s+\d+\.\d+s\b", line), line
    assert re.search(r"\d+\s+(passed|failed|error|skipped)", line), line

    failing = _format_summary({"passed": 1, "failed": 2, "error": 3, "skipped": 0}, 0.5)
    assert failing == "2 failed, 3 error, 1 passed in 0.50s", failing


# ---------------------------------------------------------------------------
# Testable-package discovery -- one fact, two implementations
# ---------------------------------------------------------------------------


def _check_powershell_and_python_agree_on_testable_packages() -> None:
    """The PowerShell and Python discoveries must return the same set.

    ``test.ps1 -All`` asks PowerShell which packages are testable;
    ``status-tests.ps1`` asks Python. Neither can call the other (the PowerShell
    answer is needed before the venv is activated), so the same predicate is
    written twice -- and two independent implementations of one fact drift unless
    something compares them. This is that comparison.
    """
    workspace = get_datrix_root()
    expected = testable_package_names(workspace)
    assert expected, f"no testable packages discovered under {workspace}"

    module_path = _LIBRARY_DIR.parent / "common" / "DatrixScriptCommon.psm1"
    command = (
        f"Import-Module '{module_path}' -Force; "
        f"Get-DatrixTestablePackageNames -WorkspaceRoot '{workspace}' | ForEach-Object {{ $_ }}"
    )
    completed = subprocess.run(  # noqa: S603 -- fixed argv, internally built command
        ["powershell", "-NoProfile", "-NonInteractive", "-Command", command],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )
    assert completed.returncode == 0, (
        f"Get-DatrixTestablePackageNames exited {completed.returncode}: "
        f"{completed.stderr.strip()}"
    )
    actual = sorted(line.strip() for line in completed.stdout.splitlines() if line.strip())

    assert actual == expected, (
        f"PowerShell and Python disagree on which packages are testable.\n"
        f"  only PowerShell: {sorted(set(actual) - set(expected))}\n"
        f"  only Python:     {sorted(set(expected) - set(actual))}"
    )


def _check_node_suite_marker_is_load_bearing() -> None:
    """Adversarial: the Node marker must be what admits a Node package.

    Proves the check above is not passing merely because both implementations
    ignore Node packages: a synthetic package.json-only tree is discovered, and
    the same tree without the `test` script is not.
    """
    with tempfile.TemporaryDirectory(prefix="tooling-gate-nodemarker-") as tmp:
        root = Path(tmp)
        (root / "datrix-with-suite").mkdir()
        (root / "datrix-with-suite" / "package.json").write_text(
            json.dumps({"name": "datrix-with-suite", "scripts": {"test": "node --test"}}),
            encoding="utf-8",
        )
        (root / "datrix-without-suite").mkdir()
        (root / "datrix-without-suite" / "package.json").write_text(
            json.dumps({"name": "datrix-without-suite", "scripts": {"build": "tsc"}}),
            encoding="utf-8",
        )
        assert testable_package_names(root) == ["datrix-with-suite"], testable_package_names(root)


# ---------------------------------------------------------------------------
# shared/logging_utils.py -- quiet-mode stream liveness
# ---------------------------------------------------------------------------


def _stream_lines_under(*, quiet: bool) -> list[str]:
    """Stream one real subprocess through TeeLogger, returning its console lines.

    Real Popen, real stream, real TeeLogger -- the only thing substituted is the
    liveness interval, so the check does not have to wait 30 seconds.
    """
    emitter = (
        "import sys\n"
        "sys.stdout.write('[gw0] [ 50%] PASSED tests/unit/test_a.py::test_one\\n')\n"
        "sys.stdout.flush()\n"
    )
    process = subprocess.Popen(  # noqa: S603 -- fixed argv, this interpreter
        [sys.executable, "-c", emitter],
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1,
    )
    config = LogConfig(
        project_name="datrix-codegen-python",
        save_to_file=False,
        quiet_mode=quiet,
    )
    captured = io.StringIO()
    with TeeLogger(config) as logger, redirect_stdout(captured):
        returncode, _ = logger.stream_process(process, progress_interval_seconds=0.0)
    assert returncode == 0, f"emitter subprocess exited {returncode}"
    return [line for line in captured.getvalue().splitlines() if line.strip()]


def _check_quiet_stream_prints_a_console_liveness_line() -> None:
    """A phase running under quiet mode must prove on the console that it is alive.

    Quiet mode routes every streamed line to the log file and none to the
    console, so datrix-codegen-python's 42-minute parallel phase printed
    nothing at all between its banner and its summary -- indistinguishable
    from a hang, and reported as one.
    """
    emitted = _stream_lines_under(quiet=True)
    liveness = [line for line in emitted if line.lstrip().startswith("...")]
    assert liveness, f"quiet stream printed no liveness line: {emitted}"
    assert not any("PASSED" in line for line in emitted), (
        f"quiet mode must not echo the stream itself to the console: {emitted}"
    )


def _check_verbose_stream_echoes_the_stream_and_adds_no_liveness_line() -> None:
    """Adversarial: verbose mode already shows progress, so it gets no extra line."""
    emitted = _stream_lines_under(quiet=False)
    assert any("PASSED" in line for line in emitted), emitted
    assert not any(line.lstrip().startswith("...") for line in emitted), emitted


def _check_stream_progress_counts_only_pytest_progress_lines() -> None:
    """Only pytest's per-test progress lines count as finished tests.

    The runner always passes -v, so every finished test prints a line carrying
    the progress column. The closing "short test summary info" section repeats
    each failure WITHOUT that column and pytest's final tally spells the
    verdicts in lowercase -- counting either would claim more tests than ran.
    """
    progress = _StreamProgress(interval_seconds=0.0)
    for line in (
        "tests/unit/test_a.py::test_one ",
        "[gw3] [  5%] PASSED tests/unit/test_a.py::test_one",
        "[gw1] [ 10%] FAILED tests/unit/test_b.py::test_two",
        "tests/unit/test_c.py::test_three SKIPPED [ 15%]",
        "FAILED tests/unit/test_b.py::test_two - AssertionError: nope",
        "========== 1 failed, 1 passed, 1 skipped in 12.34s ==========",
    ):
        progress.observe(line)

    rendered = progress.due_line("datrix-codegen-python")
    assert rendered is not None, "a zero interval makes the first line due immediately"
    assert "3 tests reported" in rendered, rendered
    assert "15% complete" in rendered, rendered
    assert "datrix-codegen-python" in rendered, rendered


def _check_stream_progress_is_silent_before_its_interval_elapses() -> None:
    """A short suite must print no liveness line at all."""
    progress = _StreamProgress(interval_seconds=_PROGRESS_INTERVAL_SECONDS)
    progress.observe("[gw0] [100%] PASSED tests/unit/test_a.py::test_one")
    assert progress.due_line("datrix-extensions") is None


def _check_stream_progress_reports_elapsed_with_no_pytest_markers() -> None:
    """A stream carrying neither a percentage nor a verdict still reports elapsed time.

    Collection is exactly that stream: 167 seconds of silence on the largest
    package, which is the stretch most in need of a liveness line.
    """
    progress = _StreamProgress(interval_seconds=0.0)
    progress.observe("collecting ... ")
    rendered = progress.due_line(None)
    assert rendered is not None
    assert "elapsed" in rendered, rendered
    assert "complete" not in rendered, rendered
    assert "tests reported" not in rendered, rendered
    assert rendered.strip().startswith("... tests:"), rendered


# ---------------------------------------------------------------------------
# Harness
# ---------------------------------------------------------------------------

_CHECKS: list[tuple[str, Callable[[], None]]] = [
    ("find_runs_compares_direct_child_unit_runs_only", _check_find_runs_compares_direct_child_unit_runs_only),
    ("unit_summary_log_fallback_parses_service_rows", _check_unit_summary_log_fallback_parses_service_rows),
    ("deploy_runs_are_discovered_and_compared_separately", _check_deploy_runs_are_discovered_and_compared_separately),
    ("read_index_json_valid_counts", _check_read_index_json_valid_counts),
    ("read_index_json_passed_result", _check_read_index_json_passed_result),
    ("failed_phase_renders_as_failed", _check_failed_phase_renders_as_failed),
    ("legacy_returncode_phase_shape_is_read_correctly", _check_legacy_returncode_phase_shape_is_read_correctly),
    ("uninterpretable_phase_shape_is_not_reported_as_passed", _check_uninterpretable_phase_shape_is_not_reported_as_passed),
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
    ("java_service_dirs_are_the_unit_test_targets", _check_java_service_dirs_are_the_unit_test_targets),
    ("java_deployment_tests_module_excluded", _check_java_deployment_tests_module_excluded),
    ("java_service_without_test_sources_is_not_a_target", _check_java_service_without_test_sources_is_not_a_target),
    ("non_java_project_is_not_detected_as_java", _check_non_java_project_is_not_detected_as_java),
    ("surefire_reports_merge_into_one_countable_junit", _check_surefire_reports_merge_into_one_countable_junit),
    ("missing_surefire_dir_reports_no_results", _check_missing_surefire_dir_reports_no_results),
    ("empty_surefire_dir_reports_no_results", _check_empty_surefire_dir_reports_no_results),
    ("surefire_merge_ignores_non_result_files", _check_surefire_merge_ignores_non_result_files),
    ("service_without_test_report_is_recorded_as_failed", _check_service_without_test_report_is_recorded_as_failed),
    ("all_services_reporting_still_passes", _check_all_services_reporting_still_passes),
    ("dtrx_source_resolves_to_a_real_file", _check_dtrx_source_resolves_to_a_real_file),
    ("collapsed_project_path_is_rejected", _check_collapsed_project_path_is_rejected),
    ("project_matching_no_example_is_rejected", _check_project_matching_no_example_is_rejected),
    ("example_resolves_under_a_custom_output_base", _check_example_resolves_under_a_custom_output_base),
    ("pytest_traceback_still_resolves_to_the_project_frame", _check_pytest_traceback_still_resolves_to_the_project_frame),
    ("v8_url_stack_resolves_to_the_project_frame", _check_v8_url_stack_resolves_to_the_project_frame),
    ("v8_plain_path_stack_resolves_to_the_project_frame", _check_v8_plain_path_stack_resolves_to_the_project_frame),
    ("v8_engine_only_stack_resolves_to_unknown", _check_v8_engine_only_stack_resolves_to_unknown),
    ("pytest_classname_still_becomes_a_python_path", _check_pytest_classname_still_becomes_a_python_path),
    ("declared_file_attribute_wins_over_classname", _check_declared_file_attribute_wins_over_classname),
    ("node_junit_merge_counts_and_attributes_every_case", _check_node_junit_merge_counts_and_attributes_every_case),
    ("node_summary_line_matches_the_shape_test_ps1_parses", _check_node_summary_line_matches_the_shape_test_ps1_parses),
    ("powershell_and_python_agree_on_testable_packages", _check_powershell_and_python_agree_on_testable_packages),
    ("node_suite_marker_is_load_bearing", _check_node_suite_marker_is_load_bearing),
    ("quiet_stream_prints_a_console_liveness_line", _check_quiet_stream_prints_a_console_liveness_line),
    ("verbose_stream_echoes_the_stream_and_adds_no_liveness_line", _check_verbose_stream_echoes_the_stream_and_adds_no_liveness_line),
    ("stream_progress_counts_only_pytest_progress_lines", _check_stream_progress_counts_only_pytest_progress_lines),
    ("stream_progress_is_silent_before_its_interval_elapses", _check_stream_progress_is_silent_before_its_interval_elapses),
    ("stream_progress_reports_elapsed_with_no_pytest_markers", _check_stream_progress_reports_elapsed_with_no_pytest_markers),
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
