#!/usr/bin/env python3
"""
Run Vulture (dead-code detection) on a Datrix project's src tree.

Finds unused code: imports, variables, functions, classes. Supports
--min-confidence, --sort-by-size, --make-whitelist. Exits 0 if no unused
code above threshold; exits 1 if any found (unless --make-whitelist).

Usage:
    python vulture.py --project-root D:\\datrix\\datrix-common
    python vulture.py --project-root D:\\datrix\\datrix-common --min-confidence 100
    python vulture.py --project-root D:\\datrix\\datrix-common --make-whitelist
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

DEFAULT_IGNORE_DIRS = ("tests", "test", "__pycache__", ".git")
DEFAULT_MIN_CONFIDENCE = 80


def collect_py_files(project_root: Path, ignore_dirs: tuple[str, ...]) -> list[Path]:
    """Return sorted list of Python files under project_root/src, excluding ignore_dirs."""
    src = project_root / "src"
    if not src.is_dir():
        return []
    out: list[Path] = []
    for py_path in src.rglob("*.py"):
        parts = py_path.relative_to(src).parts
        if any(part in ignore_dirs for part in parts):
            continue
        out.append(py_path)
    return sorted(out)


def main() -> int:
    parser = argparse.ArgumentParser(
    description="Vulture dead-code detection for a Datrix project.",
    )
    parser.add_argument(
    "--project-root",
    type=Path,
    required=True,
    help="Path to the project root (containing src/).",
    )
    parser.add_argument(
    "--min-confidence",
    type=int,
    default=DEFAULT_MIN_CONFIDENCE,
    metavar="N",
    help=f"Minimum confidence 60-100 (default: {DEFAULT_MIN_CONFIDENCE}).",
    )
    parser.add_argument(
    "--sort-by-size",
    action="store_true",
    help="Sort unused classes/functions by size.",
    )
    parser.add_argument(
    "--make-whitelist",
    action="store_true",
    help="Output whitelist of false positives to stdout.",
    )
    parser.add_argument(
    "--ignore",
    type=str,
    default=",".join(DEFAULT_IGNORE_DIRS),
    help="Comma-separated directory names to ignore under src/.",
    )
    parser.add_argument("--verbose", action="store_true", help="Verbose output.")
    parser.add_argument("--debug", action="store_true", help="Debug output.")

    args = parser.parse_args()
    project_root = args.project_root.resolve()
    if not project_root.is_dir():
        print(
            f"Error: project root is not a directory: {project_root}",
            file=sys.stderr,
        )
        return 1

    src = project_root / "src"
    if not src.is_dir():
        print(
            f"Error: project has no src/ directory: {project_root}",
            file=sys.stderr,
        )
        return 1

    ignore_dirs = tuple(s.strip() for s in args.ignore.split(",") if s.strip())
    paths = [str(p) for p in collect_py_files(project_root, ignore_dirs)]
    whitelist = project_root / "vulture_whitelist.py"
    if whitelist.is_file():
        paths.append(str(whitelist))
    if not paths:
        if args.verbose:
            print("No Python files to analyze.", file=sys.stderr)
        return 0

    cmd: list[str] = [
        sys.executable,
        "-m",
        "vulture",
        "--min-confidence",
        str(max(60, min(100, args.min_confidence))),
        *paths,
    ]
    if args.sort_by_size:
        cmd.append("--sort-by-size")
    if args.make_whitelist:
        cmd.append("--make-whitelist")

    try:
        result = subprocess.run(
            cmd,
            capture_output=not args.verbose,
            text=True,
            cwd=str(project_root),
        )
    except FileNotFoundError:
        print(
            "Error: vulture is not installed. Install with: pip install vulture",
            file=sys.stderr,
        )
        return 2

    if result.returncode != 0 and not args.make_whitelist:
        if result.stdout:
            print(result.stdout, end="")
    if result.stderr:
        print(result.stderr, end="", file=sys.stderr)
    elif result.returncode == 0 and args.make_whitelist and result.stdout:
        print(result.stdout, end="")
    elif result.stdout and (args.verbose or not args.make_whitelist):
        print(result.stdout, end="")
    if result.stderr and args.verbose:
        print(result.stderr, end="", file=sys.stderr)

    # make-whitelist exits 0; normal run: exit 1 if vulture found issues
    return result.returncode


if __name__ == "__main__":
    sys.exit(main())
