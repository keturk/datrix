"""What ``todo`` and ``completed`` share: the task and bug files of the workspace, read by their first heading.

Both read ``<base>/.tasks`` and ``<base>/.bugs`` (listed as ``(root)``) and the same two folders of every
``datrix`` and ``datrix-*`` repository under the base directory. A task or bug is a ``task-*.md`` file at
any depth of those folders; its title is the first Markdown heading. A ``phase-*`` folder holding a
``dependencies.md`` is listed with its task counts; when the folder holds no task file of its own, the
counts are those of the same-named phase folders of every repository. A filter keeps the items whose
file name or title contains it, case-insensitively, with ``*`` and ``?`` as wildcards.

What is listed is the caller's ``ListingPolicy``; this module scans, counts and prints. Files are read as
UTF-8, and folders are listed as ``Get-ChildItem`` lists them: hidden entries left out, names in
case-insensitive order, files before the subfolders they sit beside, no symbolic link or junction entered.
"""

from __future__ import annotations

import argparse
import contextlib
import fnmatch
import io
import os
import re
import sys
import tempfile
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Final

from datrix_scripts.cleanup_utils import child_dirs, children, is_link
from datrix_scripts.framework_repos import workspace_package_dirs
from datrix_scripts.gate_harness import WRAPPER_DEBUG_FLAG, write_files
from datrix_scripts.paths import WORKSPACE_DIR
from datrix_scripts.task_metadata import format_phase
from datrix_scripts.tasks.complete import COMPLETED_PREFIX

ROOT_PROJECT: Final = "(root)"
TASKS_FOLDER: Final = ".tasks"
BUGS_FOLDER: Final = ".bugs"
TASK_FILE_PATTERN: Final = "task-*.md"
PHASE_FOLDER_PATTERN: Final = "phase-*"
DEPENDENCIES_FILE: Final = "dependencies.md"
RULE: Final = "=" * 40
COMPLETED_HEADING: Final = re.compile(r"^COMPLETED:\s+", re.IGNORECASE)
EXIT_LISTED: Final = 0
# A base directory that does not exist (or a failed self-test check).
EXIT_FAILED: Final = 1
_HEADING: Final = re.compile(r"^#+\s+(.+)$")
_LINE_BREAK: Final = re.compile(r"\r?\n")


@dataclass(frozen=True)
class ListedItem:
    """A task or bug file that is listed: where it is, its title, and what is wrong with the title."""

    path: Path
    title: str
    warning: str = ""


@dataclass(frozen=True)
class PhaseCounts:
    """How many task files of a phase folder carry a heading, and how many of those are completed."""

    total: int
    completed: int


@dataclass(frozen=True)
class PhaseEntry:
    """A phase folder's ``dependencies.md`` that is listed, with the count the listing reports out of the total."""

    folder: str
    path: Path
    count: int
    total: int


@dataclass(frozen=True)
class PhaseContext:
    """One phase folder holding a ``dependencies.md``: its counts, whether they came from the other
    repositories, every ``.tasks`` root, and the filter."""

    folder: Path
    dependencies: Path
    counts: PhaseCounts
    fallback: bool
    roots: tuple[Path, ...]
    pattern: str


@dataclass
class ProjectListing:
    """The listed tasks and phase folders of one repository (or of the root)."""

    project: str
    tasks: list[ListedItem] = field(default_factory=list)
    phases: list[PhaseEntry] = field(default_factory=list)


@dataclass(frozen=True)
class ListingWords:
    """What a listing calls its sections, counts and totals."""

    tasks_heading: str
    bugs_heading: str
    phase_label: str
    none_found: str
    task_noun: str
    bug_noun: str
    item_noun: str


@dataclass(frozen=True)
class ListingPolicy:
    """Which task files, phase folders and bug headings a listing keeps."""

    select_task: Callable[[Path, str, str], ListedItem | None]
    select_phase: Callable[[PhaseContext], PhaseEntry | None]
    bug_heading: re.Pattern[str]
    words: ListingWords


@dataclass
class Listing:
    """What a scan kept, project by project."""

    tasks: list[ProjectListing] = field(default_factory=list)
    bugs: list[tuple[str, list[ListedItem]]] = field(default_factory=list)

    def task_count(self) -> int:
        return sum(len(listing.tasks) for listing in self.tasks)

    def bug_count(self) -> int:
        return sum(len(bugs) for _, bugs in self.bugs)


def first_heading(text: str) -> str | None:
    """The text of the first Markdown heading in *text*, or None when there is none."""
    if not text.strip():
        return None
    for line in _LINE_BREAK.split(text):
        match = _HEADING.match(line.strip())
        if match:
            return match.group(1).strip()
    return None


