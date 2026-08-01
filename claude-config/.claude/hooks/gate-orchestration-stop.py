"""Stop hook: an orchestration run may not end its turn with work left on the floor.

THE FAILURE THIS EXISTS TO PREVENT
----------------------------------
A 185-task, 13-wave run was launched to execute overnight. By morning: zero tasks
executed. The night went into a readiness audit, and the turn ended on a plan plus
an offer — "if you'd rather I stop at a specific wave, say so and I'll hold there."

Every prose defense was already in place and every one of them lost:
  - CLAUDE.md § Execution Contract: "A report is not an exit."
  - CLAUDE.md: "Left running unattended, the correct end state is 'all items done
    or provably blocked,' never 'stopped politely partway.'"
  - task-orchestrator SKILL.md 2f: "Do NOT wait for user confirmation."
  - task-orchestrator SKILL.md § Multi-Phase Continuation: the closed exit list.

An instruction competes with whatever is in context and can lose. A blocked Stop
cannot be forgotten past. That is the whole design: this is the main-loop twin of
check-agent-report.py, which already does the same job for subagents.

A GATE THAT IS NEVER ARMED IS NOT A GATE
----------------------------------------
The first version armed only when a user prompt literally named one of three skills.
Two weeks of transcripts show `/task-orchestrator` invoked in ~14 sessions and ZERO
state files ever reaching `"status": "running"` — the enforcement described above was
switched off for every one of them. Arming now also happens from the agent's own
task-file mutations (`observe-task-activity.py`), which survives compaction, session
resume, plain-English continuation, and any skill name.

WHAT COUNTS AS DONE IS READ OFF DISK, NOT ASKED OF THE MODEL
-----------------------------------------------------------
The gate runs `phase-status.ps1` for each phase in the run and counts tasks that
are neither COMPLETED nor carrying a B1-B4 blocker proof in their `## How Solved`.
The model cannot talk its way past this and cannot disarm it — the only ways out
are (a) the tasks are actually done, (b) Jon says stop, or (c) the block cap.

FAILING OPEN, DELIBERATELY
--------------------------
If the status script is unavailable, errors, or times out, the gate ALLOWS the
stop. A hook that can wedge a session is worse than the failure it prevents. The
block counter is a second backstop: after _MAX_BLOCKS refusals the gate gives up
and lets the turn end, so a genuinely stuck run is never unkillable.

Exit codes:
  0 — allow the turn to end
  2 — block; stderr is fed back to Claude, which continues working
"""

import json
import os
import re
import subprocess
import sys
from typing import Final

_REPO_ROOT: Final = "d:/datrix"
_STATE_DIR: Final = os.path.join(_REPO_ROOT, ".claude", "hooks", ".state")
_STATUS_SCRIPT: Final = os.path.join(
    _REPO_ROOT, "datrix", "scripts", "tasks", "phase-status.ps1"
)
_LATEST_PHASE_SCRIPT: Final = os.path.join(
    _REPO_ROOT, "datrix", "scripts", "tasks", "latest-phase.ps1"
)
_SNAPSHOT_DIR: Final = os.path.join(_REPO_ROOT, ".tmp", "tasks")

# Backstop against an unkillable session. A 13-wave run legitimately hits this
# gate a handful of times; 40 is far above that and far below "forever".
_MAX_BLOCKS: Final = 40
# The solicitation guard is advisory, so it gets a much tighter leash.
_MAX_SOLICIT_BLOCKS: Final = 2
_STATUS_TIMEOUT_S: Final = 180
_LATEST_PHASE_TIMEOUT_S: Final = 60
# Checking every phase a long run has touched must not outlive the hook's own timeout.
_MAX_PHASES_CHECKED: Final = 6

# Offering to pause is the specific move that ended the overnight run. It is
# banned mid-run regardless of how politely it is phrased.
_SOLICIT_RE: Final = re.compile(
    r"(?:"
    r"shall i (?:continue|proceed|go on|keep going)"
    r"|(?:would you like|do you want) me to (?:continue|proceed|start|keep going)"
    r"|should i (?:continue|proceed|start|keep going)"
    r"|say so and i'?ll (?:hold|stop|pause|wait)"
    r"|if you'?d (?:rather|prefer) i (?:stop|hold|pause|wait)"
    r"|let me know (?:if|whether) (?:you'?d like|you want|i should)"
    r"|(?:i'?ll |i will )?(?:hold|wait|pause) (?:here|for your|until you)"
    r"|awaiting your (?:go[- ]ahead|confirmation|approval|response)"
    r"|before i (?:continue|proceed)[, ]"
    r")",
    re.IGNORECASE,
)

