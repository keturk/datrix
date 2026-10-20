"""Write a ``.project-structure.md`` of annotated ASCII directory trees into each named Datrix project.

``scripts/workspace/project-structure.ps1`` (and its ``.sh`` twin) runs this module. For each project (a name
under the workspace root or a directory path; ``--all`` discovers the showcase repository and every
``datrix-*`` directory holding ``src/``, ``tests/`` or ``templates/``) it walks those three folders to
``--depth`` levels, skipping caches, build output and VCS folders, and writes the trees to
``<project>/.project-structure.md``. When the project's ``.gitignore`` exists and does not name that file, the
file name is appended to it, so the generated file is never committed.

Exit codes: 0 = every file written; 1 = a named project does not exist, no project was found, or a self-test
check failed; 2 = a usage error (no project and no ``--all``).

Usage (PYTHONPATH=scripts/common/lib; the wrapper sets it):
    python -m datrix_scripts.workspace.project_structure datrix-codegen-typescript
    python -m datrix_scripts.workspace.project_structure --projects=datrix-common --depth=6
    python -m datrix_scripts.workspace.project_structure --all
    python -m datrix_scripts.workspace.project_structure --self-test
"""

from __future__ import annotations

import argparse
import logging
import sys
from collections.abc import Sequence
from datetime import UTC, datetime
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Final

from datrix_scripts.framework_repos import workspace_package_dirs
from datrix_scripts.gate_harness import EXIT_PASS, EXIT_VIOLATION, WRAPPER_DEBUG_FLAG, UsageError, write_files
from datrix_scripts.paths import WORKSPACE_DIR
from datrix_scripts.test.wrappers import WORKSPACE_SCRIPTS_DIR, module_main, run_self_test

logger = logging.getLogger(__name__)

MODULE: Final = "datrix_scripts.workspace.project_structure"
WRAPPER: Final = "project-structure"

OUTPUT_FILENAME: Final = ".project-structure.md"
DEFAULT_DEPTH: Final = 4
GITIGNORE: Final = ".gitignore"
GITIGNORE_COMMENT: Final = "# Generated project structure metadata"

IGNORED_DIRECTORIES: Final = frozenset({
    ".git", ".github", "__pycache__", ".mypy_cache", ".pytest_cache", ".ruff_cache", ".benchmarks",
    ".test_results", ".tasks", ".agent_output", ".ruff_check", ".tox", ".venv", ".eggs", "build", "dist",
    "htmlcov", "node_modules", ".logic-map",
})
IGNORED_SUFFIXES: Final = frozenset({".egg-info", ".dist-info"})
TREE_DIRS_TO_GENERATE: Final = ("src", "tests", "templates")
SECTION_TITLES: Final = {
    "src": "Source Code Layout",
    "tests": "Test Directory Layout",
    "templates": "Templates Layout",
}
_BRANCH: Final = "├── "
_LAST_BRANCH: Final = "└── "
_PIPE: Final = "│   "
_BLANK: Final = "    "


class ProjectNotFoundError(Exception):
    """A named project is neither a directory under the workspace root nor an existing directory path."""


def _is_ignored_dir(name: str) -> bool:
    return name in IGNORED_DIRECTORIES or any(name.endswith(suffix) for suffix in IGNORED_SUFFIXES)


def _sorted_entries(directory: Path) -> list[Path]:
    """The entries of *directory*: directories first (ignored ones left out), then files, each by name."""
    try:
        entries = list(directory.iterdir())
    except PermissionError:
        logger.warning("Permission denied: %s", directory)
        return []
    dirs = sorted((entry for entry in entries if entry.is_dir() and not _is_ignored_dir(entry.name)),
                  key=lambda path: path.name)
    files = sorted((entry for entry in entries if entry.is_file()), key=lambda path: path.name)
    return dirs + files


def _walk_tree(directory: Path, prefix: str, depth: int, max_depth: int, lines: list[str]) -> None:
    if depth > max_depth:
        return
    entries = _sorted_entries(directory)
    for index, entry in enumerate(entries):
        is_last = index == len(entries) - 1
        connector = _LAST_BRANCH if is_last else _BRANCH
        if entry.is_dir():
            lines.append(f"{prefix}{connector}{entry.name}/")
            _walk_tree(entry, prefix + (_BLANK if is_last else _PIPE), depth + 1, max_depth, lines)
        else:
            lines.append(f"{prefix}{connector}{entry.name}")


def generate_tree(root: Path, max_depth: int) -> str:
    """The ASCII tree of *root* to *max_depth* levels (1 = root's own entries), with ``├──`` / ``└──`` connectors."""
    lines = [root.name + "/"]
    _walk_tree(root, prefix="", depth=1, max_depth=max_depth, lines=lines)
    return "\n".join(lines)