def read_text(path: Path) -> str:
    """*path* as UTF-8 (a byte-order mark dropped, an undecodable byte replaced)."""
    return path.read_text(encoding="utf-8-sig", errors="replace")


def matches_filter(name: str, title: str, pattern: str) -> bool:
    """True when *pattern* is empty, or the file name or title contains it (case-insensitive)."""
    if not pattern.strip():
        return True
    wildcard = f"*{pattern.casefold()}*"
    return fnmatch.fnmatchcase(name.casefold(), wildcard) or fnmatch.fnmatchcase(title.casefold(), wildcard)


def _named(entry: Path, pattern: str) -> bool:
    return fnmatch.fnmatchcase(entry.name.casefold(), pattern)


def files_named(folder: Path, patterns: tuple[str, ...]) -> list[Path]:
    """Every file at any depth of *folder* whose name matches one of *patterns* (lower-case wildcards,
    matched case-insensitively): a folder's files, then each subfolder's in turn."""
    entries = children(folder, include_hidden=False)
    found = [entry for entry in entries
             if entry.is_file() and any(_named(entry, pattern) for pattern in patterns)]
    for entry in entries:
        if entry.is_dir() and not is_link(entry):
            found.extend(files_named(entry, patterns))
    return found


def task_files(folder: Path) -> list[Path]:
    """Every ``task-*.md`` file at any depth of *folder*: a folder's files, then each subfolder's in turn."""
    return files_named(folder, (TASK_FILE_PATTERN,))


def phase_folders(tasks_root: Path) -> list[Path]:
    """The ``phase-*`` folders directly under *tasks_root*."""
    return [entry for entry in child_dirs(tasks_root, include_hidden=False) if _named(entry, PHASE_FOLDER_PATTERN)]


def headings(folders: list[Path]) -> list[tuple[Path, str]]:
    """``(task file, its first heading)`` for each task file of *folders* that can be read and has a heading."""
    found: list[tuple[Path, str]] = []
    for folder in folders:
        for path in task_files(folder):
            try:
                heading = first_heading(read_text(path))
            except OSError:
                continue
            if heading is not None:
                found.append((path, heading))
    return found


def phase_counts(folder: Path) -> PhaseCounts:
    """The task files of *folder* that carry a heading, and how many of them are completed."""
    found = headings([folder])
    return PhaseCounts(len(found), sum(1 for _, heading in found if COMPLETED_HEADING.match(heading)))


def phase_status_index(roots: list[Path]) -> dict[str, PhaseCounts]:
    """Phase folder name (case-insensitive) -> the counts summed over that phase's folder in every root."""
    index: dict[str, PhaseCounts] = {}
    for root in roots:
        for folder in phase_folders(root):
            key = folder.name.casefold()
            counts = phase_counts(folder)
            known = index.setdefault(key, PhaseCounts(0, 0))
            index[key] = PhaseCounts(known.total + counts.total, known.completed + counts.completed)
    return index


def projects(base: Path) -> list[tuple[str, Path]]:
    """``(name, folder)`` of the root and of every repository whose ``.tasks``/``.bugs`` are read."""
    return [(ROOT_PROJECT, base)] + [(repo.name, repo) for repo in workspace_package_dirs(base, include_showcase=True)]


def tasks_roots(base: Path) -> list[Path]:
    """The ``.tasks`` folder of the root and of every repository, present or not."""
    return [folder / TASKS_FOLDER for _, folder in projects(base)]


def _select_tasks(folder: Path, pattern: str, policy: ListingPolicy) -> list[ListedItem]:
    kept: list[ListedItem] = []
    for path in task_files(folder):
        try:
            text = read_text(path)
        except OSError as exc:
            print(f" Warning: Could not read {path.name}: {exc}")
            continue
        item = policy.select_task(path, text, pattern)
        if item is not None:
            kept.append(item)
    return kept


def _select_phases(folder: Path, roots: tuple[Path, ...], index: dict[str, PhaseCounts], pattern: str,
                   policy: ListingPolicy) -> list[PhaseEntry]:
    kept: list[PhaseEntry] = []
    for phase in phase_folders(folder):
        dependencies = phase / DEPENDENCIES_FILE
        if not dependencies.exists():
            continue
        counts = phase_counts(phase)
        fallback = counts.total == 0 and phase.name.casefold() in index
        if fallback:
            counts = index[phase.name.casefold()]
        entry = policy.select_phase(PhaseContext(phase, dependencies, counts, fallback, roots, pattern))
        if entry is not None:
            kept.append(entry)
    return kept


