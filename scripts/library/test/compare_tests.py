"""
Compare timestamped test result folders inside one .test_results directory.

The command intentionally works on a single project/test-results directory. It
does not recursively scan the workspace. Unit test runs are compared only with
other unit test runs, and deploy test runs are compared only with other deploy
test runs.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

# Same-directory helper imports. Avoid `import test.*` because it can collide
# with the stdlib test package.
_status_script_dir = Path(__file__).resolve().parent
if str(_status_script_dir) not in sys.path:
    sys.path.insert(0, str(_status_script_dir))

from status_deploy_tests import parse_jest_and_xml_results  # noqa: E402

UNIT_PREFIX = "unit-tests-"
DEPLOY_PREFIX = "deploy-test-"
RUN_TIMESTAMP_RE = re.compile(r"^(unit-tests|deploy-test)-(\d{8})-(\d{6})$")


class Colors:
    """ANSI color codes for terminal output."""

    GREEN = "\033[92m"
    RED = "\033[91m"
    YELLOW = "\033[93m"
    CYAN = "\033[96m"
    BOLD = "\033[1m"
    RESET = "\033[0m"
    GRAY = "\033[90m"

    @staticmethod
    def is_color_supported() -> bool:
        if sys.platform == "win32":
            return True
        return hasattr(sys.stdout, "isatty") and sys.stdout.isatty()


@dataclass(frozen=True)
class ServiceCounts:
    """Test counts for one service in one run."""

    passed: int = 0
    failed: int = 0
    errors: int = 0
    skipped: int = 0
    suite_failures: int = 0

    @property
    def issue_count(self) -> int:
        return self.failed + self.errors + self.suite_failures

    @property
    def total(self) -> int:
        return (
            self.passed
            + self.failed
            + self.errors
            + self.skipped
            + self.suite_failures
        )

    def add(self, other: ServiceCounts) -> ServiceCounts:
        return ServiceCounts(
            passed=self.passed + other.passed,
            failed=self.failed + other.failed,
            errors=self.errors + other.errors,
            skipped=self.skipped + other.skipped,
            suite_failures=self.suite_failures + other.suite_failures,
        )


@dataclass(frozen=True)
class ServiceResult:
    """Result for one service in one run."""

    name: str
    status: str
    counts: ServiceCounts
    detail: str = ""


@dataclass(frozen=True)
class TestRun:
    """Parsed unit or deploy run."""

    kind: str
    folder: Path
    timestamp: datetime
    timestamp_label: str
    project_path: str
    status: str
    services: dict[str, ServiceResult]

    @property
    def totals(self) -> ServiceCounts:
        total = ServiceCounts()
        for service in self.services.values():
            total = total.add(service.counts)
        return total


@dataclass(frozen=True)
class ServiceComparison:
    """Latest-vs-previous comparison for one service."""

    service: str
    previous: ServiceResult | None
    latest: ServiceResult | None
    change: str
    history: list[str]


def _colorize(text: str, color: str, use_colors: bool) -> str:
    if use_colors:
        return f"{color}{text}{Colors.RESET}"
    return text


def _counts_from_mapping(raw: object) -> ServiceCounts:
    if not isinstance(raw, dict):
        return ServiceCounts()
    return ServiceCounts(
        passed=int(raw.get("passed", 0) or 0),
        failed=int(raw.get("failed", 0) or 0),
        errors=int(raw.get("errors", raw.get("error", 0)) or 0),
        skipped=int(raw.get("skipped", 0) or 0),
        suite_failures=int(raw.get("suite_failures", 0) or 0),
    )


def _status_from_counts(counts: ServiceCounts) -> str:
    if counts.failed > 0 or counts.errors > 0 or counts.suite_failures > 0:
        return "FAILED"
    if counts.total > 0:
        return "PASSED"
    return "UNKNOWN"


def _overall_status(services: dict[str, ServiceResult]) -> str:
    if not services:
        return "UNKNOWN"
    if any(service.status == "FAILED" for service in services.values()):
        return "FAILED"
    if any(service.status == "UNKNOWN" for service in services.values()):
        return "UNKNOWN"
    return "PASSED"


def _parse_run_timestamp(folder_name: str, expected_prefix: str) -> datetime | None:
    if not folder_name.startswith(expected_prefix):
        return None
    match = RUN_TIMESTAMP_RE.match(folder_name)
    if match is None:
        return None
    try:
        return datetime.strptime(f"{match.group(2)}{match.group(3)}", "%Y%m%d%H%M%S")
    except ValueError:
        return None


def _timestamp_label(timestamp: datetime) -> str:
    return timestamp.strftime("%Y%m%d-%H%M%S")


def _display_timestamp(timestamp: datetime) -> str:
    return timestamp.strftime("%Y-%m-%d %H:%M:%S")


def _read_json(path: Path) -> dict[str, Any] | None:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return data if isinstance(data, dict) else None


def _summary_project_path(summary_path: Path) -> str:
    try:
        for line in summary_path.read_text(encoding="utf-8").splitlines():
            match = re.match(r"Project:\s+(.+)", line)
            if match:
                return match.group(1).strip()
    except OSError:
        pass
    return str(summary_path.parent.parent.parent.resolve())


def _parse_junit_counts(xml_path: Path) -> ServiceCounts | None:
    try:
        tree = ET.parse(xml_path)
    except (ET.ParseError, OSError):
        return None

    root = tree.getroot()
    if root.tag == "testsuites":
        suites = list(root.iter("testsuite"))
    elif root.tag == "testsuite":
        suites = [root]
    else:
        return None

    tests = 0
    failures = 0
    errors = 0
    skipped = 0
    for suite in suites:
        tests += int(suite.get("tests", "0") or 0)
        failures += int(suite.get("failures", "0") or 0)
        errors += int(suite.get("errors", "0") or 0)
        skipped += int(suite.get("skipped", "0") or 0)
    passed = max(tests - failures - errors - skipped, 0)
    return ServiceCounts(
        passed=passed,
        failed=failures,
        errors=errors,
        skipped=skipped,
    )


def _parse_unit_index(run_dir: Path) -> dict[str, ServiceResult]:
    data = _read_json(run_dir / "index.json")
    if data is None:
        return {}

    services: dict[str, ServiceResult] = {}
    raw_services = data.get("services", [])
    if not isinstance(raw_services, list):
        return {}

    for item in raw_services:
        if not isinstance(item, dict):
            continue
        name = str(item.get("name", "")).strip()
        if not name:
            continue
        counts = _counts_from_mapping(item.get("counts"))
        raw_status = str(item.get("result", "")).upper()
        status = raw_status if raw_status in {"PASSED", "FAILED", "UNKNOWN"} else _status_from_counts(counts)
        services[name] = ServiceResult(name=name, status=status, counts=counts)
    return services


def _parse_unit_junit_services(run_dir: Path) -> dict[str, ServiceResult]:
    services_dir = run_dir / "services"
    if not services_dir.is_dir():
        return {}

    services: dict[str, ServiceResult] = {}
    for service_dir in sorted(services_dir.iterdir()):
        if not service_dir.is_dir():
            continue
        junit_path = service_dir / "junit.xml"
        if not junit_path.is_file():
            continue
        counts = _parse_junit_counts(junit_path)
        if counts is None:
            continue
        services[service_dir.name] = ServiceResult(
            name=service_dir.name,
            status=_status_from_counts(counts),
            counts=counts,
        )
    return services


def _strip_error_prefix(line: str) -> str:
    stripped = line.strip()
    if stripped.startswith("ERROR:"):
        return stripped[len("ERROR:") :].strip()
    return stripped


def _parse_unit_summary(run_dir: Path) -> dict[str, ServiceResult]:
    summary_path = run_dir / "unit-tests-summary.log"
    if not summary_path.is_file():
        return {}

    try:
        lines = summary_path.read_text(encoding="utf-8").splitlines()
    except OSError:
        return {}

    services: dict[str, ServiceResult] = {}
    current_service: str | None = None
    for line in lines:
        text = _strip_error_prefix(line)
        service_match = re.match(r"Testing:\s+(.+)", text)
        if service_match:
            current_service = service_match.group(1).strip()
            services[current_service] = ServiceResult(
                name=current_service,
                status="UNKNOWN",
                counts=ServiceCounts(),
            )
            continue

        if current_service is None:
            continue

        passed_match = re.search(r"PASSED:\s+(\d+)\s+tests(?:\s+\((\d+)\s+skipped\))?", text)
        if passed_match:
            skipped = int(passed_match.group(2) or 0)
            counts = ServiceCounts(
                passed=int(passed_match.group(1)),
                skipped=skipped,
            )
            services[current_service] = ServiceResult(
                name=current_service,
                status="PASSED",
                counts=counts,
            )
            continue

        failed_match = re.search(r"FAILED:\s+(\d+)\s+passed,\s+(\d+)\s+failed", text)
        if failed_match:
            counts = ServiceCounts(
                passed=int(failed_match.group(1)),
                failed=int(failed_match.group(2)),
            )
            services[current_service] = ServiceResult(
                name=current_service,
                status="FAILED",
                counts=counts,
            )
            continue

        errors_match = re.search(r"COLLECTION ERRORS:\s+(\d+)\s+collection errors", text)
        if errors_match:
            counts = ServiceCounts(errors=int(errors_match.group(1)))
            services[current_service] = ServiceResult(
                name=current_service,
                status="FAILED",
                counts=counts,
            )

    return services


def parse_unit_run(run_dir: Path, timestamp: datetime) -> TestRun:
    services = _parse_unit_index(run_dir)
    if not services:
        services = _parse_unit_junit_services(run_dir)
    if not services:
        services = _parse_unit_summary(run_dir)

    summary_path = run_dir / "unit-tests-summary.log"
    project_path = _summary_project_path(summary_path) if summary_path.exists() else str(run_dir.parent.parent.resolve())

    return TestRun(
        kind="unit",
        folder=run_dir,
        timestamp=timestamp,
        timestamp_label=_timestamp_label(timestamp),
        project_path=project_path,
        status=_overall_status(services),
        services=services,
    )


def _parse_deploy_index(run_dir: Path) -> dict[str, ServiceResult]:
    data = _read_json(run_dir / "index.json")
    if data is None:
        return {}

    raw_services = data.get("services", [])
    if not isinstance(raw_services, list):
        return {}

    services: dict[str, ServiceResult] = {}
    for item in raw_services:
        if not isinstance(item, dict):
            continue
        name = str(item.get("name", "")).strip()
        if not name:
            continue
        counts = _counts_from_mapping(item.get("counts"))
        spec_result = str(item.get("spec_result", "SKIPPED")).upper()
        integration_result = str(item.get("integration_result", "SKIPPED")).upper()
        docker_healthy = item.get("docker_healthy", True)
        health_check_passed = item.get("health_check_passed", True)
        db_connectivity_passed = item.get("db_connectivity_passed", True)
        if (
            spec_result == "FAILED"
            or integration_result == "FAILED"
            or docker_healthy is False
            or health_check_passed is False
            or db_connectivity_passed is False
            or counts.issue_count > 0
        ):
            status = "FAILED"
        elif counts.total > 0 or spec_result == "PASSED" or integration_result == "PASSED":
            status = "PASSED"
        else:
            status = "UNKNOWN"
        detail = f"spec:{spec_result.lower()} integration:{integration_result.lower()}"
        services[name] = ServiceResult(name=name, status=status, counts=counts, detail=detail)
    return services


def _parse_deploy_artifacts(run_dir: Path) -> dict[str, ServiceResult]:
    services: dict[str, ServiceResult] = {}
    for suite in parse_jest_and_xml_results(run_dir):
        service_name = suite.service or "__project__"
        current = services.get(service_name)
        suite_counts = ServiceCounts(
            passed=int(suite.passed),
            failed=int(suite.failures),
            errors=int(suite.errors),
            skipped=int(suite.skipped),
        )
        if current is None:
            counts = suite_counts
        else:
            counts = current.counts.add(suite_counts)
        services[service_name] = ServiceResult(
            name=service_name,
            status=_status_from_counts(counts),
            counts=counts,
        )
    return services


def parse_deploy_run(run_dir: Path, timestamp: datetime) -> TestRun:
    services = _parse_deploy_index(run_dir)
    if not services:
        services = _parse_deploy_artifacts(run_dir)

    data = _read_json(run_dir / "index.json")
    project_path = str(run_dir.parent.parent.resolve())
    if data is not None and isinstance(data.get("project_path"), str):
        project_path = data["project_path"]

    return TestRun(
        kind="deploy",
        folder=run_dir,
        timestamp=timestamp,
        timestamp_label=_timestamp_label(timestamp),
        project_path=project_path,
        status=_overall_status(services),
        services=services,
    )


def find_runs(test_results_dir: Path, kind: str) -> list[TestRun]:
    if kind == "unit":
        prefix = UNIT_PREFIX
        parser = parse_unit_run
    elif kind == "deploy":
        prefix = DEPLOY_PREFIX
        parser = parse_deploy_run
    else:
        raise ValueError(f"Unsupported test kind: {kind}")

    runs: list[TestRun] = []
    for item in test_results_dir.iterdir():
        if not item.is_dir():
            continue
        timestamp = _parse_run_timestamp(item.name, prefix)
        if timestamp is None:
            continue
        runs.append(parser(item, timestamp))
    runs.sort(key=lambda run: run.timestamp)
    return runs


def _short_status(result: ServiceResult | None) -> str:
    if result is None:
        return "--"
    if result.status == "PASSED":
        return "OK"
    if result.status == "FAILED":
        return "FAIL"
    return "UNK"


def _classify_change(previous: ServiceResult | None, latest: ServiceResult | None) -> str:
    if previous is None and latest is None:
        return "MISSING"
    if previous is None:
        return "ADDED"
    if latest is None:
        return "REMOVED"
    if previous.status != "PASSED" and latest.status == "PASSED":
        return "IMPROVED"
    if previous.status == "PASSED" and latest.status != "PASSED":
        return "REGRESSED"
    if latest.counts.issue_count < previous.counts.issue_count:
        return "IMPROVED"
    if latest.counts.issue_count > previous.counts.issue_count:
        return "REGRESSED"
    if latest.counts != previous.counts:
        return "CHANGED"
    return "UNCHANGED"


def build_service_comparisons(runs: list[TestRun]) -> list[ServiceComparison]:
    if not runs:
        return []
    previous_run = runs[-2] if len(runs) >= 2 else None
    latest_run = runs[-1]
    service_names = set(latest_run.services)
    if previous_run is not None:
        service_names.update(previous_run.services)
    for run in runs[:-2]:
        service_names.update(run.services)

    comparisons: list[ServiceComparison] = []
    for service_name in sorted(service_names):
        previous = previous_run.services.get(service_name) if previous_run is not None else None
        latest = latest_run.services.get(service_name)
        history = [_short_status(run.services.get(service_name)) for run in runs]
        comparisons.append(
            ServiceComparison(
                service=service_name,
                previous=previous,
                latest=latest,
                change=_classify_change(previous, latest),
                history=history,
            )
        )
    return comparisons


def _delta_text(previous: int | None, latest: int | None) -> str:
    if previous is None and latest is None:
        return "-"
    if previous is None:
        return f"- -> {latest}"
    if latest is None:
        return f"{previous} -> -"
    return f"{previous}->{latest} ({latest - previous:+d})"


def _counts_delta(previous: ServiceResult | None, latest: ServiceResult | None, key: str) -> str:
    prev_count = getattr(previous.counts, key) if previous is not None else None
    latest_count = getattr(latest.counts, key) if latest is not None else None
    return _delta_text(prev_count, latest_count)


def _change_symbol(change: str) -> str:
    return {
        "REGRESSED": "!!",
        "IMPROVED": "++",
        "CHANGED": "**",
        "ADDED": "+ ",
        "REMOVED": "- ",
        "UNCHANGED": "..",
    }.get(change, "??")


def _change_color(change: str) -> str:
    return {
        "REGRESSED": Colors.RED,
        "IMPROVED": Colors.GREEN,
        "CHANGED": Colors.YELLOW,
        "ADDED": Colors.YELLOW,
        "REMOVED": Colors.YELLOW,
        "UNCHANGED": Colors.GRAY,
    }.get(change, Colors.YELLOW)


def _status_color(status: str) -> str:
    if status == "PASSED":
        return Colors.GREEN
    if status == "FAILED":
        return Colors.RED
    return Colors.YELLOW


def _format_totals(counts: ServiceCounts) -> str:
    parts = [f"{counts.passed} passed"]
    if counts.failed:
        parts.append(f"{counts.failed} failed")
    if counts.errors:
        parts.append(f"{counts.errors} errors")
    if counts.skipped:
        parts.append(f"{counts.skipped} skipped")
    if counts.suite_failures:
        parts.append(f"{counts.suite_failures} suite failures")
    return ", ".join(parts)


def _print_runs(runs: list[TestRun], use_colors: bool) -> None:
    for index, run in enumerate(runs, start=1):
        status = _colorize(run.status, _status_color(run.status), use_colors)
        print(
            f"  [{index}] {run.timestamp_label}  {status:<8}  "
            f"{_format_totals(run.totals)}  {run.folder.name}"
        )


def _print_comparison(kind: str, runs: list[TestRun], use_colors: bool) -> None:
    title = "UNIT TEST COMPARISON" if kind == "unit" else "DEPLOY TEST COMPARISON"
    print()
    print(_colorize(title, Colors.BOLD + Colors.CYAN, use_colors))
    print("-" * 120)

    if not runs:
        print(f"No {kind} test runs found.")
        return

    project_path = runs[-1].project_path
    print(f"Project: {project_path}")
    print(f"Runs: {len(runs)}")
    _print_runs(runs, use_colors)

    comparisons = build_service_comparisons(runs)
    if not comparisons:
        print()
        print("No service-level results found.")
        return

    summary = {change: 0 for change in ("REGRESSED", "IMPROVED", "CHANGED", "ADDED", "REMOVED", "UNCHANGED")}
    for comparison in comparisons:
        summary[comparison.change] = summary.get(comparison.change, 0) + 1

    print()
    print(
        "Summary: "
        f"{summary.get('REGRESSED', 0)} regressed, "
        f"{summary.get('IMPROVED', 0)} improved, "
        f"{summary.get('CHANGED', 0)} changed, "
        f"{summary.get('UNCHANGED', 0)} unchanged, "
        f"{summary.get('ADDED', 0)} added, "
        f"{summary.get('REMOVED', 0)} removed"
    )

    if len(runs) == 1:
        print("Only one run is present; service rows show current state without deltas.")
    else:
        previous = runs[-2]
        latest = runs[-1]
        print(f"Delta: {previous.timestamp_label} -> {latest.timestamp_label}")

    service_width = max(max(len(item.service) for item in comparisons), len("Service"))
    header = (
        f" {'Service':<{service_width}} {'Prev':>5} {'Latest':>6} "
        f"{'Change':<10} {'Passed':<18} {'Failed':<16} {'Errors':<16} {'History'}"
    )
    print()
    print(_colorize(header, Colors.BOLD, use_colors))
    print("-" * 120)

    for comparison in comparisons:
        symbol = _change_symbol(comparison.change)
        color = _change_color(comparison.change)
        change = _colorize(f"{symbol} {comparison.change:<10}", color, use_colors)
        row = (
            f" {comparison.service:<{service_width}} "
            f"{_short_status(comparison.previous):>5} "
            f"{_short_status(comparison.latest):>6} "
            f"{change} "
            f"{_counts_delta(comparison.previous, comparison.latest, 'passed'):<18} "
            f"{_counts_delta(comparison.previous, comparison.latest, 'failed'):<16} "
            f"{_counts_delta(comparison.previous, comparison.latest, 'errors'):<16} "
            f"{' -> '.join(comparison.history)}"
        )
        print(row)


def print_report(test_results_dir: Path, unit_runs: list[TestRun], deploy_runs: list[TestRun]) -> None:
    use_colors = Colors.is_color_supported()
    print("=" * 120)
    print(_colorize("TEST RESULT COMPARISON REPORT", Colors.BOLD + Colors.CYAN, use_colors))
    print("=" * 120)
    print(f"Source: {test_results_dir}")
    _print_comparison("unit", unit_runs, use_colors)
    _print_comparison("deploy", deploy_runs, use_colors)
    print("=" * 120)


def _markdown_counts_delta(previous: ServiceResult | None, latest: ServiceResult | None, key: str) -> str:
    return _counts_delta(previous, latest, key).replace("->", " -> ")


def _markdown_section(kind: str, runs: list[TestRun]) -> list[str]:
    title = "Unit Test Comparison" if kind == "unit" else "Deploy Test Comparison"
    lines: list[str] = [f"## {title}", ""]
    if not runs:
        lines.extend([f"No {kind} test runs found.", ""])
        return lines

    lines.append(f"**Project:** `{runs[-1].project_path}`")
    lines.append("")
    lines.append("| Run | Timestamp | Status | Totals | Folder |")
    lines.append("|---:|---|---|---|---|")
    for index, run in enumerate(runs, start=1):
        lines.append(
            f"| {index} | {run.timestamp_label} | {run.status} | "
            f"{_format_totals(run.totals)} | `{run.folder.name}` |"
        )
    lines.append("")

    comparisons = build_service_comparisons(runs)
    if not comparisons:
        lines.extend(["No service-level results found.", ""])
        return lines

    if len(runs) >= 2:
        lines.append(f"**Delta:** `{runs[-2].timestamp_label}` -> `{runs[-1].timestamp_label}`")
    else:
        lines.append("Only one run is present; rows show current state without deltas.")
    lines.append("")

    lines.append("| Service | Previous | Latest | Change | Passed | Failed | Errors | History |")
    lines.append("|---|---:|---:|---|---:|---:|---:|---|")
    for comparison in comparisons:
        lines.append(
            f"| `{comparison.service}` | {_short_status(comparison.previous)} | "
            f"{_short_status(comparison.latest)} | {comparison.change} | "
            f"{_markdown_counts_delta(comparison.previous, comparison.latest, 'passed')} | "
            f"{_markdown_counts_delta(comparison.previous, comparison.latest, 'failed')} | "
            f"{_markdown_counts_delta(comparison.previous, comparison.latest, 'errors')} | "
            f"{' -> '.join(comparison.history)} |"
        )
    lines.append("")
    return lines


def generate_markdown_report(test_results_dir: Path, unit_runs: list[TestRun], deploy_runs: list[TestRun]) -> str:
    lines: list[str] = [
        "# Test Result Comparison Report",
        "",
        f"**Source:** `{test_results_dir}`",
        "",
    ]
    lines.extend(_markdown_section("unit", unit_runs))
    lines.extend(_markdown_section("deploy", deploy_runs))
    return "\n".join(lines).rstrip() + "\n"


def _validate_test_results_dir(path: str) -> Path:
    resolved = Path(path).resolve()
    if not resolved.is_dir():
        raise argparse.ArgumentTypeError(f"Directory does not exist: {path}")
    if resolved.name != ".test_results":
        raise argparse.ArgumentTypeError(
            f"Expected a .test_results directory, got: {resolved}"
        )
    return resolved


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Compare timestamped unit/deploy test runs in one .test_results directory."
    )
    parser.add_argument(
        "--test-results",
        type=_validate_test_results_dir,
        required=True,
        help="Path to one project's .test_results directory.",
    )
    parser.add_argument(
        "--report",
        type=Path,
        default=None,
        help="Write a Markdown report to the given file path.",
    )
    parser.add_argument("--debug", action="store_true", help="Enable debug output")
    args = parser.parse_args()

    test_results_dir: Path = args.test_results
    unit_runs = find_runs(test_results_dir, "unit")
    deploy_runs = find_runs(test_results_dir, "deploy")

    if args.debug:
        print(f"DEBUG unit_runs={len(unit_runs)} deploy_runs={len(deploy_runs)}", file=sys.stderr)

    print_report(test_results_dir, unit_runs, deploy_runs)

    if args.report is not None:
        report_path = args.report.resolve()
        report_path.parent.mkdir(parents=True, exist_ok=True)
        report_path.write_text(
            generate_markdown_report(test_results_dir, unit_runs, deploy_runs),
            encoding="utf-8",
        )
        print()
        print(f"Markdown report written to: {report_path}")

    if not unit_runs and not deploy_runs:
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
