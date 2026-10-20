"""Run the tests of one or more Datrix packages, behind ``test/test.ps1`` and its ``test.sh`` twin.

Each package's suite runs in its own ``python -m datrix_scripts.test_project`` child in the shared
venv. Its output is shown as it runs and read back for the test counts and for the run directory
the runner reports. After the last package come a summary table and one
``Total: N | Passed: N | Failed: N`` line, which callers parse. Each failed package with a saved run
then gets a failure digest (``datrix_scripts.run_digest``). ``--list-tags`` runs no test: it prints
one collection-only listing per package, then compares the tags in use with the documented
vocabulary (``datrix_scripts.test.tag_vocabulary``).

The package install check runs once, before the first child, unless the caller already ran it and
says so with ``DATRIX_PACKAGES_ENSURED=1`` (``ensure_packages``). Every child's environment carries
that flag (``child_environment``), so no child repeats the check. This process's own environment is
never changed, so nothing outlives the run.

Exit codes: 0 when every package passed, ``--rerun`` found nothing to re-run, or ``--list-tags``
listed cleanly (otherwise ``--list-tags`` exits with the first failing listing's code). 1 when a
package failed, no valid package was named, two test tiers were named, or the install check failed.
"""

from __future__ import annotations

import argparse
import contextlib
import io
import json
import logging
import os
import re
import subprocess
import sys
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Final

from datrix_scripts.entrypoint import wrapper_flag
from datrix_scripts.gate_harness import EXIT_PASS, EXIT_USAGE, EXIT_VIOLATION, configure_logging, write_files
from datrix_scripts.package_suites import testable_package_names
from datrix_scripts.paths import WORKSPACE_DIR
from datrix_scripts.test.wrappers import ensure_utf8_stdio, run_self_test

logger = logging.getLogger(__name__)

MODULE: Final = "datrix_scripts.test.test"
WRAPPER: Final = "test"
TEST_PROJECT_MODULE: Final = "datrix_scripts.test_project"
RUN_DIGEST_MODULE: Final = "datrix_scripts.run_digest"
TAG_VOCABULARY_MODULE: Final = "datrix_scripts.test.tag_vocabulary"
#: Set by a caller that already ran the package install check for the one shared venv
#: (``affected-gate.ps1`` runs it once before launching any child). Read here and by ``test_project``.
PACKAGES_ENSURED_ENV: Final = "DATRIX_PACKAGES_ENSURED"
PACKAGES_ENSURED_VALUE: Final = "1"
PACKAGES_SKIPPED_LINE: Final = (
    f"Package install check skipped: the caller already ran it ({PACKAGES_ENSURED_ENV}={PACKAGES_ENSURED_VALUE})"
)
FAILED_STATUS: Final = "FAILED"
INDEX_JSON: Final = "index.json"
FULL_LOG: Final = "full.log"
#: The test tiers: the wrapper parameter, its parsed option's name, and the runner flag. At most one per run.
TIERS: Final = (
    ("Unit", "unit", "--unit"),
    ("Integration", "integration", "--integration"),
    ("E2E", "e2_e", "--e2e"),
    ("Fast", "fast", "--fast"),
    ("Slow", "slow", "--slow"),
)
#: Switches passed straight to the runner: the parsed option's name and the runner flag.
_RUNNER_SWITCHES: Final = (
    ("coverage", "--coverage"),
    ("verbose_output", "--verbose"),
    ("no_save", "--no-save"),
    ("no_auto_install", "--no-auto-install"),
)
COUNT_KEYS: Final = ("passed", "failed", "error", "skipped", "xfailed", "xpassed", "warnings")
#: The counts the summary table shows, with their labels, in order.
_SUMMARY_LABELS: Final = (
    ("passed", "pass"),
    ("failed", "fail"),
    ("error", "error"),
    ("skipped", "skip"),
    ("xfailed", "xfail"),
    ("xpassed", "xpass"),
)
_COUNT_PATTERNS: Final = {
    "passed": re.compile(r"\b(\d+)\s+passed\b", re.IGNORECASE),
    "failed": re.compile(r"\b(\d+)\s+failed\b", re.IGNORECASE),
    "error": re.compile(r"\b(\d+)\s+error", re.IGNORECASE),
    "skipped": re.compile(r"\b(\d+)\s+skipped\b", re.IGNORECASE),
    "xfailed": re.compile(r"\b(\d+)\s+xfailed\b", re.IGNORECASE),
    "xpassed": re.compile(r"\b(\d+)\s+xpassed\b", re.IGNORECASE),
    "warnings": re.compile(r"\b(\d+)\s+warning", re.IGNORECASE),
}
_HAS_RESULTS_RE: Final = re.compile(r"\d+\s+(passed|failed|error|skipped|xfailed|xpassed|warning)", re.IGNORECASE)
_TIMING_RE: Final = re.compile(r"\bin\s+\d+\.\d+s\b", re.IGNORECASE)
_SEPARATORS_RE: Final = re.compile(r"^=+.*=+$")
_DESELECTED_RE: Final = re.compile(r"deselected", re.IGNORECASE)
_PASS_FAIL_ERROR_RE: Final = re.compile(r"\b\d+\s+(passed|failed|error)\b", re.IGNORECASE)
_LINE_BREAKS_RE: Final = re.compile(r"[\r\n]+")
#: The lines by which the runner names the run directory it owns: quiet mode prints
#: ``Details: <run>/index.json`` (or ``Log: <run>/full.log``), verbose mode
#: ``Structured test results: <run>/index.json`` and ``Log file: <run>/full.log``.
_INDEX_LINE_RE: Final = re.compile(r"^\s*(?:Details|Structured test results):\s+(.+index\.json)\s*$", re.IGNORECASE | re.MULTILINE)
_LOG_LINE_RE: Final = re.compile(r"^\s*(?:Log file|Log):\s+(.+full\.log)\s*$", re.IGNORECASE | re.MULTILINE)
#: A project argument that is a path, whose folder name is the project: ``.\\datrix-common\\``, ``D:\\...``.
_PATH_INPUT_RE: Final = re.compile(r"^\.|^[A-Za-z]:\\")
_TRAILING_SEPARATORS_RE: Final = re.compile(r"[\\/]+$")
_SEPARATOR_RE: Final = re.compile(r"[\\/]")
_RULE: Final = "=" * 40
_WINDOWS: Final = os.name == "nt"


