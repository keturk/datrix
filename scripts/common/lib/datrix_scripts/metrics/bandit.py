"""Run the Bandit security scanner on Datrix projects' src trees.

Finds common security issues in Python code. A project passes when Bandit reports no issue at or
above the severity and confidence thresholds; the run exits 0 when every project passed, else 1.
Bandit's findings are printed as Bandit prints them, in the format asked for; no Bandit test is
skipped or disabled here.

Run by ``metrics/bandit.ps1`` (POSIX twin ``bandit.sh``): project names positionally or as
``--projects``, or ``--all``; ``--severity`` / ``--confidence`` low|medium|high (default medium);
``--format`` screen|json|csv|html|yaml|sarif; ``--stop-on-error``; ``--verbose-output`` (Bandit's own
output streamed as it runs); ``--self-test``.
"""

from __future__ import annotations

import argparse
import contextlib
import importlib.util
import io
import subprocess
import sys
import tempfile
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Final

from datrix_scripts.framework_repos import PackageMarker
from datrix_scripts.metrics.projects import (
    EXIT_FAILED,
    EXIT_PASSED,
    SHOWCASE,
    USAGE_ONLY_WORDING,
    ProjectSelectionError,
    add_project_arguments,
    print_stderr,
    print_summary,
    run_projects,
    select_projects,
)
from datrix_scripts.paths import WORKSPACE_DIR
from datrix_scripts.test.wrappers import METRICS_SCRIPTS_DIR, module_main, run_self_test
from datrix_scripts.venv import SCRIPTS_DEPENDENCY_GROUP, missing_declared_tool

MODULE: Final = "datrix_scripts.metrics.bandit"
WRAPPER: Final = "bandit"
# Bandit runs as a module of this interpreter, so the shared venv's copy is the one that scans.
_BANDIT_MODULE: Final = "bandit"
EXIT_TOOL_MISSING: Final = 2
LEVELS: Final = ("low", "medium", "high")
DEFAULT_LEVEL: Final = "medium"
SEVERITY_MAP: Final = {"low": "-l", "medium": "-ll", "high": "-lll"}
CONFIDENCE_MAP: Final = {"low": "-i", "medium": "-ii", "high": "-iii"}
SCREEN_FORMAT: Final = "screen"
BANDIT_FORMATS: Final = (SCREEN_FORMAT, "json", "csv", "html", "yaml", "sarif")
_EXCLUDED: Final = "tests,__pycache__"
SUMMARY_TITLE: Final = "Bandit Security Summary"
USAGE_LINES: Final = (
    "Usage: .\\bandit.ps1 <project> [options] or .\\bandit.ps1 -All [options]",
    " -Severity low|medium|high -Confidence low|medium|high -Format screen|json|csv|html|yaml|sarif",
)


@dataclass(frozen=True)
class ScanOptions:
    """The thresholds and output form of one run, shared by every project."""

    severity: str
    confidence: str
    output_format: str
    verbose: bool


def bandit_command(src: Path, options: ScanOptions) -> list[str]:
    """The Bandit argument vector scanning *src* recursively at *options*' thresholds."""
    command = [
        sys.executable,
        "-m",
        _BANDIT_MODULE,
        "-r",
        str(src),
        "--exclude",
        _EXCLUDED,
        SEVERITY_MAP[options.severity],
        CONFIDENCE_MAP[options.confidence],
    ]
    if options.output_format != SCREEN_FORMAT:
        command.extend(["-f", options.output_format])
    return command


def scan_project(project_root: Path, options: ScanOptions) -> int:
    """Bandit over ``<project_root>/src``: its exit code (0 clean, 1 issues found), 1 when the project or
    its ``src/`` is missing, 2 when Bandit is not installed in this interpreter.

    Captured (no ``verbose``), Bandit's report is printed only when it found issues, and its log lines
    always; with ``verbose`` both stream as Bandit writes them.
    """
    if importlib.util.find_spec(_BANDIT_MODULE) is None:
        print_stderr(missing_declared_tool("bandit", SCRIPTS_DEPENDENCY_GROUP))
        return EXIT_TOOL_MISSING
    if not project_root.is_dir():
        print_stderr(f"Error: project root is not a directory: {project_root}")
        return EXIT_FAILED
    src = project_root / PackageMarker.SRC.value
    if not src.is_dir():
        print_stderr(f"Error: project has no src/ directory: {project_root}")
        return EXIT_FAILED
    sys.stdout.flush()
    result = subprocess.run(
        bandit_command(src, options), capture_output=not options.verbose, text=True, cwd=str(project_root)
    )
    if result.returncode != 0 and result.stdout:
        print(result.stdout, end="")
    if result.stderr:
        print_stderr(result.stderr.rstrip("\n"))
    return result.returncode


def _selected(args: argparse.Namespace, workspace: Path) -> list[str]:
    """The projects to scan, the line announcing them printed.

    Raises:
        ProjectSelectionError: The selection is empty (the wrapper's wording).
    """
    projects = select_projects(args, workspace, usage=USAGE_LINES, wording=USAGE_ONLY_WORDING)
    scope = " all projects" if args.all else ""
    print(f"Running Bandit security scan for{scope}: {', '.join(projects)}")
    return projects


def run_bandit(args: argparse.Namespace, workspace: Path) -> int:
    """The wrapper's run over *workspace*: select, scan each project, summarize."""
    try:
        projects = _selected(args, workspace)
    except ProjectSelectionError as exc:
        for line in exc.lines:
            print(line)
        return EXIT_FAILED
    options = ScanOptions(
        severity=args.severity, confidence=args.confidence, output_format=args.output_format, verbose=args.verbose_output
    )
    results = run_projects(
        projects, lambda project: scan_project(workspace / project, options), stop_on_error=args.stop_on_error
    )
    return print_summary(SUMMARY_TITLE, results)


