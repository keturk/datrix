"""A task's ``## Orientation`` block: what an implementer needs to know, answered for it.

An implementer used to be told to read every file under "Files to Review Before Starting".
Measured over 82 implementing agents, 57% of the source and test tokens they read were on files
they never edited: orientation -- who calls this, where is that defined, how does a test build a
service -- read in full to learn a handful of facts. The task writer knows which facts those are.
It writes them down in the task, and the harness answers them (``inject-task-orientation.py``,
when the agent reads the task file) so the agent does not read the files.

THE BLOCK
    A fenced code block under ``## Orientation``. One entry per line; blank lines and ``#``
    comments are ignored::

        symbol: enum_imports_used_in_body
        refs: datrix_codegen_typescript.generators.messaging._messaging_helpers.enum_imports_used_in_body
        outline: datrix-codegen-typescript/src/datrix_codegen_typescript/generators/messaging/event_generator.py
        canonical: text/to-snake
        explain: datrix-testing/src/datrix_testing/factories.py; datrix-codegen-typescript/tests/unit/entity/test_enum_value_documentation.py :: How does a test build a service that carries an enum, and which helper adds the enum?

FACTS ARE EXACT, EXPLANATIONS ARE LEADS
    ``symbol``, ``refs``, ``outline`` and ``canonical`` are answered by the code index
    (``code_index.queries``): exact, and free. ``explain`` is answered by a local model reading the
    named files (``shared.local_reading.ask_files``): a cited lead, never a finding. A question
    about WHERE something is defined or WHO calls it is rejected -- a model asked that invents
    definitions and callers in files it never saw (observed) -- and the writer is told to use
    ``symbol`` or ``refs``, which cannot.

NOT RESOLVING IS INFORMATION
    A ``symbol`` with no definition, an ``outline`` of a file that does not exist: the task's
    premise has gone stale (another task renamed it, deleted it). Such an entry resolves to an
    ``UNRESOLVED`` line, and ``validate_task`` reports it as an error before the task is dispatched.
"""

from __future__ import annotations

import re
import sqlite3
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from pathlib import Path

KIND_SYMBOL = "symbol"
KIND_REFS = "refs"
KIND_OUTLINE = "outline"
KIND_CANONICAL = "canonical"
KIND_EXPLAIN = "explain"
FACT_KINDS = (KIND_SYMBOL, KIND_REFS, KIND_OUTLINE, KIND_CANONICAL)
ALL_KINDS = (*FACT_KINDS, KIND_EXPLAIN)

EXPLAIN_SEPARATOR = "::"
PATH_SEPARATOR = ";"

MAX_ITEMS = 12
MAX_EXPLAIN_ITEMS = 3
MAX_EXPLAIN_PATHS = 8
MIN_QUESTION_WORDS = 4
MAX_FACT_CHARS = 3500
MAX_TOTAL_CHARS = 16000
EXPLAIN_WORKERS = 3
FACT_LIMIT = 40