class RunEnded(Exception):
    """The run ends before any test, its messages printed, with ``exit_code``."""

    def __init__(self, exit_code: int) -> None:
        super().__init__(f"run ended with exit code {exit_code}")
        self.exit_code = exit_code


@dataclass(frozen=True)
class RunPaths:
    """The run directory files the runner reported for one package; each None when not reported or absent."""

    index: Path | None
    log: Path | None


@dataclass(frozen=True)
class ProjectResult:
    """One package's run: the runner's exit code, the counts read from its output, and its files."""

    exit_code: int
    counts: dict[str, int]
    paths: RunPaths

    @property
    def success(self) -> bool:
        return self.exit_code == 0


# ---------------------------------------------------------------------------
# The install check and the children's environment
# ---------------------------------------------------------------------------


def install_check_required(environ: Mapping[str, str]) -> bool:
    """True unless *environ* says the caller already ran the package install check."""
    return environ.get(PACKAGES_ENSURED_ENV) != PACKAGES_ENSURED_VALUE


def ensure_packages(environ: Mapping[str, str], check: Callable[[], bool]) -> bool:
    """Run the package install *check* unless *environ* says the caller ran it; False when it failed."""
    return not install_check_required(environ) or check()


def child_environment(environ: Mapping[str, str]) -> dict[str, str]:
    """A child's environment: a copy of *environ* carrying the flag that the install check already ran."""
    return {**environ, PACKAGES_ENSURED_ENV: PACKAGES_ENSURED_VALUE}


def _run_child(module: str, arguments: Sequence[str], environment: Mapping[str, str]) -> int:
    """Run ``python -m <module>`` in the shared venv, its output going straight to the console."""
    sys.stdout.flush()
    return subprocess.run([sys.executable, "-m", module, *arguments], env=dict(environment), check=False).returncode


def _run_child_teed(module: str, arguments: Sequence[str], environment: Mapping[str, str]) -> tuple[int, str]:
    """Run ``python -m <module>``, showing each output line (stdout and stderr) as it arrives and
    capturing them; the exit code and the captured text. The child writes its pipe in the locale
    encoding, and the pipe is read in that same encoding."""
    sys.stdout.flush()
    captured: list[str] = []
    with subprocess.Popen(
        [sys.executable, "-m", module, *arguments],
        env=dict(environment),
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        errors="replace",
        bufsize=1,
    ) as process:
        if process.stdout is None:
            raise RuntimeError(f"the {module} child was started without an output pipe; expected one to read its counts")
        for line in process.stdout:
            sys.stdout.write(line)
            sys.stdout.flush()
            captured.append(line)
    return process.returncode, "".join(captured)


