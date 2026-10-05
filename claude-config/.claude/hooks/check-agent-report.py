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

When none of the patterns match, a local model reads the report once as a second reader
(`_local_judge.py`) and can block for a security downgrade or an expedient fix -- only at
high confidence, and only with a quote that appears in the report and survives the same
quoting, negation and remediation suppressors. Not for dodges: on its first real day it
was wrong all eight times it called one. It can add a block, never lift one, and with no
model in memory it is silent.

Legitimate exits are preserved. The block is skipped when the final message carries:
  - a blocker code (B1/B2/B3/B4) with proof, or
  - a filed task file path (a defect that was properly FILED), or
  - a findings file path under reports/finding/ (execution-contract §5A), or
  - EXPANSION_REQUIRED (knows the fix, needs the file lock).

Exit codes:
  0 — allow the subagent to stop
  2 — block the stop; stderr is fed back to the subagent, which continues working
"""

import json
import sys

from _local_judge import FAMILY_EXPEDIENT, FAMILY_SECURITY, GATE_SUBAGENT, judge_report
from _report_language import (
    DODGE_REMEDY,
    EXPEDIENT_REMEDY,
    SECURITY_REMEDY,
    carries_forbade_exception,
    carries_proof,
    find_dodge,
    find_expedient,
    find_security_downgrade,
    stop_reply,
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

    text = stop_reply(data)
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
    if dodge:
        _reject(
            f'REPORT REJECTED — you are ending your turn on a dodge: "{dodge}".',
            DODGE_REMEDY,
        )

    # The patterns found nothing: a local model gets one read and blocks only with a
    # quote that stands (see _local_judge.py). A stop already continuing after a block
    # exited above, so it never re-judges.
    judged = judge_report(text, GATE_SUBAGENT)
    if not judged.flagged:
        sys.exit(0)
    remedy = {
        FAMILY_SECURITY: SECURITY_REMEDY,
        FAMILY_EXPEDIENT: EXPEDIENT_REMEDY,
    }[judged.family]
    _reject(
        f'REPORT REJECTED — the local second reader found {judged.family.replace("_", " ")} in other words: '
        f'"{judged.quote}".',
        remedy,
    )


if __name__ == "__main__":
    main()
