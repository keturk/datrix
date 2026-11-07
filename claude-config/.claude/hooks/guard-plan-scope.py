r"""PreToolUse hook: work stays inside the scope the session plan declared for Jon's order.

The session plan may carry a `## Scope` section, written from the order's own words:

    ## Scope
    paths: datrix-*/src/** datrix-*/tests/**
    scripts: split-module

Entries are separated by spaces or commas. A path glob may be absolute under the workspace, or
absolute outside it (`d:/g/some-product/**`), when Jon's order names a tree there: such an entry is
matched against the whole lower-cased path, and a relative entry never leaves the workspace. A
script may be named with its folder and suffix: `test/failure-ledger.ps1` is `failure-ledger`.

Once a scope is seen it is locked: the agent's own edit of the plan cannot widen it. This hook then
refuses a file edit outside `paths` (workspace-relative globs, plus the absolute trees the plan
names) and a command that runs a repo script not named in `scripts`. The plan file, the scratchpad, `.tmp` and Claude's memory folders are always
writable. In an attended session only Jon widens a scope: any message of his may carry a new order, so
a refused call after it reads the plan afresh, and a changed scope locks again until his next message.

An unattended session (`_agent_plan.unattended`, set by the skill chain at launch) never receives a
message of his, and its order names a unit or a finding, not the files it reaches. There every refused
call reads the plan afresh, so the session can declare what its order turns out to need; what the plan
does not declare stays refused. The refusal names the remedy that works in the session that got it.

A skill whose order can reach any repo is not fenced at all: while one is the session's latest
skill, nothing is refused. `/fix-test-suites` orders every repo and test suite. `/implement-finding`
orders a fix across every package the finding reaches, which only reading the code shows, so a scope
written before that reading cannot describe it, and a batch session has no Jon to type `scope reset`.

A skill whose order writes one more kind of file gets those paths added to the scope while it is the
session's latest skill (`_SKILL_WRITABLE`): `/absorb-design` moves a design's knowledge into the
project documents and rewrites the references other designs hold to the design it deletes, so every
repo's `docs/` tree and Markdown, and `design/*.md`, are writable under it; source stays fenced. It
often resumes the verify session, whose scope was locked for verify's narrower order.

A script another guard demands is never refused, whatever the skill or scope (`_GUARD_DEMANDED`):
`guard-test-run-discipline.py` refuses every test run until an edited fixture project is probed, so
refusing `dev/probe-fixture` here would leave a session unable to run any test.

Fails open: no plan, no `## Scope`, or an unreadable payload lets the call through.

Exit codes:
  0 - allow
  2 - refuse, the reason on stderr
"""

from __future__ import annotations

import json
import os
import re
import sys
from fnmatch import fnmatch
from typing import Final

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import _agent_plan as plan  # noqa: E402
from _advisor import latest_invoked_skill, transcript_entries  # noqa: E402
from _fixture_probe import PROBE_SCRIPT  # noqa: E402
from _report_language import content_blocks, is_jon_speaking  # noqa: E402

_WORKSPACE: Final = "d:/datrix/"
#: A canonical scope entry that names a tree outside the workspace keeps its drive; a workspace entry lost it.
_DRIVE_RE: Final = re.compile(r"^[a-z]:/")
_SCOPE_RE: Final = re.compile(r"^## Scope[ \t]*\n(.*?)(?=^## |\Z)", re.MULTILINE | re.DOTALL)
_SCRIPT_RE: Final = re.compile(r"scripts[\\/](?:[\w.-]+[\\/])*([\w-]+)\.(?:ps1|sh)\b", re.IGNORECASE)
_ENTRY_SEPARATOR_RE: Final = re.compile(r"[,\s]+")
#: Skills whose order can reach any repo; no plan scope can fence them.
_WORKSPACE_WIDE_SKILLS: Final = frozenset({"fix-test-suites", "implement-finding"})
#: Paths a skill's own order writes beyond any plan scope, by skill: `/absorb-design` moves a design's
#: knowledge into the project documents of every repo (each repo's `docs/` tree and its Markdown) and
#: rewrites the references other designs hold to the design it deletes.
_SKILL_WRITABLE: Final = {"absorb-design": ("design/*.md", "datrix*/docs/*", "datrix*/*.md")}
#: Scripts a skill's own steps run beyond any plan scope, by skill.
_SKILL_RUNNABLE: Final = {"absorb-design": ("skill-assist",)}
#: Scripts another guard demands before it lets the work go on, under every skill and scope: refusing
#: one here leaves an attended session no way forward, since only Jon can widen its locked scope.
_GUARD_DEMANDED: Final = frozenset({PROBE_SCRIPT})
_ALWAYS_WRITABLE: Final = (".agent_output/*", ".tmp/*")
_SCRATCHPAD_MARK: Final = "/scratchpad/"
#: Claude's per-project memory, outside the workspace; matched on the whole lower-cased path.
_MEMORY_GLOB: Final = "*/.claude/projects/*/memory/*"
#: User entries the harness writes on the agent's behalf: a skill body and a compaction summary.
_NOT_JON_FLAGS: Final = ("isMeta", "isCompactSummary")
_EDIT_TOOLS: Final = frozenset({"Write", "Edit", "NotebookEdit"})
_LINE_EDIT_TOOL: Final = "mcp__datrix-edit__edit_lines"


