#!/usr/bin/env python3
"""Give a task written before the ``## Orientation`` block existed one, without a writer and without a model.

A task's "Files to Review Before Starting" list used to be read file by file, whole, by its
implementer; 57% of the source and test tokens implementing agents read were on files they never
edited. The block moves those reads to the harness (``tasks.task_orientation``). New tasks are
written with it. This converts the ones that exist, deterministically:

* a Python file in the review list that the task does not edit becomes an ``outline:`` entry -- the
  definitions with line ranges and the module summary, exact -- and its line leaves the list, so the
  agent is no longer told to read it whole;
* a function a citation names (``foo.py:12`` ``name(...)``) whose definition is unique in the tree and in a
  file the task does not edit becomes a ``symbol:`` entry.

It touches nothing else: not the task's scope, numbering, dependencies, design content, success criteria.
It leaves a task alone when it is a quality gate (reading the code is the job), already has a block, has
no review list, or has nothing it can convert, and it converts an entry only when the entry resolves in
the code index -- and writes the result only if the rewritten task parses and every entry in it resolves.
It does NOT write ``refs:`` or ``explain:`` entries: which callers matter, and which question about a
test's style, are a writer's judgment.

Dry run by default. ``--apply`` writes, after copying each original to
``<workspace>/.tmp/retrofit-orientation/<stamp>/``. Idempotent: a converted task has a block and is skipped.

Usage:
    retrofit_orientation.py --phase 61 [--apply] [--base-dir D:\\datrix]
    retrofit_orientation.py <task.md> [<task.md> ...] [--apply]

Exit codes: 0 done, 2 usage error.
"""

from __future__ import annotations

import argparse
import re
import sys
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

_library_dir = Path(__file__).resolve().parent.parent
if str(_library_dir) not in sys.path:
    sys.path.insert(0, str(_library_dir))

from code_index.session import IndexSession, open_session  # noqa: E402
from code_index.sources import CodeIndexError  # noqa: E402
from shared.venv import get_datrix_root  # noqa: E402
from tasks.task_citations import cited_identifiers  # noqa: E402
from tasks.task_metadata import (  # noqa: E402
    discover_phase_task_files,
    is_list_item,
    line_path_tokens,
    parse_task_file,
    parse_task_text,
    task_prose_lines,
    task_sections,
)
from tasks.task_orientation import (  # noqa: E402
    KIND_OUTLINE,
    KIND_SYMBOL,
    MAX_ITEMS,
    OrientationItem,
    parse_orientation,
    resolve_fact,
)

OUTCOME_CONVERTED = "converted"
OUTCOME_SKIPPED = "skipped"
MAX_OUTLINES = 8
MAX_SYMBOLS = 4
BACKUP_DIR = (".tmp", "retrofit-orientation")
_SECTION_REVIEW = "files to review"
_NUMBERED_ITEM = re.compile(r"^(\d+)\.(\s)")
# A line range on a review item: "(lines 110-135)", "lines 1-20, 40-60", "`file.py:113-131`", "L200".
_RANGED = re.compile(r"\blines?\s+~?\d|\.\w{1,6}:\d|\bL\d+\b", re.IGNORECASE)
# The block is injected whole up to MAX_TOTAL_CHARS (16,000); stay well inside it so no entry is clipped.
MAX_ANSWER_CHARS = 12000
POINTER = ("The callers, the definitions and the files read only to understand are not listed here: they are in "
           "`## Orientation` below, answered for you when you read this file.")


@dataclass(frozen=True)
class RetrofitResult:
    task: Path
    outcome: str
    reason: str = ""
    outlines: tuple[str, ...] = ()
    symbols: tuple[str, ...] = ()
    removed_lines: int = 0
    source_bytes: int = 0
    answer_chars: int = 0
    new_bytes: bytes = b""

    def line(self) -> str:
        if self.outcome == OUTCOME_SKIPPED:
            return f"{self.task.name}: skipped ({self.reason})"
        return (f"{self.task.name}: {len(self.outlines)} outline(s), {len(self.symbols)} symbol(s); "
                f"{self.removed_lines} review line(s) removed; {self.source_bytes // 1024} KB of source the agent "
                f"was told to read -> {self.answer_chars // 1024} KB answered")


def _skipped(task: Path, reason: str) -> RetrofitResult:
    return RetrofitResult(task, OUTCOME_SKIPPED, reason)


def _absolute(token: str, workspace: Path, repo: Path) -> Path:
    text = token.replace("\\", "/")
    if re.match(r"^[A-Za-z]:/", text):
        return Path(text).resolve()
    for base in (repo, workspace):
        if (base / text).exists():
            return (base / text).resolve()
    return (repo / text).resolve()