# Quoting the banned phrase is not committing it. An agent writing up the rule
# ("never end on 'shall I continue?'") or citing the skill text must not trip the
# guard — a rule that punishes its own documentation teaches agents not to
# document it. Fenced blocks, inline code, and double/curly-quoted spans are
# stripped before matching, so only the agent's own unquoted speech counts.
# (This gate caught its own author doing exactly this on the turn it shipped.)
_QUOTED_SPAN_RE: Final = re.compile(
    r"```.*?```"  # fenced code
    r"|`[^`\n]*`"  # inline code
    r"|\"[^\"\n]*\""  # straight double quotes
    r"|“[^”\n]*”",  # curly double quotes
    re.DOTALL,
)


def _strip_quoted(text: str) -> str:
    """Blank out quoted and code spans so cited phrases are not read as speech."""
    return _QUOTED_SPAN_RE.sub(" ", text)


_BLOCKER_CODE_RE: Final = re.compile(
    r"\bB[1-4]\b\s*[:\-\u2014]?\s*"
    r"(?:MISSING_ACCESS|UNDECIDABLE|USER_FORBADE|FENCED_SURFACE)"
    r"|\bblocker_code\b\s*[:=]\s*[\"']?B[1-4]",
    re.IGNORECASE,
)


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


def _last_assistant_text(transcript_path: str) -> str:
    """Concatenated text of the final assistant message, or '' if unreadable."""
    try:
        with open(transcript_path, encoding="utf-8") as handle:
            lines = handle.readlines()
    except OSError:
        return ""

    for line in reversed(lines):
        try:
            entry = json.loads(line)
        except json.JSONDecodeError:
            continue
        if entry.get("type") != "assistant":
            continue
        content = entry.get("message", {}).get("content", [])
        if isinstance(content, str):
            return content
        parts = [
            block.get("text", "")
            for block in content
            if isinstance(block, dict) and block.get("type") == "text"
        ]
        text = "\n".join(parts).strip()
        if text:
            return text
    return ""


