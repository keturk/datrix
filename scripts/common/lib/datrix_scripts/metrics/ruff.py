"""Run Ruff (lint/format) on Datrix projects' src or tests trees.

Modes: check (lint), format. Supports ``--output-format``, ``--fix``, ``--diff``, ``--statistics`` for
check; ``--check``, ``--diff`` for format. A project passes when Ruff exits 0; the run exits 0 when every
project passed, else 1.

Each project's output is shown and also written to a timestamped log under the workspace-level
``.test-output/ruff/<project>/`` folder (``ruff-yyyyMMdd-HHmmss.log``). The logs live OUTSIDE every
package repo on purpose: each datrix-* package is its own git repository, so a log folder created
inside one is committed and pushed unless a human notices.

Run by ``metrics/ruff.ps1`` (POSIX twin ``ruff.sh``): project names positionally or as ``--projects``,
or ``--all``; ``--mode``, ``--output-format``, ``--fix``, ``--diff``, ``--statistics``, ``--check``,
``--test`` (the tests/ tree), ``--stop-on-error``, ``--verbose-output`` (Ruff's ``-v``), ``--self-test``.
"""

from __future__ import annotations

import argparse
import contextlib
import importlib.util
import io
import subprocess
import sys
import tempfile
import time
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
from datrix_scripts.venv import PACKAGE_DEV_EXTRAS, missing_declared_tool

MODULE: Final = "datrix_scripts.metrics.ruff"
WRAPPER: Final = "ruff"
# Ruff runs as a module of this interpreter, so the shared venv's copy is the one that checks.
_RUFF_MODULE: Final = "ruff"
EXIT_TOOL_MISSING: Final = 2
MODE_CHECK: Final = "check"
MODE_FORMAT: Final = "format"
DEFAULT_OUTPUT_FORMAT: Final = "full"
RUFF_OUTPUT_FORMATS: Final = (
    "concise",
    DEFAULT_OUTPUT_FORMAT,
    "json",
    "json-lines",
    "junit",
    "grouped",
    "github",
    "gitlab",
    "pylint",
    "rdjson",
    "azure",
    "sarif",
)
#: Where the run logs go, under a workspace (or ``cleanup-ruff``'s ``-BaseDir``).
RUFF_LOG_SUBDIR: Final = Path(".test-output") / "ruff"
RUFF_LOG_PREFIX: Final = "ruff-"
RUFF_LOG_SUFFIX: Final = ".log"
_LOG_STAMP: Final = "%Y%m%d-%H%M%S"
USAGE_LINES: Final = (
    "Usage: .\\ruff.ps1 <project> [options] or .\\ruff.ps1 -All [options]",
    " -Mode check|format -OutputFormat full|json|... -Fix -Diff -Statistics -Check -Test",
)


@dataclass(frozen=True)
class RuffOptions:
    """What one run asks of Ruff, shared by every project."""

    mode: str
    target: str
    output_format: str
    fix: bool
    diff: bool
    statistics: bool
    check: bool
    verbose: bool


@dataclass(frozen=True)
class ProjectOutput:
    """One project's exit code and what it printed; ``error`` is a refusal before Ruff ran (stderr)."""

    code: int
    text: str
    error: bool = False


def ruff_command(target_dir: Path, options: RuffOptions) -> list[str]:
    """The Ruff argument vector over *target_dir* for *options*."""
    command = [sys.executable, "-m", _RUFF_MODULE, options.mode]
    if options.mode == MODE_CHECK:
        command.extend(["--output-format", options.output_format, str(target_dir)])
        command.extend(flag for flag, on in (("--fix", options.fix), ("--diff", options.diff),
                                             ("--statistics", options.statistics)) if on)
    else:
        command.append(str(target_dir))
        command.extend(flag for flag, on in (("--check", options.check), ("--diff", options.diff)) if on)
    if options.verbose:
        command.append("-v")
    return command


def lint_project(project_root: Path, options: RuffOptions) -> ProjectOutput:
    """Ruff over ``<project_root>/<target>``: its exit code and its stdout then stderr; 1 when the project
    or the target directory is missing, 2 when Ruff is not installed in this interpreter."""
    if importlib.util.find_spec(_RUFF_MODULE) is None:
        return ProjectOutput(EXIT_TOOL_MISSING, missing_declared_tool("ruff", PACKAGE_DEV_EXTRAS) + "\n", error=True)
    if not project_root.is_dir():
        return ProjectOutput(EXIT_FAILED, f"Error: project root is not a directory: {project_root}\n", error=True)
    target_dir = project_root / options.target
    if not target_dir.is_dir():
        return ProjectOutput(
            EXIT_FAILED, f"Error: project has no {options.target}/ directory: {project_root}\n", error=True
        )
    result = subprocess.run(ruff_command(target_dir, options), cwd=str(project_root), capture_output=True, text=True)
    return ProjectOutput(result.returncode, result.stdout + result.stderr)


