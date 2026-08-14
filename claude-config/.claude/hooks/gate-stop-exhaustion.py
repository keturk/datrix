"""Stop hook: a turn may not end on "I ran out of context", on a handover, on a
security downgrade, or on an expedient fix.

THE FAILURE THIS EXISTS TO PREVENT
----------------------------------
Mid-task, with the next diagnostic step identified and two tool calls away, a
turn ended like this:

    "Out of runway to keep debugging this safely, so here is exactly where it
     stands. ... **Where it stops:** ... **Remaining after that:** ..."

Nothing was blocked. Nothing was forbidden. The model asserted a resource state
it cannot measure -- there is no context meter it can read -- and Jon cannot
check it either. That is what makes this the most expensive excuse available:
it is unfalsifiable from BOTH sides, it sounds like engineering prudence, and
it arrives wearing a tidy summary that reads like progress.

Every prose defense was already in place and every one of them lost:
  - CLAUDE.md: "Running low on context is not an exit either. Context is
    compacted and the work continues ... It is the most seductive form of
    quitting because it sounds like engineering prudence, it is unfalsifiable
    from Jon's side, and it can be written in the same breath as a tidy summary."
  - CLAUDE.md: "A report is not an exit. If your draft reply contains a
    'remaining', 'still to fix', or 'next up' section, you are not finished."

Both rules were in the always-loaded file, and the compaction hook had
re-injected the execution contract verbatim earlier in that same session. The
model quoted the first rule back to Jon one turn later. Prose in context
competes with everything else in context and can lose; a blocked Stop cannot be
forgotten past. Per CLAUDE.md's own instruction -- "Adding a check? Put it in a
hook or a test, not in this file" -- this is where the rule belongs.

TWO MORE FAMILIES, FOR THE SAME REASON
--------------------------------------
Execution-contract §13 (security is a ranked requirement: never propose or
implement a less secure option when a more secure one exists; never weaken a
control to turn a check green) and §14 (the size of a fix is set by the defect,
never by remaining context/budget/patience) have exactly the same enforcement
problem as the two above: they are prose, prose competes with everything else in
context, and both failures leave a GREEN SUITE behind. A weakened control and a
"quick fix for now" are invisible to every test in the repo -- the suite proves
the code does what it was written to do and has no opinion on whether that was
the right thing to write.

Unlike the dodge families, a blocker proof does NOT lift these: a proof answers
"whose work is this", which is not the question. The one exception is §13.1's
single open door, B3 USER_FORBADE.

WHY A SEPARATE HOOK FROM gate-orchestration-stop.py
---------------------------------------------------
That gate is armed ONLY by an explicit `/task-orchestrator` invocation and is
deliberately inert otherwise. This failure happened in an ordinary session, on
an ordinary task, with no orchestrator anywhere near it -- exactly the gap.
The dodge vocabulary is shared (`_report_language.py`) so the two gates cannot
drift apart.

FALSE POSITIVES ARE THE EXPENSIVE FAILURE
-----------------------------------------
A gate that fires on innocent prose teaches evasive phrasing, which costs more
than the dodge did. Four suppressors:

  1. JON ASKED. "Exactly two things end a turn: the task is FINISHED, or Jon
     tells you to stop." When Jon's own last turn said stop/pause, or asked a
     question ("why did you stop?", "what's left?", "explain"), ending the turn
     is CORRECT. Answering a direct question is not a handover.
  2. QUOTED SPANS are blanked upstream, so quoting this very rule -- which the
     model does when discussing it -- is documenting, not doing.
  3. NEGATION is suppressed upstream: "nothing remaining", "not out of runway".
  4. PROOF MARKERS: a real B1-B4 blocker proof or a filed task path is a
     legitimate exit and suppresses the check entirely.

FAILING OPEN, DELIBERATELY
--------------------------
Any exception, unreadable transcript, or missing field ALLOWS the stop. A hook
that can wedge a session is worse than the failure it prevents. After
_MAX_BLOCKS consecutive refusals the gate gives up, so a genuinely stuck turn is
never unkillable.

Exit codes:
  0 - allow the turn to end
  2 - block; stderr is fed back to Claude, which continues working
"""

from __future__ import annotations

import json
import os
import sys
import tempfile
from typing import Final

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from _report_language import (  # noqa: E402
    EXPEDIENT_REMEDY,
    SECURITY_REMEDY,
    carries_forbade_exception,
    carries_proof,
    find_expedient,
    find_exhaustion,
    find_handover_section,
    find_security_downgrade,
    last_assistant_text,
    last_user_text,
    user_asked_to_pause_or_report,
)

_MAX_BLOCKS: Final = 6
_STATE_DIR: Final = os.path.join(tempfile.gettempdir(), "datrix-stop-exhaustion")

