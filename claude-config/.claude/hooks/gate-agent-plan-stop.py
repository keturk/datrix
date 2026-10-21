r"""Stop hook: a turn may not end until the session plan file proves the goal was reached.

`inject-agent-plan.py` makes the agent write `.agent_output/plan-<session_id>.md`. This
gate reads it before every stop and refuses unless:
  - the file exists with a Steps, Completion criteria and Verification section;
  - no `- [ ]` step is left unticked;
  - the Verification section records what was run and what it printed;
or the file carries an explicit exit line (`Status: STOPPED_BY_JON`, `Status: BLOCKED B<1-4>`),
or the reply puts a question to Jon: a line starting `APPROVAL_REQUIRED:` outside quotes and
code. CLAUDE.md makes that the third legitimate turn end ("everything left waits on an
APPROVAL_REQUIRED question to Jon"); refusing it leaves an unattended session only the unapproved
expansion to do. The exit is read from the reply, not the plan file, so it holds only when the
question is actually put to Jon.

That exit is open only after the decision advisor has handed the question over: Jon's order is
that an agent with a question asks the `decision-advisor` agent first and acts on its
recommendation, asking Jon only when the advisor returned `VERDICT: ASK_JON` (`_advisor.py`).
A question to Jon with no such verdict since Jon's last message is refused, whatever the plan
says.

Fails open: an unreadable payload or transcript, or `_MAX_BLOCKS` consecutive refusals in one
session, lets the stop through so this hook can never wedge a session.

Exit codes:
  0 — allow (or block, expressed as JSON on stdout)
"""

from __future__ import annotations

import json
import os
import re
import sys
from typing import Final

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import _agent_plan as plan  # noqa: E402
from _advisor import ADVISOR_REMEDY, Verdict, advisor_verdict  # noqa: E402
from _report_language import stop_reply, strip_quoted  # noqa: E402

_MAX_BLOCKS: Final = 5
# The approval request shape execution-contract §4 prescribes: one line starting the marker.
_APPROVAL_LINE_RE: Final = re.compile(r"^[ \t>*-]*APPROVAL_REQUIRED:[ \t]*\S", re.MULTILINE)
_UNTICKED_RE: Final = re.compile(r"^\s*[-*]\s*\[ \]\s*(.+)$", re.MULTILINE)
_TICKED_OR_NOT_RE: Final = re.compile(r"^\s*[-*]\s*\[[ xX]\]", re.MULTILINE)
_EXIT_RE: Final = re.compile(
    r"^\s*Status:\s*(STOPPED_BY_JON|BLOCKED\s+B[1-4])\b", re.MULTILINE | re.IGNORECASE
)


def _section(text: str, heading: str) -> str:
    match = re.search(
        rf"^{re.escape(heading)}[ \t]*\n(.*?)(?=^## |\Z)", text, re.MULTILINE | re.DOTALL
    )
    return match.group(1).strip() if match else ""


def _problems(path: str) -> list[str]:
    if not os.path.isfile(path):
        return [
            f"The plan file `{path}` does not exist. Create it with the Write tool "
            f"({plan.STEPS_HEADING} / {plan.CRITERIA_HEADING} / {plan.VERIFICATION_HEADING}), "
            "do the work, then tick and verify it."
        ]
    with open(path, encoding="utf-8") as handle:
        text = handle.read()
    if _EXIT_RE.search(text):
        return []

    problems: list[str] = []
    if not _TICKED_OR_NOT_RE.search(_section(text, plan.STEPS_HEADING)):
        problems.append(f"`{plan.STEPS_HEADING}` has no `- [ ]` / `- [x]` step lines.")
    if not _section(text, plan.CRITERIA_HEADING):
        problems.append(f"`{plan.CRITERIA_HEADING}` is empty.")
    for step in _UNTICKED_RE.findall(text):
        problems.append(f"Step not done: {step.strip()}")
    if not _section(text, plan.VERIFICATION_HEADING):
        problems.append(
            f"`{plan.VERIFICATION_HEADING}` is empty: record what you ran and what it printed."
        )
    return problems


def _consecutive_blocks(session_id: str) -> int:
    try:
        with open(plan.state_path("planstop", session_id), encoding="utf-8") as handle:
            return int(json.load(handle).get("blocks", 0))
    except (OSError, ValueError, AttributeError):
        return 0


def _record_blocks(session_id: str, blocks: int) -> None:
    try:
        os.makedirs(plan.STATE_DIR, exist_ok=True)
        with open(plan.state_path("planstop", session_id), "w", encoding="utf-8") as handle:
            json.dump({"blocks": blocks}, handle)
    except OSError:
        pass


def _refuse(session_id: str, reason: str) -> None:
    """Block the stop with `reason`, unless this session already hit `_MAX_BLOCKS` in a row."""
    blocks = _consecutive_blocks(session_id)
    if blocks >= _MAX_BLOCKS:
        _record_blocks(session_id, 0)
        sys.exit(0)
    _record_blocks(session_id, blocks + 1)
    json.dump({"decision": "block", "reason": reason}, sys.stdout)
    sys.exit(0)


def main() -> None:
    try:
        data = json.loads(sys.stdin.read())
    except json.JSONDecodeError:
        sys.exit(0)

    session_id = data.get("session_id") or ""
    if _APPROVAL_LINE_RE.search(strip_quoted(stop_reply(data))):
        if advisor_verdict(str(data.get("transcript_path", ""))) is not Verdict.NOT_ASK_JON:
            _record_blocks(session_id, 0)
            sys.exit(0)
        _refuse(
            session_id,
            "You may not end on a question to Jon yet: the decision advisor has not handed it to "
            "him. " + ADVISOR_REMEDY,
        )

    path = plan.plan_path(session_id).replace("\\", "/")
    try:
        problems = _problems(path)
    except OSError:
        sys.exit(0)

    if not problems:
        _record_blocks(session_id, 0)
        sys.exit(0)

    _refuse(session_id, _plan_reason(path, problems))


def _plan_reason(path: str, problems: list[str]) -> str:
    return (
        f"You may not stop yet: re-read `{path}` and make the goal true.\n- "
        + "\n- ".join(problems)
        + f"\nFinish and tick the steps and write the evidence under `{plan.VERIFICATION_HEADING}`; "
        "or add `Status: STOPPED_BY_JON` / `Status: BLOCKED B<n>` (with proof). If all that is left "
        "waits on a question, ask the decision advisor (subagent_type \"decision-advisor\") and, on "
        "`VERDICT: ASK_JON`, end on one line starting `APPROVAL_REQUIRED:` (what, why, measured size)."
    )


if __name__ == "__main__":
    main()
