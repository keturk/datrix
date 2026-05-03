"""
Unit tests for status_tests.py (pytest summary line parsing).
"""

import sys
from pathlib import Path

# Ensure library is on path so status_tests can be imported (test.status_tests)
_library_dir = Path(__file__).resolve().parent.parent
if str(_library_dir) not in sys.path:
    sys.path.insert(0, str(_library_dir))

from test.status_tests import _extract_counts_from_summary_line, find_all_test_results


def test_extract_counts_from_summary_line_real_summary_returns_counts() -> None:
    """A real pytest summary line returns the correct counts dict."""
    line = "============ 42 failed, 425 passed, 3 skipped, 52 errors in 5.63s ============="
    result = _extract_counts_from_summary_line(line)
    assert result is not None
    assert result["passed"] == 425
    assert result["failed"] == 42
    assert result["errors"] == 52
    assert result["skipped"] == 3
    assert result["warnings"] == 0


def test_extract_counts_from_summary_line_short_summary() -> None:
    """A short pytest summary line (passed/skipped only) returns correct counts."""
    line = "====== 13 passed, 1 skipped in 0.57s ======"
    result = _extract_counts_from_summary_line(line)
    assert result is not None
    assert result["passed"] == 13
    assert result["skipped"] == 1
    assert result["failed"] == 0
    assert result["errors"] == 0


def test_extract_counts_from_summary_line_log_line_with_error_rejected() -> None:
    """A log line containing 'line=1 error=...' is rejected (not a summary)."""
    line = (
        "tests/unit/test_cache_mixin.py::TestValidateGeneratedPythonFiles::test_valid_files "
        "ERROR datrix_cli.pipeline.cache_mixin syntax_validation_failed "
        "file=C:\\path\\bad.py line=1 error='(' was never closed"
    )
    result = _extract_counts_from_summary_line(line)
    assert result is None


def test_find_all_test_results_includes_project_without_test_results_log(
 tmp_path: Path,
) -> None:
 """Projects with tests/ but no .test_results log appear as NO_LOG (not omitted)."""
 root = tmp_path
 pkg = root / "datrix-codegen-common"
 (pkg / "tests").mkdir(parents=True)
 results = find_all_test_results(root)
 assert len(results) == 1
 assert results[0].project_name == "datrix-codegen-common"
 assert results[0].status == "NO_LOG"
 assert results[0].total_passed == 0


def test_extract_counts_from_summary_line_no_leading_equals_rejected() -> None:
    """A line with digits and 'error' but no leading '=' run is rejected."""
    line = "Found 1 error error=Expecting value: line 1 column 1 (char 0)"
    result = _extract_counts_from_summary_line(line)
    assert result is None