_EXHAUSTION_REMEDY: Final = (
    "You cannot measure your remaining context, and neither can Jon. Stating it "
    "as a reason is a claim about system state that no one can check -- the same "
    "failure as reporting a test passed without running it.\n\n"
    "What actually happens when context fills: it is COMPACTED. Earlier turns "
    "become a summary, the governing docs are re-injected, and the session "
    "continues. Nothing terminates. What survives is the code you landed and the "
    "tests you left green. The handover paragraph you were about to write is the "
    "one artifact that does NOT survive.\n\n"
    "So spend what is left on the FIX: write the smallest correct change, run "
    "its check, keep going. If files fell out of context, re-read them -- that "
    "is two tool calls, not a blocker.\n\n"
    "'Running low on context' is not on the B1-B4 list and never will be."
)

_HANDOVER_REMEDY: Final = (
    "A report is not an exit. That section IS the work you have not done.\n\n"
    "Delete it and go do those items. When Jon authorizes a set of items, the "
    "turn ends when EVERY item is fixed-and-proven -- never at the boundary "
    "between items, and never at a natural-feeling pause. A green checkmark and "
    "a tidy summary are a byproduct of progress, not the deliverable.\n\n"
    "If one of those items is genuinely blocked, prove it: verbatim error text, "
    "the fix you actually wrote and ran (file:line), why it failed, and the "
    "B1-B4 code. Analysis alone is not an attempt."
)


def _state_path(session_id: str) -> str:
    safe = "".join(c for c in session_id if c.isalnum() or c in "-_")[:64] or "unknown"
    return os.path.join(_STATE_DIR, f"{safe}.json")


def _block_count(path: str) -> int:
    try:
        with open(path, encoding="utf-8") as handle:
            return int(json.load(handle).get("blocks", 0))
    except (OSError, ValueError, json.JSONDecodeError):
        return 0


def _record_block(path: str, count: int) -> None:
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as handle:
            json.dump({"blocks": count}, handle)
    except OSError:
        pass


def _clear(path: str) -> None:
    try:
        os.remove(path)
    except OSError:
        pass


def main() -> None:
    try:
        data = json.loads(sys.stdin.read())
    except (json.JSONDecodeError, ValueError):
        sys.exit(0)

    transcript = data.get("transcript_path", "")
    state = _state_path(str(data.get("session_id", "")))

    text = last_assistant_text(transcript)
    if not text:
        sys.exit(0)

    # Suppressor 1, before anything else: Jon set the terms of this turn.
    if user_asked_to_pause_or_report(last_user_text(transcript)):
        _clear(state)
        sys.exit(0)

    # §13 / §14 run BEFORE the proof suppressor and are not lifted by it. A
    # blocker proof answers "whose work is this"; it says nothing about a control
    # that was weakened or a fix that was sized to the budget. The one door §13.1
    # leaves open is B3 USER_FORBADE, and that one IS checked.
    downgrade = find_security_downgrade(text)
    if downgrade and carries_forbade_exception(text):
        downgrade = ""
    expedient = find_expedient(text)

    # Suppressor 4: a proven blocker or a filed task is a legitimate exit.
    if carries_proof(text) and not downgrade and not expedient:
        _clear(state)
        sys.exit(0)

    exhaustion = find_exhaustion(text)
    handover = find_handover_section(text)
    if not exhaustion and not handover and not downgrade and not expedient:
        _clear(state)
        sys.exit(0)

    blocks = _block_count(state)
    if blocks >= _MAX_BLOCKS:
        # Never unkillable: a turn refused this many times is stuck on
        # something this gate cannot see, and holding it hostage is worse.
        _clear(state)
        sys.exit(0)
    _record_block(state, blocks + 1)

    if downgrade:
        headline = f"STOP REJECTED - the turn reports a security downgrade: {downgrade!r}"
        remedy = SECURITY_REMEDY
    elif expedient:
        headline = f"STOP REJECTED - the turn reports an expedient fix: {expedient!r}"
        remedy = EXPEDIENT_REMEDY
    elif exhaustion:
        headline = f"STOP REJECTED - the turn ends on a context-exhaustion claim: {exhaustion!r}"
        remedy = _EXHAUSTION_REMEDY
    else:
        headline = f"STOP REJECTED - the turn ends on a handover section: {handover!r}"
        remedy = _HANDOVER_REMEDY

    print(
        f"{headline}\n\n{remedy}\n\n"
        "If this gate is genuinely wrong for this situation, say so to Jon "
        "explicitly and explain why -- do not rephrase around it. The rule is "
        "the behavior, not the wordlist.",
        file=sys.stderr,
    )
    sys.exit(2)


if __name__ == "__main__":
    main()
