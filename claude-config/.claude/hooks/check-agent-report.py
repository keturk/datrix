"""SubagentStop hook: refuse to let a subagent finish on a dodge.

Enforces .claude/skills/_shared/execution-contract.md §7 (banned report vocabulary),
§13 (security is a ranked requirement) and §14 (pressure never buys a lesser fix).

An agent that ends its turn by declaring the problem out of scope, pre-existing,
someone else's, "to be tracked separately" — or by confessing it skipped a check
and ending the turn anyway — WITHOUT either a four-part blocker proof or a filed
task file has not done its job. This hook blocks the stop and sends it back to work.

Two further families are checked, and a proof does NOT lift them: reporting that a
security control was disabled/loosened or a less secure option taken (§13), and
reporting a fix sized to the remaining budget rather than to the defect (§14).
Those describe shipping the wrong work rather than reassigning it, and both leave
a green suite behind — no other check in the harness can see either one.

The vocabulary, the false-positive suppressors, and the remedy text live in
`_report_language.py`, shared with the main-loop gate (`gate-orchestration-stop.py`)
so the two cannot drift apart. They did drift, once, and it mattered: the subagents
were policed and the agent talking to Jon was not.

Legitimate exits are preserved. The block is skipped when the final message carries:
  - a blocker code (B1/B2/B3/B4) with proof, or
  - a filed task file path (a defect that was properly FILED), or
  - EXPANSION_REQUIRED (knows the fix, needs the file lock).

Exit codes:
  0 — allow the subagent to stop
  2 — block the stop; stderr is fed back to the subagent, which continues working
"""

import json
import sys

from _report_language import (
    DODGE_REMEDY,
    EXPEDIENT_REMEDY,
    SECURITY_REMEDY,
    carries_forbade_exception,
    carries_proof,
    find_dodge,
    find_expedient,
    find_security_downgrade,
    last_assistant_text,
)


def _reject(headline: str, remedy: str) -> None:
    sys.stderr.write(f"{headline}\n\n{remedy}")
    sys.exit(2)


def main() -> None:
    try:
        data = json.loads(sys.stdin.read())
    except json.JSONDecodeError:
        sys.exit(0)

    # Never re-block a stop we already blocked — that would loop forever.
    if data.get("stop_hook_active"):
        sys.exit(0)

    text = last_assistant_text(data.get("transcript_path", ""))
    if not text:
        sys.exit(0)

    # §13 and §14 run BEFORE the proof suppressor, and are not lifted by it. A
    # blocker proof answers "whose work is this" — it has nothing to say about a
    # control you weakened or a fix you sized to your budget, and a report can
    # carry a legitimate B1 for one item while shipping a downgrade on another.
    downgrade = find_security_downgrade(text)
    if downgrade and not carries_forbade_exception(text):
        _reject(
            f'REPORT REJECTED — you are reporting a security downgrade: "{downgrade}".',
            SECURITY_REMEDY,
        )

    expedient = find_expedient(text)
    if expedient:
        _reject(
            f'REPORT REJECTED — you are reporting an expedient fix: "{expedient}".',
            EXPEDIENT_REMEDY,
        )

    # A report carrying a real blocker proof / filed task / expansion request is fine.
    if carries_proof(text):
        sys.exit(0)

    dodge = find_dodge(text)
    if not dodge:
        sys.exit(0)

    _reject(
        f'REPORT REJECTED — you are ending your turn on a dodge: "{dodge}".',
        DODGE_REMEDY,
    )


if __name__ == "__main__":
    main()
