"""List the open tasks and bugs of the workspace, and the task folders that listing cannot see.

``scripts/tasks/todo.ps1`` (and its ``.sh`` twin) runs this module over the folders ``task_listing`` reads.
A task is open when its first heading does not start ``COMPLETED:``; a task whose heading is missing, or is
not ``Task ...`` / ``<STATUS>: Task ...``, is listed with a warning. A bug is open when its heading is
``Bug ...``. A phase folder's ``dependencies.md`` is listed while the phase has an open task; with a
filter, when its name, its phase folder's name, or the name or title of one of the phase's task files
matches. Last, every ``.tasks`` folder under the base directory other than the root's and the
repositories' is reported: its files are invisible to this listing.

Exit codes: 0 = listed; 1 = the base directory does not exist, or a self-test check failed.

Usage:
  python -m datrix_scripts.tasks.todo [--base-dir D:/datrix] [--filter loader]
  .\\scripts\\tasks\\todo.ps1 [-BaseDir <path>] [-Filter <text>]
"""

from __future__ import annotations

import argparse
import os
import re
import sys
import tempfile
from collections.abc import Sequence
from pathlib import Path
from typing import Final

from datrix_scripts.cleanup_utils import child_dirs
from datrix_scripts.tasks.task_listing import (
    COMPLETED_HEADING,
    DEPENDENCIES_FILE,
    EXIT_LISTED,
    LISTED_PHASE,
    RULE,
    TASKS_FOLDER,
    ListedItem,
    ListingPolicy,
    ListingWords,
    PhaseContext,
    PhaseEntry,
    first_heading,
    listing_parser,
    matches_filter,
    missing_base_dir_check,
    plant_listing_workspace,
    planted_folder,
    planted_name,
    planted_title,
    printed_lines,
    read_text,
    render,
    run_on_base,
    same_folder,
    scan,
    task_files,
    tasks_roots,
)
from datrix_scripts.test.wrappers import TASKS_SCRIPTS_DIR, module_main, run_self_test

MODULE: Final = "datrix_scripts.tasks.todo"
WRAPPER: Final = "todo"

MISSING_TITLE: Final = "(missing)"
EMPTY_WARNING: Final = "Task file is empty; expected first heading like 'Task ...' or '<STATUS>: Task ...'."
NO_HEADING_WARNING: Final = "Missing first markdown heading; expected 'Task ...' or '<STATUS>: Task ...'."
FORMAT_WARNING: Final = "Task title is not in expected format; expected 'Task ...' or '<STATUS>: Task ...'."
TASK_TITLE: Final = re.compile(r"^(?:[A-Z][A-Z0-9_-]*:\s+)?Task\s+", re.IGNORECASE)
OPEN_BUG: Final = re.compile(r"^Bug\s+", re.IGNORECASE)

# Folders the stray sweep does not enter: tool caches, environments, build output and the workspace's scratch.
SWEEP_EXCLUDED: Final = frozenset(name.casefold() for name in (
    "node_modules", ".git", ".venv", "venv", "env", "__pycache__",
    ".mypy_cache", ".pytest_cache", ".ruff_cache", ".tox", ".idea",
    ".vscode", "dist", "build", "htmlcov", ".eggs", "site-packages",
    ".projects", ".tmp", ".test-output", ".agent_output", ".scripts",
))

WORDS: Final = ListingWords(
    tasks_heading="Incomplete Tasks",
    bugs_heading="Incomplete Bugs",
    phase_label="Incomplete Tasks",
    none_found="No incomplete tasks or bugs found!",
    task_noun="incomplete task(s)",
    bug_noun="incomplete bug(s)",
    item_noun="incomplete item(s)",
)


def select_task(path: Path, text: str, pattern: str) -> ListedItem | None:
    """The task as listed when it is open and matches *pattern*; its title warning when the title is malformed."""
    heading = first_heading(text)
    if not text.strip():
        title, warning = MISSING_TITLE, EMPTY_WARNING
    elif heading is None:
        title, warning = MISSING_TITLE, NO_HEADING_WARNING
    elif COMPLETED_HEADING.match(heading):
        return None
    else:
        title, warning = heading, "" if TASK_TITLE.match(heading) else FORMAT_WARNING
    if not matches_filter(path.name, title, pattern):
        return None
    return ListedItem(path, title, warning)


def _phase_task_folders(context: PhaseContext) -> list[Path]:
    folders = [context.folder]
    if context.fallback:
        for root in context.roots:
            same_named = root / context.folder.name
            if same_named.exists() and not same_folder(same_named, context.folder):
                folders.append(same_named)
    return folders


def _phase_matches(context: PhaseContext) -> bool:
    if matches_filter(DEPENDENCIES_FILE, context.folder.name, context.pattern):
        return True
    for folder in _phase_task_folders(context):
        for path in task_files(folder):
            try:
                title = first_heading(read_text(path)) or ""
            except OSError:
                continue
            if matches_filter(path.name, title, context.pattern):
                return True
    return False


def select_phase(context: PhaseContext) -> PhaseEntry | None:
    """The phase's ``dependencies.md`` while the phase has an open task and it matches the filter."""
    open_count = context.counts.total - context.counts.completed
    if open_count <= 0 or not _phase_matches(context):
        return None
    return PhaseEntry(context.folder.name, context.dependencies, open_count, context.counts.total)


