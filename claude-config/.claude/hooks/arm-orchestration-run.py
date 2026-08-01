"""UserPromptSubmit hook: arm the orchestration stop-gate when a run is launched.

An unattended multi-phase run has exactly one acceptable end state: every task
COMPLETED or provably blocked. The failure this hook exists to prevent is the
overnight run that spent the night on setup, presented a plan, offered to hold
for review, and ended the turn with zero tasks executed.

Prose could not prevent it — the skill already says "Do NOT wait for user
confirmation" (task-orchestrator SKILL.md 2f) and CLAUDE.md already says a report
is not an exit. The agent read both and stopped anyway. So the harness enforces
it instead: this hook records that a run is in flight, and gate-orchestration-stop.py
refuses to let the turn end while the phase still has pending tasks.

ARMING IS NOT LEFT TO THE MODEL. It fires off the user's own prompt, before the
model has produced a token, so an orchestration run cannot start un-armed.
DISARMING is likewise not left to the model — the Stop gate disarms itself only
when phase-status.ps1 reports zero unresolved tasks, or when Jon says stop.

Exit codes:
  0 — always (this hook never blocks a prompt; it only records state)
"""

import json
import os
import re
import sys
from typing import Final

_REPO_ROOT: Final = "d:/datrix"
_STATE_DIR: Final = os.path.join(_REPO_ROOT, ".claude", "hooks", ".state")

# Skills that launch an unattended multi-task run. Each one's contract is
# "finish every task"; each one has ended a turn early at least once.
#
# This list is now a CONVENIENCE, not the primary arming path. Naming a skill is one
# instant at the top of a session, and these runs span days and compactions — a run
# resumed with "keep going" was never armed by it. `observe-task-activity.py` arms the
# gate from the agent's own task-file mutations instead, which no phrasing can miss.
_RUN_SKILLS: Final = (
    "/task-orchestrator",
    "/execute-tasks-parallel",
    "/execute-tasks",
    "/codegen-fix-loop",
    "/opus-work",
    "/fable-work",
)

# `PHASE: 36` / `PHASES: 34, 35, 36` / a full path ending in phase-36
_PHASE_LINE_RE: Final = re.compile(r"^\s*PHASES?\s*:\s*(.+)$", re.IGNORECASE | re.MULTILINE)
_PHASE_NUM_RE: Final = re.compile(r"(?:phase[-_]?)?(\d{1,3})", re.IGNORECASE)

# Jon calling the run off. This has to be narrow in one direction and generous in the
# other, and the old version got the balance backwards: a sentence-initial
# `stop|pause|hold` disarmed the gate for the REST OF THE SESSION, so ordinary mid-run
# steering — "hold on, check the azure module first", "pause - is mypy really needed?",
# "cancel the aws task and continue" — silently switched the enforcement off for the
# next twenty hours, and only a fresh `/task-orchestrator` prompt could switch it back.
#
# Now: an unambiguous directive, or a short message that is plainly one. A long message
# merely CONTAINING the word (Jon's "Why did you stop? ... You don't stop.") is not a
# stop — that message is the opposite of one.
_USER_STOP_RE: Final = re.compile(
    r"^\s*(?:ok(?:ay)?[, ]+)?(?:please\s+)?(?:stop|halt|abort|stand\s+down)\b[\s.!]*$"
    r"|\b(?:stop|halt|abort|cancel|kill|end)\s+(?:the\s+|this\s+|all\s+)*"
    r"(?:run|orchestrat\w*|agents?|wave|phase|everything|execution)\b"
    r"|\bstand\s+down\b"
    r"|\bSTOP\s+RUN\b",
    re.IGNORECASE,
)

# A short message carrying a stop word is a stop, whatever its exact shape ("stop!!",
# "ok stop for now", "enough"). Jon must never have to phrase it just so.
_SHORT_STOP_MAX_CHARS: Final = 40
_STOP_WORD_RE: Final = re.compile(
    r"\b(?:stop|halt|abort|enough|stand\s+down)\b", re.IGNORECASE
)