# ---------------------------------------------------------------------------
# Which packages run
# ---------------------------------------------------------------------------


def normalize_project(raw: str) -> str:
    """A project argument as a package name: a path (``.\\datrix-common\\``, ``D:\\...``) becomes its
    folder's name, resolved when it exists; anything else is the argument, trimmed."""
    trimmed = raw.strip()
    if not _PATH_INPUT_RE.search(trimmed):
        return trimmed
    path = Path(trimmed)
    if path.exists():
        return path.resolve().name
    return _SEPARATOR_RE.split(_TRAILING_SEPARATORS_RE.sub("", trimmed))[-1]


def _no_projects_found(workspace: Path) -> RunEnded:
    """Print that *workspace* holds no testable package; the exception that ends the run."""
    print(f"ERROR: No Datrix projects found in: {workspace}")
    return RunEnded(EXIT_VIOLATION)


def _all_projects(available: list[str], workspace: Path) -> list[str]:
    if not available:
        ended = _no_projects_found(workspace)
        print()
        print("Please ensure Datrix projects are located in the Datrix workspace root directory.")
        raise ended
    print(f"Running tests for all projects: {', '.join(available)}")
    return available


def latest_run_failed(project_dir: Path) -> bool:
    """True when the project's most recent saved run failed or errored; False when it passed or none is saved."""
    from datrix_scripts.test_project import get_latest_test_result_status

    return get_latest_test_result_status(project_dir) == FAILED_STATUS


def _rerun_projects(available: list[str], workspace: Path) -> list[str]:
    if not available:
        raise _no_projects_found(workspace)
    print("Checking latest test results for all projects...")
    queued: list[str] = []
    for project in available:
        if latest_run_failed(workspace / project):
            print(f"  [FAIL] {project} - queued for re-run")
            queued.append(project)
        else:
            print(f"  [OK]   {project} - latest run passed or no results, skipping")
    print()
    if not queued:
        print("No projects with failing latest test runs found. Nothing to re-run.")
        raise RunEnded(EXIT_PASS)
    print(f"Re-running tests for {len(queued)} project(s): {', '.join(queued)}")
    return queued


def _named_projects(named: Sequence[str], available: list[str]) -> list[str]:
    selected = [project for project in map(normalize_project, named) if project in available]
    if not selected:
        print("ERROR: No valid projects specified.")
        print()
        print("Available projects:")
        for project in available:
            print(f" - {project}")
        raise RunEnded(EXIT_VIOLATION)
    print(f"Running tests for projects: {', '.join(selected)}")
    return selected


def usage_lines(available: Sequence[str], workspace: Path, *, windows: bool = _WINDOWS) -> list[str]:
    """What a run naming no package prints: the usage, examples and the packages it could name."""
    script = ".\\test.ps1" if windows else "./test.sh"
    folder, second_folder = (".\\datrix-common\\", ".\\datrix-language\\") if windows else ("./datrix-common/", "./datrix-language/")
    flag = {name: wrapper_flag(name, windows=windows) for name in
            ("All", "Rerun", "Coverage", "VerboseOutput", "Unit", "Fast", "Specific", "Keyword", "Tag", "ListTags")}
    lines = [
        "", "ERROR: No projects specified.", "", "Usage:",
        f" {script} <project-name> [options]",
        f" {script} <folder-path> [options]",
        f" {script} {flag['All']} [options]",
        f" {script} {flag['Rerun']} [options]",
        "", "Examples:",
        f" {script} datrix-common",
        f" {script} {folder}",
        f" {script} datrix-common datrix-language",
        f" {script} {folder} {second_folder}",
        f" {script} {flag['All']}",
        f" {script} {flag['Rerun']}",
        f" {script} datrix-common {flag['Coverage']} {flag['VerboseOutput']}",
        f" {script} datrix-common {flag['Unit']}",
        f" {script} {flag['All']} {flag['Fast']}",
        f' {script} datrix-common {flag["Specific"]} "tests/unit/test_parser.py"',
        f' {script} datrix-language {flag["Keyword"]} "test_basic"',
        f" {script} datrix-codegen-python datrix-codegen-typescript {flag['Tag']} gateway",
        f" {script} datrix-codegen-python {flag['ListTags']}",
        "",
    ]
    if available:
        lines.extend(["Available projects:", *(f" - {project}" for project in available), "", f"Total: {len(available)} projects"])
    else:
        lines.append(f"No projects found in: {workspace}")
    lines.append("")
    return lines


