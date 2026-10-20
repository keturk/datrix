"""Mark a task markdown file as completed: the module behind ``scripts/tasks/complete.ps1`` (and its ``.sh`` twin).

It updates the first markdown heading in a task file from:

    # Task ...

(or any status-prefixed variant like `# IN_PROGRESS: Task ...`)

to:

    # COMPLETED: Task ...

It is the one way a task's status heading changes: the edit hooks refuse a Write/Edit that adds a
``COMPLETED:`` heading to a task file. The task reference resolves to exactly one file (an absolute
path, a path relative to the current directory or the workspace, else a unique file name or path
suffix under a ``.tasks`` folder), and its first heading must be a task title (``Task ...`` or
``<STATUS>: Task ...``); anything else is refused and the file is left as it was.

Exit codes: 0 = marked or already completed; 1 = not found, ambiguous, not a task title or not
writable; 2 = usage error.

Usage:
    python -m datrix_scripts.tasks.complete --task-file <path-or-name> [--dbg]
"""

from __future__ import annotations

import argparse
import logging
import re
import sys
import tempfile
from collections.abc import Sequence
from pathlib import Path
from typing import Final

from datrix_scripts.framework_repos import workspace_package_dirs
from datrix_scripts.gate_harness import WRAPPER_DEBUG_FLAG, UsageError, expect_usage_error, write_files
from datrix_scripts.paths import WORKSPACE_DIR
from datrix_scripts.test.wrappers import TASKS_SCRIPTS_DIR, module_main, run_self_test

logger = logging.getLogger(__name__)

MODULE: Final = "datrix_scripts.tasks.complete"
WRAPPER: Final = "complete"
EXIT_OK: Final = 0
EXIT_FAILED: Final = 1

HEADING_PATTERN = re.compile(r"^(?P<prefix>#+\s+)(?P<title>.+?)\s*$")
TASK_TITLE_PATTERN = re.compile(r"^(?:[A-Z][A-Z0-9_-]*:\s+)?Task\s+.+$")
COMPLETED_TITLE_PATTERN = re.compile(r"^COMPLETED:\s+Task\s+.+$")
STRIP_STATUS_PATTERN = re.compile(r"^(?:[A-Z][A-Z0-9_-]*:\s+)?(Task\s+.+)$")
COMPLETED_PREFIX: Final = "COMPLETED: "


def _iter_task_files(datrix_root: Path) -> list[Path]:
    files: list[Path] = []

    root_tasks = datrix_root / ".tasks"
    if root_tasks.is_dir():
        files.extend(root_tasks.rglob("*.md"))

    for child in workspace_package_dirs(datrix_root, include_showcase=True):
        tasks_dir = child / ".tasks"
        if tasks_dir.is_dir():
            files.extend(tasks_dir.rglob("*.md"))

    return files


def resolve_task_path(task_arg: str, datrix_root: Path) -> Path:
    """The one task file *task_arg* names; ``FileNotFoundError`` when none, ``ValueError`` when several."""
    raw_path = Path(task_arg)

    direct_candidates: list[Path] = []
    if raw_path.is_absolute():
        direct_candidates.append(raw_path)
    else:
        direct_candidates.append((Path.cwd() / raw_path).resolve())
        direct_candidates.append((datrix_root / raw_path).resolve())

    for candidate in direct_candidates:
        if candidate.is_file():
            return candidate

    needle = task_arg.replace("\\", "/").lstrip("./").lower()
    name_needle = Path(task_arg).name.lower()

    matches: list[Path] = []
    for task_file in _iter_task_files(datrix_root):
        rel = task_file.relative_to(datrix_root).as_posix().lower()
        if task_file.name.lower() == name_needle or rel.endswith(needle):
            matches.append(task_file)

    if not matches:
        raise FileNotFoundError(f"Task file not found: {task_arg}")

    if len(matches) > 1:
        formatted = "\n".join(f"  - {path}" for path in sorted(matches))
        raise ValueError(
            "Task reference is ambiguous. Use a more specific path:\n" + formatted
        )

    return matches[0]


