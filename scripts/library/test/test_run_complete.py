"""Unit tests for run_complete.parse_test_statistics()."""

import sys
from pathlib import Path

# Ensure library is on path so run_complete can be imported (test.run_complete)
_library_dir = Path(__file__).resolve().parent.parent
if str(_library_dir) not in sys.path:
    sys.path.insert(0, str(_library_dir))

from test.run_complete import parse_test_statistics


def test_single_pytest_session_passed_only() -> None:
    """A single pytest session with only passed tests."""
    output = "============================== 63 passed in 17.93s =============================="
    stats = parse_test_statistics(output)
    assert stats["passed"] == 63
    assert stats["failed"] == 0
    assert stats["errors"] == 0
    assert stats["skipped"] == 0


def test_single_pytest_session_mixed_results() -> None:
    """A single pytest session with passed, failed, and skipped."""
    output = "======= 35 passed, 2 failed, 5 skipped in 8.48s ======="
    stats = parse_test_statistics(output)
    assert stats["passed"] == 35
    assert stats["failed"] == 2
    assert stats["skipped"] == 5


def test_single_pytest_session_with_errors() -> None:
    """A single pytest session with errors."""
    output = "======= 10 passed, 3 error in 2.15s ======="
    stats = parse_test_statistics(output)
    assert stats["passed"] == 10
    assert stats["errors"] == 3


def test_multi_session_accumulation_two_services() -> None:
    """Two pytest sessions should accumulate counts (the core bug fix).

    Simulates V10 deployment output: BookService (3+63) + MemberService (3+26) = 95.
    """
    output = (
        "============================== 3 passed in 1.16s ==============================\n"
        "===================== 63 passed, 165 deselected in 18.17s =====================\n"
        "============================== 3 passed in 1.42s ==============================\n"
        "====================== 26 passed, 71 deselected in 8.15s ======================"
    )
    stats = parse_test_statistics(output)
    assert stats["passed"] == 3 + 63 + 3 + 26  # 95, NOT 26


def test_multi_session_accumulation_three_services() -> None:
    """Three pytest sessions with mixed results accumulate correctly."""
    output = (
        "======= 10 passed, 1 failed in 5.00s =======\n"
        "======= 20 passed, 2 skipped in 3.00s =======\n"
        "======= 5 passed, 1 error in 1.00s ======="
    )
    stats = parse_test_statistics(output)
    assert stats["passed"] == 35
    assert stats["failed"] == 1
    assert stats["skipped"] == 2
    assert stats["errors"] == 1


def test_run_tests_total_format_takes_priority() -> None:
    """run_tests.py 'Total Passed: X' format is used when present, skipping pytest lines."""
    output = (
        "Total Passed: 100\n"
        "Total Failed: 2\n"
        "Total Errors: 0\n"
        "Total Skipped: 5\n"
        "============================== 3 passed in 1.16s ==============================\n"
    )
    stats = parse_test_statistics(output)
    assert stats["passed"] == 100  # From "Total Passed:", not from pytest summary
    assert stats["failed"] == 2
    assert stats["skipped"] == 5


def test_empty_output() -> None:
    """Empty output returns all zeros."""
    stats = parse_test_statistics("")
    assert stats == {"passed": 0, "failed": 0, "errors": 0, "skipped": 0}


def test_non_pytest_output() -> None:
    """Output without pytest summary lines returns all zeros."""
    output = (
        "2026-03-07 10:49:04 INFO docker_build_started\n"
        "2026-03-07 10:49:23 INFO docker_build_completed\n"
    )
    stats = parse_test_statistics(output)
    assert stats == {"passed": 0, "failed": 0, "errors": 0, "skipped": 0}


def test_deselected_not_counted_as_passed() -> None:
    """The 'deselected' count is not confused with 'passed'."""
    output = "===================== 63 passed, 165 deselected in 18.17s ====================="
    stats = parse_test_statistics(output)
    assert stats["passed"] == 63  # NOT 165


def test_log_lines_with_error_word_not_matched() -> None:
    """Log lines containing 'error' but not formatted as pytest summary are ignored."""
    output = (
        "2026-03-07 10:50:39,800 INFO test_database_url_resolved url=postgresql+asyncpg://localhost/db\n"
        "ERROR: Connection refused to localhost:14268\n"
        "============================== 3 passed in 1.26s =============================="
    )
    stats = parse_test_statistics(output)
    assert stats["passed"] == 3
    assert stats["errors"] == 0  # The ERROR log line should not be parsed