def select_projects(args: argparse.Namespace, workspace: Path, *, windows: bool = _WINDOWS) -> list[str]:
    """The packages this run tests, its selection line printed.

    Raises:
        RunEnded: Nothing to run: no package found, none of the named ones valid, nothing to
            re-run, or no package named. Its messages are printed.
    """
    available = testable_package_names(workspace)
    if args.all:
        return _all_projects(available, workspace)
    if args.rerun:
        return _rerun_projects(available, workspace)
    named = [*args.projects, *args.positional_projects]
    if named:
        return _named_projects(named, available)
    print("\n".join(usage_lines(available, workspace, windows=windows)))
    raise RunEnded(EXIT_VIOLATION)


# ---------------------------------------------------------------------------
# The runner's command line
# ---------------------------------------------------------------------------


def tier_error_lines(args: argparse.Namespace, *, windows: bool = _WINDOWS) -> list[str]:
    """The refusal when more than one test tier is named; empty when at most one is."""
    if sum(bool(vars(args)[option]) for _, option, _ in TIERS) <= 1:
        return []
    choices = ", ".join(wrapper_flag(parameter, windows=windows) for parameter, _, _ in TIERS)
    return ["ERROR: Only one test type option can be specified at a time.", f"Choose one of: {choices}"]


def runner_arguments(args: argparse.Namespace) -> list[str]:
    """The ``test_project`` arguments every package's run shares (the package name follows them)."""
    options = vars(args)
    arguments = [flag for option, flag in _RUNNER_SWITCHES if options[option]]
    arguments.extend(flag for _, option, flag in TIERS if options[option])
    for value, flag in ((args.specific, "--specific"), (args.keyword, "-k"), (args.tag, "--tags")):
        if value:
            arguments.extend([flag, value])
    if args.dbg:
        arguments.append("--debug")
    return arguments


# ---------------------------------------------------------------------------
# Reading a package's run
# ---------------------------------------------------------------------------


def _is_summary_line(line: str) -> bool:
    """A pytest summary line (``7 failed, 185 passed in 14.46s``, or one between ``=`` rules), never a
    ``collected N items / M deselected`` line."""
    if not _HAS_RESULTS_RE.search(line):
        return False
    if not (_TIMING_RE.search(line) or _SEPARATORS_RE.search(line)):
        return False
    return not (_DESELECTED_RE.search(line) and not _PASS_FAIL_ERROR_RE.search(line))


def line_counts(line: str) -> dict[str, int]:
    """Every count a summary line states; zero for each it does not."""
    counts = dict.fromkeys(COUNT_KEYS, 0)
    for key, pattern in _COUNT_PATTERNS.items():
        match = pattern.search(line)
        if match:
            counts[key] = int(match.group(1))
    return counts


def parse_counts(output: str) -> dict[str, int]:
    """The test counts of a run's *output*: its last pytest summary line, plus the one before it when
    the run had two phases (parallel, then serial); zero for every count when none is found."""
    phases: list[dict[str, int]] = []
    for raw in reversed(_LINE_BREAKS_RE.split(output)):
        line = raw.strip()
        if not _is_summary_line(line):
            continue
        counts = line_counts(line)
        if counts["passed"] or counts["failed"] or counts["error"]:
            phases.append(counts)
            if len(phases) == 2:
                break
    return {key: sum(phase[key] for phase in phases) for key in COUNT_KEYS}


def _reported_path(pattern: re.Pattern[str], output: str) -> Path | None:
    match = pattern.search(output)
    return Path(match.group(1).strip()) if match else None


def run_paths(output: str) -> RunPaths:
    """The run directory files the runner printed in *output*.

    Only the paths the runner itself printed: neither the newest directory under ``.test_results``
    nor a name rebuilt from a timestamp, either of which adopts another run's results whenever a
    second run of the same package is in flight. Each file implies its sibling in the one run
    directory, and a file that does not exist is dropped.
    """
    index = _reported_path(_INDEX_LINE_RE, output)
    log = _reported_path(_LOG_LINE_RE, output)
    if index is not None and log is None and (index.parent / FULL_LOG).exists():
        log = index.parent / FULL_LOG
    if log is not None and index is None and (log.parent / INDEX_JSON).exists():
        index = log.parent / INDEX_JSON
    return RunPaths(
        index=index if index is not None and index.exists() else None,
        log=log if log is not None and log.exists() else None,
    )


