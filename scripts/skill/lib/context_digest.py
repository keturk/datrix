"""The shared-context digest for a phase's implementation agents, built from the code index.

The orchestrator used to dispatch an agent to read the architecture docs and every package's
structure and write a digest for the implementers. Two things made that a waste: the core docs are
read by every agent anyway (a hook blocks its first edit until it has), and a package's layout is
already in the code index, with a one-line description of every module. This builds the part only
the phase can say -- the directories its tasks touch, the modules in them and what each is for --
from the index, exactly, with no model involved.
"""

from __future__ import annotations

import logging
import sqlite3
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path

from common import workspace_label
from datrix_scripts.code_index.queries import QueryError, outline
from datrix_scripts.code_index.session import open_session
from datrix_scripts.task_metadata import format_phase
from phase_tasks import PhaseTask, edit_sites, review_sites

LOG = logging.getLogger(__name__)

LINE_BUDGET = 400
MAX_ENTRIES_PER_DIRECTORY = 30
DESCRIPTION_CHARS = 160
SKIPPED_NAMES = frozenset({"__pycache__", ".pytest_cache", ".ruff_cache", ".mypy_cache"})
NOT_YET_CREATED = "(does not exist yet; a task of this phase creates it)"


@dataclass(frozen=True)
class Digest:
    """The digest text and how it was cut to fit."""

    text: str
    lines: int
    packages: int
    directories: int
    trimmed: bool


def _first_sentence(text: str) -> str:
    head = text.strip().splitlines()[0] if text.strip() else ""
    cut = head.split(". ", 1)[0].rstrip(".")
    return cut[:DESCRIPTION_CHARS]


def _description(conn: sqlite3.Connection, label: str) -> str:
    """The module's own first docstring line, else the index's summary, else nothing."""
    try:
        found = outline(conn, label)
    except QueryError:
        return ""
    return _first_sentence(found.module_doc) or _first_sentence(found.summary)


def _entry(conn: sqlite3.Connection, workspace: Path, path: Path, named: set[Path], describe: bool) -> str:
    marker = " **(named by a task)**" if path in named else ""
    if not path.exists():
        return f"- `{path.name}`{marker} {NOT_YET_CREATED}"
    if path.is_dir():
        return f"- `{path.name}/`"
    text = _description(conn, workspace_label(workspace, path)) if describe and path.suffix == ".py" else ""
    return f"- `{path.name}`{marker}" + (f" -- {text}" if text else "")


def _directory_block(conn: sqlite3.Connection, workspace: Path, directory: Path, named: set[Path],
                     describe_all: bool) -> list[str]:
    present = sorted(p for p in directory.iterdir() if p.name not in SKIPPED_NAMES) if directory.is_dir() else []
    ordered = [p for p in present if p in named] + [p for p in present if p not in named]
    ordered += sorted(p for p in named if p.parent == directory and not p.exists())
    shown = ordered[:MAX_ENTRIES_PER_DIRECTORY]
    lines = [f"### `{workspace_label(workspace, directory)}/`"]
    lines += [_entry(conn, workspace, p, named, describe_all or p in named) for p in shown]
    if len(ordered) > len(shown):
        lines.append(f"- ... and {len(ordered) - len(shown)} more")
    return lines


def _package_blocks(conn: sqlite3.Connection, workspace: Path, tasks: list[PhaseTask],
                    describe_all: bool) -> tuple[list[str], int]:
    by_package: dict[str, list[PhaseTask]] = defaultdict(list)
    for task in tasks:
        by_package[task.package].append(task)
    lines: list[str] = []
    directories = 0
    for package in sorted(by_package):
        owned = by_package[package]
        named = {path for task in owned for path in (*edit_sites(workspace, task), *review_sites(workspace, task))
                 if path.suffix and not path.name.endswith(".md")}
        dirs = sorted({path.parent for path in named})
        lines += ["", f"## Package: {package}", "",
                  "Tasks: " + ", ".join(f"{task.task_id} ({task.meta.title})" for task in owned)]
        for directory in dirs:
            lines += ["", *_directory_block(conn, workspace, directory, named, describe_all)]
        directories += len(dirs)
    return lines, directories


def build_digest(workspace: Path, phase: int, tasks: list[PhaseTask]) -> Digest:
    """The digest for ``tasks``: every package's touched directories, each module with what it is for.

    Built with every module described; when that passes ``LINE_BUDGET`` lines, rebuilt describing only
    the files a task names (the rest listed by name).
    """
    header = [
        f"# Shared context -- phase {format_phase(phase)}",
        "",
        "Built from the code index by `skill-assist.ps1 context-digest`. Your task file and the mandatory "
        "docs are still yours to read; this maps the code around the files the phase touches. Module "
        "descriptions are the module's first docstring line, or the index's summary of it.",
    ]
    session = open_session(workspace)
    try:
        session.refresh()
        body, directories = _package_blocks(session.conn, workspace, tasks, describe_all=True)
        trimmed = len(header) + len(body) > LINE_BUDGET
        if trimmed:
            LOG.info("Digest passes %d lines; describing only the files tasks name", LINE_BUDGET)
            body, directories = _package_blocks(session.conn, workspace, tasks, describe_all=False)
    finally:
        session.close()
    lines = [*header, *body]
    packages = len({task.package for task in tasks})
    return Digest("\n".join(lines) + "\n", len(lines), packages, directories, trimmed)
