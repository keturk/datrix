"""
Script to check test status across multiple test result folders.

This script recursively searches for .test_results folders, finds the latest
unit-tests-* folder, and reports the test status for each project.
"""

import argparse
import re
import sys
from pathlib import Path
from datetime import datetime
from typing import List, Tuple, Optional
from dataclasses import dataclass

# Add library directory to sys.path to import from shared
library_dir = Path(__file__).parent.parent
if library_dir.exists() and str(library_dir) not in sys.path:
    sys.path.insert(0, str(library_dir))

# Same-directory helper (avoid `import test.*` — conflicts with stdlib test package)
_status_script_dir = Path(__file__).resolve().parent
if str(_status_script_dir) not in sys.path:
    sys.path.insert(0, str(_status_script_dir))
from test_result_walk import iter_dot_test_results_dirs, resolve_unit_test_summary_log


# ANSI color codes
class Colors:
    """ANSI color codes for terminal output."""
    GREEN = '\033[92m'
    RED = '\033[91m'
    YELLOW = '\033[93m'
    CYAN = '\033[96m'
    BOLD = '\033[1m'
    RESET = '\033[0m'
    GRAY = '\033[90m'

    @staticmethod
    def is_color_supported() -> bool:
        """Check if the terminal supports color output."""
        # Windows 10+ supports ANSI colors in PowerShell and cmd
        if sys.platform == 'win32':
            return True
        # Unix-like systems typically support colors
        return hasattr(sys.stdout, 'isatty') and sys.stdout.isatty()


@dataclass
class TestResult:
    """Test result information for a project."""
    project_path: str
    status: str # 'PASSED', 'FAILED', or 'UNKNOWN'
    total_passed: int
    total_failed: int
    total_errors: int
    timestamp: str
    log_file: str


def parse_timestamp_from_folder(folder_name: str) -> Optional[datetime]:
    """
    Parse timestamp from folder name like 'unit-tests-20260107-161027'.

    Args:
        folder_name: The folder name to parse

    Returns:
        datetime object or None if parsing fails
    """
    match = re.search(r'unit-tests-(\d{8})-(\d{6})', folder_name)
    if match:
        date_str = match.group(1)  # YYYYMMDD
        time_str = match.group(2)  # HHMMSS
        try:
            return datetime.strptime(f"{date_str}{time_str}", "%Y%m%d%H%M%S")
        except ValueError:
            return None
    return None


def find_latest_test_folder(test_results_dir: Path) -> Optional[Path]:
    """
    Find the latest unit-tests-* folder based on timestamp.

    Args:
        test_results_dir: Path to .test_results folder

        Returns:
            Path to the latest unit-tests-* folder or None if not found
    """
    run_test_folders = []

    for item in test_results_dir.iterdir():
        if item.is_dir() and item.name.startswith('unit-tests-'):
            timestamp = parse_timestamp_from_folder(item.name)
            if timestamp:
                run_test_folders.append((timestamp, item))

    if not run_test_folders:
        return None

    # Sort by timestamp descending and return the latest
    run_test_folders.sort(key=lambda x: x[0], reverse=True)
    return run_test_folders[0][1]


def parse_summary_log(log_file: Path) -> TestResult:
    """
    Parse unit test summary log (unit-tests-summary.log or legacy summary.log).

    Args:
        log_file: Path to the summary log file

    Returns:
        TestResult object with parsed information
    """
    project_path = ""
    timestamp = ""
    total_passed = 0
    total_failed = 0
    total_errors = 0
    status = "UNKNOWN"

    try:
        with open(log_file, 'r', encoding='utf-8') as f:
            content = f.read()

        # Extract project path
        project_match = re.search(r'Project:\s+(.+)', content)
        if project_match:
            project_path = project_match.group(1).strip()

        # Extract timestamp
        timestamp_match = re.search(r'Timestamp:\s+(.+)', content)
        if timestamp_match:
            timestamp = timestamp_match.group(1).strip()

        # Extract totals
        passed_match = re.search(r'Total Passed:\s+(\d+)', content)
        if passed_match:
            total_passed = int(passed_match.group(1))

        failed_match = re.search(r'Total Failed:\s+(\d+)', content)
        if failed_match:
            total_failed = int(failed_match.group(1))

        errors_match = re.search(r'Total Errors:\s+(\d+)', content)
        if errors_match:
            total_errors = int(errors_match.group(1))

        # Determine status: explicit markers (Python unit_tests.py) or totals-only
        # (legacy TypeScript summary.log from run_complete.py).
        if 'All tests PASSED!' in content:
            status = 'PASSED'
        elif 'Tests FAILED!' in content:
            status = 'FAILED'
        elif total_failed > 0 or total_errors > 0:
            status = 'FAILED'
        elif total_passed > 0:
            status = 'PASSED'
        elif 'NO TESTS COLLECTED' in content:
            status = 'FAILED'

    except Exception as e:
        print(f"Warning: Could not parse {log_file}: {e}")

    if not project_path:
        project_path = str(log_file.parent.parent.parent.absolute())

    return TestResult(
        project_path=project_path,
        status=status,
        total_passed=total_passed,
        total_failed=total_failed,
        total_errors=total_errors,
        timestamp=timestamp,
        log_file=str(log_file),
    )


