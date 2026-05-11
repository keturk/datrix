#!/usr/bin/env python3
"""
Generate project structure files for Datrix projects.

Walks the src/, tests/, and templates/ directories of each project and writes
a .project-structure.md file to the project root containing annotated ASCII
directory trees.

Usage:
  python scripts/library/dev/project_structure.py datrix-codegen-typescript
  python scripts/library/dev/project_structure.py datrix-codegen-python datrix-common
  python scripts/library/dev/project_structure.py --all
  python scripts/library/dev/project_structure.py datrix-codegen-typescript --depth 5
  .\\scripts\\dev\\project-structure.ps1 datrix-codegen-typescript
  .\\scripts\\dev\\project-structure.ps1 -All
"""

from __future__ import annotations

import argparse
import io
import logging
import sys
from datetime import datetime, timezone
from pathlib import Path

# Configure UTF-8 encoding for stdout/stderr on Windows
if sys.platform == "win32" and __name__ == "__main__":
    if hasattr(sys.stdout, "buffer"):
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    if hasattr(sys.stderr, "buffer"):
        sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

# Add library directory to sys.path to import from shared
library_dir = Path(__file__).resolve().parent.parent
if library_dir.exists() and str(library_dir) not in sys.path:
    sys.path.insert(0, str(library_dir))

from shared.venv import get_datrix_root

logger = logging.getLogger(__name__)

OUTPUT_FILENAME = ".project-structure.md"

IGNORED_DIRECTORIES = frozenset({
    ".git",
    ".github",
    "__pycache__",
    ".mypy_cache",
    ".pytest_cache",
    ".ruff_cache",
    ".benchmarks",
    ".test_results",
    ".tasks",
    ".agent_output",
    ".ruff_check",
    ".tox",
    ".venv",
    ".eggs",
    "build",
    "dist",
    "htmlcov",
    "node_modules",
    ".logic-map",
})

IGNORED_SUFFIXES = frozenset({
    ".egg-info",
    ".dist-info",
})

TREE_DIRS_TO_GENERATE = ("src", "tests", "templates")

SECTION_TITLES: dict[str, str] = {
    "src": "Source Code Layout",
    "tests": "Test Directory Layout",
    "templates": "Templates Layout",
}


def _is_ignored_dir(name: str) -> bool:
    """Check if a directory name should be skipped during tree generation."""
    if name in IGNORED_DIRECTORIES:
        return True
    return any(name.endswith(suffix) for suffix in IGNORED_SUFFIXES)


def generate_tree(root: Path, max_depth: int) -> str:
    """
    Generate an ASCII directory tree for a given root path.

    Args:
        root: The directory to walk.
        max_depth: Maximum depth of directories to include (1 = root only).

    Returns:
        ASCII tree string with ``├──`` / ``└──`` connectors.
    """
    lines: list[str] = [root.name + "/"]
    _walk_tree(root, prefix="", depth=1, max_depth=max_depth, lines=lines)
    return "\n".join(lines)


def _walk_tree(
    directory: Path,
    prefix: str,
    depth: int,
    max_depth: int,
    lines: list[str],
) -> None:
    """Recursively build ASCII tree lines for a directory."""
    if depth > max_depth:
        return

    entries = _sorted_entries(directory)
    if not entries:
        return

    for i, entry in enumerate(entries):
        is_last = i == len(entries) - 1
        connector = "└── " if is_last else "├── "
        child_prefix = prefix + ("    " if is_last else "│   ")

        if entry.is_dir():
            lines.append(f"{prefix}{connector}{entry.name}/")
            _walk_tree(entry, child_prefix, depth + 1, max_depth, lines)
        else:
            lines.append(f"{prefix}{connector}{entry.name}")


def _sorted_entries(directory: Path) -> list[Path]:
    """
    List directory entries sorted: directories first, then files, alphabetical.

    Skips ignored directories and hidden files (except __init__.py).
    """
    try:
        entries = list(directory.iterdir())
    except PermissionError:
        logger.warning("Permission denied: %s", directory)
        return []

    dirs: list[Path] = []
    files: list[Path] = []

    for entry in entries:
        if entry.is_dir():
            if not _is_ignored_dir(entry.name):
                dirs.append(entry)
        elif entry.is_file():
            files.append(entry)

    dirs.sort(key=lambda p: p.name)
    files.sort(key=lambda p: p.name)
    return dirs + files


