"""PreToolUse hook (Write|Edit): three repo policies that were prose rules, now blocks.

1. NO GITHUB ACTIONS. CLAUDE.md: "No GitHub Actions." A file under `.github/workflows/` is a
   CI pipeline this project does not use and must never grow. Third-party sources parked in
   `.tmp/` are not ours and are left alone.

2. A TASK IS COMPLETED BY `complete.ps1`, NEVER BY EDITING ITS HEADING. task-orchestration.md:
   "Always use complete.ps1. Never edit the task heading directly -- Edit/Write bypass the
   validation hook complete.ps1 enforces." The failure it prevents is real: a task was once
   marked COMPLETED while its own `## How Solved` said `Status: BLOCKED`. An edit that ADDS a
   `# COMPLETED: Task ...` heading to a task file is refused; editing the rest of the file, or
   a file that already carries the heading, is not.

3. AGENTS NEVER CREATE A PHASE. task-orchestration.md: creating a `.tasks/phase-NN/` directory
   that does not already exist is a planning act reserved to Jon and to the planning skills he
   invokes by name (`/generate-tasks`, `/operationalize-design`). A phase that appears on its own
   silently seeds the next orchestration run with work nobody scheduled. Writing a file into a
   phase directory that does not exist is how an agent creates one, so that is what is refused
   -- unless the skill recorded for this session (`record-active-skill.py`) is one of the two
   planning skills. An unreadable record cannot prove a planning skill is active, and the block
   stays: a phase is cheap to ask for and expensive to unschedule.

All three fail OPEN on anything the hook cannot evaluate (unparseable input, unreadable file).

Exit codes:
  0 -- allow
  2 -- block (stderr becomes feedback to Claude)
"""

import json
import os
import re
import sys
from typing import Final

_REPO_ROOT: Final = "d:/datrix"
_STATE_DIR: Final = os.path.join(_REPO_ROOT, ".claude", "hooks", ".state")

# Planning skills Jon invokes by name; the only callers allowed to open a new phase.
_PHASE_PLANNING_SKILLS: Final = frozenset({"generate-tasks", "operationalize-design"})

_WORKFLOW_RE: Final = re.compile(r"(?:^|/)\.github/workflows/[^/]+$")
# Third-party checkouts and tooling the project does not own.
_THIRD_PARTY_SEGMENTS: Final = ("/.tmp/", "/node_modules/", "/.venv/", "/site-packages/", "/.git/")

_TASK_FILE_RE: Final = re.compile(r"(?:^|/)\.tasks/phase-(\d+)/task-[^/]+\.md$")
_PHASE_DIR_RE: Final = re.compile(r"^(.*?/\.tasks/phase-\d+)/")
_COMPLETED_HEADING_RE: Final = re.compile(r"^#\s+COMPLETED:\s+Task\b", re.MULTILINE)


def _normalize(path: str) -> str:
    return path.replace("\\", "/")


def _read(path: str) -> str:
    try:
        with open(path, encoding="utf-8", errors="replace") as handle:
            return handle.read()
    except OSError:
        return ""


def _block(message: str) -> None:
    sys.stderr.write(message)
    sys.exit(2)


def _active_skill(session_id: str) -> str:
    safe = re.sub(r"[^A-Za-z0-9_-]", "_", session_id or "unknown")
    try:
        with open(os.path.join(_STATE_DIR, f"skill-{safe}.json"), encoding="utf-8") as handle:
            return str(json.load(handle).get("skill", "")).lower()
    except (OSError, ValueError):
        return ""


def _check_workflow(path: str) -> None:
    lowered = path.lower()
    if not _WORKFLOW_RE.search(lowered) or any(seg in lowered for seg in _THIRD_PARTY_SEGMENTS):
        return
    _block(
        f"BLOCKED: `{path}` is a GitHub Actions workflow.\n\n"
        "CLAUDE.md: 'No GitHub Actions.' This project does not use GitHub Actions: do not create, "
        "edit, suggest or reference workflows or `.github/workflows/` files. Checks run as "
        "scripts under `datrix/scripts/` (`datrix/scripts/quick-reference.md`) and as the harness "
        "hooks under `.claude/hooks/`; a check that should run on every change belongs in one of "
        "those, or in a test in the owning package."
    )


