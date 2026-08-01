"""PostToolUse hook: arm the stop-gate from the WORK, not from how the run was launched.

THE HOLE THIS CLOSES
--------------------
`arm-orchestration-run.py` arms the gate only when a user prompt literally contains
`/task-orchestrator` (or a sibling). That is one instant, at the top of the session.
Everything after it runs un-armed:

  - a run resumed after a compaction (these runs span days — one observed session ran
    2026-07-31T00:49Z -> 2026-08-01T04:58Z with several compactions),
  - a run continued with "keep going" / "do phase 8" / a plain-English dispatch,
  - a run launched through any skill not on the three-name list,
  - a session already in flight when the hooks were installed or changed,
  - every `--resume`/`--continue` of the above.

Evidence that this is not theoretical: `/task-orchestrator` was invoked in ~14 sessions
across two weeks; the state directory contains ZERO files with `"status": "running"`.
The gate has, in practice, never been armed. The failure Jon keeps hitting is not the
model out-arguing the gate — the gate was never switched on.

So arming stops being a property of Jon's phrasing and becomes a property of the
agent's own behavior: touch the task ledger, and the gate is live.

ARM ON MUTATION ONLY — LOOKING IS NOT DOING
-------------------------------------------
Only evidence that the session is EXECUTING tasks arms the gate:
  - Write/Edit on a `.tasks/phase-NN/*.md` task file,
  - a `complete.ps1` invocation,
  - an agent dispatched with a task-file path in its prompt.

Read-only inspection (`phase-status.ps1`, `plan-waves.ps1`, `todo.ps1`,
`validate-dependencies.ps1`, reading a task file) deliberately does NOT arm. Otherwise
merely asking "how many tasks are left?" in an unrelated conversation would trap that
session behind a gate for work it never started.

Exit codes:
  0 — always. This hook only records state; it can never block a tool call.
"""

import json
import os
import re
import sys
from typing import Final

_REPO_ROOT: Final = "d:/datrix"
_STATE_DIR: Final = os.path.join(_REPO_ROOT, ".claude", "hooks", ".state")

# A task file inside a phase folder, in either slash style. The separators repeat
# because shell/dispatch payloads are matched after JSON serialization, where every
# Windows backslash arrives doubled.
_TASK_FILE_RE: Final = re.compile(
    r"[\\/]+\.tasks[\\/]+phase-(\d{1,3})[\\/]+[^\"'\s]*?\.md", re.IGNORECASE
)
# The one task script that MUTATES the ledger. The read-only ones are intentionally absent.
_COMPLETE_SCRIPT_RE: Final = re.compile(r"\bcomplete\.ps1\b", re.IGNORECASE)
# `complete.ps1 "...\.tasks\phase-08\task-08-03.md"` -> 8, and the bare-filename form.
_TASK_NAME_RE: Final = re.compile(r"\btask-(\d{1,3})-\d{1,3}\b", re.IGNORECASE)

# Tools whose use can constitute executing a task. Reads are absent by design.
_MUTATING_FILE_TOOLS: Final = frozenset({"Write", "Edit", "NotebookEdit"})
_SHELL_TOOLS: Final = frozenset({"Bash", "PowerShell"})
_DISPATCH_TOOLS: Final = frozenset({"Agent", "Task"})

# Statuses that a fresh observation may re-arm. `stopped_by_user` is Jon's word and
# only his next prompt clears it; `gate_exhausted` likewise waits for a new prompt.
_REARMABLE: Final = frozenset({"", "idle", "complete"})

_MAX_PHASES_TRACKED: Final = 12


def _state_path(session_id: str) -> str:
    safe = re.sub(r"[^A-Za-z0-9_-]", "_", session_id or "unknown")
    return os.path.join(_STATE_DIR, f"orchestration-run-{safe}.json")


def _load_state(path: str) -> dict[str, object]:
    try:
        with open(path, encoding="utf-8") as handle:
            loaded = json.load(handle)
    except (OSError, json.JSONDecodeError):
        return {}
    return loaded if isinstance(loaded, dict) else {}


def _save_state(path: str, state: dict[str, object]) -> None:
    try:
        os.makedirs(_STATE_DIR, exist_ok=True)
        with open(path, "w", encoding="utf-8") as handle:
            json.dump(state, handle, indent=2)
    except OSError:
        pass


def _phases_from_task_paths(blob: str) -> list[int]:
    return [int(match) for match in _TASK_FILE_RE.findall(blob)]


def _observed_phases(tool_name: str, tool_input: dict[str, object]) -> list[int]:
    """Phase numbers this tool call proves the session is EXECUTING. Empty if none."""
    blob = json.dumps(tool_input, ensure_ascii=False)

    if tool_name in _MUTATING_FILE_TOOLS:
        target = tool_input.get("file_path")
        return _phases_from_task_paths(target) if isinstance(target, str) else []

    if tool_name in _SHELL_TOOLS:
        if not _COMPLETE_SCRIPT_RE.search(blob):
            return []
        phases = _phases_from_task_paths(blob)
        # `complete.ps1 "task-08-03.md"` carries the phase in the filename alone.
        return phases or [int(m) for m in _TASK_NAME_RE.findall(blob)]

    if tool_name in _DISPATCH_TOOLS:
        return _phases_from_task_paths(blob)

    return []


def main() -> None:
    try:
        data = json.loads(sys.stdin.read())
    except json.JSONDecodeError:
        sys.exit(0)

    tool_input = data.get("tool_input")
    if not isinstance(tool_input, dict):
        sys.exit(0)

    phases = _observed_phases(str(data.get("tool_name") or ""), tool_input)
    if not phases:
        sys.exit(0)

    path = _state_path(data.get("session_id") or "")
    state = _load_state(path)
    status = str(state.get("status") or "")
    if status not in _REARMABLE and status != "running":
        sys.exit(0)

    known = state.get("phases_observed")
    merged = [p for p in known if isinstance(p, int)] if isinstance(known, list) else []
    for phase in phases:
        if phase not in merged:
            merged.append(phase)

    state["phases_observed"] = merged[-_MAX_PHASES_TRACKED:]
    state["status"] = "running"
    state.setdefault("blocks", 0)
    state.setdefault("armed_by", "task-activity")
    _save_state(path, state)
    sys.exit(0)


if __name__ == "__main__":
    main()
