#!/usr/bin/env python3
"""Validate task files against the tree as it is now, before they are dispatched.

A task is written against the tree of one day and run days later, after other tasks have changed
the same files. This checks, deterministically and without a model:

* the ``## Orientation`` block parses, and every entry in it resolves: a ``symbol`` or ``refs`` the
  code index finds, an ``outline`` of a file that exists, an ``explain`` over files a local model may
  read (``tasks.task_orientation``);
* the task is not oversized (``TASK_WARN_LINES`` / ``TASK_ERROR_LINES``; a COMPLETED task is exempt) and
  the executor's record sections stay short;
* every ``path:line`` citation in the task's prose points at a file that exists and lines that are in
  it, and the identifiers quoted beside it are still near those lines (``tasks.task_citations``).

An error means the task's premise is stale or its orientation is wrong: fix the task (or the order
tasks run in) before an implementer spends tokens finding out. Warnings are citations whose
identifiers have probably moved.

Usage:
    validate_task.py <task.md> [<task.md> ...]
    validate_task.py --phase 61 [--strict] [--require-orientation] [--base-dir D:\\datrix]

Exit codes: 0 no errors (and, with --strict, no warnings), 1 errors found, 2 usage error.
"""

from __future__ import annotations

import argparse
import sys
from dataclasses import dataclass
from pathlib import Path

_library_dir = Path(__file__).resolve().parent.parent
if str(_library_dir) not in sys.path:
    sys.path.insert(0, str(_library_dir))

from code_index.session import IndexSession, open_session  # noqa: E402
from code_index.sources import CodeIndexError  # noqa: E402
from shared.framework_repos import framework_repos  # noqa: E402
from shared.local_reading import ReadScope, ReadScopeError  # noqa: E402
from shared.venv import get_datrix_root  # noqa: E402
from tasks.task_citations import LEVEL_ERROR, LEVEL_WARN, CitationContext, RepoFiles, check_citations  # noqa: E402
from tasks.task_metadata import (  # noqa: E402
    TaskMetadata,
    discover_phase_task_files,
    parse_task_file,
    task_id_phase,
)
from tasks.task_orientation import KIND_EXPLAIN, parse_orientation, resolve_fact  # noqa: E402

EXIT_OK = 0
EXIT_FINDINGS = 1
EXIT_USAGE = 2

# An implementer reads its whole task file before the first edit, so a task's length is a per-dispatch
# cost. Past the warn line the task should be a contract, not a transcript of the code; past the error
# line it must be split (one task per language or file group) before it is dispatched.
TASK_WARN_LINES = 600
TASK_ERROR_LINES = 1500
# The executor's own record. Details belong in the code, the tests and the commit, not in the task file
# the quality gate and orchestrator read again.
RECORD_SECTIONS = ("## Implementation Notes", "## How Solved")
RECORD_WARN_LINES = 60
COMPLETED_HEADING_PREFIX = "# COMPLETED"


@dataclass(frozen=True)
class Finding:
    level: str
    message: str

    def render(self) -> str:
        return f"  {self.level} {self.message}"


class Validator:
    """Validates tasks of one workspace; the code index and the repository file lists are opened once."""

    def __init__(self, workspace: Path, *, require_orientation: bool = False) -> None:
        self._workspace = workspace
        self._require_orientation = require_orientation
        self._scope = ReadScope(workspace)
        self._repo_files = RepoFiles()
        self._repos = tuple(framework_repos(workspace))
        self._creates_by_phase: dict[int, frozenset[Path]] = {}
        self._session: IndexSession | None = None

    def close(self) -> None:
        if self._session is not None:
            self._session.close()

    def _index(self) -> IndexSession:
        if self._session is None:
            self._session = open_session(self._workspace)
            self._session.refresh()
        return self._session

    def _orientation(self, meta: TaskMetadata) -> list[Finding]:
        if not meta.orientation:
            return [Finding(LEVEL_ERROR, "no '## Orientation' block (required by --require-orientation)")] \
                if self._require_orientation else []
        parsed = parse_orientation(meta.orientation)
        findings = [Finding(LEVEL_ERROR, error) for error in parsed.errors]
        for item in parsed.items:
            if item.kind == KIND_EXPLAIN:
                try:
                    self._scope.files(list(item.paths))
                except ReadScopeError as exc:
                    findings.append(Finding(LEVEL_ERROR, f"orientation line {item.line}: {exc}"))
                continue
            resolved = resolve_fact(self._index().conn, item)
            if not resolved.resolved:
                reason = resolved.text.splitlines()[0] if resolved.text else "no match"
                findings.append(Finding(LEVEL_ERROR, f"orientation line {item.line}: '{item.label()}' does not "
                                                     f"resolve against the tree as it is now ({reason})"))
        return findings

    def _phase_creates(self, phase: int) -> frozenset[Path]:
        """Every file any task of ``phase`` lists under its Files to Create / Modify: those may not exist yet."""
        if phase not in self._creates_by_phase:
            created: set[Path] = set()
            for sibling in discover_phase_task_files(self._workspace, phase):
                try:
                    tokens = parse_task_file(sibling).files_to_create_modify
                except (ValueError, OSError):
                    continue
                created.update(Path(token.replace("\\", "/")).resolve() for token in tokens)
            self._creates_by_phase[phase] = frozenset(created)
        return self._creates_by_phase[phase]

    def _citations(self, meta: TaskMetadata, text: str) -> list[Finding]:
        listed: dict[str, list[Path]] = {}
        for token in (*meta.files_to_review, *meta.files_to_create_modify):
            if "..." in token or "…" in token:
                continue  # an abbreviated path names no file
            path = Path(token.replace("\\", "/"))
            listed.setdefault(path.name, []).append(path)
        repo = self._workspace / meta.repo
        context = CitationContext(self._workspace, repo, listed, self._phase_creates(task_id_phase(meta.task_id)),
                                  self._repo_files, tuple(r for r in self._repos if r != repo))
        return [Finding(found.level, found.render().split(" ", 1)[1]) for found in check_citations(text, context)]

    def validate(self, task_path: Path) -> list[Finding]:
        try:
            meta = parse_task_file(task_path)
        except (ValueError, OSError) as exc:
            return [Finding(LEVEL_ERROR, f"cannot parse the task: {exc}")]
        text = task_path.read_text(encoding="utf-8")
        try:
            return [*task_size_findings(text), *self._orientation(meta), *self._citations(meta, text)]
        except CodeIndexError as exc:
            return [Finding(LEVEL_ERROR, f"the code index could not answer: {exc}")]


