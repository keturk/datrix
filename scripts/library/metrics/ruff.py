#!/usr/bin/env python3
"""
Run Ruff (lint/format) on a Datrix project's src tree.

Modes: check (lint), format. Supports --output-format, --fix, --diff,
--statistics for check; --check, --diff for format. Exits with ruff's
exit code.

Usage:
    python ruff.py --project-root D:\\datrix\\datrix-common --mode check
    python ruff.py --project-root D:\\datrix\\datrix-common --mode check --output-format json
    python ruff.py --project-root D:\\datrix\\datrix-common --mode format --diff
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

RUFF_OUTPUT_FORMATS = (
    "concise",
    "full",
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


def main() -> int:
    parser = argparse.ArgumentParser(
    description="Ruff lint/format for a Datrix project.",
    )
    parser.add_argument(
        "--project-root",
        type=Path,
        required=True,
        help="Path to the project root (containing src/ or tests/).",
    )
    parser.add_argument(
        "--target",
        choices=("src", "tests"),
        default="src",
        help="Directory under project root to check: src or tests (default: src).",
    )
    parser.add_argument(
        "--mode",
    choices=("check", "format"),
    default="check",
    help="Run ruff check or ruff format (default: check).",
    )
    parser.add_argument(
    "--output-format",
    choices=RUFF_OUTPUT_FORMATS,
    default="full",
    metavar="FMT",
    help="Output format for mode=check (default: full).",
    )
    parser.add_argument(
    "--fix",
    action="store_true",
    help="Apply fixes (mode=check only).",
    )
    parser.add_argument(
    "--diff",
    action="store_true",
    help="Show diff only, do not write (check: fix diff; format: format diff).",
    )
    parser.add_argument(
    "--statistics",
    action="store_true",
    help="Show rule violation counts (mode=check only).",
    )
    parser.add_argument(
    "--check",
    action="store_true",
    help="Dry run: exit non-zero if changes needed (mode=format only).",
    )
    parser.add_argument(
    "--verbose",
    action="store_true",
    help="Verbose output.",
    )
    parser.add_argument(
    "--quiet",
    action="store_true",
    help="Quiet output.",
    )

    args = parser.parse_args()
    project_root = args.project_root.resolve()
    if not project_root.is_dir():
        print(
            f"Error: project root is not a directory: {project_root}",
            file=sys.stderr,
        )
        return 1

    target_dir = project_root / args.target
    if not target_dir.is_dir():
        print(
            f"Error: project has no {args.target}/ directory: {project_root}",
            file=sys.stderr,
        )
        return 1

    paths = [str(target_dir)]
    if args.mode == "check":
        cmd: list[str] = [
            sys.executable,
            "-m",
            "ruff",
            "check",
            "--output-format",
            args.output_format,
            *paths,
        ]
        if args.fix:
            cmd.append("--fix")
        if args.diff:
            cmd.append("--diff")
        if args.statistics:
            cmd.append("--statistics")
    else:
        cmd = [
            sys.executable,
            "-m",
            "ruff",
            "format",
            *paths,
        ]
        if args.check:
            cmd.append("--check")
        if args.diff:
            cmd.append("--diff")

    if args.verbose:
        cmd.append("-v")
    if args.quiet:
        cmd.append("-q")

    try:
        result = subprocess.run(
            cmd,
            cwd=str(project_root),
            capture_output=True,
            text=True,
        )
    except FileNotFoundError:
        print(
            "Error: ruff is not installed. Install with: pip install ruff",
            file=sys.stderr,
        )
        return 2

    # Print both stdout and stderr to stdout so the parent (e.g. PowerShell)
    # does not see stderr and trigger ErrorActionPreference = "Stop".
    if result.stdout:
        print(result.stdout, end="")
    if result.stderr:
        print(result.stderr, end="", file=sys.stdout)

    return result.returncode


if __name__ == "__main__":
    sys.exit(main())