def prompt_text(log: Path, index: Path | None, counts: Mapping[str, int]) -> str:
    """The note appended to a failing run's ``full.log`` (*log*): what to fix, and the run's
    ``index.json`` to read when it has one."""
    parts = [
        f"{counts[key]} {noun}"
        for key, noun in (("failed", "failures"), ("error", "errors"), ("warnings", "warning"))
        if counts[key] > 0
    ]
    if index is not None:
        body = f"Read {os.path.abspath(index)} and fix failures by cluster. {', '.join(parts)} found."
    else:
        body = f"Peruse {os.path.abspath(log)} and fix {', '.join(parts)}."
    return f"\n<--->\n{body}\n<--->\n"


def _append_prompt(paths: RunPaths, counts: Mapping[str, int]) -> None:
    if paths.log is None or not (counts["failed"] or counts["error"] or counts["warnings"]):
        return
    try:
        with paths.log.open("a", encoding="utf-8") as log:
            log.write(prompt_text(paths.log, paths.index, counts))
    except OSError as exc:
        print(f"WARNING: Failed to append AI prompt to project log file: {exc}", file=sys.stderr)


def run_project(
    position: tuple[int, int], project: str, arguments: Sequence[str], environment: Mapping[str, str], *, no_save: bool
) -> ProjectResult:
    """Run one package's suite (*position* is its ``(number, total)``) and print its verdict."""
    number, total = position
    print()
    print(_RULE)
    print(f"[{number}/{total}] Testing: {project}")
    print(_RULE)
    print()
    exit_code, output = _run_child_teed(TEST_PROJECT_MODULE, [*arguments, project], environment)
    counts = parse_counts(output)
    paths = run_paths(output)
    if output and paths.index is None and paths.log is None and not no_save:
        print(f"  (no run directory reported by the test runner for {project} - results were not saved)")
    _append_prompt(paths, counts)
    print()
    print(f"[PASS] Tests passed for {project}" if exit_code == 0 else f"[FAIL] Tests failed for {project} (exit code: {exit_code})")
    return ProjectResult(exit_code=exit_code, counts=counts, paths=paths)


# ---------------------------------------------------------------------------
# After the runs
# ---------------------------------------------------------------------------


def summary_line(project: str, result: ProjectResult) -> str:
    """One package's row of the summary table: its verdict and every non-zero count."""
    info = [f"{label}: {result.counts[key]}" for key, label in _SUMMARY_LABELS if result.counts[key] > 0]
    suffix = f" ({', '.join(info)})" if info else ""
    return f" {'[PASS]' if result.success else '[FAIL]'} : {project}{suffix}"


def total_line(total: int, results: Mapping[str, ProjectResult]) -> str:
    """The line callers parse for the run's verdict."""
    passed = sum(result.success for result in results.values())
    return f"Total: {total} | Passed: {passed} | Failed: {len(results) - passed}"


def print_summary(total: int, results: Mapping[str, ProjectResult]) -> None:
    print()
    print(_RULE)
    print("Test Summary")
    print(_RULE)
    for project in sorted(results):
        print(summary_line(project, results[project]))
    print()
    print(total_line(total, results))


def write_digests(results: Mapping[str, ProjectResult], environment: Mapping[str, str]) -> None:
    """A failure digest for each failed package with a saved run. A digest never changes the exit
    code (the tests decide it), but one that could not be written says so."""
    for project in sorted(results):
        result = results[project]
        if result.success:
            continue
        print()
        if result.paths.index is None:
            print(f"No failure digest for {project}: the run saved no index.json.")
            continue
        digest_exit = _run_child(RUN_DIGEST_MODULE, [str(result.paths.index)], environment)
        if digest_exit != 0:
            print(f"No failure digest for {project} (run_digest.py exit code: {digest_exit}).")


def list_tags(projects: Sequence[str], specific: str, environment: Mapping[str, str]) -> int:
    """One collection-only tag listing per package, then the vocabulary comparison (report only).
    Runs no test; the exit code is the first failing listing's, else 0."""
    exit_code = EXIT_PASS
    for project in projects:
        print()
        print(f"=== {project} ===")
        selection = ["--specific", specific] if specific else []
        project_exit = _run_child(TEST_PROJECT_MODULE, ["--list-tags", *selection, project], environment)
        if project_exit != 0 and exit_code == EXIT_PASS:
            exit_code = project_exit
    print()
    print("=== Tag vocabulary ===")
    _run_child(TAG_VOCABULARY_MODULE, projects, environment)
    return exit_code


