#!/usr/bin/env python3
"""Repo-level gate for the test tooling's parsers, absorbing orphaned pytest files.

Run through ``test/test-tooling-parsing-gate.ps1``. The test tooling once carried pytest files
that no runner ever executed (the `datrix` showcase repo hosts no test suite of any kind -- see
CLAUDE.md "Datrix Showcase Repo Boundaries"). This gate absorbs their valuable, non-vacuous
coverage as a plain-Python check harness and re-expresses each file's distinct behavioral
classes as named ``_check_*`` functions:

  - test_compare_tests.py     -> test/lib/compare_tests.py (find_runs, build_service_comparisons,
    parse_unit_run: direct-child-only run discovery, service change classification, the
    flat-log fallback parser, and unit/deploy population separation)
  - test_status_tests_index.py -> datrix_scripts.status_tests (TestResult, _format_result_row,
    _read_index_json, find_latest_log_file, parse_pytest_summary, parse_timestamp_from_log_file)
  - test_status_tests.py      -> datrix_scripts.status_tests (_extract_counts_from_summary_line,
    find_all_test_results)
  - test_run_complete.py      -> test/lib/run_complete.py (parse_test_statistics)

Repo-level validation script, not a pytest suite (per the datrix showcase boundary). Uses only
``assert`` + a small harness that catches ``AssertionError`` per check and prints [OK]/[FAIL] --
no pytest, no mocks/fakes, real ``tempfile.TemporaryDirectory()`` fixtures for every filesystem
case.

Exit codes: 0 = every check passed, 1 = at least one check (or the harness self-test) failed.
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
import tempfile
import xml.etree.ElementTree as ET
from collections.abc import Callable
from pathlib import Path

from compare_tests import (
    build_service_comparisons,
    find_runs,
    parse_unit_run,
)
from datrix_scripts.node_test_runner import (
    NodeSuiteError,
    _format_summary,
    merge_junit_xml,
    tags_name_pattern,
    untagged_cases,
)
from datrix_scripts.package_suites import testable_package_names
from datrix_scripts.paths import SCRIPTS_DIR
from datrix_scripts.status_tests import (
    TestResult,
    _extract_counts_from_summary_line,
    _format_result_row,
    _read_index_json,
    find_all_test_results,
    find_latest_log_file,
    parse_pytest_summary,
    parse_timestamp_from_log_file,
)
from datrix_scripts.structured_log_writer import StructuredLogWriter
from datrix_scripts.venv import get_datrix_root
from post_process_test_results import post_process_results
from run_complete import _derive_generated_project_metadata, parse_test_statistics

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
        language="python",
        platform="docker",
    )
    assert exit_code == 0, f"post_process_results returned {exit_code}, expected 0"
    index_path = run_dir / "index.json"
    assert index_path.is_file(), f"no index.json written to {run_dir}"
    return json.loads(index_path.read_text(encoding="utf-8"))


def _check_service_without_test_report_is_recorded_as_failed() -> None:
    """A service that produced no test report must FAIL the run, never vanish.

    The defect this pins: a service whose compile step failed wrote a
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
    project = datrix_root / ".generated" / "typescript" / "docker-compose" / "local" / example

    project_name, derived_example, dtrx_source = _derive_generated_project_metadata(project)

    assert derived_example == example, f"{derived_example!r} != {example!r}"
    assert (datrix_root / dtrx_source).is_file(), (
        f"derived dtrx_source {dtrx_source!r} does not resolve to a real file"
    )
    assert project_name.startswith("typescript/docker-compose/local/"), project_name


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
    project = datrix_root / ".generated2" / "typescript" / "docker-compose" / "local" / example

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


_NODE_JUNIT_WITH_PLACEHOLDER = """\
<?xml version="1.0" encoding="utf-8"?>
<testsuites>
\t<testcase name="a.test.js" time="0.08" classname="test" file="C:\\\\pkg\\\\out\\\\test\\\\a.test.js"/>
</testsuites>
"""

