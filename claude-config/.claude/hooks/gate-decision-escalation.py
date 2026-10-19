"""PreToolUse(AskUserQuestion): a question reaches Jon only through the decision advisor.

THE HOLE THIS CLOSES
--------------------
The Stop gates see a question to Jon only when a turn ends on it. An agent that asks
through `AskUserQuestion` never reaches a Stop event: the tool blocks inside the turn,
waiting on a human, and the run halts just as completely.

Jon's order: "When an agent has a question it delegates the question to a Fable agent at
high effort and acts on its recommendation. If that agent cannot recommend anything, then
it asks me." The `decision-advisor` agent (`.claude/agents/decision-advisor.md`) is that
Fable agent; it answers `VERDICT: RECOMMEND` or `VERDICT: ASK_JON`.
`_shared/decision-adjudication-protocol.md` holds the ladder:
  1 INVESTIGATE -> 2 DECIDE -> 3 ADVISOR (Fable) -> 4 ASK JON

WHAT IS AND IS NOT BLOCKED
--------------------------
  - Every `AskUserQuestion`, in every session, is refused until an advisor dispatched
    since Jon's last message returned `VERDICT: ASK_JON` (`_advisor.py` reads the
    transcript). Text in the question payload is not evidence: the verdict must be in an
    advisor's tool result.
  - An `APPROVAL_REQUIRED` question is a question like any other.
  - `ExitPlanMode` is deliberately NOT gated: plan mode is Jon's own explicit choice,
    and blocking the exit from it would trap the agent before it could start working.
  - An unreadable transcript, or `_MAX_BLOCKS` refusals in one session, lets the tool
    through, so the hook can never wedge a session.

Exit codes:
  0 — allow the tool call
  2 — deny; stderr is fed back to Claude, which continues working
"""

from __future__ import annotations

import json
import os
import re
import sys
from typing import Final

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from _advisor import ADVISOR_REMEDY, Verdict, advisor_verdict  # noqa: E402

_STATE_DIR: Final = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".state")

# Generous enough that a real rung-4 is never permanently unreachable, tight enough
# that "ask Jon" cannot become the loop the run settles into.
_MAX_BLOCKS: Final = 5

_MESSAGE: Final = (
    "QUESTION REJECTED — you are handing a question to Jon before the decision advisor has.\n\n"
    "Jon is the LAST rung of the ladder, not the first "
    "(.claude/skills/_shared/decision-adjudication-protocol.md §0):\n\n"
    "  1 INVESTIGATE — read the code, the design doc, the file:line yourself. Most "
    "questions dissolve here; they were missing information, not genuine ties.\n"
    "  2 DECIDE      — if the evidence, a doc or a rule settles it, decide and act. How and "
    "where to build what was asked is always yours (execution-contract §4).\n"
    "  3 ADVISOR     — still a question? " + ADVISOR_REMEDY + "\n"
    "  4 ASK JON     — only after the advisor returned VERDICT: ASK_JON.\n\n"
    "Everything that does not depend on the answer continues in the meantime."
)


def _state_path(session_id: str) -> str:
    safe = re.sub(r"[^A-Za-z0-9_-]", "_", session_id or "unknown")
    return os.path.join(_STATE_DIR, f"ask-blocks-{safe}.json")


def _blocks_so_far(path: str) -> int:
    try:
        with open(path, encoding="utf-8") as handle:
            return int(json.load(handle).get("blocks", 0))
    except (OSError, ValueError, AttributeError):
        return 0


def _record_blocks(path: str, blocks: int) -> None:
    try:
        os.makedirs(_STATE_DIR, exist_ok=True)
        with open(path, "w", encoding="utf-8") as handle:
            json.dump({"blocks": blocks}, handle)
    except OSError:
        pass


def main() -> None:
    try:
        data = json.loads(sys.stdin.read())
    except json.JSONDecodeError:
        sys.exit(0)

    if advisor_verdict(str(data.get("transcript_path", ""))) is not Verdict.NOT_ASK_JON:
        sys.exit(0)

    path = _state_path(str(data.get("session_id") or ""))
    blocks = _blocks_so_far(path)
    if blocks >= _MAX_BLOCKS:
        sys.exit(0)
    _record_blocks(path, blocks + 1)
    sys.stderr.write(_MESSAGE)
    sys.exit(2)


if __name__ == "__main__":
    main()