def run(args: argparse.Namespace, *, windows: bool = _WINDOWS) -> int:
    """Select the packages, run the install check, then list their tags or run their suites; the exit code."""
    from datrix_scripts.venv import require_packages

    try:
        projects = select_projects(args, WORKSPACE_DIR, windows=windows)
    except RunEnded as ended:
        return ended.exit_code
    if not install_check_required(os.environ):
        print(PACKAGES_SKIPPED_LINE)
    tier_error = tier_error_lines(args, windows=windows)
    if tier_error:
        print("\n".join(tier_error))
        return EXIT_VIOLATION
    if not ensure_packages(os.environ, require_packages):
        return EXIT_VIOLATION
    environment = child_environment(os.environ)
    if args.list_tags:
        return list_tags(projects, args.specific, environment)
    arguments = runner_arguments(args)
    results: dict[str, ProjectResult] = {}
    for number, project in enumerate(projects, start=1):
        results[project] = run_project((number, len(projects)), project, arguments, environment, no_save=args.no_save)
    print_summary(len(projects), results)
    if not args.no_digest:
        write_digests(results, environment)
    return EXIT_PASS if all(result.success for result in results.values()) else EXIT_VIOLATION


def build_parser() -> argparse.ArgumentParser:
    """The options ``test/test.ps1`` passes (each wrapper parameter as ``--kebab-name``)."""
    parser = argparse.ArgumentParser(
        prog="test", description="Run the tests of one or more Datrix packages.", allow_abbrev=False
    )
    parser.add_argument("positional_projects", nargs="*", metavar="PROJECT", help="as --projects, for a caller of the .sh twin")
    parser.add_argument("--projects", action="append", default=[], metavar="PROJECT",
                        help="a package name or folder path to test (repeat for each)")
    parser.add_argument("--all", action="store_true", help="test every package that carries a test suite")
    parser.add_argument("--rerun", action="store_true", help="test only the packages whose latest saved run failed")
    parser.add_argument("--coverage", action="store_true", help="write coverage reports")
    parser.add_argument("--verbose-output", action="store_true", help="show the full test output")
    parser.add_argument("--no-save", action="store_true", help="save no run directory")
    parser.add_argument("--no-auto-install", action="store_true", help="prompt instead of installing a missing dependency")
    for parameter, option, _ in TIERS:
        parser.add_argument(f"--{option.replace('_', '-')}", action="store_true", help=f"run only the {parameter} tier")
    parser.add_argument("--specific", default="", help="test files or node IDs, comma-separated, run in one session")
    parser.add_argument("--keyword", default="", help="pytest -k expression")
    parser.add_argument("--tag", default="", help="run only the tests carrying one of these feature tags (comma-separated)")
    parser.add_argument("--list-tags", action="store_true", help="list each package's feature tags; run no test")
    parser.add_argument("--no-digest", action="store_true", help="write no failure digest")
    parser.add_argument("--dbg", action="store_true", help="debug logging, here and in the runner")
    parser.add_argument("--self-test", action="store_true", help="run this module's self-test")
    return parser


# ---------------------------------------------------------------------------
# Self-test
# ---------------------------------------------------------------------------


def _check_count_parsing() -> None:
    two_phase = (
        "collected 40 items / 2 errors / 5 deselected\n"
        "===== 30 passed, 1 skipped, 2 warnings in 3.10s =====\n"
        "noise\n"
        "===== 5 passed, 2 failed, 1 error in 1.50s =====\n"
    )
    counts = parse_counts(two_phase)
    expected = {"passed": 35, "failed": 2, "error": 1, "skipped": 1, "xfailed": 0, "xpassed": 0, "warnings": 2}
    assert counts == expected, f"two-phase counts: {counts}"
    single = parse_counts("12 passed, 3 xfailed in 0.40s\r\n")
    assert single["passed"] == 12 and single["xfailed"] == 3, f"single-phase counts: {single}"
    deselected_only = parse_counts("===== 40 deselected in 0.10s =====\n")
    assert deselected_only == dict.fromkeys(COUNT_KEYS, 0), f"a deselected-only line was counted: {deselected_only}"
    assert parse_counts("") == dict.fromkeys(COUNT_KEYS, 0), "empty output was counted"


def _check_run_paths() -> None:
    with TemporaryDirectory() as temp:
        run_dir = Path(temp) / "test-results-20260101-000000"
        write_files(run_dir, {INDEX_JSON: "{}", FULL_LOG: "log"})
        index, log = run_dir / INDEX_JSON, run_dir / FULL_LOG
        cases = (
            (f"  Details: {index}\n", RunPaths(index, log)),
            (f"Log file: {log}\nStructured test results: {index}\n", RunPaths(index, log)),
            (f"Log: {log}\n", RunPaths(index, log)),
            (f"Details: {Path(temp) / 'gone' / INDEX_JSON}\n", RunPaths(None, None)),
            ("no paths here\n", RunPaths(None, None)),
        )
        for output, expected in cases:
            assert run_paths(output) == expected, f"{output!r} resolved to {run_paths(output)}, expected {expected}"