def _review_candidates(
    lines: list[str], review: tuple[int, int], prose: set[int], edited: set[Path], workspace: Path, repo: Path
) -> list[tuple[int, Path]]:
    """(line index, file) for each review-list item that names exactly one Python file the task does not edit."""
    found: list[tuple[int, Path]] = []
    for index in range(*review):
        if index + 1 not in prose or not is_list_item(lines[index]):
            continue
        tokens = line_path_tokens(lines[index])
        if len(tokens) != 1 or _RANGED.search(lines[index]):
            continue  # a ranged item is a targeted read the writer chose: an outline would replace it with less
        path = _absolute(tokens[0], workspace, repo)
        if path.suffix == ".py" and path.is_file() and path not in edited:
            found.append((index, path))
    return found


def _renumbered(lines: list[str], start: int, end: int) -> list[str]:
    """Top-level numbered list items of ``lines[start:end]`` numbered 1..n again, after removals."""
    out, number = list(lines), 1
    for index in range(start, end):
        match = _NUMBERED_ITEM.match(out[index])
        if match is not None:
            out[index] = f"{number}.{match.group(2)}{out[index][match.end():]}"
            number += 1
    return out


def _block(entries: list[str]) -> list[str]:
    return ["", POINTER, "", "## Orientation", "", "```orientation", *entries, "```"]


def _symbol_entries(
    text: str, session: IndexSession, edited: set[Path], outlined: set[Path], workspace: Path, room: int,
    chars: int,
) -> list[tuple[str, str]]:
    """(entry, answer text) for names written beside citations whose definition is unique and not edited.

    At most ``room`` entries, and no more answer text than ``chars`` characters in all.
    """
    from code_index.queries import find_symbol

    entries: list[tuple[str, str]] = []
    seen: set[str] = set()
    for _, line in task_prose_lines(text):
        for name in cited_identifiers(line):
            if name in seen or len(entries) >= room:
                continue
            seen.add(name)
            hits = find_symbol(session.conn, name, None, 3).hits
            if len(hits) != 1:
                continue
            defined = (workspace / hits[0].path).resolve()
            if defined in edited or defined in outlined:
                continue
            answer = resolve_fact(session.conn, OrientationItem(KIND_SYMBOL, name, 0)).text
            if sum(len(text) for _, text in entries) + len(answer) > chars:
                continue
            entries.append((f"{KIND_SYMBOL}: {name}", answer))
    return entries


def convert(task: Path, workspace: Path, session: IndexSession) -> RetrofitResult:
    """Plan the retrofit of one task: the rewritten text, or why it is left alone."""
    try:
        meta = parse_task_file(task)
    except (ValueError, OSError) as exc:
        return _skipped(task, f"cannot parse: {exc}")
    if meta.orientation:
        return _skipped(task, "already has an Orientation block")
    if meta.is_quality_gate:
        return _skipped(task, "quality gate: reading the code is its job")
    raw = task.read_bytes().decode("utf-8")
    newline = "\r\n" if "\r\n" in raw else "\n"
    lines = raw.split(newline)
    review = next(((start, end) for name, start, end in task_sections(lines) if name.startswith(_SECTION_REVIEW)), None)
    if review is None:
        return _skipped(task, "no Files to Review section")
    repo = workspace / meta.repo
    edited = {_absolute(token, workspace, repo) for token in meta.files_to_create_modify}
    prose = {number for number, _ in task_prose_lines(raw)}
    outlines: list[tuple[int, Path, str]] = []
    answers: dict[Path, str] = {}
    used = 0
    for index, path in _review_candidates(lines, review, prose, edited, workspace, repo):
        relative = path.relative_to(workspace.resolve()).as_posix() if path.is_relative_to(workspace.resolve()) else ""
        resolved = resolve_fact(session.conn, OrientationItem(KIND_OUTLINE, relative, 0)) if relative else None
        if resolved is None or not resolved.resolved:
            continue
        if len(outlines) >= MAX_OUTLINES or used + len(resolved.text) > MAX_ANSWER_CHARS:
            continue  # this item stays in the review list, to be read as before
        outlines.append((index, path, relative))
        answers[path] = resolved.text
        used += len(resolved.text)
    symbols = _symbol_entries(raw, session, edited, {path for _, path, _ in outlines}, workspace,
                              min(MAX_SYMBOLS, MAX_ITEMS - len(outlines)), MAX_ANSWER_CHARS - used)
    if not outlines and not symbols:
        return _skipped(task, "nothing the index can answer instead of a file read")
    entries = [f"{KIND_OUTLINE}: {rel}" for _, _, rel in outlines] + [entry for entry, _ in symbols]
    removed = {index for index, _, _ in outlines}
    kept = [line for index, line in enumerate(lines) if index not in removed]
    start, end = review[0], review[1] - len(removed)
    kept = _renumbered(kept, start, end)
    last_content = max((i for i in range(start, end) if kept[i].strip()), default=start - 1)
    rewritten = kept[:last_content + 1] + _block(entries) + kept[last_content + 1:]
    new_bytes = newline.join(rewritten).encode("utf-8")
    problem = _check(task, new_bytes, entries, session)
    if problem:
        return _skipped(task, f"the rewrite did not validate ({problem})")
    return RetrofitResult(
        task, OUTCOME_CONVERTED, outlines=tuple(rel for _, _, rel in outlines), symbols=tuple(e for e, _ in symbols),
        removed_lines=len(removed), source_bytes=sum(path.stat().st_size for _, path, _ in outlines),
        answer_chars=sum(len(text) for text in answers.values()) + sum(len(text) for _, text in symbols),
        new_bytes=new_bytes)