_ENTRY = re.compile(r"^(?P<kind>[a-z]+)\s*:\s*(?P<rest>.*)$")
# A question that asks the model where something is defined or who uses it. A model invents both.
_LOOKUP_QUESTION = re.compile(
    r"\bwhere\s+(?:is|are|does|do)\b[^?.]*\b(?:defined|declared|implemented|located|live|lives)\b"
    r"|\bwho\s+(?:calls|uses|imports)\b|\bwhat\s+(?:calls|uses|imports)\b|\bcallers?\s+of\b"
    r"|\b(?:find|list)\s+(?:all\s+)?(?:the\s+)?(?:uses|usages|references|callers|call\s+sites)\b"
    r"|\bwhich\s+(?:functions|files|modules|classes)\s+(?:call|use|import|reference)\b",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class OrientationItem:
    """One entry of the block."""

    kind: str
    argument: str
    line: int
    paths: tuple[str, ...] = ()
    question: str = ""

    def label(self) -> str:
        if self.kind == KIND_EXPLAIN:
            return f"explain {'; '.join(self.paths)} :: {self.question}"
        return f"{self.kind} {self.argument}"


@dataclass(frozen=True)
class ParsedOrientation:
    items: tuple[OrientationItem, ...]
    errors: tuple[str, ...]


def _parse_explain(rest: str, number: int) -> tuple[OrientationItem | None, str]:
    if EXPLAIN_SEPARATOR not in rest:
        return None, (f"orientation line {number}: 'explain' needs 'path; path :: question' (the '::' is missing). "
                      f"Name the files to read and the question to answer from them.")
    files_text, question = (part.strip() for part in rest.split(EXPLAIN_SEPARATOR, 1))
    paths = tuple(path.strip() for path in files_text.split(PATH_SEPARATOR) if path.strip())
    if not paths or len(paths) > MAX_EXPLAIN_PATHS:
        return None, (f"orientation line {number}: 'explain' names {len(paths)} files; name 1 to {MAX_EXPLAIN_PATHS}.")
    if len(question.split()) < MIN_QUESTION_WORDS:
        return None, (f"orientation line {number}: the question '{question}' is too short to answer; ask a full "
                      f"question about what the code does or how something is done.")
    if _LOOKUP_QUESTION.search(question):
        return None, (f"orientation line {number}: '{question}' asks where something is defined or who uses it. A "
                      f"local model invents those answers; use 'symbol: <name>' or 'refs: <dotted.path>', which the "
                      f"code index answers exactly.")
    return OrientationItem(KIND_EXPLAIN, files_text, number, paths, question), ""


def parse_orientation(lines: list[str]) -> ParsedOrientation:
    """Parse the lines of an ``## Orientation`` block; errors are collected, never raised."""
    items: list[OrientationItem] = []
    errors: list[str] = []
    for number, raw in enumerate(lines, start=1):
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        match = _ENTRY.match(line)
        if match is None or match.group("kind") not in ALL_KINDS:
            errors.append(f"orientation line {number}: '{line[:80]}' is not '<kind>: <argument>' with kind one of "
                          f"{', '.join(ALL_KINDS)}.")
            continue
        kind, rest = match.group("kind"), match.group("rest").strip()
        if not rest:
            errors.append(f"orientation line {number}: '{kind}:' has no argument.")
        elif kind == KIND_EXPLAIN:
            item, error = _parse_explain(rest, number)
            if item is None:
                errors.append(error)
            else:
                items.append(item)
        else:
            items.append(OrientationItem(kind, rest, number))
    if len(items) > MAX_ITEMS:
        errors.append(f"orientation has {len(items)} entries; at most {MAX_ITEMS}. Keep the facts this task needs.")
    explains = sum(1 for item in items if item.kind == KIND_EXPLAIN)
    if explains > MAX_EXPLAIN_ITEMS:
        errors.append(f"orientation has {explains} 'explain' entries; at most {MAX_EXPLAIN_ITEMS}: each costs a "
                      f"local-model read, and an explanation is a lead, not a fact.")
    return ParsedOrientation(tuple(items), tuple(errors))


@dataclass(frozen=True)
class ResolvedItem:
    item: OrientationItem
    text: str
    resolved: bool


@dataclass(frozen=True)
class ResolvedOrientation:
    items: tuple[ResolvedItem, ...] = ()
    errors: tuple[str, ...] = ()

    @property
    def unresolved(self) -> tuple[str, ...]:
        """The entries that did not resolve: a stale premise, or an explanation no model could give."""
        return tuple(resolved.item.label() for resolved in self.items if not resolved.resolved)

    def render(self, task_id: str) -> str:
        """The block as text for an agent: facts exact, explanations marked as leads, stale entries loud."""
        if not self.items and not self.errors:
            return ""
        parts = [f"Orientation for {task_id}, answered for you just now -- facts are exact code-index answers, "
                 f"explanations are local-model leads (confirm cited lines with a ranged Read before relying on "
                 f"them). You do not need to read these files to learn what is below."]
        parts.extend(f"INVALID ORIENTATION: {error}" for error in self.errors)
        for resolved in self.items:
            parts.append(f"[{resolved.item.label()}]\n{resolved.text}")
        if self.unresolved:
            parts.append("STALE TASK PREMISE: " + "; ".join(self.unresolved) + " did not resolve against the tree as it "
                         "is now. Another task or commit may have renamed or removed it: find its current form (the "
                         "code index's find_symbol / search) before editing, and say so in your report.")
        return "\n\n".join(parts)[:MAX_TOTAL_CHARS]


def _clip(text: str) -> str:
    return text if len(text) <= MAX_FACT_CHARS else text[:MAX_FACT_CHARS] + "\n... (clipped)"


def resolve_fact(conn: sqlite3.Connection, item: OrientationItem) -> ResolvedItem:
    """Answer one fact entry from the code index."""
    from code_index.queries import QueryError, find_canonical, find_references, find_symbol, outline

    try:
        if item.kind == KIND_SYMBOL:
            result = find_symbol(conn, item.argument, None, FACT_LIMIT)
            return ResolvedItem(item, _clip(result.render()), bool(result.hits))
        if item.kind == KIND_REFS:
            refs = find_references(conn, item.argument, FACT_LIMIT)
            return ResolvedItem(item, _clip(refs.render()), bool(refs.definitions))
        if item.kind == KIND_OUTLINE:
            return ResolvedItem(item, _clip(outline(conn, item.argument).render()), True)
        canonical = find_canonical(conn, item.argument, False, FACT_LIMIT)
        return ResolvedItem(item, _clip(canonical.render()), bool(canonical.hits))
    except QueryError as exc:
        return ResolvedItem(item, f"UNRESOLVED: {exc}", False)


def resolve_explanation(item: OrientationItem, ask: Callable[[OrientationItem], str]) -> ResolvedItem:
    """Answer one ``explain`` entry with ``ask`` (a local-model read); a failure is reported, not raised."""
    from shared.local_llm import LocalLlmUnavailable
    from shared.local_reading import ReadScopeError

    try:
        return ResolvedItem(item, _clip(ask(item)), True)
    except (ReadScopeError, LocalLlmUnavailable, OSError) as exc:
        return ResolvedItem(item, f"UNAVAILABLE: {exc}", False)


def resolve_orientation(
    lines: list[str],
    conn: sqlite3.Connection,
    ask: Callable[[OrientationItem], str] | None,
) -> ResolvedOrientation:
    """Parse and answer a block: facts from the index, explanations through ``ask`` (None = none are answered).

    Items come back in the order written. Explanations run in parallel; they are the slow part.
    """
    parsed = parse_orientation(lines)
    answers: dict[int, ResolvedItem] = {}
    explains = [item for item in parsed.items if item.kind == KIND_EXPLAIN]
    for item in parsed.items:
        if item.kind != KIND_EXPLAIN:
            answers[item.line] = resolve_fact(conn, item)
    if ask is not None and explains:
        with ThreadPoolExecutor(max_workers=EXPLAIN_WORKERS) as workers:
            for item, resolved in zip(explains, workers.map(lambda i: resolve_explanation(i, ask), explains)):
                answers[item.line] = resolved
    ordered = tuple(answers[item.line] for item in parsed.items if item.line in answers)
    return ResolvedOrientation(ordered, parsed.errors)


def orientation_lines(path: Path) -> list[str]:
    """The orientation lines of a task file, read by the one task parser."""
    from tasks.task_metadata import parse_task_file

    return parse_task_file(path).orientation
