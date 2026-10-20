"""Run pytest with coverage on Datrix projects and display coverage details.

Per project, runs the project's tests with pytest-cov and prints the coverage report, then reads the
total from ``coverage report`` for the summary. With ``--fail-under N`` (N > 0) a project whose total is
below N fails. The run exits 0 when every project passed, else 1.

Run by ``metrics/coverage.ps1`` (POSIX twin ``coverage.sh``): project names positionally or as
``--projects``, or ``--all``; ``--format`` term|term-missing|html|xml; ``--fail-under N``;
``--stop-on-error``; ``--verbose-output`` (pytest ``-v``); ``--self-test`` (no test is run).
"""

from __future__ import annotations

import argparse
import contextlib
import importlib.util
import io
import re
import subprocess
import sys
import tempfile
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Final

from datrix_scripts.framework_repos import PackageMarker
from datrix_scripts.gates.repo_hygiene.gate_options import packages_current
from datrix_scripts.metrics.projects import (
    DEFAULT_WORDING,
    EXIT_FAILED,
    SHOWCASE,
    ProjectSelectionError,
    add_project_arguments,
    print_stderr,
    print_summary,
    run_projects,
    select_projects,
)
from datrix_scripts.paths import WORKSPACE_DIR
from datrix_scripts.test.wrappers import METRICS_SCRIPTS_DIR, module_main, run_self_test
from datrix_scripts.venv import PACKAGE_DEV_EXTRAS, missing_declared_tool

MODULE: Final = "datrix_scripts.metrics.coverage"
WRAPPER: Final = "coverage"
EXIT_TOOL_MISSING: Final = 2
COVERAGE_FORMATS: Final = ("term", "term-missing", "html", "xml")
DEFAULT_FORMAT: Final = "term-missing"
_PYTEST_COV_MODULE: Final = "pytest_cov"
_REPORT_TIMEOUT_SECONDS: Final = 30
#: The package folder a namespace-style project keeps under ``src/``; coverage measures it when present.
_NAMESPACE_SOURCE: Final = Path(PackageMarker.SRC.value) / "datrix"
# The TOTAL line of ``coverage report``: "TOTAL ... 6017  696  88%".
_COVERAGE_TOTAL_RE: Final = re.compile(r"TOTAL\s+.*\s+(\d+(?:\.\d+)?)%\s*$")
SUMMARY_TITLE: Final = "Coverage Summary"
USAGE_LINES: Final = (
    "Usage:",
    " .\\coverage.ps1 <project-name> [options]",
    " .\\coverage.ps1 <folder-path> [options]",
    " .\\coverage.ps1 -All [options]",
    "",
    "Examples:",
    " .\\coverage.ps1 datrix-common",
    " .\\coverage.ps1 datrix-common -Format html",
    " .\\coverage.ps1 -All -FailUnder 90",
    "",
    "Parameters:",
    " -Format term | term-missing | html | xml (default: term-missing)",
    " -FailUnder Minimum coverage percent; fail if below (e.g. 90)",
    " -All Run for all datrix-* projects",
    " -StopOnError Stop on first project failure",
    " -VerboseOutput Verbose pytest output",
)


def coverage_source(project_root: Path) -> str:
    """The ``--cov`` source of *project_root*: ``src/datrix`` when the project has it, else ``src``."""
    if (project_root / _NAMESPACE_SOURCE).exists():
        return _NAMESPACE_SOURCE.as_posix()
    return PackageMarker.SRC.value


@dataclass(frozen=True)
class CoverageOptions:
    """The report and threshold of one run, shared by every project."""

    report_format: str
    fail_under: float
    verbose: bool


def pytest_command(project_root: Path, options: CoverageOptions) -> list[str]:
    """The pytest-cov argument vector over *project_root*'s ``tests/``."""
    command = [
        sys.executable,
        "-m",
        "pytest",
        f"{PackageMarker.TESTS.value}/",
        f"--cov={coverage_source(project_root)}",
        f"--cov-report={options.report_format}",
    ]
    if options.fail_under > 0:
        command.append(f"--cov-fail-under={options.fail_under}")
    if options.verbose:
        command.append("-v")
    return command


def total_percent(report: str) -> float | None:
    """The TOTAL percentage of a ``coverage report`` text; None when it holds no TOTAL line."""
    for line in report.strip().splitlines():
        match = _COVERAGE_TOTAL_RE.search(line.strip())
        if match:
            return float(match.group(1))
    return None


def summary_detail(total: float | None, fail_under: float) -> str:
    """The line under a project in the summary: its total, and the threshold when one was set."""
    if total is None:
        return "total unknown: `coverage report` printed no TOTAL line"
    if fail_under > 0:
        return f"{total:.2f}% (required {fail_under:.1f}%)"
    return f"{total:.2f}% total"