_NODE_JUNIT_FAILING_PLACEHOLDER = """\
<?xml version="1.0" encoding="utf-8"?>
<testsuites>
\t<testcase name="a.test.js" time="0.08" classname="test" file="C:\\\\pkg\\\\out\\\\test\\\\a.test.js">
\t\t<failure type="testCodeFailure" message="SyntaxError">stack text</failure>
\t</testcase>
</testsuites>
"""

_NODE_JUNIT_PATH_NAMED_PLACEHOLDER = """\
<?xml version="1.0" encoding="utf-8"?>
<testsuites>
\t<testcase name="C:\\\\pkg\\\\out\\\\test\\\\a.test.js" time="0.28" classname="test"/>
</testsuites>
"""

_NODE_JUNIT_FAILING_PATH_NAMED_PLACEHOLDER = """\
<?xml version="1.0" encoding="utf-8"?>
<testsuites>
\t<testcase name="C:\\\\pkg\\\\out\\\\test\\\\a.test.js" time="0.28" classname="test">
\t\t<failure type="testCodeFailure" message="SyntaxError">stack text</failure>
\t</testcase>
</testsuites>
"""

_NODE_JUNIT_TAGGED = """\
<?xml version="1.0" encoding="utf-8"?>
<testsuites>
\t<testcase name="resolves the server #lsp-client" time="0.1" classname="test" file="C:\\\\pkg\\\\out\\\\test\\\\a.test.js"/>
\t<testcase name="an untagged test" time="0.1" classname="test" file="C:\\\\pkg\\\\out\\\\test\\\\a.test.js"/>
\t<testcase name="only a tier token #slow" time="0.1" classname="test" file="C:\\\\pkg\\\\out\\\\test\\\\a.test.js"/>
\t<testsuite name="grammar suite #grammar" tests="1">
\t\t<testcase name="inherits the suite tag" time="0.1" classname="test" file="C:\\\\pkg\\\\out\\\\test\\\\a.test.js"/>
\t</testsuite>
</testsuites>
"""


def _check_node_file_placeholder_is_not_counted_as_a_test() -> None:
    """A file where no test ran reports one passing case named after the file.

    Counting it turned a name pattern that selected nothing into a green run.
    A FAILING placeholder is a file that could not load, and stays a failure.
    """
    with tempfile.TemporaryDirectory(prefix="tooling-gate-nodeplaceholder-") as tmp:
        root = Path(tmp)
        passing = root / "junit-node-001.xml"
        passing.write_text(_NODE_JUNIT_WITH_PLACEHOLDER, encoding="utf-8")
        counts = merge_junit_xml([("src/test/a.test.ts", passing)], root / "merged-1.xml", 0.1)
        assert counts == {"passed": 0, "failed": 0, "error": 0, "skipped": 0}, counts

        failing = root / "junit-node-002.xml"
        failing.write_text(_NODE_JUNIT_FAILING_PLACEHOLDER, encoding="utf-8")
        counts = merge_junit_xml([("src/test/a.test.ts", failing)], root / "merged-2.xml", 0.1)
        assert counts == {"passed": 0, "failed": 1, "error": 0, "skipped": 0}, counts

        # The same placeholder as a Node whose reporter names it by absolute path and
        # states no `file` attribute: still no test case, never an untagged one, and a
        # file that failed to load is still a failure.
        by_path = root / "junit-node-003.xml"
        by_path.write_text(_NODE_JUNIT_PATH_NAMED_PLACEHOLDER, encoding="utf-8")
        counts = merge_junit_xml([("src/test/a.test.ts", by_path)], root / "merged-3.xml", 0.1)
        assert counts == {"passed": 0, "failed": 0, "error": 0, "skipped": 0}, counts
        assert untagged_cases([("src/test/a.test.ts", by_path)]) == []

        by_path_failing = root / "junit-node-004.xml"
        by_path_failing.write_text(_NODE_JUNIT_FAILING_PATH_NAMED_PLACEHOLDER, encoding="utf-8")
        counts = merge_junit_xml(
            [("src/test/a.test.ts", by_path_failing)], root / "merged-4.xml", 0.1
        )
        assert counts == {"passed": 0, "failed": 1, "error": 0, "skipped": 0}, counts


