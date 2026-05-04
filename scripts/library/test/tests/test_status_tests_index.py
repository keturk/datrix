"""
Unit tests for status_tests.py directory-based test result discovery and index.json parsing.
"""

import json
import sys
from pathlib import Path

# Ensure library is on path so status_tests can be imported (test.status_tests)
_library_dir = Path(__file__).resolve().parent.parent.parent
if str(_library_dir) not in sys.path:
    sys.path.insert(0, str(_library_dir))

from test.status_tests import (
    _read_index_json,
    find_latest_log_file,
    parse_pytest_summary,
    parse_timestamp_from_log_file,
)


def _make_run_dir(tmp_path: Path, timestamp: str = "20260503-191002") -> Path:
    """Create a project/.test_results/test-results-TIMESTAMP/ structure."""
    project = tmp_path / "datrix-example"
    run_dir = project / ".test_results" / f"test-results-{timestamp}"
    run_dir.mkdir(parents=True)
    return run_dir


def _write_index(run_dir: Path, data: dict) -> Path:
    """Write an index.json into the run directory."""
    index_path = run_dir / "index.json"
    index_path.write_text(json.dumps(data), encoding="utf-8")
    return index_path


def _write_full_log(run_dir: Path, content: str = "") -> Path:
    """Write a full.log into the run directory."""
    full_log = run_dir / "full.log"
    full_log.write_text(content, encoding="utf-8")
    return full_log


# --- Test _read_index_json ---


def test_read_index_json_valid_counts(tmp_path: Path) -> None:
    """A valid index.json with counts returns a TestResult with correct values."""
    run_dir = _make_run_dir(tmp_path)
    _write_full_log(run_dir)
    index_path = _write_index(run_dir, {
        "schema_version": 1,
        "result": "FAILED",
        "counts": {
            "passed": 42,
            "failed": 3,
            "errors": 1,
            "skipped": 5,
            "warnings": 2,
        },
    })

    result = _read_index_json(index_path)

    assert result is not None
    assert result.status == "FAILED"
    assert result.total_passed == 42
    assert result.total_failed == 3
    assert result.total_errors == 1
    assert result.total_skipped == 5
    assert result.total_warnings == 2
    assert result.project_name == "datrix-example"
    assert "2026-05-03 19:10:02" == result.timestamp


def test_read_index_json_passed_result(tmp_path: Path) -> None:
    """A PASSED result is correctly reported."""
    run_dir = _make_run_dir(tmp_path)
    _write_full_log(run_dir)
    index_path = _write_index(run_dir, {
        "schema_version": 1,
        "result": "PASSED",
        "counts": {
            "passed": 100,
            "failed": 0,
            "errors": 0,
            "skipped": 2,
            "warnings": 0,
        },
    })

    result = _read_index_json(index_path)

    assert result is not None
    assert result.status == "PASSED"
    assert result.total_passed == 100


def test_read_index_json_incomplete_returns_none(tmp_path: Path) -> None:
    """An INCOMPLETE result returns None so caller falls back to full.log."""
    run_dir = _make_run_dir(tmp_path)
    index_path = _write_index(run_dir, {
        "schema_version": 1,
        "result": "INCOMPLETE",
        "counts": None,
        "note": "No JUnit XML produced",
    })

    result = _read_index_json(index_path)
    assert result is None


def test_read_index_json_no_counts_returns_none(tmp_path: Path) -> None:
    """Missing counts field returns None (INCOMPLETE equivalent)."""
    run_dir = _make_run_dir(tmp_path)
    index_path = _write_index(run_dir, {
        "schema_version": 1,
        "result": "INCOMPLETE",
    })

    result = _read_index_json(index_path)
    assert result is None


def test_read_index_json_corrupt_returns_none(tmp_path: Path) -> None:
    """Corrupt JSON returns None (caller falls back)."""
    run_dir = _make_run_dir(tmp_path)
    index_path = run_dir / "index.json"
    index_path.write_text("not valid json {{{", encoding="utf-8")

    result = _read_index_json(index_path)
    assert result is None


# --- Test find_latest_log_file ---


def test_find_latest_log_file_directory_with_index_json(tmp_path: Path) -> None:
    """Directory format with index.json is found and preferred."""
    run_dir = _make_run_dir(tmp_path)
    index_path = _write_index(run_dir, {"counts": {"passed": 1}})
    test_results_dir = run_dir.parent

    result = find_latest_log_file(test_results_dir)

    assert result is not None
    assert result == index_path


def test_find_latest_log_file_directory_with_full_log_only(tmp_path: Path) -> None:
    """Directory without index.json but with full.log falls back to full.log."""
    run_dir = _make_run_dir(tmp_path)
    full_log = _write_full_log(run_dir, "====== 5 passed in 1.0s ======\n")
    test_results_dir = run_dir.parent

    result = find_latest_log_file(test_results_dir)

    assert result is not None
    assert result == full_log


