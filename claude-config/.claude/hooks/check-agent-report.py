"""SubagentStop hook: refuse to let a subagent finish on a dodge.

Enforces .claude/skills/_shared/execution-contract.md §7 (banned report vocabulary).

An agent that ends its turn by declaring the problem out of scope, pre-existing,
someone else's, "to be tracked separately" — or by confessing it skipped a check
and ending the turn anyway — WITHOUT either a four-part blocker proof or a filed
task file has not done its job. This hook blocks the stop and sends it back to work.

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
    carries_proof,
    find_dodge,
    last_assistant_text,
)


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

    # A report carrying a real blocker proof / filed task / expansion request is fine.
    if carries_proof(text):
        sys.exit(0)

    dodge = find_dodge(text)
    if not dodge:
        sys.exit(0)

    sys.stderr.write(
        f'REPORT REJECTED — you are ending your turn on a dodge: "{dodge}".\n\n'
        + DODGE_REMEDY
    )
    sys.exit(2)


if __name__ == "__main__":
    main()
