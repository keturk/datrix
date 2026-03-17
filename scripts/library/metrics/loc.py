#!/usr/bin/env python3
"""
Run pygount (lines-of-code counting) on a Datrix project's src tree.

Reports code, documentation, and empty line counts per language.
Supports multiple output formats: summary, cloc-xml, json.

Usage:
    python loc.py --project-root D:\\datrix\\datrix-common
    python loc.py --project-root D:\\datrix\\datrix-common --format json
    python loc.py --project-root D:\\datrix\\datrix-common --suffix py
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

DEFAULT_IGNORE_DIRS = ("tests", "test", "__pycache__", ".git", ".venv", "node_modules")
DEFAULT_FORMAT = "summary"


def main() -> int:
    parser = argparse.ArgumentParser(
    description="Pygount LOC metrics for a Datrix project.",
    )
    parser.add_argument(
    "--project-root",
    type=Path,
    required=True,
    help="Path to the project root (containing src/).",
    )
    parser.add_argument(
    "--format",
    choices=("summary", "cloc-xml", "json"),
    default=DEFAULT_FORMAT,
    help=f"Output format (default: {DEFAULT_FORMAT}).",
    )
    parser.add_argument(
    "--suffix",
    type=str,
    default="",
    help="Comma-separated file suffixes to include (e.g. py,js). Empty = all.",
    )
    parser.add_argument(
    "--folders-to-skip",
    type=str,
    default=",".join(DEFAULT_IGNORE_DIRS),
    help="Comma-separated folder names to skip.",
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

    verbose = args.verbose or args.debug

    cmd: list[str] = [
        "pygount",
        "--format",
        args.format,
        "--folders-to-skip",
        args.folders_to_skip,
        str(src),
    ]
    if args.suffix:
        cmd.extend(["--suffix", args.suffix])

    if verbose:
        print(f"Running: {' '.join(cmd)}", file=sys.stderr)

    try:
        result = subprocess.run(
            cmd,
            text=True,
            cwd=str(project_root),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
    except FileNotFoundError:
        print(
            "Error: pygount is not installed. Install with: pip install pygount",
            file=sys.stderr,
        )
        return 2

    if result.stdout:
        print(result.stdout, end="")
    if result.stderr:
        if verbose or result.returncode != 0:
            print(result.stderr, end="", file=sys.stderr)

    return result.returncode


if __name__ == "__main__":
    sys.exit(main())
