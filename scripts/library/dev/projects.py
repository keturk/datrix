#!/usr/bin/env python3
"""
List Datrix projects or full paths to their src/tests/docs folders.

Discovers all datrix* directories under the workspace root. With no arguments,
prints project names (one per line). With --src, --tests, or --docs, prints the
full path of each project's corresponding folder (only for projects that have it).

Usage:
  python scripts/library/dev/projects.py
  python scripts/library/dev/projects.py --src
  python scripts/library/dev/projects.py --tests
  python scripts/library/dev/projects.py --docs
  .\\scripts\\dev\\projects.ps1
  .\\scripts\\dev\\projects.ps1 -Src
  .\\scripts\\dev\\projects.ps1 -Tests
  .\\scripts\\dev\\projects.ps1 -Docs
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

# Add library directory to sys.path to import from shared
library_dir = Path(__file__).resolve().parent.parent
if library_dir.exists() and str(library_dir) not in sys.path:
    sys.path.insert(0, str(library_dir))

from shared.venv import get_datrix_root


def get_project_roots() -> list[Path]:
    """
    Return sorted list of project root directories under the Datrix workspace.

    Returns:
        Sorted paths to directories whose names start with "datrix".

    Raises:
        FileNotFoundError: If the Datrix root cannot be found.
    """
    datrix_root = get_datrix_root()
    return sorted(
        d for d in datrix_root.iterdir()
        if d.is_dir() and d.name.startswith("datrix")
    )


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