def _check_node_untagged_cases_and_tag_pattern() -> None:
    """A Node test is tagged by a `#tag` token in its own or an ancestor suite's
    name; a tier token is not a tag; the tag pattern selects exactly the tags."""
    with tempfile.TemporaryDirectory(prefix="tooling-gate-nodetags-") as tmp:
        raw = Path(tmp) / "junit-node-001.xml"
        raw.write_text(_NODE_JUNIT_TAGGED, encoding="utf-8")
        untagged = untagged_cases([("src/test/a.test.ts", raw)])
        assert untagged == [
            "src/test/a.test.ts: an untagged test",
            "src/test/a.test.ts: only a tier token #slow",
        ], untagged

    pattern = re.compile(tags_name_pattern(["lsp-client", "grammar"]))
    assert pattern.search("resolves the server #lsp-client")
    assert pattern.search("grammar suite #grammar")
    assert not pattern.search("resolves #lsp-client-extra"), "a longer tag must not match a prefix"
    assert not pattern.search("an untagged test")
    for invalid in ("Grammar", "slow", "gram_mar"):
        try:
            tags_name_pattern([invalid])
        except NodeSuiteError:
            continue
        raise AssertionError(f"tags_name_pattern accepted invalid tag {invalid!r}")


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

    module_path = SCRIPTS_DIR / "common" / "DatrixScriptCommon.psm1"
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
# run_complete.parse_test_statistics: pytest/Jest summary lines -> counts
# ---------------------------------------------------------------------------

_ZERO_STATISTICS: dict[str, int] = {"passed": 0, "failed": 0, "errors": 0, "skipped": 0, "suiteFailures": 0}


def _check_run_complete_single_session_counts() -> None:
    """One pytest session: passed only, mixed results, and errors are each counted."""
    stats = parse_test_statistics(
        "============================== 63 passed in 17.93s =============================="
    )
    assert (stats["passed"], stats["failed"], stats["errors"], stats["skipped"]) == (63, 0, 0, 0), stats
    stats = parse_test_statistics("======= 35 passed, 2 failed, 5 skipped in 8.48s =======")
    assert (stats["passed"], stats["failed"], stats["skipped"]) == (35, 2, 5), stats
    stats = parse_test_statistics("======= 10 passed, 3 error in 2.15s =======")
    assert (stats["passed"], stats["errors"]) == (10, 3), stats


def _check_run_complete_sessions_accumulate() -> None:
    """Several pytest sessions in one output are summed, never last-one-wins."""
    two_services = (
        "============================== 3 passed in 1.16s ==============================\n"
        "===================== 63 passed, 165 deselected in 18.17s =====================\n"
        "============================== 3 passed in 1.42s ==============================\n"
        "====================== 26 passed, 71 deselected in 8.15s ======================"
    )
    assert parse_test_statistics(two_services)["passed"] == 3 + 63 + 3 + 26
    three_services = (
        "======= 10 passed, 1 failed in 5.00s =======\n"
        "======= 20 passed, 2 skipped in 3.00s =======\n"
        "======= 5 passed, 1 error in 1.00s ======="
    )
    stats = parse_test_statistics(three_services)
    assert (stats["passed"], stats["failed"], stats["skipped"], stats["errors"]) == (35, 1, 2, 1), stats


