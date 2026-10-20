"""List the completed tasks and fixed bugs of the workspace.

``scripts/tasks/completed.ps1`` (and its ``.sh`` twin) runs this module over the folders ``task_listing``
reads. A task is completed when its first heading is ``COMPLETED: Task ...``; a bug is fixed when its
heading is ``FIXED: Bug ...``. A phase folder's ``dependencies.md`` is listed once every task of the phase
is completed and, with a filter, when its name or its phase folder's name matches.

Exit codes: 0 = listed; 1 = the base directory does not exist, or a self-test check failed.

Usage:
  python -m datrix_scripts.tasks.completed [--base-dir D:/datrix] [--filter loader]
  .\\scripts\\tasks\\completed.ps1 [-BaseDir <path>] [-Filter <text>]
"""

from __future__ import annotations

import argparse
import re
import sys
import tempfile
from collections.abc import Sequence
from pathlib import Path
from typing import Final

from datrix_scripts.tasks.task_listing import (
    DEPENDENCIES_FILE,
    DONE_PHASE,
    EXIT_LISTED,
    LISTED_PHASE,
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
    render,
    run_on_base,
    scan,
)
from datrix_scripts.test.wrappers import TASKS_SCRIPTS_DIR, module_main, run_self_test

MODULE: Final = "datrix_scripts.tasks.completed"
WRAPPER: Final = "completed"

COMPLETED_TASK: Final = re.compile(r"^COMPLETED:\s+Task\s", re.IGNORECASE)
FIXED_BUG: Final = re.compile(r"^FIXED:\s+Bug\s+", re.IGNORECASE)

WORDS: Final = ListingWords(
    tasks_heading="Completed Tasks",
    bugs_heading="Fixed Bugs",
    phase_label="Completed Tasks",
    none_found="No completed tasks or fixed bugs found!",
    task_noun="completed task(s)",
    bug_noun="fixed bug(s)",
    item_noun="completed item(s)",
)


def select_task(path: Path, text: str, pattern: str) -> ListedItem | None:
    """The task as listed when it is completed and matches *pattern*."""
    heading = first_heading(text)
    if heading is None or not COMPLETED_TASK.match(heading) or not matches_filter(path.name, heading, pattern):
        return None
    return ListedItem(path, heading)


def select_phase(context: PhaseContext) -> PhaseEntry | None:
    """The phase's ``dependencies.md`` once every task of the phase is completed and it matches the filter."""
    counts = context.counts
    if counts.total == 0 or counts.completed != counts.total:
        return None
    if not matches_filter(DEPENDENCIES_FILE, context.folder.name, context.pattern):
        return None
    return PhaseEntry(context.folder.name, context.dependencies, counts.completed, counts.total)


POLICY: Final = ListingPolicy(select_task, select_phase, FIXED_BUG, WORDS)


def report(base: Path, pattern: str) -> int:
    """Print the completed tasks and fixed bugs under *base* that match *pattern*."""
    for line in render(scan(base, pattern, POLICY), WORDS):
        print(line)
    return EXIT_LISTED


def _check_completed_tasks_fixed_bugs_and_finished_phases_are_listed() -> None:
    with tempfile.TemporaryDirectory() as raw:
        root = plant_listing_workspace(Path(raw))
        alpha = root / planted_folder("datrix-alpha", LISTED_PHASE)
        beta = root / planted_folder("datrix-beta", DONE_PHASE)
        lines = printed_lines(report, root, "")
    expected = [
        "=== datrix-alpha ===",
        f"   {alpha / planted_name(LISTED_PHASE, 2, 'done')}",
        f"   Title: {planted_title(LISTED_PHASE, 2, 'Done work', completed=True)}",
        "=== datrix-beta ===",
        f"   {beta / DEPENDENCIES_FILE}",
        f"   Phase: {beta.name} | Completed Tasks: 1/1",
        f"   Title: {planted_title(DONE_PHASE, 1, 'Final step', completed=True)}",
        " Title: FIXED: Bug leak",
        "Total: 2 completed task(s) across 2 project(s)",
        "Total: 1 fixed bug(s) across 1 project(s)",
        "Grand Total: 3 completed item(s)",
    ]
    missing = [line for line in expected if line not in lines]
    assert not missing, f"missing lines {missing}; printed:\n" + "\n".join(lines)
    listed = "\n".join(lines)
    assert "(root)" not in listed and "Open work" not in listed and "crash" not in listed, listed


def _check_a_filter_keeps_only_what_matches() -> None:
    with tempfile.TemporaryDirectory() as raw:
        root = plant_listing_workspace(Path(raw))
        lines = printed_lines(report, root, "FINAL")
        nothing = printed_lines(report, root, "no-such-item")
    assert "Total: 1 completed task(s) across 1 project(s)" in lines, lines
    assert "Done work" not in "\n".join(lines) and "Phase:" not in "\n".join(lines), lines
    assert WORDS.none_found in nothing, nothing


def build_parser() -> argparse.ArgumentParser:
    """The options of ``tasks/completed.ps1``."""
    return listing_parser("List completed tasks and fixed bugs across the workspace")


def _run(args: argparse.Namespace) -> int:
    if args.self_test:
        checks = [_check_completed_tasks_fixed_bugs_and_finished_phases_are_listed,
                  _check_a_filter_keeps_only_what_matches, missing_base_dir_check(main)]
        return run_self_test(checks, wrapper=WRAPPER, module=MODULE, parser=build_parser(), folder=TASKS_SCRIPTS_DIR)
    return run_on_base(args, lambda base: report(base, args.filter))


def main(argv: Sequence[str] | None = None) -> int:
    """Entry point."""
    return module_main(build_parser(), _run, argv)


if __name__ == "__main__":
    sys.exit(main())
