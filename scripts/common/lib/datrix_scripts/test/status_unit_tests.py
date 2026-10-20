"""The status of the latest unit-test run of every generated project, behind ``test/status-unit-tests.ps1``.

Searches ``<workspace>/.generated`` (or its ``<language>`` subtree with ``--language``) for
``.test_results`` folders, reads the ``unit-tests-summary.log`` of each folder's latest
``unit-tests-<date>-<time>`` run, and prints one status block per project and a summary, with the
log folders of the failing projects.
"""

from __future__ import annotations

import argparse
import contextlib
import io
import logging
import re
import sys
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Final

from datrix_scripts.gate_harness import EXIT_PASS, EXIT_VIOLATION, configure_logging, write_files
from datrix_scripts.paths import WORKSPACE_DIR
from datrix_scripts.test_result_walk import (
    iter_dot_test_results_dirs,
    resolve_language_root,
    resolve_unit_test_summary_log,
)

logger = logging.getLogger(__name__)

MODULE: Final = "datrix_scripts.test.status_unit_tests"
WRAPPER: Final = "status-unit-tests"
GENERATED_ROOT: Final = WORKSPACE_DIR / ".generated"

STATUS_PASSED: Final = "PASSED"
STATUS_FAILED: Final = "FAILED"
STATUS_UNKNOWN: Final = "UNKNOWN"
RUN_FOLDER_PREFIX: Final = "unit-tests-"
_RUN_FOLDER_RE: Final = re.compile(r"unit-tests-(\d{8})-(\d{6})")
_RUN_TIMESTAMP_FORMAT: Final = "%Y%m%d%H%M%S"
_PROJECT_RE: Final = re.compile(r"Project:\s+(.+)")
_TIMESTAMP_RE: Final = re.compile(r"Timestamp:\s+(.+)")
_PASSED_RE: Final = re.compile(r"Total Passed:\s+(\d+)")
_FAILED_RE: Final = re.compile(r"Total Failed:\s+(\d+)")
_ERRORS_RE: Final = re.compile(r"Total Errors:\s+(\d+)")
#: Markers the Python unit-test runner writes; a TypeScript summary carries totals only.
_PASSED_MARKER: Final = "All tests PASSED!"
_FAILED_MARKER: Final = "Tests FAILED!"
_NO_TESTS_MARKER: Final = "NO TESTS COLLECTED"
_RULE: Final = "=" * 100


class Colors:
    """ANSI color codes for terminal output."""

    GREEN: Final = "\033[92m"
    RED: Final = "\033[91m"
    YELLOW: Final = "\033[93m"
    CYAN: Final = "\033[96m"
    BOLD: Final = "\033[1m"
    RESET: Final = "\033[0m"
    GRAY: Final = "\033[90m"

    @staticmethod
    def is_color_supported() -> bool:
        """Windows 10+ consoles render ANSI colors; elsewhere only a terminal does."""
        if sys.platform == "win32":
            return True
        return hasattr(sys.stdout, "isatty") and sys.stdout.isatty()


@dataclass
class TestResult:
    """The latest unit-test run of one project."""

    __test__ = False  # Not a pytest test class, whatever its name.

    project_path: str
    status: str
    total_passed: int
    total_failed: int
    total_errors: int
    timestamp: str
    log_file: str


def parse_timestamp_from_folder(folder_name: str) -> datetime | None:
    """The run time a folder name like ``unit-tests-20260107-161027`` carries; None when it carries none."""
    match = _RUN_FOLDER_RE.search(folder_name)
    if match is None:
        return None
    try:
        return datetime.strptime(match.group(1) + match.group(2), _RUN_TIMESTAMP_FORMAT)
    except ValueError:
        return None


def find_latest_test_folder(test_results_dir: Path) -> Path | None:
    """The newest ``unit-tests-*`` folder under *test_results_dir*; None when it holds none."""
    runs = [
        (timestamp, item)
        for item in test_results_dir.iterdir()
        if item.is_dir() and item.name.startswith(RUN_FOLDER_PREFIX)
        and (timestamp := parse_timestamp_from_folder(item.name)) is not None
    ]
    if not runs:
        return None
    return max(runs, key=lambda run: run[0])[1]


def _first_int(pattern: re.Pattern[str], content: str) -> int:
    match = pattern.search(content)
    return int(match.group(1)) if match else 0


def _first_text(pattern: re.Pattern[str], content: str) -> str:
    match = pattern.search(content)
    return match.group(1).strip() if match else ""