def test_find_latest_log_file_legacy_flat_file(tmp_path: Path) -> None:
    """Legacy flat test-results-*.log file is found when no directories exist."""
    project = tmp_path / "datrix-example"
    test_results_dir = project / ".test_results"
    test_results_dir.mkdir(parents=True)
    legacy_log = test_results_dir / "test-results-20260503-191002.log"
    legacy_log.write_text("====== 10 passed in 2.0s ======\n", encoding="utf-8")

    result = find_latest_log_file(test_results_dir)

    assert result is not None
    assert result == legacy_log


def test_find_latest_log_file_directory_preferred_over_legacy(tmp_path: Path) -> None:
    """When both directory and legacy file exist, directory is preferred."""
    project = tmp_path / "datrix-example"
    test_results_dir = project / ".test_results"
    test_results_dir.mkdir(parents=True)

    # Legacy file (older timestamp)
    legacy_log = test_results_dir / "test-results-20260502-100000.log"
    legacy_log.write_text("====== 5 passed in 1.0s ======\n", encoding="utf-8")

    # New directory (newer timestamp)
    run_dir = test_results_dir / "test-results-20260503-191002"
    run_dir.mkdir()
    index_path = _write_index(run_dir, {"counts": {"passed": 10}})

    result = find_latest_log_file(test_results_dir)

    assert result is not None
    assert result == index_path


def test_find_latest_log_file_empty_dir_returns_none(tmp_path: Path) -> None:
    """Empty .test_results directory returns None."""
    test_results_dir = tmp_path / ".test_results"
    test_results_dir.mkdir()

    result = find_latest_log_file(test_results_dir)
    assert result is None


# --- Test parse_timestamp_from_log_file ---


def test_parse_timestamp_directory_name() -> None:
    """Timestamp is parsed from directory name (no .log suffix)."""
    result = parse_timestamp_from_log_file("test-results-20260503-191002")
    assert result is not None
    assert result.year == 2026
    assert result.month == 5
    assert result.day == 3
    assert result.hour == 19
    assert result.minute == 10
    assert result.second == 2


def test_parse_timestamp_legacy_file_name() -> None:
    """Timestamp is parsed from legacy .log filename."""
    result = parse_timestamp_from_log_file("test-results-20260503-191002.log")
    assert result is not None
    assert result.year == 2026
    assert result.month == 5
    assert result.day == 3


def test_parse_timestamp_invalid_name() -> None:
    """Invalid name returns None."""
    result = parse_timestamp_from_log_file("not-a-test-result")
    assert result is None


# --- Test parse_pytest_summary with index.json ---


def test_parse_pytest_summary_from_index_json(tmp_path: Path) -> None:
    """parse_pytest_summary reads index.json and returns structured counts."""
    run_dir = _make_run_dir(tmp_path)
    _write_full_log(run_dir)
    index_path = _write_index(run_dir, {
        "schema_version": 1,
        "result": "PASSED",
        "counts": {
            "passed": 50,
            "failed": 0,
            "errors": 0,
            "skipped": 1,
            "warnings": 0,
        },
    })

    result = parse_pytest_summary(index_path)

    assert result.status == "PASSED"
    assert result.total_passed == 50
    assert result.total_skipped == 1
    assert result.project_name == "datrix-example"


def test_parse_pytest_summary_index_json_incomplete_falls_back_to_full_log(
    tmp_path: Path,
) -> None:
    """INCOMPLETE index.json falls back to parsing full.log."""
    run_dir = _make_run_dir(tmp_path)
    _write_full_log(run_dir, "====== 8 passed, 2 failed in 3.0s ======\n")
    _write_index(run_dir, {
        "schema_version": 1,
        "result": "INCOMPLETE",
        "counts": None,
    })

    index_path = run_dir / "index.json"
    result = parse_pytest_summary(index_path)

    assert result.status == "FAILED"
    assert result.total_passed == 8
    assert result.total_failed == 2


def test_parse_pytest_summary_full_log_in_directory(tmp_path: Path) -> None:
    """full.log inside a run directory is parsed correctly (project path derived)."""
    run_dir = _make_run_dir(tmp_path)
    full_log = _write_full_log(run_dir, "====== 15 passed in 1.5s ======\n")

    result = parse_pytest_summary(full_log)

    assert result.status == "PASSED"
    assert result.total_passed == 15
    assert result.project_name == "datrix-example"


def test_parse_pytest_summary_legacy_flat_file(tmp_path: Path) -> None:
    """Legacy flat .log file is still parsed correctly."""
    project = tmp_path / "datrix-example"
    test_results_dir = project / ".test_results"
    test_results_dir.mkdir(parents=True)
    legacy_log = test_results_dir / "test-results-20260503-191002.log"
    legacy_log.write_text("====== 20 passed, 1 skipped in 2.0s ======\n", encoding="utf-8")

    result = parse_pytest_summary(legacy_log)

    assert result.status == "PASSED"
    assert result.total_passed == 20
    assert result.total_skipped == 1
    assert result.project_name == "datrix-example"