def _find_first_heading(lines: list[str]) -> tuple[int, str, str]:
    for index, line in enumerate(lines):
        sanitized = line.lstrip("\N{ZERO WIDTH NO-BREAK SPACE}").strip()
        match = HEADING_PATTERN.match(sanitized)
        if match:
            return index, match.group("prefix"), match.group("title").strip()
    raise ValueError("No markdown heading found in task file")


def _mark_heading_completed(title: str) -> tuple[str, bool]:
    if COMPLETED_TITLE_PATTERN.match(title):
        return title, False

    if not TASK_TITLE_PATTERN.match(title):
        raise ValueError(
            "First heading is not a task title. Expected 'Task ...' or '<STATUS>: Task ...'."
        )

    task_only_match = STRIP_STATUS_PATTERN.match(title)
    if task_only_match is None:
        raise ValueError("Could not normalize task title")

    return f"{COMPLETED_PREFIX}{task_only_match.group(1)}", True


def mark_task_complete(task_path: Path) -> bool:
    """Rewrite the first heading of *task_path* to ``COMPLETED: Task ...``; False when it already was."""
    content = task_path.read_text(encoding="utf-8")
    lines = content.splitlines()

    heading_index, heading_prefix, heading_title = _find_first_heading(lines)
    new_title, changed = _mark_heading_completed(heading_title)

    if not changed:
        print(f"Already completed: {task_path}")
        return False

    lines[heading_index] = f"{heading_prefix}{new_title}"

    # Preserve trailing newline if present in the original file.
    rewritten = "\n".join(lines)
    if content.endswith("\n"):
        rewritten += "\n"

    task_path.write_text(rewritten, encoding="utf-8")
    print(f"Marked completed: {task_path}")
    print(f"Title: {new_title}")
    return True


def complete(task_arg: str, datrix_root: Path) -> int:
    """Resolve *task_arg* under *datrix_root* and mark it completed; the exit code."""
    try:
        task_path = resolve_task_path(task_arg, datrix_root)
        logger.debug("Resolved task path: %s", task_path)
        mark_task_complete(task_path)
        return EXIT_OK
    except (FileNotFoundError, ValueError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return EXIT_FAILED
    except OSError as exc:
        print(f"ERROR: Failed to update task file: {exc}", file=sys.stderr)
        return EXIT_FAILED


def build_parser() -> argparse.ArgumentParser:
    """The options of ``tasks/complete.ps1``: one per wrapper parameter, spelled exactly."""
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter, allow_abbrev=False
    )
    parser.add_argument("--task-file", help="Task file path (absolute, relative, or task filename); required.")
    parser.add_argument(WRAPPER_DEBUG_FLAG, dest="debug", action="store_true", help="Debug logging.")
    parser.add_argument("--self-test", action="store_true",
                        help="Run only the self-test: planted task files are marked, refused or found.")
    return parser


def _task_file(args: argparse.Namespace) -> str:
    if not args.task_file:
        raise UsageError("-TaskFile is required: pass the task file's path or its file name, e.g. "
                         "complete.ps1 <workspace>\\datrix-cli\\.tasks\\<phase folder>\\<task file>.md.")
    return str(args.task_file)


# ---------------------------------------------------------------------------
# Self-test: planted task files in a temporary workspace.
# ---------------------------------------------------------------------------

_PHASE: Final = 1
_BYTE_ORDER_MARK: Final = "\N{ZERO WIDTH NO-BREAK SPACE}"


def _title(number: int, name: str, phase: int = _PHASE) -> str:
    return f"Task {phase:02d}-{number:02d}: {name}"


def _task_path(repo: str, number: int, slug: str, phase: int = _PHASE) -> str:
    return f"{repo}/.tasks/phase-{phase:02d}/task-{phase:02d}-{number:02d}-{slug}.md"


def _planted(root: Path) -> None:
    write_files(root, {
        _task_path("datrix-alpha", 1, "open"): f"# {_title(1, 'Open')}\n\nBody line.\n",
        _task_path("datrix-alpha", 2, "progress"): f"# IN_PROGRESS: {_title(2, 'Progress')}\n\nBody.",
        _task_path("datrix-alpha", 3, "notes"): f"# Notes about the phase\n\n# {_title(3, 'Later heading')}\n",
        _task_path("datrix-beta", 1, "open"): f"# {_title(1, 'Same name in another repository')}\n",
        _task_path("datrix-beta", 1, "unique", phase=2): f"# {_title(1, 'Unique', phase=2)}\n",
        _task_path("datrix-alpha", 4, "bom"): f"{_BYTE_ORDER_MARK}# {_title(4, 'Saved with a byte-order mark')}\n",
    })