def _adds_completed_heading(tool: str, tool_input: dict[str, object], path: str) -> bool:
    if tool == "Write":
        content = str(tool_input.get("content", ""))
        return bool(_COMPLETED_HEADING_RE.search(content)) and not _COMPLETED_HEADING_RE.search(_read(path))
    new = str(tool_input.get("new_string", ""))
    old = str(tool_input.get("old_string", ""))
    return bool(_COMPLETED_HEADING_RE.search(new)) and not _COMPLETED_HEADING_RE.search(old)


def _check_task_heading(tool: str, tool_input: dict[str, object], path: str) -> None:
    if not _TASK_FILE_RE.search(path.lower()) or not _adds_completed_heading(tool, tool_input, path):
        return
    _block(
        f"BLOCKED: this edit marks `{path}` COMPLETED by hand.\n\n"
        ".claude/rules/task-orchestration.md: 'Always use complete.ps1. Never edit the task "
        "heading directly -- Edit/Write bypass the validation `complete.ps1` enforces.' "
        "That validation is what refuses a task whose own `## How Solved` says BLOCKED, `partial`, "
        "`out of scope` or `workaround`, or whose design-acceptance property is unproven; a task was "
        "once marked COMPLETED while its How-Solved said `Status: BLOCKED`.\n\n"
        "Read `datrix/scripts/tasks/quick-reference.md` for the invocation, and call `complete.ps1`. "
        "In /task-orchestrator and /execute-tasks-parallel runs, mark a task COMPLETED only after "
        "the wave's test gate passes, never as an individual agent returns. Editing the rest of the "
        "task file (How Solved, notes) is fine; only the status heading is `complete.ps1`'s."
    )


def _check_new_phase(path: str, session_id: str) -> None:
    lowered = path.lower()
    match = _PHASE_DIR_RE.match(lowered)
    if not match or any(seg in lowered for seg in _THIRD_PARTY_SEGMENTS):
        return
    phase_dir = path[: len(match.group(1))]
    if os.path.isdir(phase_dir):
        return
    if _active_skill(session_id) in _PHASE_PLANNING_SKILLS:
        return
    _block(
        f"BLOCKED: writing `{path}` would create the phase directory `{phase_dir}`, which does not exist.\n\n"
        ".claude/rules/task-orchestration.md: 'Agents never create a phase.' Opening a new "
        "`.tasks/phase-NN/` is a planning act reserved to Jon and to the planning skills he invokes by "
        "name (`/generate-tasks`, `/operationalize-design`). A phase that appears on its own seeds the "
        "next orchestration run with work nobody scheduled, and it moves what `latest-phase.ps1` reports. "
        "'The execution contract told me to file a real tracked task' is not authorization to open one.\n\n"
        "If this task belongs in the phase you are executing: number it the next free {TT} "
        "(`validate-dependencies.ps1 -Phase {NN} -NextTaskNumber`) and put it in the owning package's "
        "EXISTING `.tasks/phase-{NN}/`. If it is design-sized, it is a findings file "
        "(`d:\\datrix\\reports\\finding\\`, execution-contract-reporting.md section 5A), not a task."
    )


def main() -> None:
    try:
        data = json.loads(sys.stdin.read())
    except json.JSONDecodeError:
        sys.exit(0)

    tool = data.get("tool_name", "")
    if tool not in ("Write", "Edit"):
        sys.exit(0)
    tool_input = data.get("tool_input") or {}
    raw_path = str(tool_input.get("file_path", ""))
    if not raw_path:
        sys.exit(0)

    path = _normalize(raw_path)
    _check_workflow(path)
    _check_task_heading(tool, tool_input, path)
    if tool == "Write":
        _check_new_phase(path, str(data.get("session_id", "")))
    sys.exit(0)


if __name__ == "__main__":
    main()