def _check_run_complete_total_format_takes_priority() -> None:
    """The unit_tests.py ``Total Passed:`` block wins over any pytest summary line."""
    output = (
        "Total Passed: 100\n"
        "Total Failed: 2\n"
        "Total Errors: 0\n"
        "Total Skipped: 5\n"
        "============================== 3 passed in 1.16s ==============================\n"
    )
    stats = parse_test_statistics(output)
    assert (stats["passed"], stats["failed"], stats["skipped"]) == (100, 2, 5), stats


def _check_run_complete_output_without_summary_is_all_zero() -> None:
    """Empty output, and output holding no summary line, both count nothing."""
    assert parse_test_statistics("") == _ZERO_STATISTICS
    logs_only = (
        "2026-03-07 10:49:04 INFO docker_build_started\n"
        "2026-03-07 10:49:23 INFO docker_build_completed\n"
    )
    assert parse_test_statistics(logs_only) == _ZERO_STATISTICS


def _check_run_complete_ignores_deselected_and_error_log_lines() -> None:
    """``deselected`` is not ``passed``, and a log line saying ERROR is not an error count."""
    stats = parse_test_statistics(
        "===================== 63 passed, 165 deselected in 18.17s ====================="
    )
    assert stats["passed"] == 63, stats
    output = (
        "2026-03-07 10:50:39,800 INFO test_database_url_resolved url=postgresql+asyncpg://localhost/db\n"
        "ERROR: Connection refused to localhost:14268\n"
        "============================== 3 passed in 1.26s =============================="
    )
    stats = parse_test_statistics(output)
    assert (stats["passed"], stats["errors"]) == (3, 0), stats


def _check_run_complete_jest_suite_failures() -> None:
    """A failing Jest suite is a suite failure when tests ran, and an error when none did."""
    stats = parse_test_statistics(
        "Test Suites: 1 failed, 50 passed, 51 total\n"
        "Tests:       2 failed, 100 passed, 102 total\n"
    )
    assert (stats["passed"], stats["failed"], stats["errors"], stats["suiteFailures"]) == (100, 2, 0, 1), stats
    stats = parse_test_statistics("Test Suites: 1 failed, 1 total\nTests:       0 total\n")
    assert (stats["passed"], stats["failed"], stats["errors"], stats["suiteFailures"]) == (0, 0, 1, 1), stats
    stats = parse_test_statistics("Test Suites: 2 failed, 2 total\n")
    assert (stats["errors"], stats["suiteFailures"]) == (2, 2), stats


# ---------------------------------------------------------------------------
# status_tests: summary-line extraction and result discovery
# ---------------------------------------------------------------------------


def _check_summary_line_counts_are_extracted() -> None:
    """A full and a short pytest summary line each yield their counts."""
    full = _extract_counts_from_summary_line(
        "============ 42 failed, 425 passed, 3 skipped, 52 errors in 5.63s ============="
    )
    assert full is not None
    assert (full["passed"], full["failed"], full["errors"], full["skipped"], full["warnings"]) == (
        425, 42, 52, 3, 0,
    ), full
    short = _extract_counts_from_summary_line("====== 13 passed, 1 skipped in 0.57s ======")
    assert short is not None
    assert (short["passed"], short["skipped"], short["failed"], short["errors"]) == (13, 1, 0, 0), short


def _check_non_summary_lines_are_rejected() -> None:
    """A log line mentioning ``error`` -- with or without a leading ``=`` run -- is not a summary."""
    log_line = (
        "tests/unit/test_cache_mixin.py::TestValidateGeneratedPythonFiles::test_valid_files "
        "ERROR datrix_cli.pipeline.cache_mixin syntax_validation_failed "
        "file=C:\\path\\bad.py line=1 error='(' was never closed"
    )
    assert _extract_counts_from_summary_line(log_line) is None
    assert _extract_counts_from_summary_line("Found 1 error error=Expecting value: line 1 column 1 (char 0)") is None