def _check_project_normalization() -> None:
    with TemporaryDirectory() as temp:
        write_files(Path(temp), {"datrix-shop/README.md": ""})
        cases = (
            ("datrix-common", "datrix-common"),
            ("  datrix-common ", "datrix-common"),
            (".\\datrix-missing\\", "datrix-missing"),
            ("./datrix-missing/", "datrix-missing"),
            ("Q:\\work\\datrix-gone\\", "datrix-gone"),
        )
        for raw, expected in cases:
            assert normalize_project(raw) == expected, f"{raw!r} normalized to {normalize_project(raw)!r}"
        # An existing path is resolved: "./datrix-shop/." names datrix-shop, where its text's last part is ".".
        with contextlib.chdir(temp):
            assert normalize_project("./datrix-shop/.") == "datrix-shop", normalize_project("./datrix-shop/.")


def _check_rerun_decision() -> None:
    with TemporaryDirectory() as temp:
        workspace = Path(temp)
        write_files(workspace, {
            "datrix-a/.test_results/test-results-20260101-000000/index.json": json.dumps({"result": FAILED_STATUS}),
            "datrix-b/.test_results/test-results-20260101-000000/index.json": json.dumps(
                {"result": "PASSED", "counts": {"failed": 0, "error": 0}}),
            "datrix-c/.test_results/test-results-20260101-000000/index.json": "not json",
            "datrix-c/.test_results/test-results-20260101-000000/full.log": "=== 3 failed, 1 passed in 1.00s ===",
            "datrix-d/.test_results/test-results-20250101-000000.log": "2 error",
            "datrix-e/README.md": "",
            "datrix-f/.test_results/test-results-20250101-000000/index.json": json.dumps({"result": FAILED_STATUS}),
            "datrix-f/.test_results/test-results-20260101-000000/index.json": json.dumps({"result": "PASSED"}),
        })
        expected = {"datrix-a": True, "datrix-b": False, "datrix-c": True, "datrix-d": True, "datrix-e": False, "datrix-f": False}
        decided = {project: latest_run_failed(workspace / project) for project in expected}
        assert decided == expected, f"rerun decisions {decided}, expected {expected}"


def _check_prompt_text() -> None:
    with TemporaryDirectory() as temp:
        run_dir = Path(temp)
        write_files(run_dir, {INDEX_JSON: "{}", FULL_LOG: "log\n"})
        counts = {**dict.fromkeys(COUNT_KEYS, 0), "failed": 2, "warnings": 1}
        index, log = run_dir / INDEX_JSON, run_dir / FULL_LOG
        with_index = prompt_text(log, index, counts)
        assert with_index == f"\n<--->\nRead {os.path.abspath(index)} and fix failures by cluster. 2 failures, 1 warning found.\n<--->\n", with_index
        log_only = prompt_text(log, None, {**counts, "error": 3})
        assert log_only == f"\n<--->\nPeruse {os.path.abspath(log)} and fix 2 failures, 3 errors, 1 warning.\n<--->\n", log_only
        _append_prompt(RunPaths(index, log), counts)
        assert log.read_text(encoding="utf-8") == "log\n" + with_index, "the prompt was not appended to full.log"
        _append_prompt(RunPaths(index, log), dict.fromkeys(COUNT_KEYS, 0))
        assert log.read_text(encoding="utf-8") == "log\n" + with_index, "a clean run appended a prompt"


def _check_summary_lines() -> None:
    no_paths = RunPaths(None, None)
    passed = ProjectResult(0, {**dict.fromkeys(COUNT_KEYS, 0), "passed": 28, "skipped": 2}, no_paths)
    failed = ProjectResult(1, {**dict.fromkeys(COUNT_KEYS, 0), "failed": 1, "warnings": 4}, no_paths)
    empty = ProjectResult(0, dict.fromkeys(COUNT_KEYS, 0), no_paths)
    assert summary_line("datrix-a", passed) == " [PASS] : datrix-a (pass: 28, skip: 2)", summary_line("datrix-a", passed)
    assert summary_line("datrix-b", failed) == " [FAIL] : datrix-b (fail: 1)", summary_line("datrix-b", failed)
    assert summary_line("datrix-c", empty) == " [PASS] : datrix-c", summary_line("datrix-c", empty)
    results = {"datrix-a": passed, "datrix-b": failed}
    assert total_line(2, results) == "Total: 2 | Passed: 1 | Failed: 1", total_line(2, results)


