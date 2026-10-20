#!/usr/bin/env python3
"""Remove extraneous parentheses in Datrix Python code using Ruff (UP034).

Runs ``ruff check`` with rule UP034 (pyupgrade *extraneous-parentheses*) on
one or more projects, or the whole monorepo with ``--all``.

UP034 does **not** remove parentheses around comma-separated tuples (for example
``return ("a", b)``), because pyupgrade treats those as tuple syntax, not
redundant grouping. Use ``return "a", b`` by hand when you want unparenthesized
tuple returns.

The module behind ``scan/extra-parens.ps1`` (and its ``.sh`` twin). ``--all`` wins over named projects;
neither prints the usage and exits 1, and ``--dry-run`` with ``--diff`` is refused (exit 1). Otherwise
the exit code is Ruff's.

Usage:
    python -m datrix_scripts.scan.extra_parens --projects=datrix-common
    python -m datrix_scripts.scan.extra_parens --all --dry-run
    python -m datrix_scripts.scan.extra_parens --projects=datrix-language --diff
"""

from __future__ import annotations

import argparse
import importlib.util
import subprocess
import sys
import tempfile
from collections.abc import Sequence
from pathlib import Path
from typing import Final

from datrix_scripts.gate_harness import EXIT_VIOLATION, write_files
from datrix_scripts.logic_map import resolve_scan_paths
from datrix_scripts.paths import WORKSPACE_DIR
from datrix_scripts.scan.selection import SelectionRefused, expect_refusal, require_selection, wrapper_usage
from datrix_scripts.test.wrappers import SCAN_SCRIPTS_DIR, module_main, run_self_test
from datrix_scripts.venv import PACKAGE_DEV_EXTRAS, missing_declared_tool

MODULE: Final = "datrix_scripts.scan.extra_parens"
WRAPPER: Final = "extra-parens"

UP034 = "UP034"
# Ruff runs as a module of this interpreter, so the shared venv's copy is the one that fixes.
_RUFF_MODULE = "ruff"

_USAGE: Final = wrapper_usage(WRAPPER, ["<project> [project2 ...] [-DryRun] [-Diff]", "-All [-DryRun] [-Diff]"])
_BOTH_MODES: Final = "Specify only one of -DryRun or -Diff."


def build_ruff_argv(paths: list[Path], *, dry_run: bool, diff: bool) -> list[str]:
    """Build ``python -m ruff check`` argument list for UP034."""
    argv: list[str] = [sys.executable, "-m", _RUFF_MODULE, "check", "--select", UP034]
    if diff:
        argv.extend(["--fix", "--diff"])
    elif not dry_run:
        argv.append("--fix")
    argv.extend(str(p.resolve()) for p in paths)
    return argv


