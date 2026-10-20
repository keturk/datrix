"""
Helpers for scanning trees that contain .test_results without traversing heavy dirs.

``os.walk`` lists *every file* in every directory, so scanning ``.generated`` under
large ``src/`` trees is extremely slow even when ``node_modules`` is pruned. Status
tools use directory-only traversal and only yield ``.test_results`` paths.
"""

import os
from collections.abc import Iterator
from pathlib import Path

# Unit test summary filename under each ``unit-tests-*`` folder.
UNIT_TEST_SUMMARY_PRIMARY: str = "unit-tests-summary.log"

# Directories that never contain nested project .test_results for our layout
SKIP_TRAVERSAL_DIRS: frozenset[str] = frozenset(
    {
        "node_modules",
        ".git",
        "__pycache__",
        ".venv",
        "venv",
        "build",
        "dist",
        ".tox",
        ".mypy_cache",
        ".pytest_cache",
        ".eggs",
        ".ruff_cache",
        ".hypothesis",
        "htmlcov",
        ".benchmarks",
        ".cache",
        ".nox",
        # Source and test trees: results live under project/.test_results only
        "src",
        "tests",
        "test",
        "__tests__",
        "coverage",
        "cypress",
        "e2e",
    }
)


def iter_dot_test_results_dirs(root_dir: Path) -> Iterator[Path]:
    """
    Yield each ``.test_results`` directory under ``root_dir``.

    Uses ``os.scandir`` and only follows subdirectories (never enumerates files).
    Does not descend into ``.test_results`` (unit-tests / deploy-test folders are
    read separately via ``iterdir`` on that path only).
    """
    if not root_dir.is_dir():
        return
    stack: list[Path] = [root_dir.resolve()]
    while stack:
        current = stack.pop()
        try:
            with os.scandir(current) as it:
                for entry in it:
                    try:
                        if not entry.is_dir(follow_symlinks=False):
                            continue
                    except OSError:
                        continue
                    name = entry.name
                    if name == ".test_results":
                        yield Path(entry.path)
                        continue
                    if name in SKIP_TRAVERSAL_DIRS:
                        continue
                    stack.append(Path(entry.path))
        except OSError:
            continue


def resolve_unit_test_summary_log(latest_run_folder: Path) -> Path | None:
    """Pick the unit-test summary file inside a ``run-unit-tests-*`` directory."""
    primary = latest_run_folder / UNIT_TEST_SUMMARY_PRIMARY
    if primary.exists():
        return primary
    return None


def list_language_dirs(root_dir: Path) -> list[str]:
    """
    Return the language directory names directly under ``root_dir``.

    The set is discovered from disk rather than from a hardcoded language list, so
    a newly generated target appears with no edit to this module.
    """
    if not root_dir.is_dir():
        return []
    return sorted(
        entry.name
        for entry in root_dir.iterdir()
        if entry.is_dir() and not entry.name.startswith(".")
    )


def resolve_language_root(root_dir: Path, language: str) -> Path:
    """
    Narrow ``root_dir`` to the subtree holding one language's generated projects.

    Generated output is laid out as ``<root>/<language>/<platform>/...``, so filtering
    by language is a subtree selection: results outside it are never scanned.

    Args:
        root_dir: Root of the generated tree (normally ``<workspace>/.generated``)
        language: Language directory name to restrict the search to

    Returns:
        Path to ``<root_dir>/<language>``

    Raises:
        ValueError: If ``root_dir`` holds no directory for ``language``
    """
    language_root = root_dir / language
    if language_root.is_dir():
        return language_root

    available = list_language_dirs(root_dir)
    available_text = ", ".join(available) if available else "(none)"
    raise ValueError(
        f"No generated output for language '{language}' under {root_dir}. "
        f"Expected the directory {language_root}. "
        f"Languages present: {available_text}. "
        f"Generate that language first, or omit the language filter to report on all."
    )