def _check_tiers_and_runner_arguments() -> None:
    parser = build_parser()
    two = parser.parse_intermixed_args(["datrix-common", "--unit", "--fast"])
    assert tier_error_lines(two, windows=True) == [
        "ERROR: Only one test type option can be specified at a time.",
        "Choose one of: -Unit, -Integration, -E2E, -Fast, -Slow",
    ], tier_error_lines(two, windows=True)
    assert tier_error_lines(two, windows=False)[1] == "Choose one of: --unit, --integration, --e2-e, --fast, --slow"
    one = parser.parse_intermixed_args(
        ["--projects=datrix-common", "--e2-e", "--specific=tests/a.py,tests/b.py", "--keyword=enum", "--tag=gateway",
         "--no-save", "--verbose-output", "--dbg"])
    assert not tier_error_lines(one), tier_error_lines(one)
    expected = ["--verbose", "--no-save", "--e2e", "--specific", "tests/a.py,tests/b.py", "-k", "enum", "--tags", "gateway", "--debug"]
    assert runner_arguments(one) == expected, runner_arguments(one)


def _check_selection_and_install_decision() -> None:
    parser = build_parser()
    with TemporaryDirectory() as temp:
        workspace = Path(temp)
        write_files(workspace, {"datrix-shop/tests/test_cart.py": "", "datrix-docs/README.md": ""})
        assert testable_package_names(workspace) == ["datrix-shop"], testable_package_names(workspace)
        with contextlib.redirect_stdout(io.StringIO()):
            for argv in (["no-such-package"], ["datrix-docs"], []):
                try:
                    select_projects(parser.parse_intermixed_args(argv), workspace)
                except RunEnded as ended:
                    assert ended.exit_code == EXIT_VIOLATION, f"{argv} ended with {ended.exit_code}"
                    continue
                raise AssertionError(f"{argv} selected packages")
            chosen = select_projects(parser.parse_intermixed_args(["--projects=x", "datrix-shop"]), workspace)
        assert chosen == ["datrix-shop"], chosen
    calls: list[str] = []

    def recording_check() -> bool:
        calls.append("check")
        return True

    caller = {PACKAGES_ENSURED_ENV: PACKAGES_ENSURED_VALUE}
    assert ensure_packages(caller, recording_check) and not calls, "the check ran though the caller ran it"
    assert ensure_packages({}, recording_check) and calls == ["check"], "the check did not run"
    plain = {"PATH": "x"}
    child = child_environment(plain)
    assert child[PACKAGES_ENSURED_ENV] == PACKAGES_ENSURED_VALUE and PACKAGES_ENSURED_ENV not in plain, child


def _check_abbreviations_refused() -> None:
    """The full-suite guard reads ``test.sh``'s flags by their exact spelling, so an abbreviation it
    cannot see (``--al`` for ``--all``, ``--rer`` for ``--rerun``, ``--ta=`` for ``--tag=``) must be a
    usage error here, never a wider run than the guard judged."""
    parser = build_parser()
    for argv in (
        ["datrix-common", "--al", "--tag", "gateway"],
        ["datrix-common", "--rer", "--tag", "gateway"],
        ["datrix-common", "--tag", "a", "--ta=b,c,d,e"],
    ):
        try:
            with contextlib.redirect_stderr(io.StringIO()):  # argparse's usage text for a case refused on purpose.
                parsed = parser.parse_intermixed_args(argv)
        except SystemExit as exc:
            assert exc.code == EXIT_USAGE, f"{argv} exited {exc.code}, expected the usage error {EXIT_USAGE}"
            continue
        raise AssertionError(f"{argv} was accepted as {vars(parsed)}; an abbreviated option must be refused")


_CHECKS: Final = (
    _check_count_parsing,
    _check_abbreviations_refused,
    _check_run_paths,
    _check_project_normalization,
    _check_rerun_decision,
    _check_prompt_text,
    _check_summary_lines,
    _check_tiers_and_runner_arguments,
    _check_selection_and_install_decision,
)


def main(argv: Sequence[str] | None = None) -> int:
    ensure_utf8_stdio()
    parser = build_parser()
    args = parser.parse_intermixed_args(argv)
    configure_logging(args.dbg)
    if args.self_test:
        return run_self_test(_CHECKS, wrapper=WRAPPER, module=MODULE, parser=parser)
    return run(args)


if __name__ == "__main__":
    sys.exit(main())
