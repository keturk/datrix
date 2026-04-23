#!/usr/bin/env python3
"""Remove extraneous parentheses in Datrix Python code using Ruff (UP034).

Runs ``ruff check`` with rule UP034 (pyupgrade *extraneous-parentheses*) on
one or more projects, or the whole monorepo with ``--all``.

UP034 does **not** remove parentheses around comma-separated tuples (for example
``return ("a", b)``), because pyupgrade treats those as tuple syntax, not
redundant grouping. Use ``return "a", b`` by hand when you want unparenthesized
tuple returns.

Usage:
    python scripts/library/dev/extra_parens.py datrix-common
    python scripts/library/dev/extra_parens.py --all
    python scripts/library/dev/extra_parens.py --all --dry-run
    python scripts/library/dev/extra_parens.py datrix-language --diff

    Or use the PowerShell wrapper:
        .\\scripts\\dev\\extra-parens.ps1 -All
        .\\scripts\\dev\\extra-parens.ps1 datrix-common --dry-run
"""

from __future__ import annotations

import argparse
import io
import subprocess
import sys
from pathlib import Path

if sys.platform == "win32" and __name__ == "__main__":
    if hasattr(sys.stdout, "buffer"):
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    if hasattr(sys.stderr, "buffer"):
        sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

_library_dir = Path(__file__).resolve().parent.parent
if _library_dir.exists() and str(_library_dir) not in sys.path:
    sys.path.insert(0, str(_library_dir))

from shared.venv import get_datrix_root

UP034 = "UP034"


def resolve_scan_paths(
    datrix_root: Path,
    project_names: list[str],
    scan_all: bool,
) -> list[tuple[str, Path]]:
    """Return ``(project_name, directory)`` pairs for Ruff (``src`` / ``tests``).

    Raises:
        FileNotFoundError: If a requested project does not exist under the monorepo root.
    """
    if scan_all:
        pairs: list[tuple[str, Path]] = []
        for d in sorted(datrix_root.iterdir()):
            if d.is_dir() and d.name.startswith("datrix") and (d / "src").is_dir():
                pairs.append((d.name, d / "src"))
                tests_dir = d / "tests"
                if tests_dir.is_dir():
                    pairs.append((d.name, tests_dir))
        return pairs

    pairs = []
    for name in project_names:
        clean = name.rstrip("/\\")
        project_dir = datrix_root / clean
        if not project_dir.is_dir():
            available = sorted(
                d.name for d in datrix_root.iterdir() if d.is_dir() and d.name.startswith("datrix")
            )
            raise FileNotFoundError(
                f"Project '{clean}' not found. Available: {available}"
            )
        src_dir = project_dir / "src"
        if src_dir.is_dir():
            pairs.append((clean, src_dir))
        tests_dir = project_dir / "tests"
        if tests_dir.is_dir():
            pairs.append((clean, tests_dir))
    return pairs


def build_ruff_argv(paths: list[Path], *, dry_run: bool, diff: bool) -> list[str]:
    """Build ``python -m ruff check`` argument list for UP034."""
    argv: list[str] = [sys.executable, "-m", "ruff", "check", "--select", UP034]
    if diff:
        argv.extend(["--fix", "--diff"])
    elif not dry_run:
        argv.append("--fix")
    argv.extend(str(p.resolve()) for p in paths)
    return argv


def run_ruff(argv: list[str]) -> int:
    """Run Ruff; return its process exit code."""
    try:
        proc = subprocess.run(
            argv,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
    except FileNotFoundError:
        print(
            "ERROR: could not run Python or ruff. Install with: pip install ruff",
            file=sys.stderr,
        )
        return 1
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

    if not args.projects and not args.scan_all:
        parser.print_help()
        print("\nProvide project names or use --all.", file=sys.stderr)
        return 1

    try:
        datrix_root = get_datrix_root()
    except FileNotFoundError:
        print("ERROR: Could not find Datrix root directory", file=sys.stderr)
        return 1

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