def resolve_projects(
    project_names: list[str],
    discover_all: bool,
    datrix_root: Path,
) -> list[Path]:
    """
    Resolve project names or --all flag to a list of project root paths.

    Args:
        project_names: Explicit project names or paths from CLI.
        discover_all: If True, discover all datrix-* projects that have src/ or tests/.
        datrix_root: The workspace root directory.

    Returns:
        Sorted list of validated project paths.

    Raises:
        SystemExit: If a named project does not exist.
    """
    if discover_all:
        projects = sorted(
            d
            for d in datrix_root.iterdir()
            if d.is_dir()
            and d.name.startswith("datrix")
            and (
                (d / "src").is_dir()
                or (d / "tests").is_dir()
                or (d / "templates").is_dir()
            )
        )
        logger.info("Discovered %d projects", len(projects))
        return projects

    resolved: list[Path] = []
    for name in project_names:
        candidate = Path(name)
        if candidate.is_absolute() and candidate.is_dir():
            resolved.append(candidate)
            continue

        project_path = datrix_root / name
        if project_path.is_dir():
            resolved.append(project_path)
            continue

        print(
            "ERROR: Project '%s' not found at %s" % (name, project_path),
            file=sys.stderr,
        )
        sys.exit(1)

    return sorted(resolved)


def ensure_gitignore_entry(project_path: Path) -> None:
    """Ensure .project-structure.md is listed in the project's .gitignore."""
    gitignore_path = project_path / ".gitignore"
    if not gitignore_path.is_file():
        return

    content = gitignore_path.read_text(encoding="utf-8")
    if OUTPUT_FILENAME in content:
        return

    # Append the entry
    if not content.endswith("\n"):
        content += "\n"
    content += "\n# Generated project structure metadata\n"
    content += OUTPUT_FILENAME + "\n"
    gitignore_path.write_text(content, encoding="utf-8")
    logger.info("  Added %s to %s", OUTPUT_FILENAME, gitignore_path.name)


def generate_project_structure(project_path: Path, max_depth: int) -> str:
    """
    Generate the full .project-structure.md content for a project.

    Args:
        project_path: Root directory of the project.
        max_depth: Maximum tree depth.

    Returns:
        Markdown string with all directory trees.
    """
    now = datetime.now(tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    sections: list[str] = [
        f"# Project Structure: {project_path.name}\n",
        f"Generated: {now}\n",
    ]

    for dir_name in TREE_DIRS_TO_GENERATE:
        target = project_path / dir_name
        if not target.is_dir():
            continue

        title = SECTION_TITLES.get(dir_name, dir_name.title() + " Layout")
        tree = generate_tree(target, max_depth)
        sections.append(f"## {title}\n")
        sections.append(f"```\n{tree}\n```\n")

    return "\n".join(sections)


def main() -> int:
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Generate .project-structure.md files for Datrix projects",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument(
        "projects",
        nargs="*",
        help="Project names or paths (e.g., datrix-codegen-typescript)",
    )
    parser.add_argument(
        "--all",
        action="store_true",
        dest="discover_all",
        help="Generate structure for all discoverable projects",
    )
    parser.add_argument(
        "--depth",
        type=int,
        default=4,
        help="Maximum directory depth to include (default: 4)",
    )
    parser.add_argument(
        "--debug",
        action="store_true",
        help="Enable debug logging",
    )
    args = parser.parse_args()

    if args.debug:
        logging.basicConfig(level=logging.DEBUG, format="%(levelname)s: %(message)s")
    else:
        logging.basicConfig(level=logging.INFO, format="%(message)s")

    if not args.projects and not args.discover_all:
        parser.error("Provide project name(s) or use --all")

    try:
        datrix_root = get_datrix_root()
    except FileNotFoundError:
        print("ERROR: Could not find Datrix root directory", file=sys.stderr)
        return 1

    projects = resolve_projects(args.projects, args.discover_all, datrix_root)

    if not projects:
        print("No projects found", file=sys.stderr)
        return 1

    for project_path in projects:
        content = generate_project_structure(project_path, args.depth)
        output_path = project_path / OUTPUT_FILENAME
        output_path.write_text(content, encoding="utf-8")
        ensure_gitignore_entry(project_path)
        print(f"  {project_path.name} -> {output_path.name}")

    print(f"\nGenerated {len(projects)} project structure file(s)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