def _select_bugs(folder: Path, pattern: str, policy: ListingPolicy) -> list[ListedItem]:
    kept: list[ListedItem] = []
    for path in task_files(folder):
        try:
            heading = first_heading(read_text(path))
        except OSError as exc:
            print(f" Warning: Could not read {path.name}: {exc}")
            continue
        if heading is not None and policy.bug_heading.match(heading) and matches_filter(path.name, heading, pattern):
            kept.append(ListedItem(path, heading))
    return kept


def scan(base: Path, pattern: str, policy: ListingPolicy) -> Listing:
    """What *policy* keeps of the tasks, phase folders and bugs under *base*."""
    roots = tuple(tasks_roots(base))
    index = phase_status_index(list(roots))
    listing = Listing()
    for name, folder in projects(base):
        tasks = _select_tasks(folder / TASKS_FOLDER, pattern, policy)
        phases = _select_phases(folder / TASKS_FOLDER, roots, index, pattern, policy)
        if tasks or phases:
            listing.tasks.append(ProjectListing(name, tasks, phases))
        bugs = _select_bugs(folder / BUGS_FOLDER, pattern, policy)
        if bugs:
            listing.bugs.append((name, bugs))
    return listing


def _section(heading: str) -> list[str]:
    return [RULE, heading, RULE, ""]


def _task_lines(listing: Listing, words: ListingWords) -> list[str]:
    if not listing.tasks:
        return []
    lines = _section(words.tasks_heading)
    for project in listing.tasks:
        lines.append(f"=== {project.project} ===")
        for phase in project.phases:
            lines += [f"   {phase.path}", f"   Phase: {phase.folder} | {words.phase_label}: {phase.count}/{phase.total}"]
        if project.phases and project.tasks:
            lines.append("")
        for task in project.tasks:
            lines += [f"   {task.path}", f"   Title: {task.title}"]
            if task.warning:
                lines.append(f"   Warning: {task.warning}")
        lines.append("")
    return lines


def _bug_lines(listing: Listing, words: ListingWords) -> list[str]:
    if not listing.bugs:
        return []
    lines = _section(words.bugs_heading)
    for project, bugs in listing.bugs:
        lines.append(f"=== {project} ===")
        for bug in bugs:
            lines += [f" {bug.path}", f" Title: {bug.title}"]
        lines.append("")
    return lines


def _summary_lines(listing: Listing, words: ListingWords) -> list[str]:
    tasks, bugs = listing.task_count(), listing.bug_count()
    lines = [RULE]
    if tasks == 0 and bugs == 0:
        lines.append(words.none_found)
    if tasks:
        lines.append(f"Total: {tasks} {words.task_noun} across {len(listing.tasks)} project(s)")
    if bugs:
        lines.append(f"Total: {bugs} {words.bug_noun} across {len(listing.bugs)} project(s)")
    if tasks and bugs:
        lines.append(f"Grand Total: {tasks + bugs} {words.item_noun}")
    return [*lines, RULE, ""]


def render(listing: Listing, words: ListingWords) -> list[str]:
    """The lines a listing prints: its tasks section, its bugs section, then the totals."""
    return [*_task_lines(listing, words), *_bug_lines(listing, words), *_summary_lines(listing, words)]


def listing_parser(description: str) -> argparse.ArgumentParser:
    """The options of ``tasks/todo.ps1`` and ``tasks/completed.ps1``: one per wrapper parameter, spelled exactly."""
    parser = argparse.ArgumentParser(description=description, allow_abbrev=False)
    parser.add_argument("--base-dir", default=None,
                        help="Workspace root holding .tasks, .bugs and the datrix* repos (default: this workspace)")
    parser.add_argument("--filter", default="",
                        help="Only items whose file name or title contains this text (case-insensitive)")
    parser.add_argument(WRAPPER_DEBUG_FLAG, dest="debug", action="store_true", help="Enable debug logging")
    parser.add_argument("--self-test", action="store_true", help="Run only the self-test over a planted workspace.")
    return parser


class MissingBaseDirError(Exception):
    """``--base-dir`` names no directory."""


def listing_base(args: argparse.Namespace) -> Path:
    """``--base-dir`` as an absolute path (this workspace when it is not given); ``MissingBaseDirError`` when it
    is not a directory."""
    chosen = Path(os.path.abspath(args.base_dir)) if args.base_dir else WORKSPACE_DIR
    if not chosen.is_dir():
        raise MissingBaseDirError(f"Base directory does not exist: {chosen}. Pass -BaseDir <workspace root>.")
    return chosen


