#!/usr/bin/env python3
"""Report documentation status for Datrix projects.

Scans Datrix project source directories and reports which documentation
artifacts exist: diagrams, OpenAPI specs, AsyncAPI specs, and snapshots.
Supports single-file and batch modes.
"""

from __future__ import annotations

import argparse
import io
import signal
import sys
from pathlib import Path

# ── UTF-8 for Windows ──
if sys.platform == "win32":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")


def _sigint_handler(_signum: int, _frame: object) -> None:
    sys.exit(130)


signal.signal(signal.SIGINT, _sigint_handler)

# ── sys.path setup ──
library_dir = Path(__file__).resolve().parent.parent
if library_dir.exists() and str(library_dir) not in sys.path:
    sys.path.insert(0, str(library_dir))

from shared.venv import get_datrix_root  # noqa: E402
from shared.logging_utils import ColorCodes, colorize  # noqa: E402
from shared.test_projects import get_test_projects  # noqa: E402

datrix_root = get_datrix_root()

DOC_TYPES = ("diagrams", "openapi", "asyncapi")


def _check_docs(project_dir: Path) -> dict[str, bool]:
    """Check which documentation types exist under a project directory.

    Looks for docs/{type} as children of the project directory.

    Args:
        project_dir: The Datrix project root (directory containing system.dtrx).

    Returns:
        Dict mapping doc type names to presence booleans.
    """
    docs_dir = project_dir / "docs"
    result: dict[str, bool] = {}
    for doc_type in DOC_TYPES:
        type_dir = docs_dir / doc_type
        if type_dir.is_dir():
            files = [f for f in type_dir.iterdir() if not f.name.startswith(".")]
            result[doc_type] = len(files) > 0
        else:
            result[doc_type] = False
    return result


def _scan_single_project(project_dir: Path) -> None:
    """Report docs status for a single Datrix project directory."""
    project_dir = project_dir.resolve()
    if not project_dir.is_dir():
        print(
            colorize(f"Project directory not found: {project_dir}", ColorCodes.RED),
            file=sys.stderr,
        )
        return

    print(f"Project: {project_dir.name}")
    print(f"Path:    {project_dir}\n")

    status = _check_docs(project_dir)
    has_any = any(status.values())

    if has_any:
        for doc_type in DOC_TYPES:
            if status[doc_type]:
                docs_dir = project_dir / "docs" / doc_type
                files = [f for f in docs_dir.iterdir() if not f.name.startswith(".")]
                print(f"  {doc_type}: {colorize(f'{len(files)} files', ColorCodes.GREEN)}")
                for f in sorted(files):
                    print(f"    {f.name}")
            else:
                print(f"  {doc_type}: {colorize('none', ColorCodes.GRAY)}")
    else:
        print(colorize("  No documentation found.", ColorCodes.YELLOW))


def _print_table(projects: list[tuple[str, Path]]) -> None:
    """Print a table of docs status for multiple projects."""
    col_project = 45
    col_type = 12
    header = f"{'Project':<{col_project}}"
    for doc_type in DOC_TYPES:
        header += f"  {doc_type:<{col_type}}"
    print(header)
    print("-" * len(header))

    total = len(projects)
    with_docs = 0

    for project_name, project_dir in projects:
        status = _check_docs(project_dir)
        has_any = any(status.values())

        line = f"{project_name:<{col_project}}"
        for doc_type in DOC_TYPES:
            if status.get(doc_type, False):
                marker = colorize("YES", ColorCodes.GREEN)
            else:
                marker = colorize(" - ", ColorCodes.GRAY)
            line += f"  {marker:<{col_type}}"

        print(line)
        if has_any:
            with_docs += 1

    print(f"\n{total} projects scanned, {with_docs} have documentation")


def main() -> int:
    """Entry point for status-docs script."""
    parser = argparse.ArgumentParser(
        description="Report documentation status for Datrix projects.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--source", type=str, default=None, help="Path to .dtrx file or directory")
    parser.add_argument("--all", action="store_true", dest="batch_all", help="All projects from test-projects.json")
    parser.add_argument("--tutorial", action="store_true", help="Tutorial examples only")
    parser.add_argument("--domains", action="store_true", help="Domain examples only")
    parser.add_argument("--test-set", type=str, default="generate-all", help="Named test set")
    parser.add_argument("--debug", action="store_true", help="Enable debug logging")

    args = parser.parse_args()

    batch_mode = args.batch_all or args.tutorial or args.domains

    if not batch_mode and not args.source:
        parser.error("Either --source or a batch flag (--all, --tutorial, --domains) is required.")

    if args.source:
        # Single project mode — scan the source project directory
        source_path = Path(args.source)
        if not source_path.is_absolute():
            source_path = datrix_root / source_path
        source_path = source_path.resolve()
        project_dir = source_path.parent if source_path.is_file() else source_path
        _scan_single_project(project_dir)
        return 0

    # Batch mode
    test_set = "generate-all"
    if args.tutorial:
        test_set = "tutorial-all"
    elif args.domains:
        test_set = "domains"
    elif args.test_set != "generate-all":
        test_set = args.test_set

    try:
        test_projects = get_test_projects(test_set=test_set)
    except Exception as e:
        print(colorize(f"ERROR: Failed to load test projects: {e}", ColorCodes.RED), file=sys.stderr)
        return 1

    if not test_projects:
        print(colorize(f"No projects found in test set '{test_set}'", ColorCodes.YELLOW))
        return 1

    projects: list[tuple[str, Path]] = []
    for project in test_projects:
        name = project.get("name", "unknown")
        source = project.get("path", "")
        source_path = Path(source)
        if not source_path.is_absolute():
            source_path = datrix_root / source
        project_dir = source_path.parent if source_path.is_file() else source_path
        projects.append((name, project_dir))

    print(f"Documentation status for {len(projects)} projects (test set: {test_set})\n")
    _print_table(projects)
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception:
        import traceback
        traceback.print_exc()
        sys.exit(1)