def _check_task_headings_are_marked_and_nothing_else_changes() -> None:
    with tempfile.TemporaryDirectory() as raw:
        root = Path(raw)
        _planted(root)
        opened_path = root / _task_path("datrix-alpha", 1, "open")
        progressed_path = root / _task_path("datrix-alpha", 2, "progress")
        assert mark_task_complete(opened_path)
        assert mark_task_complete(progressed_path)
        opened = opened_path.read_text(encoding="utf-8")
        progressed = progressed_path.read_text(encoding="utf-8")
        again = mark_task_complete(opened_path)
        bom_path = root / _task_path("datrix-alpha", 4, "bom")
        assert mark_task_complete(bom_path), "a heading after a byte-order mark is a task title"
        bom_heading = bom_path.read_text(encoding="utf-8").lstrip(_BYTE_ORDER_MARK).splitlines()[0]
    assert opened == f"# {COMPLETED_PREFIX}{_title(1, 'Open')}\n\nBody line.\n", repr(opened)
    assert bom_heading == f"# {COMPLETED_PREFIX}{_title(4, 'Saved with a byte-order mark')}", repr(bom_heading)
    assert progressed == f"# {COMPLETED_PREFIX}{_title(2, 'Progress')}\n\nBody.", \
        "a status prefix is replaced and no trailing newline is added"
    assert not again, "a completed task is reported as already completed"


def _check_a_heading_that_is_not_a_task_title_is_refused() -> None:
    with tempfile.TemporaryDirectory() as raw:
        root = Path(raw)
        _planted(root)
        notes = root / _task_path("datrix-alpha", 3, "notes")
        before = notes.read_text(encoding="utf-8")
        try:
            mark_task_complete(notes)
        except ValueError as exc:
            refused = "not a task title" in str(exc)
        else:
            refused = False
        after = notes.read_text(encoding="utf-8")
    assert refused, "a first heading that is not a task title must be refused"
    assert before == after, "a refused task file was changed"


def _check_a_reference_resolves_to_exactly_one_task() -> None:
    with tempfile.TemporaryDirectory() as raw:
        root = Path(raw)
        _planted(root)
        unique = _task_path("datrix-beta", 1, "unique", phase=2)
        shared = _task_path("datrix-beta", 1, "open")
        found = resolve_task_path(Path(unique).name, root)
        suffix = resolve_task_path(shared, root)
        outcomes: list[str] = []
        for reference in (Path(shared).name, "no-such-task-file.md"):
            try:
                resolve_task_path(reference, root)
            except ValueError as exc:
                outcomes.append("ambiguous" if "ambiguous" in str(exc) else str(exc))
            except FileNotFoundError:
                outcomes.append("missing")
        exit_code = complete("no-such-task-file.md", root)
    assert found == root / unique, found
    assert suffix == root / shared, suffix
    assert outcomes == ["ambiguous", "missing"], outcomes
    assert exit_code == EXIT_FAILED, exit_code


def _check_no_task_file_is_a_usage_error() -> None:
    expect_usage_error(lambda: _task_file(build_parser().parse_args([])), "-TaskFile is required")


_SELF_TEST_CHECKS: Final = (
    _check_task_headings_are_marked_and_nothing_else_changes,
    _check_a_heading_that_is_not_a_task_title_is_refused,
    _check_a_reference_resolves_to_exactly_one_task,
    _check_no_task_file_is_a_usage_error,
)


def _run(args: argparse.Namespace) -> int:
    if args.self_test:
        return run_self_test(_SELF_TEST_CHECKS, wrapper=WRAPPER, module=MODULE, parser=build_parser(),
                             folder=TASKS_SCRIPTS_DIR)
    return complete(_task_file(args), WORKSPACE_DIR)


def main(argv: Sequence[str] | None = None) -> int:
    """Entry point."""
    return module_main(build_parser(), _run, argv)


if __name__ == "__main__":
    sys.exit(main())
