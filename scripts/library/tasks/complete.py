#!/usr/bin/env python3
"""Mark a task markdown file as completed.

This script updates the first markdown heading in a task file from:

    # Task ...

(or any status-prefixed variant like `# IN_PROGRESS: Task ...`)

to:

    # COMPLETED: Task ...
"""

from __future__ import annotations

import argparse
import logging
import re
import sys
from pathlib import Path

# Allow imports from scripts/library/shared
library_dir = Path(__file__).resolve().parent.parent
if str(library_dir) not in sys.path:
    sys.path.insert(0, str(library_dir))

from shared.venv import get_datrix_root

logger = logging.getLogger(__name__)

HEADING_PATTERN = re.compile(r"^(?P<prefix>#+\s+)(?P<title>.+?)\s*$")
TASK_TITLE_PATTERN = re.compile(r"^(?:[A-Z][A-Z0-9_-]*:\s+)?Task\s+.+$")
COMPLETED_TITLE_PATTERN = re.compile(r"^COMPLETED:\s+Task\s+.+$")
STRIP_STATUS_PATTERN = re.compile(r"^(?:[A-Z][A-Z0-9_-]*:\s+)?(Task\s+.+)$")


def _iter_task_files(datrix_root: Path) -> list[Path]:
    files: list[Path] = []

    root_tasks = datrix_root / ".tasks"
    if root_tasks.is_dir():
        files.extend(root_tasks.rglob("*.md"))

    for child in datrix_root.iterdir():
        if not child.is_dir() or not child.name.startswith("datrix"):
            continue
        tasks_dir = child / ".tasks"
        if tasks_dir.is_dir():
            files.extend(tasks_dir.rglob("*.md"))

    return files


def _resolve_task_path(task_arg: str, datrix_root: Path) -> Path:
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
        sanitized = line.lstrip("\ufeff").strip()
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

    return f"COMPLETED: {task_only_match.group(1)}", True


def mark_task_complete(task_path: Path) -> bool:
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


def main() -> int:
    parser = argparse.ArgumentParser(description="Mark a task markdown file as completed")
    parser.add_argument("task_file", help="Task file path (absolute, relative, or task filename)")
    parser.add_argument("--debug", action="store_true", help="Enable debug logging")
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.DEBUG if args.debug else logging.INFO,
        format="%(levelname)s: %(message)s",
    )

    try:
        datrix_root = get_datrix_root()
    except FileNotFoundError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1

    try:
        task_path = _resolve_task_path(args.task_file, datrix_root)
        logger.debug("Resolved task path: %s", task_path)
        mark_task_complete(task_path)
        return 0
    except (FileNotFoundError, ValueError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    except OSError as exc:
        print(f"ERROR: Failed to update task file: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())