def _path_glob(entry: str) -> str:
    return entry.replace("\\", "/").lower().removeprefix(_WORKSPACE)


def _script_name(entry: str) -> str:
    return os.path.splitext(entry.replace("\\", "/").rsplit("/", 1)[-1])[0].lower()


def _entries(values: str) -> list[str]:
    return [entry for entry in _ENTRY_SEPARATOR_RE.split(values) if entry]


def _declared(session_id: str) -> dict[str, list[str]] | None:
    """The plan's scope, or None when the plan declares none."""
    try:
        with open(plan.plan_path(session_id), encoding="utf-8") as handle:
            match = _SCOPE_RE.search(handle.read())
    except OSError:
        return None
    if match is None:
        return None
    scope: dict[str, list[str]] = {"paths": [], "scripts": []}
    for line in match.group(1).splitlines():
        key, _, values = line.partition(":")
        if key.strip() in scope:
            scope[key.strip()] = _entries(values)
    return scope


def _canonical(scope: dict[str, list[str]]) -> dict[str, list[str]]:
    """The scope in the form calls are compared in, whichever spelling the plan used."""
    return {
        "paths": [_path_glob(entry) for raw in scope["paths"] for entry in _entries(raw)],
        "scripts": [_script_name(entry) for raw in scope["scripts"] for entry in _entries(raw)],
    }


def _jon_messages(entries: list[dict[str, object]]) -> int:
    """How many messages of Jon's the transcript holds; a skill body or summary the agent caused is none."""
    return sum(
        1
        for entry in entries
        if entry.get("type") == "user"
        and not any(entry.get(flag) for flag in _NOT_JON_FLAGS)
        and is_jon_speaking(content_blocks(entry))
    )


def _read_lock(session_id: str) -> tuple[dict[str, list[str]], int] | None:
    """The locked scope and the count of Jon's messages it was locked at; None when nothing is locked."""
    try:
        with open(plan.state_path("scope", session_id), encoding="utf-8") as handle:
            lock = json.load(handle)
    except (OSError, ValueError):
        return None
    return {"paths": lock.get("paths", []), "scripts": lock.get("scripts", [])}, int(lock.get("jon_messages", 0))


def _write_lock(session_id: str, scope: dict[str, list[str]], jon_messages: int) -> None:
    try:
        os.makedirs(plan.STATE_DIR, exist_ok=True)
        with open(plan.state_path("scope", session_id), "w", encoding="utf-8") as handle:
            json.dump({**scope, "jon_messages": jon_messages}, handle)
    except OSError:
        return


def _locked(session_id: str, jon_messages: int) -> dict[str, list[str]] | None:
    """The session's scope as locked; the first sighting locks it."""
    lock = _read_lock(session_id)
    if lock is not None:
        return lock[0]
    scope = _declared(session_id)
    if scope is not None:
        _write_lock(session_id, scope, jon_messages)
    return scope


def _rescoped(session_id: str, jon_messages: int, scope: dict[str, list[str]]) -> dict[str, list[str]]:
    """The scope a refused call is judged by: the plan's, when the plan says something new and either Jon
    has spoken since the lock or the session is unattended, where no message of his will ever come. An
    unchanged plan spends nothing, so a refusal before the agent writes his new order into the plan does
    not cost that order; a changed one locks until his next message."""
    lock = _read_lock(session_id)
    if lock is None or (lock[1] >= jon_messages and not plan.unattended()):
        return scope
    declared = _declared(session_id)
    if declared is None or _canonical(declared) == _canonical(scope):
        return scope
    _write_lock(session_id, declared, jon_messages)
    return declared