# The exact inversion that short-message matching would otherwise produce: "You don't
# stop." is 15 characters and contains the word `stop`, so Jon's most emphatic
# ANTI-stop instruction would have been read as an order to stop and would have
# switched the gate off. A negated or second-person `stop` is never a directive.
_ANTI_STOP_RE: Final = re.compile(
    r"\b(?:do\s*n[o']?t|does\s*n[o']?t|never|no|not|why\s+did\s+you|who)\b[^.!?]{0,24}\bstop\b"
    r"|\bkeep\s+(?:going|working)\b"
    r"|\bstop\s+(?:ping)?\b\s*\?"
    r"|\byou\s+(?:don'?t|do\s+not|never)\s+stop\b",
    re.IGNORECASE,
)


def _is_stop_directive(prompt: str) -> bool:
    """True when Jon is calling the run off — one of the two legitimate exits."""
    text = prompt.strip()
    if _ANTI_STOP_RE.search(text):
        return False
    if len(text) <= _SHORT_STOP_MAX_CHARS and _STOP_WORD_RE.search(text):
        return True
    return bool(_USER_STOP_RE.search(text))


def _state_path(session_id: str) -> str:
    safe = re.sub(r"[^A-Za-z0-9_-]", "_", session_id or "unknown")
    return os.path.join(_STATE_DIR, f"orchestration-run-{safe}.json")


def _parse_phases(prompt: str) -> list[int]:
    """Pull phase numbers out of PHASE:/PHASES: lines. Empty list if none given."""
    phases: list[int] = []
    for line in _PHASE_LINE_RE.findall(prompt):
        # Stop at the first comment/annotation so `PHASE: 36  # most common` is clean.
        payload = line.split("#", 1)[0]
        for token in re.split(r"[,\s]+", payload.strip()):
            if not token:
                continue
            match = _PHASE_NUM_RE.search(token.replace("\\", "/").rsplit("/", 1)[-1])
            if match:
                number = int(match.group(1))
                if number not in phases:
                    phases.append(number)
    return phases


def _read(path: str) -> dict[str, object]:
    try:
        with open(path, encoding="utf-8") as handle:
            loaded = json.load(handle)
    except (OSError, json.JSONDecodeError):
        return {}
    return loaded if isinstance(loaded, dict) else {}


def _write(path: str, payload: dict[str, object]) -> None:
    os.makedirs(_STATE_DIR, exist_ok=True)
    with open(path, "w", encoding="utf-8") as handle:
        json.dump(payload, handle, indent=2)


def main() -> None:
    try:
        data = json.loads(sys.stdin.read())
    except json.JSONDecodeError:
        sys.exit(0)

    prompt = data.get("prompt") or ""
    session_id = data.get("session_id") or ""
    path = _state_path(session_id)

    state = _read(path)

    # Jon's word ends a run immediately — it is one of the two legitimate exits.
    if _is_stop_directive(prompt):
        if state:
            state["status"] = "stopped_by_user"
            _write(path, state)
        sys.exit(0)

    # A stop applies to the run Jon stopped, not to the rest of the session. Any later
    # prompt that is NOT itself a stop lifts the latch back to a re-armable state — and
    # likewise gives an exhausted gate a fresh start. Without this, one "hold on" (or
    # one exhausted counter) disabled the enforcement for every hour that followed.
    if state.get("status") in ("stopped_by_user", "gate_exhausted"):
        state["status"] = "idle"
        state["blocks"] = 0
        state["ask_blocks"] = 0
        _write(path, state)

    lowered = prompt.lower()
    skill = next((s for s in _RUN_SKILLS if s in lowered), "")
    if not skill:
        sys.exit(0)

    phases = _parse_phases(prompt)
    _write(
        path,
        {
            "status": "running",
            "skill": skill,
            "phases": phases,
            "phases_observed": state.get("phases_observed", []),
            "session_id": session_id,
            "blocks": 0,
            "ask_blocks": 0,
            # No phase numbers in the prompt (e.g. TASKS: with explicit paths) means
            # the gate cannot verify completion from disk. It degrades to the
            # solicitation guard rather than wedging on an unverifiable condition.
            "verifiable": bool(phases),
        },
    )
    sys.exit(0)


if __name__ == "__main__":
    main()