def generate_project_structure(project_path: Path, max_depth: int, *, now: datetime | None = None) -> str:
    """The ``.project-structure.md`` text of *project_path*: one tree section per existing ``src``/``tests``/
    ``templates`` folder, stamped with *now* (the current UTC time unless given)."""
    stamp = (now or datetime.now(tz=UTC)).strftime("%Y-%m-%dT%H:%M:%SZ")
    sections = [f"# Project Structure: {project_path.name}\n", f"Generated: {stamp}\n"]
    for dir_name in TREE_DIRS_TO_GENERATE:
        target = project_path / dir_name
        if target.is_dir():
            sections.append(f"## {SECTION_TITLES[dir_name]}\n")
            sections.append(f"```\n{generate_tree(target, max_depth)}\n```\n")
    return "\n".join(sections)


def ensure_gitignore_entry(project_path: Path) -> None:
    """Append ``.project-structure.md`` to the project's ``.gitignore`` when that file exists and lacks it."""
    gitignore_path = project_path / GITIGNORE
    if not gitignore_path.is_file():
        return
    content = gitignore_path.read_text(encoding="utf-8")
    if OUTPUT_FILENAME in content:
        return
    if not content.endswith("\n"):
        content += "\n"
    gitignore_path.write_text(f"{content}\n{GITIGNORE_COMMENT}\n{OUTPUT_FILENAME}\n", encoding="utf-8")
    logger.info("  Added %s to %s", OUTPUT_FILENAME, gitignore_path.name)


def discover_projects(workspace: Path) -> list[Path]:
    """The showcase repository and every ``datrix-*`` directory holding ``src/``, ``tests/`` or ``templates/``."""
    return [
        project for project in workspace_package_dirs(workspace, include_showcase=True)
        if any((project / folder).is_dir() for folder in TREE_DIRS_TO_GENERATE)
    ]


def resolve_projects(names: Sequence[str], workspace: Path) -> list[Path]:
    """The project directories *names* name, sorted; a name is an absolute directory or a directory under
    *workspace*. Raises ``ProjectNotFoundError`` for the first that is neither."""
    resolved: list[Path] = []
    for name in names:
        candidate = Path(name)
        if candidate.is_absolute() and candidate.is_dir():
            resolved.append(candidate)
        elif (workspace / name).is_dir():
            resolved.append(workspace / name)
        else:
            raise ProjectNotFoundError(
                f"Project '{name}' not found at {workspace / name}. Expected a directory name under {workspace} "
                "(e.g. datrix-common) or an existing directory path; run workspace\\projects.ps1 to list them."
            )
    return sorted(resolved)


def write_structures(projects: Sequence[Path], depth: int) -> None:
    """Write each project's ``.project-structure.md`` and its ``.gitignore`` entry, printing one line each."""
    for project_path in projects:
        output_path = project_path / OUTPUT_FILENAME
        output_path.write_text(generate_project_structure(project_path, depth), encoding="utf-8")
        ensure_gitignore_entry(project_path)
        print(f"  {project_path.name} -> {output_path.name}")
    print(f"\nGenerated {len(projects)} project structure file(s)")


def run(args: argparse.Namespace, workspace: Path = WORKSPACE_DIR) -> int:
    """Resolve the requested projects and write their structure files; returns the exit code."""
    names = [*args.projects, *args.positional_projects]
    if not names and not args.all:
        raise UsageError("Provide project name(s) or -All. Example: workspace\\project-structure.ps1 datrix-common")
    try:
        projects = discover_projects(workspace) if args.all else resolve_projects(names, workspace)
    except ProjectNotFoundError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return EXIT_VIOLATION
    if args.all:
        logger.info("Discovered %d projects", len(projects))
    if not projects:
        print(f"No projects found under {workspace}", file=sys.stderr)
        return EXIT_VIOLATION
    write_structures(projects, args.depth)
    return EXIT_PASS


def build_parser() -> argparse.ArgumentParser:
    """The options of ``project-structure.ps1``: its parameters as ``--kebab-name`` flags."""
    parser = argparse.ArgumentParser(
        prog=WRAPPER,
        description="Write .project-structure.md (ASCII trees of src/, tests/, templates/) into Datrix projects.",
        allow_abbrev=False,
    )
    parser.add_argument("positional_projects", nargs="*", metavar="PROJECT",
                        help="as --projects, for a caller of the .sh twin")
    parser.add_argument("--projects", action="append", default=[],
                        help="a project name (e.g. datrix-codegen-typescript) or directory path; repeatable")
    parser.add_argument("--all", action="store_true",
                        help="every datrix project holding src/, tests/ or templates/ (the showcase included)")
    parser.add_argument("--depth", type=int, default=DEFAULT_DEPTH,
                        help=f"maximum directory depth of each tree (default: {DEFAULT_DEPTH})")
    parser.add_argument(WRAPPER_DEBUG_FLAG, dest="debug", action="store_true", help="debug logging")
    parser.add_argument("--self-test", action="store_true", help="run the self-test and exit")
    return parser