def new_log_file(log_root: Path, project: str) -> Path:
    """``<log_root>/<project>/ruff-<yyyyMMdd-HHmmss>.log``, its folder created."""
    folder = log_root / project
    folder.mkdir(parents=True, exist_ok=True)
    return folder / f"{RUFF_LOG_PREFIX}{time.strftime(_LOG_STAMP)}{RUFF_LOG_SUFFIX}"


def _lint_and_log(project_root: Path, log_file: Path, options: RuffOptions) -> int:
    """Lint one project, showing its output and writing the same output to *log_file*."""
    print(f"Log file: {log_file}")
    outcome = lint_project(project_root, options)
    if outcome.error:
        print_stderr(outcome.text.rstrip("\n"))
    elif outcome.text:
        print(outcome.text, end="")
    log_file.write_text(outcome.text, encoding="utf-8")
    return outcome.code


def _selected(args: argparse.Namespace, workspace: Path, target: str) -> list[str]:
    """The projects to lint, the line announcing them printed.

    Raises:
        ProjectSelectionError: The selection is empty (the wrapper's wording).
    """
    projects = select_projects(args, workspace, usage=USAGE_LINES, wording=USAGE_ONLY_WORDING)
    scope = " all projects" if args.all else ""
    print(f"Running Ruff (mode={args.mode}, target={target}/) for{scope}: {', '.join(projects)}")
    return projects


def run_ruff(args: argparse.Namespace, workspace: Path, log_root: Path) -> int:
    """The wrapper's run over *workspace*: select, lint each project with a log under *log_root*, summarize."""
    target = PackageMarker.TESTS.value if args.test else PackageMarker.SRC.value
    try:
        projects = _selected(args, workspace, target)
    except ProjectSelectionError as exc:
        for line in exc.lines:
            print(line)
        return EXIT_FAILED
    options = RuffOptions(
        mode=args.mode,
        target=target,
        output_format=args.output_format,
        fix=args.fix,
        diff=args.diff,
        statistics=args.statistics,
        check=args.check,
        verbose=args.verbose_output,
    )
    results = run_projects(
        projects,
        lambda project: _lint_and_log(workspace / project, new_log_file(log_root, project), options),
        stop_on_error=args.stop_on_error,
        header_info=f"mode={args.mode}, {target}",
    )
    return print_summary(f"Ruff Summary (mode={args.mode})", results)


def build_parser() -> argparse.ArgumentParser:
    """The options of ``metrics/ruff.ps1``: one per wrapper parameter, spelled exactly."""
    parser = argparse.ArgumentParser(description="Ruff lint/format for Datrix projects.", allow_abbrev=False)
    add_project_arguments(parser)
    parser.add_argument(
        "--mode", choices=(MODE_CHECK, MODE_FORMAT), default=MODE_CHECK, help="ruff check or ruff format (default: check)."
    )
    parser.add_argument(
        "--output-format", choices=RUFF_OUTPUT_FORMATS, default=DEFAULT_OUTPUT_FORMAT, metavar="FMT",
        help="Output format for mode=check (default: full).",
    )
    parser.add_argument("--fix", action="store_true", help="Apply fixes (mode=check only).")
    parser.add_argument(
        "--diff", action="store_true", help="Show diff only, do not write (check: fix diff; format: format diff)."
    )
    parser.add_argument("--statistics", action="store_true", help="Show rule violation counts (mode=check only).")
    parser.add_argument("--check", action="store_true", help="Dry run: exit non-zero if changes needed (mode=format).")
    parser.add_argument("--test", action="store_true", help="Run on each project's tests/ instead of src/.")
    parser.add_argument("--stop-on-error", action="store_true", help="Stop on the first project that fails.")
    parser.add_argument("--verbose-output", action="store_true", help="Pass -v to Ruff.")
    parser.add_argument("--self-test", action="store_true", help="Run only the self-test over planted projects.")
    parser.set_defaults(debug=False)
    return parser


def _run(args: argparse.Namespace) -> int:
    if args.self_test:
        return run_self_test(
            SELF_TEST_CHECKS, wrapper=WRAPPER, module=MODULE, parser=build_parser(), folder=METRICS_SCRIPTS_DIR
        )
    return run_ruff(args, WORKSPACE_DIR, WORKSPACE_DIR / RUFF_LOG_SUBDIR)


# ---------------------------------------------------------------------------
# Self-test
# ---------------------------------------------------------------------------

