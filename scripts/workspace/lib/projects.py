#!/usr/bin/env python3
"""
List Datrix projects or full paths to their src/tests/docs folders.

Discovers all datrix* directories under the workspace root. With no arguments,
prints project names (one per line). With --src, --tests, or --docs, prints the
full path of each project's corresponding folder (only for projects that have it).

Usage:
  python scripts/workspace/lib/projects.py   (PYTHONPATH=scripts/common/lib)
  python scripts/workspace/lib/projects.py --src
  python scripts/workspace/lib/projects.py --tests
  python scripts/workspace/lib/projects.py --docs
  .\\scripts\\workspace\\projects.ps1
  .\\scripts\\workspace\\projects.ps1 -Src
  .\\scripts\\workspace\\projects.ps1 -Tests
  .\\scripts\\workspace\\projects.ps1 -Docs
"""

import argparse
import io
import sys
from pathlib import Path

# Configure UTF-8 encoding for stdout/stderr on Windows
if sys.platform == "win32":
    if hasattr(sys.stdout, "buffer"):
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    if hasattr(sys.stderr, "buffer"):
        sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

from datrix_scripts.framework_repos import workspace_package_dirs  # noqa: E402
from datrix_scripts.paths import WORKSPACE_DIR  # noqa: E402


def get_project_roots() -> list[Path]:
    """
    Return sorted list of project root directories under the Datrix workspace.

    Returns:
        Sorted paths to directories whose names start with "datrix".

    """
    return workspace_package_dirs(WORKSPACE_DIR, include_showcase=True)


def main() -> int:
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="List Datrix projects or full paths to src/tests/docs folders",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument(
        "--src",
        action="store_true",
        help="Print full path of each project's src folder (only if it exists)",
    )
    parser.add_argument(
        "--tests",
        action="store_true",
        help="Print full path of each project's tests folder (only if it exists)",
    )
    parser.add_argument(
        "--docs",
        action="store_true",
        help="Print full path of each project's docs folder (only if it exists)",
    )
    args = parser.parse_args()

    try:
        projects = get_project_roots()
    except FileNotFoundError:
        print("ERROR: Could not find Datrix root directory", file=sys.stderr)
        return 1

    if not args.src and not args.tests and not args.docs:
        for p in projects:
            print(p.name)
        return 0

    if args.src:
        for p in projects:
            src_dir = p / "src"
            if src_dir.is_dir():
                print(src_dir.resolve())
    if args.tests:
        for p in projects:
            tests_dir = p / "tests"
            if tests_dir.is_dir():
                print(tests_dir.resolve())
    if args.docs:
        for p in projects:
            docs_dir = p / "docs"
            if docs_dir.is_dir():
                print(docs_dir.resolve())

    return 0


if __name__ == "__main__":
    sys.exit(main())
