"""Tests for compare_tests.py single-.test_results comparison behavior."""

from __future__ import annotations

import json
import sys
from pathlib import Path

_library_dir = Path(__file__).resolve().parent.parent.parent
if str(_library_dir) not in sys.path:
    sys.path.insert(0, str(_library_dir))

from test.compare_tests import build_service_comparisons, find_runs, parse_unit_run


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


def test_find_runs_compares_direct_child_unit_runs_only(tmp_path: Path) -> None:
    root = tmp_path / ".test_results"
    first = root / "unit-tests-20260511-100000"
    second = root / "unit-tests-20260511-110000"
    nested = root / "archive" / "unit-tests-20260511-120000"

    _write_junit(first, "orders_service", tests=10)
    _write_junit(second, "orders_service", tests=10, failures=2)
    _write_junit(nested, "orders_service", tests=10, failures=9)

    unit_runs = find_runs(root, "unit")
    comparisons = build_service_comparisons(unit_runs)

    assert [run.folder.name for run in unit_runs] == [
        "unit-tests-20260511-100000",
        "unit-tests-20260511-110000",
    ]
    assert len(comparisons) == 1
    assert comparisons[0].service == "orders_service"
    assert comparisons[0].change == "REGRESSED"
    assert comparisons[0].history == ["OK", "FAIL"]


def test_unit_summary_log_fallback_parses_service_rows(tmp_path: Path) -> None:
    run_dir = tmp_path / ".test_results" / "unit-tests-20260511-100000"
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


def test_deploy_runs_are_discovered_and_compared_separately(tmp_path: Path) -> None:
    root = tmp_path / ".test_results"
    unit_run = root / "unit-tests-20260511-100000"
    deploy_run = root / "deploy-test-20260511-100000"
    _write_junit(unit_run, "orders_service", tests=4)
    deploy_run.mkdir(parents=True)
    (deploy_run / "index.json").write_text(
        json.dumps(
            {
                "project_path": str(tmp_path),
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
