#!/usr/bin/env python3
"""Remove extraneous parentheses in Datrix Python code using Ruff (UP034).

Runs ``ruff check`` with rule UP034 (pyupgrade *extraneous-parentheses*) on
one or more projects, or the whole monorepo with ``--all``.

UP034 does **not** remove parentheses around comma-separated tuples (for example
``return ("a", b)``), because pyupgrade treats those as tuple syntax, not
redundant grouping. Use ``return "a", b`` by hand when you want unparenthesized
tuple returns.

Usage:
    python scripts/scan/lib/extra_parens.py datrix-common   (PYTHONPATH=scripts/common/lib)
    python scripts/scan/lib/extra_parens.py --all
    python scripts/scan/lib/extra_parens.py --all --dry-run
    python scripts/scan/lib/extra_parens.py datrix-language --diff

    Or use the PowerShell wrapper:
        .\\scripts\\scan\\extra-parens.ps1 -All
        .\\scripts\\scan\\extra-parens.ps1 datrix-common --dry-run
"""

from __future__ import annotations

import argparse
import importlib.util
import io
import subprocess
import sys
from pathlib import Path

if sys.platform == "win32" and __name__ == "__main__":
    if hasattr(sys.stdout, "buffer"):
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    if hasattr(sys.stderr, "buffer"):
        sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

from datrix_scripts.logic_map import resolve_scan_paths  # noqa: E402
from datrix_scripts.paths import WORKSPACE_DIR  # noqa: E402
from datrix_scripts.venv import PACKAGE_DEV_EXTRAS, missing_declared_tool  # noqa: E402

UP034 = "UP034"
# Ruff runs as a module of this interpreter, so the shared venv's copy is the one that fixes.
_RUFF_MODULE = "ruff"


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


def main() -> int:
    """CLI entry point."""
    parser = argparse.ArgumentParser(
        description="Remove extraneous parentheses (Ruff UP034) in Datrix Python trees.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument(
        "projects",
        nargs="*",
        help="Project names (e.g. datrix-common datrix-language)",
    )
    parser.add_argument(
        "--all",
        "-a",
        action="store_true",
        dest="scan_all",
        help="Include every datrix* project under the monorepo root",
    )
    exclusive = parser.add_mutually_exclusive_group()
    exclusive.add_argument(
        "--dry-run",
        action="store_true",
        help="Report UP034 violations only; do not modify files",
    )
    exclusive.add_argument(
        "--diff",
        action="store_true",
        help="Show fix diffs on stdout; do not write files (implies --fix for Ruff)",
    )
    args = parser.parse_args()
    if importlib.util.find_spec(_RUFF_MODULE) is None:
        print(missing_declared_tool("ruff", PACKAGE_DEV_EXTRAS), file=sys.stderr)
        return 1

    if not args.projects and not args.scan_all:
        parser.print_help()
        print("\nProvide project names or use --all.", file=sys.stderr)
        return 1

    datrix_root = WORKSPACE_DIR

    try:
        scan_pairs = resolve_scan_paths(datrix_root, args.projects, args.scan_all)
    except FileNotFoundError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1

    if not scan_pairs:
        print("No src/ or tests/ directories found to scan.")
        return 0

    paths = [directory for _name, directory in scan_pairs]
    unique_projects = sorted({name for name, _ in scan_pairs})
    mode = "dry-run (no writes)"
    if args.diff:
        mode = "diff preview (no writes)"
    elif not args.dry_run:
        mode = "fix in place"

    print(
        f"Ruff UP034 ({mode}): {len(paths)} path(s), "
        f"{len(unique_projects)} project(s): {', '.join(unique_projects)}",
        flush=True,
    )

    argv = build_ruff_argv(paths, dry_run=args.dry_run, diff=args.diff)
    return run_ruff(argv)


if __name__ == "__main__":
    sys.exit(main())
