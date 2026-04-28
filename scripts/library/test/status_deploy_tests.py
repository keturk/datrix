"""
Script to check deployment test status across multiple test result folders.

This script recursively searches for .test_results folders, finds the latest
deploy-test-* folder, and reports the deployment test status for each project.

When --detail is passed, it also parses JUnit XML files to break results down
into spec, integration-project, and integration-service categories.
"""

import argparse
import re
import sys
import xml.etree.ElementTree as ET
from pathlib import Path
from datetime import datetime
from typing import List, Optional
from dataclasses import dataclass, field

# Add library directory to sys.path to import from shared
library_dir = Path(__file__).parent.parent
if library_dir.exists() and str(library_dir) not in sys.path:
    sys.path.insert(0, str(library_dir))

# Same-directory helper (avoid `import test.*` — conflicts with stdlib test package)
_status_script_dir = Path(__file__).resolve().parent
if str(_status_script_dir) not in sys.path:
    sys.path.insert(0, str(_status_script_dir))
from test_result_walk import iter_dot_test_results_dirs


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
class XmlSuiteResult:
    """Parsed result from a single JUnit XML file."""
    category: str  # 'spec', 'integration-project', 'integration-service'
    service: str
    tests: int
    passed: int
    failures: int
    errors: int
    skipped: int
    time_seconds: float


@dataclass
class TestResult:
    """Deployment test result information for a project."""
    project_path: str
    status: str  # 'PASSED', 'FAILED', or 'UNKNOWN'
    total_passed: int
    total_failed: int
    total_errors: int
    timestamp: str
    log_file: str
    # Detailed breakdown from XML (populated when --detail is used)
    xml_suites: List[XmlSuiteResult] = field(default_factory=list)


def parse_timestamp_from_folder(folder_name: str) -> Optional[datetime]:
    """
    Parse timestamp from folder name like 'deploy-test-20260107-161027'.

    Args:
        folder_name: The folder name to parse

    Returns:
        datetime object or None if parsing fails
    """
    match = re.search(r'deploy-test-(\d{8})-(\d{6})', folder_name)
    if match:
        date_str = match.group(1)  # YYYYMMDD
        time_str = match.group(2)  # HHMMSS
        try:
            return datetime.strptime(f"{date_str}{time_str}", "%Y%m%d%H%M%S")
        except ValueError:
            return None
    return None


def _timestamp_from_folder_name(folder_name: str) -> str:
    """Return a human-readable timestamp string from a deploy-test folder name."""
    dt = parse_timestamp_from_folder(folder_name)
    if dt is None:
        return ""
    return dt.strftime("%Y-%m-%d %H:%M:%S")


def find_latest_test_folder(test_results_dir: Path) -> Optional[Path]:
    """
    Find the latest deploy-test-* folder based on timestamp.

    Args:
        test_results_dir: Path to .test_results folder

    Returns:
        Path to the latest deploy-test-* folder or None if not found
    """
    deploy_test_folders = []

    for item in test_results_dir.iterdir():
        if item.is_dir() and item.name.startswith('deploy-test-'):
            timestamp = parse_timestamp_from_folder(item.name)
            if timestamp:
                deploy_test_folders.append((timestamp, item))

    if not deploy_test_folders:
        return None

    # Sort by timestamp descending and return the latest
    deploy_test_folders.sort(key=lambda x: x[0], reverse=True)
    return deploy_test_folders[0][1]


# ---------------------------------------------------------------------------
# JUnit XML parsing
# ---------------------------------------------------------------------------

_SPEC_PATTERN = re.compile(r'^pytest-spec-(.+)\.xml$')
_INT_PROJECT_PATTERN = re.compile(r'^pytest-integration-(.+)-project\.xml$')
_INT_SERVICE_PATTERN = re.compile(r'^pytest-integration-(.+)-service\.xml$')


def _classify_xml_file(filename: str) -> Optional[tuple[str, str]]:
    """Return (category, service_name) or None if the file is not a known XML."""
    m = _SPEC_PATTERN.match(filename)
    if m:
        return ('spec', m.group(1))
    m = _INT_PROJECT_PATTERN.match(filename)
    if m:
        return ('integration-project', m.group(1))
    m = _INT_SERVICE_PATTERN.match(filename)
    if m:
        return ('integration-service', m.group(1))
    return None