def _check_find_all_test_results_reports_a_suite_without_a_log() -> None:
    """A package with tests/ but no .test_results run is listed as NO_LOG, never omitted."""
    with tempfile.TemporaryDirectory(prefix="tooling-gate-nolog-") as tmp:
        root = Path(tmp)
        (root / "datrix-codegen-common" / "tests").mkdir(parents=True)
        results = find_all_test_results(root)
        assert len(results) == 1, results
        assert (results[0].project_name, results[0].status, results[0].total_passed) == (
            "datrix-codegen-common", "NO_LOG", 0,
        ), results[0]


def _check_find_all_test_results_reads_directory_runs() -> None:
    """A directory-format run is read through index.json, including the writer's singular ``error`` key."""
    with tempfile.TemporaryDirectory(prefix="tooling-gate-dirrun-") as tmp:
        root = Path(tmp)
        package = root / "datrix-example"
        (package / "tests").mkdir(parents=True)
        passed_run = package / ".test_results" / "test-results-20260503-191002"
        passed_run.mkdir(parents=True)
        (passed_run / "full.log").write_text("", encoding="utf-8")
        (passed_run / "index.json").write_text(json.dumps({
            "schema_version": 1,
            "result": "PASSED",
            "counts": {"passed": 25, "failed": 0, "errors": 0, "skipped": 1, "warnings": 0},
        }), encoding="utf-8")
        results = find_all_test_results(root)
        assert len(results) == 1, results
        assert (results[0].status, results[0].total_passed, results[0].total_skipped) == ("PASSED", 25, 1), results[0]

        failed_run = package / ".test_results" / "test-results-20260508-191848"
        failed_run.mkdir(parents=True)
        (failed_run / "index.json").write_text(json.dumps({
            "schema_version": 1,
            "result": "FAILED",
            "counts": {"passed": 371, "failed": 0, "error": 40, "skipped": 0},
            "phases": {"Parallel": 1, "Serial": 0},
        }), encoding="utf-8")
        results = find_all_test_results(root)
        assert len(results) == 1, results
        assert (results[0].status, results[0].total_passed, results[0].total_errors) == ("FAILED", 371, 40), results[0]


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
    ("node_file_placeholder_is_not_counted_as_a_test", _check_node_file_placeholder_is_not_counted_as_a_test),
    ("node_untagged_cases_and_tag_pattern", _check_node_untagged_cases_and_tag_pattern),
    ("node_summary_line_matches_the_shape_test_ps1_parses", _check_node_summary_line_matches_the_shape_test_ps1_parses),
    ("powershell_and_python_agree_on_testable_packages", _check_powershell_and_python_agree_on_testable_packages),
    ("node_suite_marker_is_load_bearing", _check_node_suite_marker_is_load_bearing),
    ("run_complete_single_session_counts", _check_run_complete_single_session_counts),
    ("run_complete_sessions_accumulate", _check_run_complete_sessions_accumulate),
    ("run_complete_total_format_takes_priority", _check_run_complete_total_format_takes_priority),
    ("run_complete_output_without_summary_is_all_zero", _check_run_complete_output_without_summary_is_all_zero),
    ("run_complete_ignores_deselected_and_error_log_lines", _check_run_complete_ignores_deselected_and_error_log_lines),
    ("run_complete_jest_suite_failures", _check_run_complete_jest_suite_failures),
    ("summary_line_counts_are_extracted", _check_summary_line_counts_are_extracted),
    ("non_summary_lines_are_rejected", _check_non_summary_lines_are_rejected),
    ("find_all_test_results_reports_a_suite_without_a_log", _check_find_all_test_results_reports_a_suite_without_a_log),
    ("find_all_test_results_reads_directory_runs", _check_find_all_test_results_reads_directory_runs),
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
            "Repo-level gate for the test tooling's parsers (compare_tests.py run discovery/comparison, "
            "status_tests.py index.json/log parsing, run_complete.py summary-line statistics)."
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