# What a retrofit must leave exactly as it was: the task's scope, order and what proves it done.
_UNCHANGED_FIELDS = ("task_id", "title", "status", "package", "category", "depends_on", "design_reference",
                     "design_acceptance_property", "files_to_create_modify", "targeted_tests", "has_how_solved")


def _check(task: Path, new_bytes: bytes, entries: list[str], session: IndexSession) -> str:
    """Why the rewritten task is not good enough to write, or the empty string.

    The rewrite must parse, carry exactly the entries it was built with, have every one of them
    resolve in the index, and have changed nothing the task is scoped, ordered or proven by.
    """
    after = parse_task_text(task, new_bytes.decode("utf-8"))
    before = parse_task_file(task)
    if after.orientation != entries:
        return "the block does not read back as written"
    parsed = parse_orientation(after.orientation)
    if parsed.errors:
        return parsed.errors[0]
    for item in parsed.items:
        if not resolve_fact(session.conn, item).resolved:
            return f"'{item.label()}' does not resolve"
    changed = [name for name in _UNCHANGED_FIELDS if getattr(before, name) != getattr(after, name)]
    if changed:
        return f"it changed {', '.join(changed)}"
    return ""


def apply(result: RetrofitResult, workspace: Path, stamp: str) -> None:
    """Copy the original aside, then write the rewritten task."""
    original = result.task.read_bytes()
    backup = workspace.joinpath(*BACKUP_DIR, stamp, f"{result.task.parent.parent.parent.name}__{result.task.name}")
    backup.parent.mkdir(parents=True, exist_ok=True)
    backup.write_bytes(original)
    result.task.write_bytes(result.new_bytes)


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description="Retrofit an ## Orientation block onto existing tasks.")
    parser.add_argument("tasks", nargs="*", help="Task files to retrofit.")
    parser.add_argument("--phase", type=int, help="Retrofit every task of this phase, in every repository.")
    parser.add_argument("--base-dir", type=Path, default=None, help="The workspace root (default: this checkout's).")
    parser.add_argument("--apply", action="store_true", help="Write the rewritten tasks (default: a dry run).")
    args = parser.parse_args(argv)
    workspace = (args.base_dir or get_datrix_root()).resolve()
    files = [Path(path) for path in args.tasks]
    if args.phase is not None:
        files.extend(discover_phase_task_files(workspace, args.phase))
    if not files:
        print("Error: no task files. Pass task file paths, or --phase <NN>.", file=sys.stderr)
        return 2
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    converted = skipped = source = answered = 0
    try:
        session = open_session(workspace)
    except CodeIndexError as exc:
        print(f"Error: the code index could not be opened: {exc}", file=sys.stderr)
        return 2
    try:
        session.refresh()
        for task in sorted(files):
            result = convert(task, workspace, session)
            print(result.line())
            if result.outcome == OUTCOME_CONVERTED:
                converted += 1
                source += result.source_bytes
                answered += result.answer_chars
                if args.apply:
                    apply(result, workspace, stamp)
            else:
                skipped += 1
    finally:
        session.close()
    verb = "converted" if args.apply else "would convert"
    print(f"\n{len(files)} task(s): {verb} {converted}, skipped {skipped}. Source the agents were told to read: "
          f"~{source // 1024} KB; answered instead: ~{answered // 1024} KB."
          + ("" if args.apply else " Dry run: pass --apply to write."))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