def find_all_test_results(root_dir: Path) -> List[TestResult]:
    """
    Recursively find all .test_results folders and extract their status.

    Args:
        root_dir: Root directory to start searching from

        Returns:
            List of TestResult objects
    """
    results = []

    for test_results_dir in iter_dot_test_results_dirs(root_dir):
        latest_folder = find_latest_test_folder(test_results_dir)

        if latest_folder:
            summary_log = resolve_unit_test_summary_log(latest_folder)

            if summary_log is not None:
                result = parse_summary_log(summary_log)
                result.project_path = str(test_results_dir.parent.absolute())
                results.append(result)

    return results


def print_results(results: List[TestResult]):
    """
    Print the test results in a formatted manner with colors.

    Args:
        results: List of TestResult objects to print
    """
    if not results:
        print("No test results found.")
        return

    use_colors = Colors.is_color_supported()

    def colorize(text: str, color: str) -> str:
        """Apply color to text if colors are supported."""
        if use_colors:
            return f"{color}{text}{Colors.RESET}"
        return text

    print("=" * 100)
    print(colorize("TEST STATUS REPORT", Colors.BOLD + Colors.CYAN))
    print("=" * 100)
    print()

    passed_count = 0
    failed_count = 0
    unknown_count = 0

    for result in results:
            if result.status == "PASSED":
                status_color = Colors.GREEN
                status_symbol = "+"
                passed_count += 1
            elif result.status == "FAILED":
                status_color = Colors.RED
                status_symbol = "x"
                failed_count += 1
            else:
                status_color = Colors.YELLOW
                status_symbol = "?"
                unknown_count += 1

            status_line = f"{status_symbol} [{result.status}] {result.project_path}"
            print(colorize(status_line, Colors.BOLD + status_color))

            if result.status == "PASSED":
                passed_text = f" Passed: {result.total_passed}"
                print(colorize(passed_text, Colors.GREEN))
            elif result.status == "FAILED":
                parts = []
                if result.total_passed > 0:
                    parts.append(colorize(f"Passed: {result.total_passed}", Colors.GREEN))
                if result.total_failed > 0:
                    parts.append(colorize(f"Failed: {result.total_failed}", Colors.RED))
                if result.total_errors > 0:
                    parts.append(colorize(f"Errors: {result.total_errors}", Colors.YELLOW))
                if parts:
                    print(f" {', '.join(parts)}")

            if result.timestamp:
                timestamp_text = f" Timestamp: {result.timestamp}"
                print(colorize(timestamp_text, Colors.GRAY))

            print()

    print("=" * 100)
    print(colorize("SUMMARY", Colors.BOLD + Colors.CYAN))
    print("=" * 100)
    print(f"Total Projects: {len(results)}")

    if passed_count > 0:
        print(colorize(f" Passed: {passed_count}", Colors.GREEN))
    if failed_count > 0:
        print(colorize(f" Failed: {failed_count}", Colors.RED))
    if unknown_count > 0:
        print(colorize(f" Unknown: {unknown_count}", Colors.YELLOW))

    failed_results = [r for r in results if r.status == 'FAILED']
    if failed_results:
        print()
        print(colorize("LOG FOLDERS (failing projects — contains summary and detail logs)", Colors.BOLD + Colors.RED))
        for r in failed_results:
            log_dir = str(Path(r.log_file).parent)
            print(f" {log_dir}")

    print("=" * 100)


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Check test status across .test_results folders."
    )
    parser.add_argument(
        "--root",
        type=Path,
        default=None,
        help="Root directory to search (default: current working directory)",
    )
    parser.add_argument("--debug", action="store_true", help="Enable debug output")
    args = parser.parse_args()

    root_dir = args.root.resolve() if args.root else Path.cwd()

    print(f"Searching for test results in: {root_dir}")
    print()

    # Find all test results
    results = find_all_test_results(root_dir)

    # Sort results by project path for consistent output
    results.sort(key=lambda x: x.project_path)

    # Print results
    print_results(results)


if __name__ == "__main__":
    main()