def summary_status(content: str, passed: int, failed: int, errors: int) -> str:
    """The run's status: the runner's explicit marker when present, else read from the totals."""
    if _PASSED_MARKER in content:
        return STATUS_PASSED
    if _FAILED_MARKER in content or failed > 0 or errors > 0:
        return STATUS_FAILED
    if passed > 0:
        return STATUS_PASSED
    if _NO_TESTS_MARKER in content:
        return STATUS_FAILED
    return STATUS_UNKNOWN


def parse_summary_log(log_file: Path) -> TestResult:
    """The result a ``unit-tests-summary.log`` records; UNKNOWN when it cannot be read."""
    content = ""
    try:
        content = log_file.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as exc:
        print(f"Warning: Could not parse {log_file}: {exc}")
    passed = _first_int(_PASSED_RE, content)
    failed = _first_int(_FAILED_RE, content)
    errors = _first_int(_ERRORS_RE, content)
    return TestResult(
        project_path=_first_text(_PROJECT_RE, content) or str(log_file.parent.parent.parent.absolute()),
        status=summary_status(content, passed, failed, errors),
        total_passed=passed,
        total_failed=failed,
        total_errors=errors,
        timestamp=_first_text(_TIMESTAMP_RE, content),
        log_file=str(log_file),
    )


def find_all_test_results(root_dir: Path) -> list[TestResult]:
    """The latest run of every project with a ``.test_results`` folder under *root_dir*."""
    results: list[TestResult] = []
    for test_results_dir in iter_dot_test_results_dirs(root_dir):
        latest_folder = find_latest_test_folder(test_results_dir)
        if latest_folder is None:
            continue
        summary_log = resolve_unit_test_summary_log(latest_folder)
        if summary_log is None:
            logger.debug("No summary log in %s", latest_folder)
            continue
        result = parse_summary_log(summary_log)
        result.project_path = str(test_results_dir.parent.absolute())
        results.append(result)
    return results


class _Painter:
    def __init__(self) -> None:
        self.enabled = Colors.is_color_supported()

    def __call__(self, text: str, color: str) -> str:
        return f"{color}{text}{Colors.RESET}" if self.enabled else text


_STATUS_STYLE: Final = {STATUS_PASSED: (Colors.GREEN, "+"), STATUS_FAILED: (Colors.RED, "x")}
_UNKNOWN_STYLE: Final = (Colors.YELLOW, "?")


def _print_failed_counts(result: TestResult, paint: _Painter) -> None:
    parts = [
        paint(f"{label}: {count}", color)
        for label, count, color in (
            ("Passed", result.total_passed, Colors.GREEN),
            ("Failed", result.total_failed, Colors.RED),
            ("Errors", result.total_errors, Colors.YELLOW),
        )
        if count > 0
    ]
    if parts:
        print(f" {', '.join(parts)}")


def _print_result(result: TestResult, paint: _Painter) -> None:
    color, symbol = _STATUS_STYLE[result.status] if result.status in _STATUS_STYLE else _UNKNOWN_STYLE
    print(paint(f"{symbol} [{result.status}] {result.project_path}", Colors.BOLD + color))
    if result.status == STATUS_PASSED:
        print(paint(f" Passed: {result.total_passed}", Colors.GREEN))
    elif result.status == STATUS_FAILED:
        _print_failed_counts(result, paint)
    if result.timestamp:
        print(paint(f" Timestamp: {result.timestamp}", Colors.GRAY))
    print()


def _print_summary(results: Sequence[TestResult], paint: _Painter) -> None:
    print(_RULE)
    print(paint("SUMMARY", Colors.BOLD + Colors.CYAN))
    print(_RULE)
    print(f"Total Projects: {len(results)}")
    for label, status, color in (
        ("Passed", STATUS_PASSED, Colors.GREEN),
        ("Failed", STATUS_FAILED, Colors.RED),
    ):
        count = sum(1 for result in results if result.status == status)
        if count > 0:
            print(paint(f" {label}: {count}", color))
    unknown = sum(1 for result in results if result.status not in _STATUS_STYLE)
    if unknown > 0:
        print(paint(f" Unknown: {unknown}", Colors.YELLOW))
    failed = [result for result in results if result.status == STATUS_FAILED]
    if failed:
        print()
        print(paint("LOG FOLDERS (failing projects — contains summary and detail logs)", Colors.BOLD + Colors.RED))
        for result in failed:
            print(f" {Path(result.log_file).parent}")
    print(_RULE)