def _parse_junit_xml(xml_path: Path, category: str, service: str) -> Optional[XmlSuiteResult]:
    """Parse a JUnit XML file and return an XmlSuiteResult."""
    try:
        tree = ET.parse(xml_path)
    except ET.ParseError:
        return None

    root = tree.getroot()
    # The file may have <testsuites><testsuite ...> or just <testsuite ...>
    if root.tag == 'testsuites':
        suites = list(root.iter('testsuite'))
    elif root.tag == 'testsuite':
        suites = [root]
    else:
        return None

    total_tests = 0
    total_failures = 0
    total_errors = 0
    total_skipped = 0
    total_time = 0.0

    for suite in suites:
        total_tests += int(suite.get('tests', '0'))
        total_failures += int(suite.get('failures', '0'))
        total_errors += int(suite.get('errors', '0'))
        total_skipped += int(suite.get('skipped', '0'))
        total_time += float(suite.get('time', '0'))

    total_passed = total_tests - total_failures - total_errors - total_skipped

    return XmlSuiteResult(
        category=category,
        service=service,
        tests=total_tests,
        passed=total_passed,
        failures=total_failures,
        errors=total_errors,
        skipped=total_skipped,
        time_seconds=total_time,
    )


def parse_xml_results(deploy_test_folder: Path) -> List[XmlSuiteResult]:
    """Parse all JUnit XML files in a deploy-test folder."""
    results: List[XmlSuiteResult] = []
    for xml_file in sorted(deploy_test_folder.iterdir()):
        if not xml_file.is_file() or xml_file.suffix != '.xml':
            continue
        classified = _classify_xml_file(xml_file.name)
        if classified is None:
            continue
        category, service = classified
        suite = _parse_junit_xml(xml_file, category, service)
        if suite is not None:
            results.append(suite)
    return results


# ---------------------------------------------------------------------------
# Summary log parsing
# ---------------------------------------------------------------------------