def record_section_lines(lines: list[str]) -> int:
    """Lines the executor's record sections (Implementation Notes, How Solved) occupy in the task."""
    total = 0
    in_record = False
    for line in lines:
        if line.startswith("## "):
            in_record = line.strip().startswith(RECORD_SECTIONS)
        if in_record:
            total += 1
    return total


def task_size_findings(text: str) -> list[Finding]:
    """Size findings for one task: its length (open tasks only) and the length of the executor's record."""
    lines = text.splitlines()
    findings: list[Finding] = []
    completed = any(line.startswith(COMPLETED_HEADING_PREFIX) for line in lines[:5])
    if not completed and len(lines) > TASK_ERROR_LINES:
        findings.append(Finding(
            LEVEL_ERROR,
            f"task is {len(lines)} lines (limit {TASK_ERROR_LINES}): the implementer reads all of it before its "
            f"first edit. Split it into one task per language or file group that share the design text by "
            f"reference, and replace code bodies with contracts (signature, ordering, invariants, "
            f"'mirror <file:line>')"))
    elif not completed and len(lines) > TASK_WARN_LINES:
        findings.append(Finding(
            LEVEL_WARN,
            f"task is {len(lines)} lines (advised maximum {TASK_WARN_LINES}): state contracts, not code "
            f"bodies, wherever the exact text is not itself the requirement"))
    record = record_section_lines(lines)
    if record > RECORD_WARN_LINES:
        findings.append(Finding(
            LEVEL_WARN,
            f"Implementation Notes / How Solved take {record} lines (advised maximum {RECORD_WARN_LINES}): "
            f"keep the decisions and the acceptance evidence, drop the per-file narration"))
    return findings


def task_files(args: argparse.Namespace, base_dir: Path) -> list[Path]:
    files = [Path(path) for path in args.tasks]
    if args.phase is not None:
        files.extend(discover_phase_task_files(base_dir, args.phase))
    return files


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description="Validate task files against the tree as it is now.")
    parser.add_argument("tasks", nargs="*", help="Task files to validate.")
    parser.add_argument("--phase", type=int, help="Validate every task of this phase, in every repository.")
    parser.add_argument("--base-dir", type=Path, default=None, help="The workspace root (default: this checkout's).")
    parser.add_argument("--strict", action="store_true", help="Warnings (moved lines) fail the run too.")
    parser.add_argument("--require-orientation", action="store_true",
                        help="A task with no '## Orientation' block is an error.")
    args = parser.parse_args(argv)
    base_dir = (args.base_dir or get_datrix_root()).resolve()
    files = task_files(args, base_dir)
    if not files:
        print("Error: no task files. Pass task file paths, or --phase <NN>.", file=sys.stderr)
        return EXIT_USAGE
    validator = Validator(base_dir, require_orientation=args.require_orientation)
    errors = warnings = 0
    try:
        for path in sorted(files):
            findings = validator.validate(path)
            errors += sum(1 for f in findings if f.level == LEVEL_ERROR)
            warnings += sum(1 for f in findings if f.level == LEVEL_WARN)
            print(f"{path.name}: {'OK' if not findings else f'{len(findings)} finding(s)'}")
            for finding in findings:
                print(finding.render())
    finally:
        validator.close()
    print(f"\n{len(files)} task(s): {errors} error(s), {warnings} warning(s).")
    return EXIT_FINDINGS if errors or (args.strict and warnings) else EXIT_OK


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