# ---------------------------------------------------------------------------
# Self-test: a planted workspace in a temporary directory.
# ---------------------------------------------------------------------------

_PLANTED: Final = {
    "datrix-a/src/a/__init__.py": "\n",
    "datrix-a/src/a/core/model.py": "\n",
    "datrix-a/src/a/__pycache__/x.pyc": "",
    "datrix-a/tests/test_a.py": "\n",
    "datrix-a/.gitignore": "dist/",
    "datrix-b/templates/t.j2": "\n",
    "datrix-b/.gitignore": f"{OUTPUT_FILENAME}\n",
    "datrix-c/README.md": "x\n",
}
_STAMP: Final = datetime(2026, 1, 2, 3, 4, 5, tzinfo=UTC)


def _parse(argv: Sequence[str]) -> argparse.Namespace:
    return build_parser().parse_args(argv)


def _check_tree_lists_dirs_first_and_skips_caches() -> None:
    with TemporaryDirectory() as raw:
        root = Path(raw)
        write_files(root, _PLANTED)
        text = generate_project_structure(root / "datrix-a", DEFAULT_DEPTH, now=_STAMP)
    expected = (
        "# Project Structure: datrix-a\n\nGenerated: 2026-01-02T03:04:05Z\n\n## Source Code Layout\n\n"
        "```\nsrc/\n└── a/\n    ├── core/\n    │   └── model.py\n    └── __init__.py\n```\n\n"
        "## Test Directory Layout\n\n```\ntests/\n└── test_a.py\n```\n"
    )
    assert text == expected, text


def _check_depth_bounds_the_tree() -> None:
    with TemporaryDirectory() as raw:
        root = Path(raw)
        write_files(root, _PLANTED)
        tree = generate_tree(root / "datrix-a" / "src", 1)
    assert tree == "src/\n└── a/", tree


def _check_all_discovers_projects_with_a_tree_folder() -> None:
    with TemporaryDirectory() as raw:
        root = Path(raw)
        write_files(root, _PLANTED)
        assert run(_parse(["--all"]), root) == EXIT_PASS
        written = sorted(path.parent.name for path in root.glob(f"*/{OUTPUT_FILENAME}"))
        gitignore_a = (root / "datrix-a" / GITIGNORE).read_text(encoding="utf-8")
        gitignore_b = (root / "datrix-b" / GITIGNORE).read_text(encoding="utf-8")
    assert written == ["datrix-a", "datrix-b"], written
    assert gitignore_a == f"dist/\n\n{GITIGNORE_COMMENT}\n{OUTPUT_FILENAME}\n", gitignore_a
    assert gitignore_b == f"{OUTPUT_FILENAME}\n", "a .gitignore already naming the file was changed"


def _check_named_and_unknown_projects() -> None:
    with TemporaryDirectory() as raw:
        root = Path(raw)
        write_files(root, _PLANTED)
        assert run(_parse(["datrix-b", f"--projects={root / 'datrix-c'}"]), root) == EXIT_PASS
        written = sorted(path.parent.name for path in root.glob(f"*/{OUTPUT_FILENAME}"))
        assert run(_parse(["datrix-missing"]), root) == EXIT_VIOLATION
    assert written == ["datrix-b", "datrix-c"], written


def _check_no_selection_is_a_usage_error() -> None:
    try:
        run(_parse([]))
    except UsageError:
        return
    raise AssertionError("a run naming no project and no --all was not refused")


_SELF_TEST_CHECKS: Final = (
    _check_tree_lists_dirs_first_and_skips_caches,
    _check_depth_bounds_the_tree,
    _check_all_discovers_projects_with_a_tree_folder,
    _check_named_and_unknown_projects,
    _check_no_selection_is_a_usage_error,
)


def _run(args: argparse.Namespace) -> int:
    if args.self_test:
        return run_self_test(
            _SELF_TEST_CHECKS, wrapper=WRAPPER, module=MODULE, parser=build_parser(), folder=WORKSPACE_SCRIPTS_DIR
        )
    return run(args)


def main(argv: Sequence[str] | None = None) -> int:
    """Run the self-test, or write the structure files of the requested projects."""
    return module_main(build_parser(), _run, argv)


if __name__ == "__main__":
    sys.exit(main())