def _edited_paths(tool_name: str, tool_input: dict[str, object]) -> list[str]:
    if tool_name in _EDIT_TOOLS:
        return [str(tool_input.get("file_path", ""))]
    if tool_name == _LINE_EDIT_TOOL:
        edits = tool_input.get("edits")
        return [str(edit.get("file_path", "")) for edit in edits if isinstance(edit, dict)] if isinstance(edits, list) else []
    return []


def _absolute_globs(allowed: list[str]) -> list[str]:
    """The scope entries naming a tree outside the workspace, matched on the whole path."""
    return [glob for glob in allowed if _DRIVE_RE.match(glob)]


def _outside_paths(paths: list[str], allowed: list[str]) -> list[str]:
    outside: list[str] = []
    absolute = _absolute_globs(allowed)
    for raw in paths:
        path = raw.replace("\\", "/").lower()
        in_workspace = path.startswith(_WORKSPACE)
        relative = path.removeprefix(_WORKSPACE)
        if _SCRATCHPAD_MARK in path or fnmatch(path, _MEMORY_GLOB):
            continue
        if in_workspace and any(fnmatch(relative, glob) for glob in (*_ALWAYS_WRITABLE, *allowed)):
            continue
        if not in_workspace and any(fnmatch(path, glob) for glob in absolute):
            continue
        outside.append(raw)
    return outside


def _violations(data: dict[str, object], declared: dict[str, list[str]], skill: str) -> list[str]:
    tool_name = str(data.get("tool_name", ""))
    tool_input = data.get("tool_input")
    if not isinstance(tool_input, dict):
        return []
    scope = _canonical(declared)
    allowed = [*scope["paths"], *_SKILL_WRITABLE.get(skill, ())]
    problems = [f"file outside the scope: {path}" for path in _outside_paths(_edited_paths(tool_name, tool_input), allowed)]
    if tool_name in ("Bash", "PowerShell"):
        scripts = {name.lower() for name in _SCRIPT_RE.findall(str(tool_input.get("command", "")))}
        runnable = {*scope["scripts"], *_GUARD_DEMANDED, *_SKILL_RUNNABLE.get(skill, ())}
        problems += [f"script outside the scope: {name}" for name in sorted(scripts - runnable)]
    return problems


def _refusal(problems: list[str]) -> str:
    """The refusal, with the one remedy that can work in this kind of session."""
    listed = "\n- ".join(problems)
    if plan.unattended():
        return (
            f"Refused by the session scope (`## Scope` in the plan):\n- {listed}\n"
            "This session is unattended, so the plan is read afresh on every refused call. If your order "
            "needs this, write its paths and scripts into the plan's `## Scope` and retry. Otherwise it is "
            "not part of your order: do not do it."
        )
    return (
        f"Refused by the session scope (`## Scope` in the plan, locked until Jon's next message):\n- {listed}\n"
        "If Jon's latest message orders this, write his order's paths and scripts into the plan's "
        "`## Scope` and retry: the plan is read afresh once per message of his. Otherwise it is not "
        "part of his order: do not do it and do not route around this; tell him in one line if it matters."
    )


def main() -> None:
    try:
        data = json.loads(sys.stdin.read())
    except json.JSONDecodeError:
        sys.exit(0)
    session_id = str(data.get("session_id") or "")
    entries = transcript_entries(str(data.get("transcript_path", ""))) or []
    jon_messages = _jon_messages(entries)
    scope = _locked(session_id, jon_messages)
    if scope is None:
        sys.exit(0)
    skill = latest_invoked_skill(entries) or ""
    problems = _violations(data, scope, skill)
    if problems and skill in _WORKSPACE_WIDE_SKILLS:
        sys.exit(0)
    if problems:
        problems = _violations(data, _rescoped(session_id, jon_messages, scope), skill)
    if problems:
        print(_refusal(problems), file=sys.stderr)
        sys.exit(2)
    sys.exit(0)


if __name__ == "__main__":
    main()
