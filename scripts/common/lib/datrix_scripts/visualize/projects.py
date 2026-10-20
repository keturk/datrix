"""The projects a docs script runs on: one ``--source``, or a test set from ``test-projects.json``.

Shared by the visualize modules (diagrams, API specs, snapshots, docs status), which take the same
selection options: ``--source`` for one project, or ``--all`` / ``--domains`` / ``--test-set`` for a
batch. A project's docs are written next to its ``.dtrx`` source (``<project>/docs/...``).
"""

from __future__ import annotations

import argparse
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Final

from datrix_scripts.gate_harness import WRAPPER_DEBUG_FLAG, UsageError
from datrix_scripts.paths import SHOWCASE_DIR, WORKSPACE_DIR
from datrix_scripts.test_projects import get_test_projects

ALL_TEST_SET: Final = "all"
DOMAINS_TEST_SET: Final = "domains"
DOCS_DIR_NAME: Final = "docs"
EXAMPLES_DIR: Final = SHOWCASE_DIR / "examples"


class ProjectSelectionError(Exception):
    """The batch's test set could not be read, or names no project."""


@dataclass(frozen=True)
class Project:
    """One project of a run: its name and its ``.dtrx`` file or directory."""

    name: str
    source: Path

    @property
    def directory(self) -> Path:
        """The project directory: the source's folder, or the source when it is a directory."""
        return self.source.parent if self.source.is_file() else self.source


def add_selection_arguments(parser: argparse.ArgumentParser) -> None:
    """``--source``, ``--all``, ``--domains``, ``--test-set`` and ``--dbg``: the wrappers' shared parameters."""
    parser.add_argument("--source", help="Path to a .dtrx file or a directory holding system.dtrx (single mode).")
    parser.add_argument("--all", action="store_true", dest="batch_all", help="All projects from test-projects.json.")
    parser.add_argument("--domains", action="store_true", help="Domain examples only.")
    parser.add_argument("--test-set", default=ALL_TEST_SET, help="Named test set from test-projects.json (default: all).")
    parser.add_argument(WRAPPER_DEBUG_FLAG, dest="debug", action="store_true", help="Enable debug logging.")


def require_selection(args: argparse.Namespace) -> None:
    """Refuse a run naming neither a source nor a batch.

    Raises:
        UsageError: Neither ``--source`` nor ``--all`` / ``--domains`` was given.
    """
    if not args.source and not args.batch_all and not args.domains:
        raise UsageError("Either -Source or a batch flag (-All, -Domains) is required.")


def workspace_path(value: str) -> Path:
    """*value* as a path, a relative one taken from the workspace root."""
    path = Path(value)
    return path if path.is_absolute() else WORKSPACE_DIR / path


def selected_test_set(args: argparse.Namespace) -> str:
    """The test set a batch run reads: ``domains`` with ``--domains``, else ``--test-set``."""
    return DOMAINS_TEST_SET if args.domains else args.test_set


def batch_projects(test_set: str) -> list[Project]:
    """The projects of *test_set*, each source taken from the workspace root when relative.

    Raises:
        ProjectSelectionError: The test set could not be read, or names no project.
    """
    try:
        entries = get_test_projects(test_set=test_set)
    except (OSError, ValueError, KeyError) as exc:
        raise ProjectSelectionError(f"Failed to load test projects: {exc}") from exc
    if not entries:
        raise ProjectSelectionError(
            f"No projects found in test set '{test_set}'. Pass a test set test-projects.json defines."
        )
    return [Project(name=str(entry["name"]), source=workspace_path(str(entry["path"]))) for entry in entries]


def plant_example(example: str, root: Path) -> Path:
    """A copy of ``examples/<example>`` under *root* without its ``docs/`` (for a self-test that writes docs)."""
    target = root / Path(example).name
    shutil.copytree(EXAMPLES_DIR / example, target, ignore=shutil.ignore_patterns(DOCS_DIR_NAME))
    return target