def parse_summary_log(log_file: Path) -> TestResult:
    """
    Parse the deploy-test-summary.log file to extract test results.

    Supports the run_complete.py format (Total Tests: / Passed: N, Failed: N,
    Errors: N, Successful Projects, Failed Projects) and the Total Passed /
    Total Failed / marker-based format.

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

        # Extract totals: Total Passed / Total Failed fields
        passed_match = re.search(r'Total Passed:\s+(\d+)', content)
        if passed_match:
            total_passed = int(passed_match.group(1))

        failed_match = re.search(r'Total Failed:\s+(\d+)', content)
        if failed_match:
            total_failed = int(failed_match.group(1))

        # run_complete.py format: "Total Tests:" block with " Passed: N", " Failed: N", " Errors: N"
        if not passed_match:
            run_complete_passed = re.search(r'^ Passed:\s+(\d+)', content, re.MULTILINE)
            if run_complete_passed:
                total_passed = int(run_complete_passed.group(1))
        if not failed_match:
            run_complete_failed = re.search(r'^ Failed:\s+(\d+)', content, re.MULTILINE)
            if run_complete_failed:
                total_failed = int(run_complete_failed.group(1))

        # Errors: Total Tests block and/or collection errors / failed services
        run_complete_errors = re.search(r'^ Errors:\s+(\d+)', content, re.MULTILINE)
        if run_complete_errors:
            total_errors = int(run_complete_errors.group(1))

        collection_errors = re.findall(r'COLLECTION ERRORS:\s+(\d+)\s+errors', content)
        if collection_errors:
            total_errors = sum(int(e) for e in collection_errors)

        if 'Failed services:' in content and total_errors == 0:
            failed_services_match = re.search(r'Failed services:\s+(.+)', content)
            if failed_services_match:
                failed_services = [
                    s.strip()
                    for s in failed_services_match.group(1).split(',')
                ]
                total_errors = len(failed_services)

        # Determine status (FAILED first, then PASSED, then fallback markers)
        failed_projects_match = re.search(r'Failed Projects:\s*([1-9]\d*)', content)
        if (
            failed_projects_match
            or '\u2717' in content  # ✗ (legacy deploy_test.py output)
            or '[FAIL] LOGIC FAILURES' in content
            or total_failed > 0
            or total_errors > 0
        ):
            status = 'FAILED'
        elif 'Tests FAILED' in content:
            status = 'FAILED'
        elif (
            re.search(r'Failed Projects:\s*0', content)
            and total_failed == 0
            and total_errors == 0
            and (
                'Successful Projects' in content
                or '\u2713' in content  # ✓ (legacy deploy_test.py output)
                or '[OK] All tests passed' in content
            )
        ):
            status = 'PASSED'
        elif (
            'All services are healthy!' in content
            and total_failed == 0
            and total_errors == 0
        ):
            status = 'PASSED'

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


# ---------------------------------------------------------------------------
# Discovery
# ---------------------------------------------------------------------------

def find_all_test_results(root_dir: Path, *, detail: bool = False) -> List[TestResult]:
    """
    Recursively find all .test_results folders and extract deployment test status.

    Args:
        root_dir: Root directory to start searching from
        detail: When True, also parse JUnit XML for spec/integration breakdown

    Returns:
        List of TestResult objects
    """
    results = []

    for test_results_dir in iter_dot_test_results_dirs(root_dir):
        latest_folder = find_latest_test_folder(test_results_dir)

        if latest_folder:
            summary_log = latest_folder / 'deploy-test-summary.log'
            project_path = str(test_results_dir.parent.absolute())

            if summary_log.exists():
                result = parse_summary_log(summary_log)
                result.project_path = project_path
                if detail:
                    result.xml_suites = parse_xml_results(latest_folder)
                results.append(result)
            else:
                # No summary log — the deploy pipeline crashed before
                # writing results (e.g. Docker build failure).  Report
                # as FAILED so the project is never silently omitted.
                xml_suites = parse_xml_results(latest_folder) if detail else []
                total_passed = sum(s.passed for s in xml_suites)
                total_failed = sum(s.failures for s in xml_suites)
                total_errors = sum(s.errors for s in xml_suites)
                timestamp = _timestamp_from_folder_name(latest_folder.name)
                results.append(TestResult(
                    project_path=project_path,
                    status="FAILED",
                    total_passed=total_passed,
                    total_failed=total_failed,
                    total_errors=total_errors,
                    timestamp=timestamp,
                    log_file=str(summary_log),
                    xml_suites=xml_suites,
                ))

    return results


# ---------------------------------------------------------------------------
# Display helpers
# ---------------------------------------------------------------------------

def _shorten_path(full_path: str, root_dir: Path) -> str:
    """Return a shorter relative path when possible."""
    try:
        return str(Path(full_path).relative_to(root_dir))
    except ValueError:
        return full_path


def print_results(results: List[TestResult], *, detail: bool = False,
                  root_dir: Optional[Path] = None) -> None:
    """
    Print the deployment test results in a formatted manner with colors.

    Args:
        results: List of TestResult objects to print
        detail: Show spec/integration breakdown
        root_dir: Root directory used for path shortening
    """
    if not results:
        print("No deployment test results found.")
        return

    use_colors = Colors.is_color_supported()

    def colorize(text: str, color: str) -> str:
        """Apply color to text if colors are supported."""
        if use_colors:
            return f"{color}{text}{Colors.RESET}"
        return text

    print("=" * 100)
    print(colorize("DEPLOYMENT TEST STATUS REPORT", Colors.BOLD + Colors.CYAN))
    print("=" * 100)
    print()

    passed_count = 0
    failed_count = 0
    unknown_count = 0

    # Grand totals for detail mode
    grand_spec = _CategoryTotals()
    grand_int_proj = _CategoryTotals()
    grand_int_svc = _CategoryTotals()

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

        display_path = _shorten_path(result.project_path, root_dir) if root_dir else result.project_path
        status_line = f"{status_symbol} [{result.status}] {display_path}"
        print(colorize(status_line, Colors.BOLD + status_color))

        if detail and result.xml_suites:
            spec, int_proj, int_svc = _aggregate_by_category(result.xml_suites)
            _print_category_line("  Spec", spec, colorize)
            _print_category_line("  Integration (project)", int_proj, colorize)
            _print_category_line("  Integration (service)", int_svc, colorize)
            grand_spec.add(spec)
            grand_int_proj.add(int_proj)
            grand_int_svc.add(int_svc)
        elif result.status == "PASSED":
            passed_text = f"  Passed: {result.total_passed}"
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
                print(f"  {', '.join(parts)}")

        if result.timestamp:
            timestamp_text = f"  Timestamp: {result.timestamp}"
            print(colorize(timestamp_text, Colors.GRAY))

        print()

    # Summary
    print("=" * 100)
    print(colorize("SUMMARY", Colors.BOLD + Colors.CYAN))
    print("=" * 100)
    print(f"Total Projects: {len(results)}")

    if passed_count > 0:
        print(colorize(f"  Passed: {passed_count}", Colors.GREEN))
    if failed_count > 0:
        print(colorize(f"  Failed: {failed_count}", Colors.RED))
    if unknown_count > 0:
        print(colorize(f"  Unknown: {unknown_count}", Colors.YELLOW))

    if detail and (grand_spec.tests > 0 or grand_int_proj.tests > 0 or grand_int_svc.tests > 0):
        print()
        print(colorize("TEST TYPE BREAKDOWN", Colors.BOLD + Colors.CYAN))
        _print_category_line("  Spec", grand_spec, colorize)
        _print_category_line("  Integration (project)", grand_int_proj, colorize)
        _print_category_line("  Integration (service)", grand_int_svc, colorize)
        grand_all = _CategoryTotals()
        grand_all.add(grand_spec)
        grand_all.add(grand_int_proj)
        grand_all.add(grand_int_svc)
        _print_category_line("  ALL", grand_all, colorize)

    failed_results = [r for r in results if r.status == 'FAILED']
    if failed_results:
        print()
        print(colorize("LOG FOLDERS (failing projects — contains summary and detail logs)", Colors.BOLD + Colors.RED))
        for r in failed_results:
            log_dir = str(Path(r.log_file).parent)
            print(f"  {log_dir}")

    print("=" * 100)


# ---------------------------------------------------------------------------
# Markdown report generation
# ---------------------------------------------------------------------------

def generate_markdown_report(results: List[TestResult], root_dir: Path) -> str:
    """Generate a Markdown report string from test results."""
    lines: List[str] = []
    w = lines.append

    w("# Deploy Test Status Report")
    w("")
    w(f"**Source:** `{root_dir}`")
    w("")

    # Compute grand totals from XML
    grand_spec = _CategoryTotals()
    grand_int_proj = _CategoryTotals()
    grand_int_svc = _CategoryTotals()
    for r in results:
        s, ip, isv = _aggregate_by_category(r.xml_suites)
        grand_spec.add(s)
        grand_int_proj.add(ip)
        grand_int_svc.add(isv)

    passed_projects = sum(1 for r in results if r.status == 'PASSED')
    failed_projects = sum(1 for r in results if r.status == 'FAILED')

    w("## Grand Totals")
    w("")
    w(f"| Metric | Count |")
    w(f"|---|---|")
    w(f"| Total projects | {len(results)} |")
    w(f"| Projects all-green | {passed_projects} |")
    w(f"| Projects with failures | {failed_projects} |")
    w("")

    grand_all = _CategoryTotals()
    grand_all.add(grand_spec)
    grand_all.add(grand_int_proj)
    grand_all.add(grand_int_svc)

    w("| Test Type | Total | Passed | Failed | Errors | Skipped |")
    w("|---|---|---|---|---|---|")
    w(f"| Spec | {grand_spec.tests} | {grand_spec.passed} | {grand_spec.failures} | {grand_spec.errors} | {grand_spec.skipped} |")
    w(f"| Integration (project) | {grand_int_proj.tests} | {grand_int_proj.passed} | {grand_int_proj.failures} | {grand_int_proj.errors} | {grand_int_proj.skipped} |")
    w(f"| Integration (service) | {grand_int_svc.tests} | {grand_int_svc.passed} | {grand_int_svc.failures} | {grand_int_svc.errors} | {grand_int_svc.skipped} |")
    w(f"| **All** | **{grand_all.tests}** | **{grand_all.passed}** | **{grand_all.failures}** | **{grand_all.errors}** | **{grand_all.skipped}** |")
    w("")

    if grand_all.tests > 0:
        rate = grand_all.passed / grand_all.tests * 100
        w(f"**Pass rate:** {rate:.1f}% ({grand_all.passed:,} / {grand_all.tests:,})")
        w("")

    w("---")
    w("")

    # Per-project
    w("## Per-Project Results")
    w("")

    passing_results = [r for r in results if r.status != 'FAILED']
    failing_results = [r for r in results if r.status == 'FAILED']

    for result in passing_results:
        display_path = _shorten_path(result.project_path, root_dir)
        w(f"### {display_path} — {result.total_passed} passed, 0 failed")
        w("")
        if result.xml_suites:
            w("| Type | Service | Tests | Pass | Fail |")
            w("|---|---|---|---|---|")
            for suite in result.xml_suites:
                fail_str = str(suite.failures) if suite.failures == 0 else f"**{suite.failures}**"
                w(f"| {suite.category} | {suite.service} | {suite.tests} | {suite.passed} | {fail_str} |")
            w("")
        else:
            w(f"Passed: {result.total_passed}")
            w("")

    if failing_results:
        w("---")
        w("")
        w(f"## Failed Projects ({len(failing_results)} of {len(results)})")
        w("")

        for result in failing_results:
            display_path = _shorten_path(result.project_path, root_dir)
            w(f"### {display_path} — {result.total_passed} passed, {result.total_failed} failed")
            w("")
            if result.xml_suites:
                w("| Type | Service | Tests | Pass | Fail |")
                w("|---|---|---|---|---|")
                for suite in result.xml_suites:
                    fail_str = str(suite.failures) if suite.failures == 0 else f"**{suite.failures}**"
                    w(f"| {suite.category} | {suite.service} | {suite.tests} | {suite.passed} | {fail_str} |")
                w("")
            else:
                w(f"Passed: {result.total_passed}, Failed: {result.total_failed}, Errors: {result.total_errors}")
                w("")

    return "\n".join(lines) + "\n"


# ---------------------------------------------------------------------------
# Category aggregation helpers
# ---------------------------------------------------------------------------

class _CategoryTotals:
    """Mutable accumulator for test counts within one category."""

    __slots__ = ('tests', 'passed', 'failures', 'errors', 'skipped', 'time_seconds')

    def __init__(self) -> None:
        self.tests = 0
        self.passed = 0
        self.failures = 0
        self.errors = 0
        self.skipped = 0
        self.time_seconds = 0.0

    def add(self, other: '_CategoryTotals') -> None:
        self.tests += other.tests
        self.passed += other.passed
        self.failures += other.failures
        self.errors += other.errors
        self.skipped += other.skipped
        self.time_seconds += other.time_seconds

    def add_suite(self, suite: XmlSuiteResult) -> None:
        self.tests += suite.tests
        self.passed += suite.passed
        self.failures += suite.failures
        self.errors += suite.errors
        self.skipped += suite.skipped
        self.time_seconds += suite.time_seconds


def _aggregate_by_category(
    suites: List[XmlSuiteResult],
) -> tuple[_CategoryTotals, _CategoryTotals, _CategoryTotals]:
    """Aggregate suites into (spec, integration-project, integration-service)."""
    spec = _CategoryTotals()
    int_proj = _CategoryTotals()
    int_svc = _CategoryTotals()
    for s in suites:
        if s.category == 'spec':
            spec.add_suite(s)
        elif s.category == 'integration-project':
            int_proj.add_suite(s)
        elif s.category == 'integration-service':
            int_svc.add_suite(s)
    return spec, int_proj, int_svc


def _print_category_line(
    label: str,
    totals: _CategoryTotals,
    colorize: object,
) -> None:
    """Print a single category summary line with colors."""
    # colorize is actually a callable (str, str) -> str
    _colorize = colorize  # type: ignore[assignment]
    if totals.tests == 0:
        print(f"{label}: (none)")
        return
    parts = [f"{totals.passed} passed"]
    if totals.failures > 0:
        parts.append(_colorize(f"{totals.failures} failed", Colors.RED))
    if totals.errors > 0:
        parts.append(_colorize(f"{totals.errors} errors", Colors.YELLOW))
    if totals.skipped > 0:
        parts.append(f"{totals.skipped} skipped")
    parts.append(f"{totals.tests} total")
    print(f"{label}: {', '.join(parts)}")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Check deployment test status across .test_results folders."
    )
    parser.add_argument(
        "--root",
        type=Path,
        default=None,
        help="Root directory to search (default: current working directory)",
    )
    parser.add_argument(
        "--detail",
        action="store_true",
        help="Show spec/integration breakdown by parsing JUnit XML files",
    )
    parser.add_argument(
        "--report",
        type=Path,
        default=None,
        help="Write a Markdown report to the given file path",
    )
    parser.add_argument("--debug", action="store_true", help="Enable debug output")
    args = parser.parse_args()

    root_dir = args.root.resolve() if args.root else Path.cwd()
    # When --report is requested, always parse XML detail
    want_detail = args.detail or args.report is not None

    print(f"Searching for deployment test results in: {root_dir}")
    print()

    # Find all test results
    results = find_all_test_results(root_dir, detail=want_detail)

    # Sort results by project path for consistent output
    results.sort(key=lambda x: x.project_path)

    # Print results
    print_results(results, detail=want_detail, root_dir=root_dir)

    # Write markdown report if requested
    if args.report is not None:
        report_path: Path = args.report.resolve()
        report_content = generate_markdown_report(results, root_dir)
        report_path.parent.mkdir(parents=True, exist_ok=True)
        report_path.write_text(report_content, encoding='utf-8')
        print()
        print(f"Markdown report written to: {report_path}")


if __name__ == "__main__":
    main()