def build_parser() -> argparse.ArgumentParser:
    """The options of ``metrics/bandit.ps1``: one per wrapper parameter, spelled exactly."""
    parser = argparse.ArgumentParser(description="Bandit security scanner for Datrix projects.", allow_abbrev=False)
    add_project_arguments(parser)
    parser.add_argument(
        "--severity", choices=LEVELS, default=DEFAULT_LEVEL, help="Minimum severity to report (default: medium)."
    )
    parser.add_argument(
        "--confidence", choices=LEVELS, default=DEFAULT_LEVEL, help="Minimum confidence to report (default: medium)."
    )
    parser.add_argument(
        "--format", choices=BANDIT_FORMATS, default=SCREEN_FORMAT, dest="output_format",
        help="Output format (default: screen).",
    )
    parser.add_argument("--stop-on-error", action="store_true", help="Stop on the first project that fails.")
    parser.add_argument("--verbose-output", action="store_true", help="Stream Bandit's output as it runs.")
    parser.add_argument("--self-test", action="store_true", help="Run only the self-test over planted projects.")
    parser.set_defaults(debug=False)
    return parser


def _run(args: argparse.Namespace) -> int:
    if args.self_test:
        return run_self_test(
            SELF_TEST_CHECKS, wrapper=WRAPPER, module=MODULE, parser=build_parser(), folder=METRICS_SCRIPTS_DIR
        )
    return run_bandit(args, WORKSPACE_DIR)


# ---------------------------------------------------------------------------
# Self-test
# ---------------------------------------------------------------------------

#: A shell=True call on a non-literal command: Bandit's B602, high severity and high confidence.
_HIGH_ISSUE: Final = "import subprocess\n\n\ndef run(command: str) -> None:\n    subprocess.call(command, shell=True)\n"
#: ``eval`` of a non-literal: Bandit's B307, medium severity.
_MEDIUM_ISSUE: Final = "def parse(text: str) -> object:\n    return eval(text)\n"
_CLEAN: Final = "def add(a: int, b: int) -> int:\n    return a + b\n"


def _plant(root: Path) -> Path:
    """``datrix-high`` (a high-severity issue), ``datrix-medium`` (a medium one), ``datrix-clean``,
    ``datrix-nosrc`` (no ``src/``) and the showcase directory."""
    for name, text in (("datrix-high", _HIGH_ISSUE), ("datrix-medium", _MEDIUM_ISSUE), ("datrix-clean", _CLEAN)):
        src = root / name / PackageMarker.SRC.value
        src.mkdir(parents=True)
        (src / "module.py").write_text(text, encoding="utf-8")
    (root / "datrix-nosrc").mkdir()
    (root / SHOWCASE).mkdir()
    return root


def _report(argv: Sequence[str]) -> tuple[int, str, str]:
    """Exit code, stdout and stderr of a run over a planted workspace."""
    out, err = io.StringIO(), io.StringIO()
    with tempfile.TemporaryDirectory() as raw:
        workspace = _plant(Path(raw))
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = run_bandit(build_parser().parse_args(list(argv)), workspace)
    return code, out.getvalue(), err.getvalue()


def _check_high_issue_fails_and_its_finding_is_printed() -> None:
    code, out, _ = _report(["datrix-high", "datrix-clean"])
    assert code == EXIT_FAILED, (code, out)
    assert "B602" in out, out
    assert " [FAIL] : datrix-high" in out and " [PASS] : datrix-clean" in out, out


def _check_thresholds_reach_bandit() -> None:
    code, out, _ = _report(["datrix-medium", "--severity=high"])
    assert code == EXIT_PASSED, (code, out)
    code, out, _ = _report(["datrix-medium"])
    assert code == EXIT_FAILED and "B307" in out, (code, out)


def _check_json_format_reaches_bandit() -> None:
    options = ScanOptions(severity="high", confidence="low", output_format="json", verbose=False)
    command = bandit_command(Path("src"), options)
    assert command[3:] == ["-r", "src", "--exclude", _EXCLUDED, "-lll", "-i", "-f", "json"], command


def _check_missing_src_fails_and_stop_on_error_stops() -> None:
    code, out, err = _report(["datrix-nosrc", "datrix-clean", "--stop-on-error"])
    assert code == EXIT_FAILED, (code, out)
    assert "Error: project has no src/ directory:" in err, err
    assert "Stopping due to -StopOnError" in out and "datrix-clean" not in out.split("Stopping")[1], out


def _check_refusals_print_the_wrapper_lines() -> None:
    code, out, _ = _report([SHOWCASE])
    assert (code, out.splitlines()) == (EXIT_FAILED, [USAGE_ONLY_WORDING.none_valid]), (code, out)
    code, out, _ = _report([])
    assert (code, out.splitlines()) == (EXIT_FAILED, list(USAGE_LINES)), (code, out)


SELF_TEST_CHECKS: Final[tuple[Callable[[], None], ...]] = (
    _check_high_issue_fails_and_its_finding_is_printed,
    _check_thresholds_reach_bandit,
    _check_json_format_reaches_bandit,
    _check_missing_src_fails_and_stop_on_error_stops,
    _check_refusals_print_the_wrapper_lines,
)


def main(argv: Sequence[str] | None = None) -> int:
    """Entry point."""
    return module_main(build_parser(), _run, argv)


if __name__ == "__main__":
    sys.exit(main())
