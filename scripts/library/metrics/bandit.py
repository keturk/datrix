#!/usr/bin/env python3
"""
Run Bandit security scanner on a Datrix project's src tree.

Finds common security issues in Python code. Exits 0 if no issues
above threshold; exits 1 if any found.

Usage:
    python bandit.py --project-root D:\\datrix\\datrix-common
    python bandit.py --project-root D:\\datrix\\datrix-common --severity high
    python bandit.py --project-root D:\\datrix\\datrix-common --format json
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

SEVERITY_MAP = {"low": "-l", "medium": "-ll", "high": "-lll"}
CONFIDENCE_MAP = {"low": "-i", "medium": "-ii", "high": "-iii"}
BANDIT_FORMATS = ("screen", "json", "csv", "html", "yaml", "sarif")


def main() -> int:
    parser = argparse.ArgumentParser(
    description="Bandit security scanner for a Datrix project.",
    )
    parser.add_argument(
    "--project-root",
    type=Path,
    required=True,
    help="Path to the project root (containing src/).",
    )
    parser.add_argument(
    "--severity",
    choices=("low", "medium", "high"),
    default="medium",
    help="Minimum severity to report (default: medium).",
    )
    parser.add_argument(
    "--confidence",
    choices=("low", "medium", "high"),
    default="medium",
    help="Minimum confidence to report (default: medium).",
    )
    parser.add_argument(
    "--format",
    choices=BANDIT_FORMATS,
    default="screen",
    dest="output_format",
    help="Output format (default: screen).",
    )
    parser.add_argument("--verbose", action="store_true", help="Verbose output.")

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

    cmd: list[str] = [
        sys.executable,
        "-m",
        "bandit",
        "-r",
        str(src),
        "--exclude",
        "tests,__pycache__",
        SEVERITY_MAP[args.severity],
        CONFIDENCE_MAP[args.confidence],
    ]
    if args.output_format != "screen":
        cmd.extend(["-f", args.output_format])

    try:
        result = subprocess.run(
            cmd,
            capture_output=not args.verbose,
            text=True,
            cwd=str(project_root),
        )
    except FileNotFoundError:
        print(
            "Error: bandit is not installed. Install with: pip install bandit",
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