def _phase_snapshot(phase: int) -> dict[str, object] | None:
    """Run phase-status.ps1 and return its JSON. None on any failure (fail open)."""
    if not os.path.isfile(_STATUS_SCRIPT):
        return None
    os.makedirs(_SNAPSHOT_DIR, exist_ok=True)
    out_path = os.path.join(_SNAPSHOT_DIR, f"phase-{phase:02d}-stopgate.json")
    try:
        subprocess.run(
            [
                "powershell",
                "-NoProfile",
                "-NonInteractive",
                "-File",
                _STATUS_SCRIPT,
                str(phase),
                "-Output",
                out_path,
            ],
            capture_output=True,
            timeout=_STATUS_TIMEOUT_S,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    try:
        # PowerShell's JSON output is frequently BOM-prefixed.
        with open(out_path, encoding="utf-8-sig") as handle:
            loaded = json.load(handle)
    except (OSError, json.JSONDecodeError):
        return None
    return loaded if isinstance(loaded, dict) else None


def _latest_phase() -> list[int]:
    """The highest phase on disk, as a last-resort target. Empty list on any failure."""
    if not os.path.isfile(_LATEST_PHASE_SCRIPT):
        return []
    try:
        result = subprocess.run(
            ["powershell", "-NoProfile", "-NonInteractive", "-File", _LATEST_PHASE_SCRIPT],
            capture_output=True,
            text=True,
            timeout=_LATEST_PHASE_TIMEOUT_S,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return []
    match = re.search(r"\d{1,3}", result.stdout or "")
    return [int(match.group(0))] if match else []


def _target_phases(state: dict[str, object]) -> list[int]:
    """Which phases to hold this run to, in descending order of authority.

    1. `phases` — parsed from Jon's own `PHASE:` line when he named one.
    2. `phases_observed` — phases whose task files this session actually mutated.
       This is what rescues every run that was never launched by name: resumed after a
       compaction, continued with "keep going", or already in flight when the hooks
       changed.
    3. `latest-phase.ps1` — the phase on disk, when the session is armed but neither of
       the above says which.
    """
    for key in ("phases", "phases_observed"):
        value = state.get(key)
        if isinstance(value, list):
            phases = [p for p in value if isinstance(p, int)]
            if phases:
                return phases
    return _latest_phase()


def _carries_blocker_proof(task_path: str) -> bool:
    """True if the task file's How Solved records a B1-B4 code.

    Validity of the four-part proof is the orchestrator's call, not this hook's.
    The gate only needs to know the task has a recorded terminal outcome so a
    legitimately blocked task cannot wedge the run forever.
    """
    try:
        with open(task_path, encoding="utf-8", errors="replace") as handle:
            text = handle.read()
    except OSError:
        return False
    lowered = text.lower()
    marker = lowered.find("## how solved")
    if marker == -1:
        return False
    return bool(_BLOCKER_CODE_RE.search(text[marker:]))


def _unresolved(phase: int) -> tuple[int, int, list[str]] | None:
    """(unresolved, total, sample ids) for a phase, or None if unverifiable."""
    snapshot = _phase_snapshot(phase)
    if snapshot is None:
        return None
    tasks = snapshot.get("tasks")
    if not isinstance(tasks, list):
        return None

    pending: list[str] = []
    for task in tasks:
        if not isinstance(task, dict) or task.get("is_completed"):
            continue
        path = task.get("task_path")
        if isinstance(path, str) and _carries_blocker_proof(path):
            continue
        task_id = task.get("task_id")
        pending.append(task_id if isinstance(task_id, str) else "?")
    return len(pending), len(tasks), pending[:8]


_CONTRACT: Final = (
    "There is no third exit. A run ends when every task is COMPLETED or carries a "
    "valid B1-B4 blocker proof, or when Jon tells you to stop. Not when the plan "
    "looks good, not at a green phase boundary, not because the run is long or "
    "expensive, and NEVER on an offer to hold for review.\n\n"
    "If your draft reply contains a 'remaining', 'next up', or 'shall I continue' "
    "section: delete it and dispatch the next wave instead.\n\n"
    "Resume where you left off — Step 3 of the task-orchestrator skill. If the "
    "wave plan is already computed, spawn the next wave's agents now."
)


def _block(state: dict[str, object], path: str, message: str) -> None:
    state["blocks"] = int(state.get("blocks", 0) or 0) + 1
    _save_state(path, state)
    sys.stderr.write(message)
    sys.exit(2)


def main() -> None:
    try:
        data = json.loads(sys.stdin.read())
    except json.JSONDecodeError:
        sys.exit(0)

    session_id = data.get("session_id") or ""
    path = _state_path(session_id)
    state = _load_state(path)
    text = _last_assistant_text(data.get("transcript_path", ""))

    if state.get("status") in ("stopped_by_user", "gate_exhausted"):
        # Jon's word is one of the two legitimate exits, and an exhausted gate has
        # already given up. Neither gets second-guessed by the advisory guard.
        sys.exit(0)

    if state.get("status") != "running":
        # Outside a tracked run the gate is advisory only: it refuses an explicit
        # offer to pause mid-work, twice at most, then stays out of the way.
        solicit_blocks = int(state.get("solicit_blocks", 0) or 0)
        if text and _SOLICIT_RE.search(_strip_quoted(text)) and solicit_blocks < _MAX_SOLICIT_BLOCKS:
            state["solicit_blocks"] = solicit_blocks + 1
            state.setdefault("status", "idle")
            _save_state(path, state)
            sys.stderr.write(
                "STOP REJECTED — you are ending the turn by asking permission to "
                "continue your own work.\n\n" + _CONTRACT
            )
            sys.exit(2)
        sys.exit(0)

    blocks = int(state.get("blocks", 0) or 0)
    if blocks >= _MAX_BLOCKS:
        state["status"] = "gate_exhausted"
        _save_state(path, state)
        sys.exit(0)

    phases = _target_phases(state)[:_MAX_PHASES_CHECKED]

    if not phases:
        # No phase numbers to verify against (a TASKS: invocation). Fall back to
        # refusing the one move that caused the original failure.
        if text and _SOLICIT_RE.search(_strip_quoted(text)):
            _block(
                state,
                path,
                "STOP REJECTED — an orchestration run is in flight and you are "
                "ending the turn on an offer to pause.\n\n" + _CONTRACT,
            )
        sys.exit(0)

    totals: list[str] = []
    unresolved_total = 0
    sample: list[str] = []
    verified_any = False

    for phase in phases:
        result = _unresolved(phase)
        if result is None:
            continue
        verified_any = True
        count, total, ids = result
        unresolved_total += count
        sample.extend(ids)
        totals.append(f"  phase {phase:02d}: {total - count}/{total} resolved, {count} pending")

    if not verified_any:
        # Could not read disk truth. Fail open rather than risk a wedge.
        sys.exit(0)

    if unresolved_total == 0:
        state["status"] = "complete"
        _save_state(path, state)
        sys.exit(0)

    # The block cap exists to stop a WEDGED run, not a slow one. A run that is still
    # closing tasks has its budget restored, so `_MAX_BLOCKS` counts consecutive
    # refusals WITHOUT progress. Otherwise a long, healthy 190-task run simply spends
    # its 40 blocks and is handed a free exit at the 41st — the very outcome the gate
    # was built to prevent.
    previous = state.get("last_unresolved")
    if isinstance(previous, int) and unresolved_total < previous:
        state["blocks"] = 0
    state["last_unresolved"] = unresolved_total

    listed = ", ".join(sample[:8])
    more = f" (+{unresolved_total - len(sample[:8])} more)" if unresolved_total > 8 else ""
    _block(
        state,
        path,
        f"STOP REJECTED — the orchestration run is not finished. "
        f"{unresolved_total} task(s) are still neither COMPLETED nor carrying a "
        f"B1-B4 blocker proof.\n\n"
        + "\n".join(totals)
        + f"\n\nPending: {listed}{more}\n\n"
        + _CONTRACT
        + "\n\n(Ground truth: phase-status.ps1, read off disk. This gate does not "
        "read your summary and cannot be argued with. Jon can end the run at any "
        "time by telling you to stop.)",
    )


if __name__ == "__main__":
    main()
