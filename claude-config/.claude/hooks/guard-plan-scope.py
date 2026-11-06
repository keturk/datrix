r"""PreToolUse hook: work stays inside the scope the session plan declared for Jon's order.

The session plan may carry a `## Scope` section, written from the order's own words:

    ## Scope
    paths: datrix-*/src/** datrix-*/tests/**
    scripts: split-module

Entries are separated by spaces or commas. A path glob may be absolute under the workspace, and a
script may be named with its folder and suffix: `test/failure-ledger.ps1` is `failure-ledger`.

Once a scope is seen it is locked for the session: a later edit of the plan cannot widen it. This
hook then refuses a file edit outside `paths` (workspace-relative globs) and a command that runs a
repo script not named in `scripts`. The plan file, the scratchpad and `.tmp` are always writable.
Only Jon widens a scope: his message saying `scope reset` drops the lock, and the plan's section
is read afresh.

A skill whose order can reach any repo is not fenced at all: while one is the session's latest
skill, nothing is refused. `/fix-test-suites` orders every repo and test suite. `/implement-finding`
orders a fix across every package the finding reaches, which only reading the code shows, so a scope
written before that reading cannot describe it, and a batch session has no Jon to type `scope reset`.

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
from _report_language import content_blocks, is_jon_speaking  # noqa: E402

_WORKSPACE: Final = "d:/datrix/"
_SCOPE_RE: Final = re.compile(r"^## Scope[ \t]*\n(.*?)(?=^## |\Z)", re.MULTILINE | re.DOTALL)
_SCRIPT_RE: Final = re.compile(r"scripts[\\/](?:[\w.-]+[\\/])*([\w-]+)\.(?:ps1|sh)\b", re.IGNORECASE)
_RESET_RE: Final = re.compile(r"\bscope reset\b", re.IGNORECASE)
_ENTRY_SEPARATOR_RE: Final = re.compile(r"[,\s]+")
#: Skills whose order can reach any repo; no plan scope can fence them.
_WORKSPACE_WIDE_SKILLS: Final = frozenset({"fix-test-suites", "implement-finding"})
_ALWAYS_WRITABLE: Final = (".agent_output/*", ".tmp/*")
_SCRATCHPAD_MARK: Final = "/scratchpad/"
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


def _locked(session_id: str) -> dict[str, list[str]] | None:
    """The session's scope as first seen; the first sighting locks it."""
    path = plan.state_path("scope", session_id)
    try:
        with open(path, encoding="utf-8") as handle:
            return dict(json.load(handle))
    except (OSError, ValueError):
        pass
    scope = _declared(session_id)
    if scope is not None:
        try:
            os.makedirs(plan.STATE_DIR, exist_ok=True)
            with open(path, "w", encoding="utf-8") as handle:
                json.dump(scope, handle)
        except OSError:
            return scope
    return scope


def _in_workspace_wide_skill(transcript_path: str) -> bool:
    return latest_invoked_skill(transcript_entries(transcript_path) or []) in _WORKSPACE_WIDE_SKILLS


def _jon_reset_the_scope(transcript_path: str) -> bool:
    for entry in reversed(transcript_entries(transcript_path) or []):
        blocks = content_blocks(entry)
        if entry.get("type") == "user" and is_jon_speaking(blocks):
            return any(_RESET_RE.search(str(block.get("text", ""))) for block in blocks)
    return False


def _edited_paths(tool_name: str, tool_input: dict[str, object]) -> list[str]:
    if tool_name in _EDIT_TOOLS:
        return [str(tool_input.get("file_path", ""))]
    if tool_name == _LINE_EDIT_TOOL:
        edits = tool_input.get("edits")
        return [str(edit.get("file_path", "")) for edit in edits if isinstance(edit, dict)] if isinstance(edits, list) else []
    return []


def _outside_paths(paths: list[str], allowed: list[str]) -> list[str]:
    outside: list[str] = []
    for raw in paths:
        path = raw.replace("\\", "/").lower()
        in_workspace = path.startswith(_WORKSPACE)
        relative = path.removeprefix(_WORKSPACE)
        if _SCRATCHPAD_MARK in path or (in_workspace and any(fnmatch(relative, glob) for glob in (*_ALWAYS_WRITABLE, *allowed))):
            continue
        outside.append(raw)
    return outside


def _violations(data: dict[str, object], declared: dict[str, list[str]]) -> list[str]:
    tool_name = str(data.get("tool_name", ""))
    tool_input = data.get("tool_input")
    if not isinstance(tool_input, dict):
        return []
    scope = _canonical(declared)
    problems = [f"file outside the scope: {path}" for path in _outside_paths(_edited_paths(tool_name, tool_input), scope["paths"])]
    if tool_name in ("Bash", "PowerShell"):
        scripts = {name.lower() for name in _SCRIPT_RE.findall(str(tool_input.get("command", "")))}
        problems += [f"script outside the scope: {name}" for name in sorted(scripts - set(scope["scripts"]))]
    return problems


def main() -> None:
    try:
        data = json.loads(sys.stdin.read())
    except json.JSONDecodeError:
        sys.exit(0)
    session_id = str(data.get("session_id") or "")
    scope = _locked(session_id)
    if scope is None:
        sys.exit(0)
    problems = _violations(data, scope)
    transcript_path = str(data.get("transcript_path", ""))
    if problems and _in_workspace_wide_skill(transcript_path):
        sys.exit(0)
    if problems and _jon_reset_the_scope(transcript_path):
        try:
            os.remove(plan.state_path("scope", session_id))
        except OSError:
            pass
        scope = _locked(session_id)
        problems = _violations(data, scope) if scope is not None else []
    if problems:
        print(
            "Refused by the session scope (`## Scope` in the plan, locked for this session):\n- "
            + "\n- ".join(problems)
            + "\nThis is not part of Jon's order. Do not do it and do not route around this. Tell Jon in "
            "one line if it matters; only his `scope reset` widens the scope.",
            file=sys.stderr,
        )
        sys.exit(2)
    sys.exit(0)


if __name__ == "__main__":
    main()