POLICY: Final = ListingPolicy(select_task, select_phase, OPEN_BUG, WORDS)


def stray_tasks_folders(base: Path) -> list[Path]:
    """Every ``.tasks`` folder under *base* other than the root's and the repositories' (sorted)."""
    legitimate = {os.path.normcase(str(root)) for root in tasks_roots(base)}
    stray: list[Path] = []
    pending = [base]
    while pending:
        for child in child_dirs(pending.pop(), include_hidden=True):
            name = child.name.casefold()
            if name == TASKS_FOLDER:
                if os.path.normcase(str(child)) not in legitimate:
                    stray.append(child)
            elif name not in SWEEP_EXCLUDED:
                pending.append(child)
    return sorted(stray, key=lambda path: str(path).casefold())


def stray_lines(stray: list[Path]) -> list[str]:
    """The warning about stray ``.tasks`` folders; nothing when there is none."""
    if not stray:
        return []
    return [
        RULE,
        "WARNING: Stray .tasks folder(s) found",
        RULE,
        "These .tasks folders are NOT at the root of a project package,",
        "so their task/bug files are invisible to this tool:",
        *(f"   {path}" for path in stray),
        "",
        "Move the task files into the appropriate package's root .tasks folder",
        "(e.g. <package>\\.tasks\\phase-NN\\...), then delete the stray folder.",
        RULE,
        "",
    ]


def report(base: Path, pattern: str) -> int:
    """Print the open tasks and bugs under *base* that match *pattern*, then the stray ``.tasks`` folders."""
    for line in [*render(scan(base, pattern, POLICY), WORDS), *stray_lines(stray_tasks_folders(base))]:
        print(line)
    return EXIT_LISTED


def _check_open_tasks_bugs_and_phases_are_listed() -> None:
    with tempfile.TemporaryDirectory() as raw:
        root = plant_listing_workspace(Path(raw))
        alpha = root / planted_folder("datrix-alpha", LISTED_PHASE)
        lines = printed_lines(report, root, "")
        phase = root / planted_folder("", LISTED_PHASE)
    expected = [
        "=== (root) ===",
        f"   {phase / DEPENDENCIES_FILE}",
        f"   Phase: {phase.name} | Incomplete Tasks: 2/3",
        "=== datrix-alpha ===",
        f"   {alpha / planted_name(LISTED_PHASE, 1, 'open')}",
        f"   Title: {planted_title(LISTED_PHASE, 1, 'Open work')}",
        f"   {alpha / planted_name(LISTED_PHASE, 3, 'odd')}",
        "   Title: Odd heading",
        f"   Warning: {FORMAT_WARNING}",
        f"   {alpha / planted_name(LISTED_PHASE, 4, 'empty')}",
        f"   Title: {MISSING_TITLE}",
        f"   Warning: {EMPTY_WARNING}",
        f"   {alpha / planted_name(LISTED_PHASE, 5, 'bare')}",
        f"   Title: {MISSING_TITLE}",
        f"   Warning: {NO_HEADING_WARNING}",
        " Title: Bug 1: crash on start",
        "Total: 4 incomplete task(s) across 2 project(s)",
        "Total: 1 incomplete bug(s) across 1 project(s)",
        "Grand Total: 5 incomplete item(s)",
        f"   {root / 'datrix-beta' / 'src' / TASKS_FOLDER}",
    ]
    missing = [line for line in expected if line not in lines]
    assert not missing, f"missing lines {missing}; printed:\n" + "\n".join(lines)
    listed = "\n".join(lines)
    assert "Done work" not in listed and "leak" not in listed and "Final step" not in listed, listed


def _check_a_filter_reaches_the_phase_through_another_repository() -> None:
    with tempfile.TemporaryDirectory() as raw:
        root = plant_listing_workspace(Path(raw))
        lines = printed_lines(report, root, "OPEN")
        nothing = printed_lines(report, root, "no-such-item")
        phase = root / planted_folder("", LISTED_PHASE)
    assert f"   {phase / DEPENDENCIES_FILE}" in lines, "the root phase is listed: datrix-alpha's open task matches"
    assert "Total: 1 incomplete task(s) across 2 project(s)" in lines, lines
    assert "crash" not in "\n".join(lines), lines
    assert WORDS.none_found in nothing, nothing


def build_parser() -> argparse.ArgumentParser:
    """The options of ``tasks/todo.ps1``."""
    return listing_parser("List incomplete tasks and bugs across the workspace")


def _run(args: argparse.Namespace) -> int:
    if args.self_test:
        checks = [_check_open_tasks_bugs_and_phases_are_listed, _check_a_filter_reaches_the_phase_through_another_repository,
                  missing_base_dir_check(main)]
        return run_self_test(checks, wrapper=WRAPPER, module=MODULE, parser=build_parser(), folder=TASKS_SCRIPTS_DIR)
    return run_on_base(args, lambda base: report(base, args.filter))


def main(argv: Sequence[str] | None = None) -> int:
    """Entry point."""
    return module_main(build_parser(), _run, argv)


if __name__ == "__main__":
    sys.exit(main())