def run_on_base(args: argparse.Namespace, action: Callable[[Path], int]) -> int:
    """*action*'s exit code on the base directory ``listing_base`` reads from *args*; exit 1, with the error
    printed, when that is not a directory."""
    try:
        base = listing_base(args)
    except MissingBaseDirError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return EXIT_FAILED
    return action(base)


def printed_lines(report: Callable[[Path, str], int], base: Path, pattern: str) -> list[str]:
    """What *report* prints for *base* and *pattern*, line by line."""
    output = io.StringIO()
    with contextlib.redirect_stdout(output):
        report(base, pattern)
    return output.getvalue().splitlines()


def missing_base_dir_check(main: Callable[[Sequence[str] | None], int]) -> Callable[[], None]:
    """The self-test check that a listing's ``main`` refuses a base directory that does not exist, with exit 1."""

    def _check_a_missing_base_dir_fails() -> None:
        with tempfile.TemporaryDirectory() as raw:
            refused = io.StringIO()
            with contextlib.redirect_stderr(refused):
                exit_code = main([f"--base-dir={Path(raw) / 'absent'}"])
        assert exit_code == EXIT_FAILED and "Base directory does not exist" in refused.getvalue(), refused.getvalue()

    return _check_a_missing_base_dir_fails


def same_folder(first: Path, second: Path) -> bool:
    """True when the two paths name the same folder, compared as Windows compares paths."""
    return os.path.normcase(os.path.abspath(first)) == os.path.normcase(os.path.abspath(second))


# The workspace the self-tests of todo and completed read. Phase 1 of the root has only a dependencies.md, so its
# counts come from datrix-alpha's phase 1. datrix-alpha holds an open task, a completed one, a task with a
# malformed title, an empty one and one with no heading, and a fixed and an open bug; datrix-beta's phase 2 is complete and listed by
# its dependencies.md. A stray .tasks folder sits inside a source folder.
LISTED_PHASE: Final = 1
DONE_PHASE: Final = 2


def planted_name(phase: int, number: int, slug: str) -> str:
    """The file name of task *number* of *phase*."""
    return f"task-{format_phase(phase)}-{number:02d}-{slug}.md"


def planted_folder(repo: str, phase: int) -> str:
    """The phase folder of *repo* (``""`` for the root), relative to the workspace."""
    tasks = f"{repo}/{TASKS_FOLDER}" if repo else TASKS_FOLDER
    return f"{tasks}/phase-{format_phase(phase)}"


def planted_title(phase: int, number: int, title: str, *, completed: bool = False) -> str:
    """The heading of a planted task."""
    return f"{COMPLETED_PREFIX if completed else ''}Task {format_phase(phase)}-{number:02d}: {title}"


def plant_listing_workspace(root: Path) -> Path:
    """Write the workspace the listing self-tests read (see above) under *root*; returns *root*."""
    alpha = planted_folder("datrix-alpha", LISTED_PHASE)
    beta = planted_folder("datrix-beta", DONE_PHASE)
    write_files(root, {
        f"{planted_folder('', LISTED_PHASE)}/{DEPENDENCIES_FILE}": "{}\n",
        f"{alpha}/{planted_name(LISTED_PHASE, 1, 'open')}": f"# {planted_title(LISTED_PHASE, 1, 'Open work')}\n",
        f"{alpha}/{planted_name(LISTED_PHASE, 2, 'done')}":
            f"# {planted_title(LISTED_PHASE, 2, 'Done work', completed=True)}\n",
        f"{alpha}/{planted_name(LISTED_PHASE, 3, 'odd')}": "Intro.\n\n## Odd heading\n",
        f"{alpha}/{planted_name(LISTED_PHASE, 4, 'empty')}": "  \n",
        f"{alpha}/{planted_name(LISTED_PHASE, 5, 'bare')}": "Text with no heading.\n",
        f"datrix-alpha/{BUGS_FOLDER}/{planted_name(LISTED_PHASE, 1, 'crash')}": "# Bug 1: crash on start\n",
        f"datrix-alpha/{BUGS_FOLDER}/{planted_name(LISTED_PHASE, 2, 'leak')}": "# FIXED: Bug leak\n",
        f"{beta}/{DEPENDENCIES_FILE}": "{}\n",
        f"{beta}/{planted_name(DONE_PHASE, 1, 'final')}":
            f"# {planted_title(DONE_PHASE, 1, 'Final step', completed=True)}\n",
        f"datrix-beta/src/{TASKS_FOLDER}/notes.md": "stray\n",
    })
    return root
