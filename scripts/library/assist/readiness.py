"""Evidence for the task orchestrator's readiness audit, gathered without dispatching an agent.

Three of the audit's drift dimensions are answered here:

* missing dependency edge -- exact: a task reads or edits a file that does not exist yet and that only
  another task creates, but does not depend on that task (directly or through others); or two tasks
  create the same new file with no order between them;
* stale premise -- exact: a dotted module or symbol a task's ``## Codebase Context`` names that the
  code index cannot resolve and no task of the phase creates;
* already satisfied -- a lead: a local model reads the files a task edits (all of which exist) and says
  whether the task's design acceptance property already holds, citing ``path:line``. The citations are
  checked against what it was sent; the orchestrator still proves it before acting on it.

``validate-task.ps1`` owns the citation and orientation checks; they are not repeated here.
"""

from __future__ import annotations

import logging
import re
import sqlite3
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path

from assist.common import markdown_sections, parallel, workspace_label
from assist.phase_tasks import PhaseTask, edit_sites, review_sites
from code_index.queries import QueryError, find_symbol, outline
from code_index.session import open_session
from shared.local_llm import LocalLlmPool
from shared.local_reading import ReadScope, ReadScopeError, ask_local, read_section

LOG = logging.getLogger(__name__)

CODEBASE_CONTEXT_HEADING = "Codebase Context"
_DOTTED_NAME = re.compile(r"`(datrix_\w+(?:\.\w+)+)`")
VERDICT_SATISFIED = "SATISFIED"
VERDICT_NOT_SATISFIED = "NOT SATISFIED"
VERDICT_UNCLEAR = "UNCLEAR"
# NOT SATISFIED before SATISFIED: the first verdict that prefixes the answer's first line wins.
VERDICTS = (VERDICT_NOT_SATISFIED, VERDICT_SATISFIED, VERDICT_UNCLEAR)
VACUOUS_PROPERTIES = ("tests pass", "tests green", "it generates", "generates clean")
SATISFIED_QUESTION = (
    "A task will change these files so that the following property holds:\n\n{property}\n\n"
    "Does the property ALREADY hold in the files as they are now, before the task runs? Begin your answer "
    "with exactly one of SATISFIED, NOT SATISFIED or UNCLEAR on its own line, then give the evidence in at "
    "most 6 lines, citing path:line for every claim.")


@dataclass(frozen=True)
class EdgeFinding:
    """A dependency the task graph lacks."""

    task_id: str
    needs: tuple[str, ...]
    file: str
    reason: str


@dataclass(frozen=True)
class ModuleFinding:
    """A module or symbol a task's Codebase Context names that does not resolve."""

    task_id: str
    name: str


@dataclass(frozen=True)
class SatisfiedLead:
    """A local model's reading of whether a task's acceptance property already holds."""

    task_id: str
    verdict: str
    answer: str


@dataclass
class ReadinessEvidence:
    tasks: int
    edges: list[EdgeFinding] = field(default_factory=list)
    modules: list[ModuleFinding] = field(default_factory=list)
    leads: list[SatisfiedLead] = field(default_factory=list)
    lead_note: str = ""


def dependency_closure(tasks: list[PhaseTask]) -> dict[str, set[str]]:
    """Every task each task depends on, directly or through others."""
    direct = {task.task_id: set(task.meta.depends_on) for task in tasks}
    closure: dict[str, set[str]] = {}

    def reach(task_id: str, trail: frozenset[str]) -> set[str]:
        if task_id in closure:
            return closure[task_id]
        found: set[str] = set()
        for dep in direct.get(task_id, set()):
            if dep in trail:
                continue  # a cycle is plan-waves.ps1's finding, not this one's
            found |= {dep, *reach(dep, trail | {dep})}
        closure[task_id] = found
        return found

    for task_id in direct:
        reach(task_id, frozenset({task_id}))
    return closure


def _ordered(a: str, b: str, closure: dict[str, set[str]]) -> bool:
    return a in closure.get(b, set()) or b in closure.get(a, set())


def missing_edges(workspace: Path, every: list[PhaseTask], pending: list[PhaseTask]) -> list[EdgeFinding]:
    """Dependency edges the graph needs: a not-yet-existing file read or edited before its creator runs."""
    creators: dict[Path, list[str]] = defaultdict(list)
    for task in every:
        for path in edit_sites(workspace, task):
            if not path.exists():
                creators[path].append(task.task_id)
    closure = dependency_closure(every)
    findings: list[EdgeFinding] = []
    for task in pending:
        own_edits = set(edit_sites(workspace, task))
        for path in dict.fromkeys([*own_edits, *review_sites(workspace, task)]):
            others = [c for c in creators.get(path, []) if c != task.task_id]
            if not others:
                continue
            label = workspace_label(workspace, path)
            if path in own_edits:
                unordered = tuple(c for c in others if not _ordered(c, task.task_id, closure))
                if unordered:
                    findings.append(EdgeFinding(task.task_id, unordered, label,
                                                "both tasks create this file and neither depends on the other"))
            elif not any(c in closure.get(task.task_id, set()) for c in others):
                findings.append(EdgeFinding(task.task_id, tuple(others), label,
                                            "the task reads this file, which does not exist until the other "
                                            "task creates it, and does not depend on that task"))
    return findings