#: An unused import: Ruff's F401, in its default rule set.
_LINT_ISSUE: Final = "import os\n"
#: Lint-clean but not formatted.
_UNFORMATTED: Final = "x=1\n"
_CLEAN: Final = "x = 1\n"


def _plant(root: Path) -> Path:
    """``datrix-lint`` (F401 in src/), ``datrix-ugly`` (unformatted src/), ``datrix-clean`` (clean src/ and
    tests/) and the showcase directory, each with a ``pyproject.toml`` so Ruff reads no outer config."""
    for name, text in (("datrix-lint", _LINT_ISSUE), ("datrix-ugly", _UNFORMATTED), ("datrix-clean", _CLEAN)):
        (root / name / PackageMarker.SRC.value).mkdir(parents=True)
        (root / name / PackageMarker.SRC.value / "module.py").write_text(text, encoding="utf-8")
        (root / name / PackageMarker.PYPROJECT.value).write_text(f"[project]\nname = '{name}'\n", encoding="utf-8")
    (root / "datrix-clean" / PackageMarker.TESTS.value).mkdir()
    (root / "datrix-clean" / PackageMarker.TESTS.value / "test_module.py").write_text(_CLEAN, encoding="utf-8")
    (root / SHOWCASE).mkdir()
    return root


def _report(argv: Sequence[str]) -> tuple[int, str, str, dict[str, str]]:
    """Exit code, stdout, stderr and the log written per project, of a run over a planted workspace."""
    out, err = io.StringIO(), io.StringIO()
    with tempfile.TemporaryDirectory() as raw:
        workspace = _plant(Path(raw) / "ws")
        log_root = Path(raw) / "logs"
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = run_ruff(build_parser().parse_args(list(argv)), workspace, log_root)
        logs = {path.parent.name: path.read_text(encoding="utf-8") for path in log_root.glob("*/*.log")}
    return code, out.getvalue(), err.getvalue(), logs


def _check_lint_issue_fails_and_is_shown_and_logged() -> None:
    code, out, _, logs = _report(["datrix-lint", "datrix-clean"])
    assert code == EXIT_FAILED, (code, out)
    assert "F401" in out and "F401" in logs["datrix-lint"], (out, logs)
    assert f"======== datrix-lint (mode={MODE_CHECK}, src) ========" in out, out
    assert " [FAIL] : datrix-lint" in out and " [PASS] : datrix-clean" in out, out
    assert set(logs) == {"datrix-lint", "datrix-clean"}, logs


def _check_format_check_flags_an_unformatted_file() -> None:
    code, out, _, _ = _report(["datrix-ugly", "--mode=format", "--check"])
    assert code == EXIT_FAILED and "1 file would be reformatted" in out, (code, out)
    code, out, _, _ = _report(["datrix-ugly"])
    assert code == EXIT_PASSED, (code, out)


def _check_test_targets_the_tests_tree() -> None:
    code, out, err, logs = _report(["datrix-clean", "datrix-lint", "--test", "--statistics"])
    assert "Running Ruff (mode=check, target=tests/) for: datrix-clean, datrix-lint" in out, out
    assert code == EXIT_FAILED and "Error: project has no tests/ directory:" in err, (code, err)
    assert "Error: project has no tests/ directory:" in logs["datrix-lint"], logs


def _check_command_carries_every_flag() -> None:
    options = RuffOptions(MODE_CHECK, "src", "json", fix=True, diff=True, statistics=True, check=True, verbose=True)
    command = ruff_command(Path("src"), options)
    assert command[3:] == ["check", "--output-format", "json", "src", "--fix", "--diff", "--statistics", "-v"], command
    formatted = ruff_command(Path("src"), RuffOptions(MODE_FORMAT, "src", "full", True, True, True, True, False))
    assert formatted[3:] == ["format", "src", "--check", "--diff"], formatted


def _check_refusals_print_the_wrapper_lines() -> None:
    code, out, _, _ = _report([SHOWCASE])
    assert (code, out.splitlines()) == (EXIT_FAILED, [USAGE_ONLY_WORDING.none_valid]), (code, out)
    code, out, _, _ = _report([])
    assert (code, out.splitlines()) == (EXIT_FAILED, list(USAGE_LINES)), (code, out)


SELF_TEST_CHECKS: Final[tuple[Callable[[], None], ...]] = (
    _check_lint_issue_fails_and_is_shown_and_logged,
    _check_format_check_flags_an_unformatted_file,
    _check_test_targets_the_tests_tree,
    _check_command_carries_every_flag,
    _check_refusals_print_the_wrapper_lines,
)


def main(argv: Sequence[str] | None = None) -> int:
    """Entry point."""
    return module_main(build_parser(), _run, argv)


if __name__ == "__main__":
    sys.exit(main())