def measured_detail(project_root: Path, fail_under: float, timeout_seconds: float = _REPORT_TIMEOUT_SECONDS) -> str:
    """The summary detail of *project_root* read from ``coverage report``: its total, or why no total was read
    (the report printed no TOTAL line, did not finish within *timeout_seconds*, or could not start)."""
    try:
        report = subprocess.run(
            [sys.executable, "-m", "coverage", "report"],
            capture_output=True,
            text=True,
            cwd=str(project_root),
            timeout=timeout_seconds,
        )
    except subprocess.TimeoutExpired:
        return f"total unknown: `coverage report` did not finish within {timeout_seconds:g} s"
    except OSError as exc:
        return f"total unknown: `coverage report` could not start in {project_root}: {exc}"
    return summary_detail(total_percent(report.stdout), fail_under)


class NotMeasurableError(Exception):
    """A project coverage cannot run on; ``exit_code`` is the project's result."""

    def __init__(self, message: str, exit_code: int) -> None:
        super().__init__(message)
        self.exit_code = exit_code


def require_measurable(project_root: Path) -> None:
    """Fail unless coverage can run on *project_root*.

    Raises:
        NotMeasurableError: pytest-cov is not installed (2), or *project_root*, its src/ or its tests/ is
            missing (1).
    """
    if importlib.util.find_spec(_PYTEST_COV_MODULE) is None:
        raise NotMeasurableError(missing_declared_tool("pytest-cov", PACKAGE_DEV_EXTRAS), EXIT_TOOL_MISSING)
    if not project_root.is_dir():
        raise NotMeasurableError(f"Error: project root is not a directory: {project_root}", EXIT_FAILED)
    for marker in (PackageMarker.SRC, PackageMarker.TESTS):
        if not (project_root / marker.value).is_dir():
            raise NotMeasurableError(f"Error: project has no {marker.value}/ directory: {project_root}", EXIT_FAILED)


def measure_project(project_root: Path, options: CoverageOptions, details: dict[str, str]) -> int:
    """pytest-cov over one project (output streamed): pytest's exit code, the summary detail recorded in
    *details*; 2 when pytest-cov is not installed, 1 when the project, its src/ or its tests/ is missing."""
    try:
        require_measurable(project_root)
    except NotMeasurableError as exc:
        print_stderr(str(exc))
        return exc.exit_code
    sys.stdout.flush()
    try:
        result = subprocess.run(pytest_command(project_root, options), cwd=str(project_root))
    except FileNotFoundError as exc:
        print_stderr(f"Error: could not run pytest: {exc}")
        return EXIT_TOOL_MISSING
    details[project_root.name] = measured_detail(project_root, options.fail_under)
    return result.returncode


def _selected(args: argparse.Namespace, workspace: Path) -> list[str]:
    """The projects to measure, the line announcing them printed.

    Raises:
        ProjectSelectionError: The selection is empty (the wrapper's wording).
    """
    projects = select_projects(args, workspace, usage=USAGE_LINES, wording=DEFAULT_WORDING)
    scope = " all projects" if args.all else ""
    print(f"Running coverage (format={args.format}) for{scope}: {', '.join(projects)}")
    return projects


def run_coverage(args: argparse.Namespace, workspace: Path, packages_ready: Callable[[], bool]) -> int:
    """The wrapper's run over *workspace*: select, check the package installs (*packages_ready*), measure
    each project, summarize."""
    try:
        projects = _selected(args, workspace)
    except ProjectSelectionError as exc:
        for line in exc.lines:
            print(line)
        return EXIT_FAILED
    if not packages_ready():
        return EXIT_FAILED
    options = CoverageOptions(report_format=args.format, fail_under=args.fail_under, verbose=args.verbose_output)
    details: dict[str, str] = {}
    results = run_projects(
        projects, lambda project: measure_project(workspace / project, options, details), stop_on_error=args.stop_on_error
    )
    return print_summary(SUMMARY_TITLE, results, details)


def build_parser() -> argparse.ArgumentParser:
    """The options of ``metrics/coverage.ps1``: one per wrapper parameter, spelled exactly."""
    parser = argparse.ArgumentParser(description="Run pytest with coverage for Datrix projects.", allow_abbrev=False)
    add_project_arguments(parser)
    parser.add_argument(
        "--format", choices=COVERAGE_FORMATS, default=DEFAULT_FORMAT,
        help=f"Coverage report format (default: {DEFAULT_FORMAT}).",
    )
    parser.add_argument(
        "--fail-under", type=float, default=0.0, metavar="N",
        help="Fail a project whose total coverage is below N percent (0: no threshold).",
    )
    parser.add_argument("--stop-on-error", action="store_true", help="Stop on the first project that fails.")
    parser.add_argument("--verbose-output", action="store_true", help="Verbose pytest output (-v).")
    parser.add_argument("--self-test", action="store_true", help="Run only the self-test (no test is run).")
    parser.set_defaults(debug=False)
    return parser


def _run(args: argparse.Namespace) -> int:
    if args.self_test:
        return run_self_test(
            SELF_TEST_CHECKS, wrapper=WRAPPER, module=MODULE, parser=build_parser(), folder=METRICS_SCRIPTS_DIR
        )
    return run_coverage(args, WORKSPACE_DIR, packages_current)