def _context_text(task: PhaseTask) -> str:
    lines = task.text.splitlines()
    for section in markdown_sections(lines, max_level=2):
        if section.heading.strip().lower() == CODEBASE_CONTEXT_HEADING.lower():
            return "\n".join(lines[section.start - 1:section.end])
    return ""


def _is_module(conn: sqlite3.Connection, name: str) -> bool:
    try:
        outline(conn, name)
    except QueryError:
        return False
    return True


def _is_symbol(conn: sqlite3.Connection, name: str) -> bool:
    try:
        return bool(find_symbol(conn, name).hits)
    except QueryError:
        return False


def unresolved_modules(workspace: Path, pending: list[PhaseTask], every: list[PhaseTask]) -> list[ModuleFinding]:
    """Dotted names in each task's Codebase Context that the index cannot resolve and no task creates."""
    created_stems = {path.stem for task in every for path in edit_sites(workspace, task) if not path.exists()}
    findings: list[ModuleFinding] = []
    session = open_session(workspace)
    try:
        session.refresh()
        for task in pending:
            for name in dict.fromkeys(_DOTTED_NAME.findall(_context_text(task))):
                if set(name.split(".")) & created_stems:
                    continue
                if not (_is_module(session.conn, name) or _is_symbol(session.conn, name)):
                    findings.append(ModuleFinding(task.task_id, name))
    finally:
        session.close()
    return findings


def _verdict(answer: str) -> str:
    first = answer.strip().splitlines()[0].strip().upper() if answer.strip() else ""
    return next((verdict for verdict in VERDICTS if first.startswith(verdict)), VERDICT_UNCLEAR)


def _checkable(workspace: Path, task: PhaseTask) -> list[Path]:
    """The files to read for a task whose property is concrete and whose edit sites all exist."""
    prop = (task.meta.design_acceptance_property or "").strip()
    if not prop or prop.lower().rstrip(".") in VACUOUS_PROPERTIES:
        return []
    sites = edit_sites(workspace, task)
    return sites if sites and all(path.is_file() for path in sites) else []


def satisfied_leads(workspace: Path, pool: LocalLlmPool, pending: list[PhaseTask]) -> list[SatisfiedLead]:
    """For each task whose edit sites all exist: does its acceptance property already hold? (a lead)."""
    scope = ReadScope(workspace)
    work = [(task, files) for task in pending if (files := _checkable(workspace, task))]

    def ask(item: tuple[PhaseTask, list[Path]]) -> SatisfiedLead:
        task, files = item
        try:
            sections = [read_section(scope, path) for path in scope.files([str(p) for p in files])]
        except ReadScopeError as exc:
            return SatisfiedLead(task.task_id, VERDICT_UNCLEAR, f"Not read: {exc}")
        question = SATISFIED_QUESTION.format(property=task.meta.design_acceptance_property)
        answer = ask_local(pool, question, sections)
        return SatisfiedLead(task.task_id, _verdict(answer.text), answer.render())

    return parallel(work, ask)


def render(evidence: ReadinessEvidence, phase_label: str) -> str:
    """The evidence as markdown for the orchestrator to adjudicate."""
    lines = [f"# Readiness evidence -- phase {phase_label}", "",
             f"{evidence.tasks} pending task(s). Exact findings first; model leads after. Every item is "
             "evidence for your verdict, not a verdict.", "", "## Missing dependency edges (exact)", ""]
    lines += [f"- {e.task_id} needs {', '.join(e.needs)}: `{e.file}` -- {e.reason}" for e in evidence.edges] \
        or ["None."]
    lines += ["", "## Unresolvable names in Codebase Context (exact)", ""]
    lines += [f"- {m.task_id}: `{m.name}` is not a module or symbol in the index and no task creates it"
              for m in evidence.modules] or ["None."]
    lines += ["", "## Already satisfied? (local-model leads)", ""]
    if evidence.lead_note:
        lines.append(evidence.lead_note)
    for lead in evidence.leads:
        lines += [f"### {lead.task_id}: {lead.verdict}", "", lead.answer, ""]
    if not evidence.leads and not evidence.lead_note:
        lines.append("No task has a concrete acceptance property over files that all exist.")
    return "\n".join(lines) + "\n"
