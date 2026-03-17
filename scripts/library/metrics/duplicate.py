#!/usr/bin/env python3
"""
Run Pylint duplicate-code detection (R0801) on Datrix project(s) Python code.

By default scans src/. With --tests, scans src/ and tests/ together.
Finds similar/duplicated code blocks across files. Exits 0 if no duplicates
above threshold; exits 1 if any found.

Supports one or more --project-root; multiple roots run one analysis across
all projects (e.g. monorepo duplicate detection).

Usage:
    python duplicate.py --project-root D:\\datrix\\datrix-common
    python duplicate.py --project-root D:\\datrix\\datrix-common --min-lines 6
    python duplicate.py --project-root D:\\datrix\\datrix-common --tests
    python duplicate.py --project-root D:\\datrix\\datrix-common --project-root D:\\datrix\\datrix-language
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

DEFAULT_MIN_LINES = 4


def main() -> int:
    parser = argparse.ArgumentParser(
    description="Pylint duplicate-code detection for a Datrix project.",
    )
    parser.add_argument(
        "--project-root",
        type=Path,
        action="append",
        required=True,
        dest="project_roots",
        help="Path(s) to project root(s) (containing src/). May be repeated for mono run.",
    )
    parser.add_argument(
    "--min-lines",
    type=int,
    default=DEFAULT_MIN_LINES,
    metavar="N",
    help=f"Minimum similar lines to report (default: {DEFAULT_MIN_LINES}).",
    )
    parser.add_argument("--verbose", action="store_true", help="Verbose output.")
    parser.add_argument(
        "--tests",
        action="store_true",
        help="Also include tests/ in duplicate-code detection.",
    )

    args = parser.parse_args()
    project_roots = [p.resolve() for p in args.project_roots]
    for root in project_roots:
        if not root.is_dir():
            print(
                f"Error: project root is not a directory: {root}",
                file=sys.stderr,
            )
            return 1

    scan_paths: list[Path] = []
    for project_root in project_roots:
        src_dir = project_root / "src"
        if not src_dir.is_dir():
            print(
                f"Warning: skipping {project_root} (no src/)",
                file=sys.stderr,
            )
            continue
        scan_paths.append(src_dir)
        if args.tests:
            tests_dir = project_root / "tests"
            if tests_dir.is_dir():
                scan_paths.append(tests_dir)
            else:
                print(
                    f"Warning: --tests specified but no tests/ in {project_root}",
                    file=sys.stderr,
                )

    if not scan_paths:
        print("Error: no project has src/ to scan.", file=sys.stderr)
        return 1

    # Mono (multi-root) runs: default to 30 lines so cross-language (Python vs TS) pairs are not reported
    min_lines = max(2, args.min_lines)
    if len(project_roots) > 1 and args.min_lines == DEFAULT_MIN_LINES:
        min_lines = max(min_lines, 30)

    cmd: list[str] = [
        sys.executable,
        "-m",
        "pylint",
        "--disable=all",
        "--enable=R0801",
        f"--min-similarity-lines={min_lines}",
    ]
    cmd.extend(str(path) for path in scan_paths)

    cwd = str(project_roots[0])
    try:
        result = subprocess.run(
            cmd,
            capture_output=not args.verbose,
            text=True,
            cwd=cwd,
        )
    except FileNotFoundError:
        print(
            "Error: pylint is not installed. Install with: pip install pylint",
            file=sys.stderr,
        )
        return 2

    if result.returncode != 0:
        if result.stdout:
            print(result.stdout, end="")
    if result.stderr:
        print(result.stderr, end="", file=sys.stderr)
    elif result.stdout and args.verbose:
        print(result.stdout, end="")
    if result.stderr and args.verbose:
        print(result.stderr, end="", file=sys.stderr)

    return result.returncode


if __name__ == "__main__":
    sys.exit(main())
