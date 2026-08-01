"""PreToolUse(AskUserQuestion): a decision is not an exit either.

THE HOLE THIS CLOSES
--------------------
`gate-orchestration-stop.py` guards the Stop event. But an agent that parks the run by
asking Jon a question never REACHES a Stop event — `AskUserQuestion` blocks inside the
turn, waiting on a human. The run halts just as completely, and no gate sees it.

That is the exact move Jon named: "You don't queue decisions for me. You delegate them
to a Fable agent." Observed instance: three decisions (a nullable field's typing, a
design-doc axis error, an identity-stack wiring choice) handed up mid-run while 112
tasks sat unstarted. One of the three was not even a decision — it was a correction the
agent should have made itself.

`_shared/decision-adjudication-protocol.md` already states the ladder:
  1 INVESTIGATE -> 2 DECIDE -> 3 ADJUDICATE (Fable) -> 4 ASK THE USER
and already says rung 4 is reachable ONLY after a Fable adjudicator returns decision F
(ASK_USER). Nothing enforced it. This hook does.

WHAT IS AND IS NOT BLOCKED
--------------------------
  - Blocked only while a run is actually in flight (`status: running`).
  - Outside a run, the tool is untouched — ordinary clarifying questions are fine.
  - `ExitPlanMode` is deliberately NOT gated: plan mode is Jon's own explicit choice,
    and blocking the exit from it would trap the agent before it could start working.
  - An escape exists for a genuine rung-4: cite the Fable adjudication (`ASK_USER` /
    decision `F`) in the question payload and it passes.
  - After `_MAX_BLOCKS` refusals the hook stands aside, so it can never wedge a session.

Exit codes:
  0 — allow the tool call
  2 — deny; stderr is fed back to Claude, which continues working
"""

import json
import os
import re
import sys
from typing import Final

_REPO_ROOT: Final = "d:/datrix"
_STATE_DIR: Final = os.path.join(_REPO_ROOT, ".claude", "hooks", ".state")

# Generous enough that a real rung-4 is never permanently unreachable, tight enough
# that "ask Jon" cannot become the loop the run settles into.
_MAX_BLOCKS: Final = 5

# Evidence that rung 3 actually happened and returned F (ASK_USER).
_ADJUDICATED_RE: Final = re.compile(
    r"\bASK_USER\b"
    r"|\bfable\b[^.\n]{0,80}\b(?:returned|adjudicat\w*|decided|verdict)\b"
    r"|\b(?:decision|verdict)\s*[:=]\s*\"?F\b",
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


_MESSAGE: Final = (
    "QUESTION REJECTED — an orchestration run is in flight and you are handing a "
    "decision back to Jon.\n\n"
    "The user is the LAST rung of the adjudication ladder, not the first "
    "(.claude/skills/_shared/decision-adjudication-protocol.md §0):\n\n"
    "  1 INVESTIGATE — read the code, the design doc, the file:line yourself. Most "
    "'decisions' dissolve here; they were missing information, not genuine ties.\n"
    "  2 DECIDE      — if the evidence settles it, decide and act. Escalating a "
    "decision you are able to make is as much a failure as stopping. A design doc "
    "citing the wrong axis is not a decision — it is a correction. Make it.\n"
    "  3 ADJUDICATE  — genuinely cannot decide after real investigation? Spawn a "
    "Fable adjudicator (model: \"fable\", effort: \"high\"). Its ruling is BINDING; "
    "you execute it. This is the rung you are skipping.\n"
    "  4 ASK JON     — only once Fable itself returns decision F (ASK_USER).\n\n"
    "Go to rung 3 now. Spawn the adjudicator, take its ruling, and keep executing. "
    "Everything that does not depend on the answer continues in the meantime.\n\n"
    "If Fable has already returned F on this exact question, say so in the question "
    "payload (cite ASK_USER / the Fable ruling) and this gate will pass it through."
)


def main() -> None:
    try:
        data = json.loads(sys.stdin.read())
    except json.JSONDecodeError:
        sys.exit(0)

    path = _state_path(data.get("session_id") or "")
    state = _load_state(path)
    if state.get("status") != "running":
        sys.exit(0)

    tool_input = data.get("tool_input")
    payload = json.dumps(tool_input, ensure_ascii=False) if tool_input is not None else ""
    if _ADJUDICATED_RE.search(payload):
        sys.exit(0)

    blocks = int(state.get("ask_blocks", 0) or 0)
    if blocks >= _MAX_BLOCKS:
        sys.exit(0)

    state["ask_blocks"] = blocks + 1
    _save_state(path, state)
    sys.stderr.write(_MESSAGE)
    sys.exit(2)


if __name__ == "__main__":
    main()