def print_results(results: Sequence[TestResult]) -> None:
    """Print one status block per result, then the summary."""
    if not results:
        print("No test results found.")
        return
    paint = _Painter()
    print(_RULE)
    print(paint("TEST STATUS REPORT", Colors.BOLD + Colors.CYAN))
    print(_RULE)
    print()
    for result in results:
        _print_result(result, paint)
    _print_summary(results, paint)


def report(root: Path, language: str | None) -> int:
    """Print the status of every project under *root* (its *language* subtree when given); the exit code."""
    search_root = root
    if language:
        try:
            search_root = resolve_language_root(root, language)
        except ValueError as exc:
            print(f"Error: {exc}", file=sys.stderr)
            return EXIT_VIOLATION
    print(f"Searching for test results in: {search_root}")
    print()
    print_results(sorted(find_all_test_results(search_root), key=lambda result: result.project_path))
    return EXIT_PASS


def build_parser() -> argparse.ArgumentParser:
    """The options ``test/status-unit-tests.ps1`` passes (each wrapper parameter as ``--kebab-name``)."""
    parser = argparse.ArgumentParser(
        prog="status-unit-tests",
        description=f"Report the latest unit-test run of every generated project under {GENERATED_ROOT}.",
        allow_abbrev=False,
    )
    parser.add_argument(
        "--language", "-L",
        help="report only on the <.generated>/<language> subtree (validated against the language folders present)",
    )
    parser.add_argument("--dbg", action="store_true", help="log debug detail to stderr")
    parser.add_argument("--self-test", action="store_true", help="run this module's self-test")
    return parser


_PLANTED_PASSED: Final = "Project: x\nTimestamp: 2026-01-07 16:10:27\nTotal Passed: 4\nAll tests PASSED!\n"
_PLANTED_TOTALS_FAILED: Final = "Total Passed: 3\nTotal Failed: 1\nTotal Errors: 2\n"


def _check_folder_timestamps() -> None:
    assert parse_timestamp_from_folder("unit-tests-20260107-161027") == datetime(2026, 1, 7, 16, 10, 27)
    assert parse_timestamp_from_folder("unit-tests-20261399-000000") is None, "an impossible date parsed"
    assert parse_timestamp_from_folder("deploy-tests-20260107-161027") is None, "a non-unit folder parsed"


def _check_summary_status() -> None:
    cases = (
        (_PLANTED_PASSED, STATUS_PASSED),
        (_PLANTED_TOTALS_FAILED, STATUS_FAILED),
        ("Total Passed: 2\n", STATUS_PASSED),
        ("NO TESTS COLLECTED\n", STATUS_FAILED),
        ("", STATUS_UNKNOWN),
    )
    for content, expected in cases:
        status = summary_status(content, _first_int(_PASSED_RE, content), _first_int(_FAILED_RE, content),
                                _first_int(_ERRORS_RE, content))
        assert status == expected, f"{content!r} read as {status}, expected {expected}"


def _check_planted_tree() -> None:
    with TemporaryDirectory() as temp:
        root = Path(temp)
        write_files(root, {
            "python/docker/shop/.test_results/unit-tests-20260101-000000/unit-tests-summary.log": _PLANTED_TOTALS_FAILED,
            "python/docker/shop/.test_results/unit-tests-20260107-161027/unit-tests-summary.log": _PLANTED_PASSED,
            "python/docker/shop/src/.test_results/unit-tests-20260107-161027/unit-tests-summary.log": _PLANTED_PASSED,
            "python/docker/orders/.test_results/unit-tests-20260107-161027/unit-tests-summary.log": _PLANTED_TOTALS_FAILED,
        })
        results = {Path(result.project_path).name: result for result in find_all_test_results(root)}
        assert set(results) == {"shop", "orders"}, f"found {sorted(results)}; a src/ tree must not be walked"
        assert results["shop"].status == STATUS_PASSED, "the latest run of shop is not the one read"
        assert (results["orders"].total_failed, results["orders"].total_errors) == (1, 2)
        with contextlib.redirect_stderr(io.StringIO()):  # The refusal message of a case refused on purpose.
            refused = report(root, "nosuchlang")
        assert refused == EXIT_VIOLATION, "an unknown language was not refused"


def run_self_test(parser: argparse.ArgumentParser) -> int:
    from datrix_scripts.test.wrappers import run_self_test as run_wrapper_self_test

    checks = [_check_folder_timestamps, _check_summary_status, _check_planted_tree]
    return run_wrapper_self_test(checks, wrapper=WRAPPER, module=MODULE, parser=parser)


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    configure_logging(args.dbg)
    if args.self_test:
        return run_self_test(parser)
    return report(GENERATED_ROOT, args.language)


if __name__ == "__main__":
    sys.exit(main())