def run_ruff(argv: list[str]) -> int:
    """Run Ruff; return its process exit code."""
    proc = subprocess.run(
        argv,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    return int(proc.returncode)


def build_parser() -> argparse.ArgumentParser:
    """The options of ``scan/extra-parens.ps1``: one per wrapper parameter, spelled exactly."""
    parser = argparse.ArgumentParser(
        prog=WRAPPER, description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter, allow_abbrev=False
    )
    parser.add_argument("--projects", action="append", default=[],
                        help="A project name, e.g. datrix-common (repeatable).")
    parser.add_argument("--all", action="store_true", dest="scan_all",
                        help="Include every datrix* project under the monorepo root.")
    parser.add_argument("--dry-run", action="store_true", help="Report UP034 violations only; do not modify files.")
    parser.add_argument("--diff", action="store_true",
                        help="Show fix diffs on stdout; do not write files (implies --fix for Ruff).")
    parser.add_argument("--self-test", action="store_true",
                        help="Run only the self-test: the usage is printed when nothing is selected, --dry-run "
                             "with --diff is refused, each mode builds its Ruff command, a planted UP034 violation "
                             "is reported by a dry run, and the wrapper seam holds.")
    parser.set_defaults(debug=False)
    return parser


def refuse_unrunnable(args: argparse.Namespace) -> None:
    """Refuse a run that selects nothing (the usage) or asks for both ``--dry-run`` and ``--diff``.

    Raises:
        SelectionRefused: with exit code 1.
    """
    require_selection(args.projects, args.scan_all, _USAGE, refuse_both=False)
    if args.dry_run and args.diff:
        raise SelectionRefused(_BOTH_MODES, EXIT_VIOLATION, to_stderr=True)


def _mode(args: argparse.Namespace) -> str:
    if args.diff:
        return "diff preview (no writes)"
    return "dry-run (no writes)" if args.dry_run else "fix in place"


def fix_projects(args: argparse.Namespace, datrix_root: Path) -> int:
    """Run Ruff UP034 over the selected projects under *datrix_root*; Ruff's exit code, or 1 on a refusal."""
    if importlib.util.find_spec(_RUFF_MODULE) is None:
        print(missing_declared_tool("ruff", PACKAGE_DEV_EXTRAS), file=sys.stderr)
        return EXIT_VIOLATION
    try:
        scan_pairs = resolve_scan_paths(datrix_root, args.projects, args.scan_all)
    except FileNotFoundError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return EXIT_VIOLATION
    if not scan_pairs:
        print("No src/ or tests/ directories found to scan.")
        return 0

    paths = [directory for _name, directory in scan_pairs]
    unique_projects = sorted({name for name, _ in scan_pairs})
    print(
        f"Ruff UP034 ({_mode(args)}): {len(paths)} path(s), "
        f"{len(unique_projects)} project(s): {', '.join(unique_projects)}",
        flush=True,
    )
    return run_ruff(build_ruff_argv(paths, dry_run=args.dry_run, diff=args.diff))


def _check_nothing_selected_prints_the_usage() -> None:
    expect_refusal(lambda: refuse_unrunnable(build_parser().parse_args([])), EXIT_VIOLATION, _USAGE)


def _check_dry_run_with_diff_is_refused() -> None:
    args = build_parser().parse_args(["--all", "--dry-run", "--diff"])
    expect_refusal(lambda: refuse_unrunnable(args), EXIT_VIOLATION, _BOTH_MODES)


def _check_each_mode_builds_its_ruff_command() -> None:
    path = [Path("x.py")]
    expected = {
        (False, False): ["--fix"],
        (True, False): [],
        (False, True): ["--fix", "--diff"],
    }
    for (dry_run, diff), flags in expected.items():
        argv = build_ruff_argv(path, dry_run=dry_run, diff=diff)
        assert argv[3:6] == ["check", "--select", UP034], f"UP034 only: {argv}"
        assert argv[6:-1] == flags, f"dry_run={dry_run} diff={diff} must add {flags}; got {argv[6:-1]}"


def _check_a_dry_run_reports_a_planted_violation() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        (planted,) = write_files(Path(tmp), {"planted.py": 'print(("hello"))\n'})
        argv = build_ruff_argv([planted], dry_run=True, diff=False)
        proc = subprocess.run(argv, capture_output=True, text=True, encoding="utf-8", errors="replace")
        assert planted.read_text(encoding="utf-8") == 'print(("hello"))\n', "a dry run must not modify the file"
    assert proc.returncode == 1 and UP034 in proc.stdout, (
        f"a dry run must report the planted UP034 violation (exit 1); got {proc.returncode}: {proc.stdout!r}"
    )


def _run(args: argparse.Namespace) -> int:
    if args.self_test:
        checks = [
            _check_nothing_selected_prints_the_usage,
            _check_dry_run_with_diff_is_refused,
            _check_each_mode_builds_its_ruff_command,
            _check_a_dry_run_reports_a_planted_violation,
        ]
        return run_self_test(checks, wrapper=WRAPPER, module=MODULE, parser=build_parser(), folder=SCAN_SCRIPTS_DIR)
    try:
        refuse_unrunnable(args)
    except SelectionRefused as refused:
        return refused.report()
    return fix_projects(args, WORKSPACE_DIR)


def main(argv: Sequence[str] | None = None) -> int:
    """Entry point."""
    return module_main(build_parser(), _run, argv)


if __name__ == "__main__":
    sys.exit(main())