# ---------------------------------------------------------------------------
# Self-test
# ---------------------------------------------------------------------------


def _plant(root: Path) -> Path:
    """``datrix-ns`` (src/datrix/ and tests/), ``datrix-flat`` (src/ only) and the showcase directory."""
    (root / "datrix-ns" / _NAMESPACE_SOURCE).mkdir(parents=True)
    (root / "datrix-ns" / PackageMarker.TESTS.value).mkdir()
    (root / "datrix-flat" / PackageMarker.SRC.value).mkdir(parents=True)
    (root / SHOWCASE).mkdir()
    return root


def _report(argv: Sequence[str], packages_ready: bool = True) -> tuple[int, str, str]:
    """Exit code, stdout and stderr of a run over a planted workspace (forms that stop before pytest)."""
    out, err = io.StringIO(), io.StringIO()
    with tempfile.TemporaryDirectory() as raw:
        workspace = _plant(Path(raw))
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = run_coverage(build_parser().parse_args(list(argv)), workspace, lambda: packages_ready)
    return code, out.getvalue(), err.getvalue()


def _check_source_and_command() -> None:
    with tempfile.TemporaryDirectory() as raw:
        workspace = _plant(Path(raw))
        assert coverage_source(workspace / "datrix-ns") == "src/datrix", coverage_source(workspace / "datrix-ns")
        assert coverage_source(workspace / "datrix-flat") == "src", coverage_source(workspace / "datrix-flat")
        gated = pytest_command(workspace / "datrix-flat", CoverageOptions("html", 90.0, verbose=True))
        plain = pytest_command(workspace / "datrix-flat", CoverageOptions(DEFAULT_FORMAT, 0.0, verbose=False))
    assert gated[3:] == ["tests/", "--cov=src", "--cov-report=html", "--cov-fail-under=90.0", "-v"], gated
    assert plain[3:] == ["tests/", "--cov=src", "--cov-report=term-missing"], plain


def _check_total_and_detail() -> None:
    report = "Name    Stmts   Miss  Cover\n----\nsrc/a.py   10   1   90%\nTOTAL   6017   696   88%\n"
    assert total_percent(report) == 88.0 and total_percent("no total here") is None, total_percent(report)
    assert summary_detail(88.0, 90.0) == "88.00% (required 90.0%)", summary_detail(88.0, 90.0)
    assert summary_detail(88.456, 0.0) == "88.46% total", summary_detail(88.456, 0.0)
    assert summary_detail(None, 0.0).startswith("total unknown"), summary_detail(None, 0.0)


#: Shorter than any interpreter start, so the ``coverage report`` child cannot finish in time.
_NO_TIME_SECONDS: Final = 0.001


def _check_measured_detail_names_why_no_total() -> None:
    with tempfile.TemporaryDirectory() as raw:
        no_data = measured_detail(Path(raw), 0.0)
        timed_out = measured_detail(Path(raw), 0.0, timeout_seconds=_NO_TIME_SECONDS)
        no_folder = measured_detail(Path(raw) / "missing", 0.0)
    assert no_data == "total unknown: `coverage report` printed no TOTAL line", no_data
    assert timed_out == f"total unknown: `coverage report` did not finish within {_NO_TIME_SECONDS:g} s", timed_out
    assert no_folder.startswith("total unknown: `coverage report` could not start in "), no_folder


def _check_missing_tests_and_root_fail_before_pytest() -> None:
    code, out, err = _report(["datrix-flat", "no-such-project", "--fail-under=90"])
    assert code == EXIT_FAILED, (code, out)
    assert "Error: project has no tests/ directory:" in err and "Error: project root is not a directory:" in err, err
    assert " [FAIL] : datrix-flat" in out and " [FAIL] : no-such-project" in out, out


def _check_failed_install_check_stops_the_run() -> None:
    code, out, _ = _report(["datrix-flat"], packages_ready=False)
    assert code == EXIT_FAILED and SUMMARY_TITLE not in out, (code, out)


def _check_refusals_print_the_wrapper_lines() -> None:
    code, out, _ = _report([SHOWCASE])
    assert (code, out.splitlines()) == (EXIT_FAILED, [DEFAULT_WORDING.none_valid]), (code, out)
    code, out, _ = _report([])
    expected = [*DEFAULT_WORDING.none_given_heading, *USAGE_LINES, "", "Available projects:", " - datrix-flat",
                " - datrix-ns", ""]
    assert (code, out.splitlines()) == (EXIT_FAILED, expected), (code, out)


SELF_TEST_CHECKS: Final[tuple[Callable[[], None], ...]] = (
    _check_source_and_command,
    _check_total_and_detail,
    _check_measured_detail_names_why_no_total,
    _check_missing_tests_and_root_fail_before_pytest,
    _check_failed_install_check_stops_the_run,
    _check_refusals_print_the_wrapper_lines,
)


def main(argv: Sequence[str] | None = None) -> int:
    """Entry point."""
    return module_main(build_parser(), _run, argv)


if __name__ == "__main__":
    sys.exit(main())
