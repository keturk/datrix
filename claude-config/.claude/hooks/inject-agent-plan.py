r"""UserPromptSubmit hook: make the agent write a session plan file before it starts work.

On the first prompt of a session -- and on any later prompt while the file still does not
exist -- the hook injects an instruction to create `.agent_output/plan-<session_id>.md`
listing the steps the task needs and how completion will be judged. `gate-agent-plan-stop.py`
enforces the other half: the turn cannot end until the plan is ticked and verified.

Passive: never blocks the prompt. Exit 0 always.
"""

from __future__ import annotations

import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import _agent_plan as plan  # noqa: E402


def _instruction(path: str) -> str:
    return (
        "SESSION PLAN FILE (required before any other work).\n"
        f"Create `{path}` with the Write tool, as your first action for this task, "
        "containing exactly these sections:\n"
        f"{plan.STEPS_HEADING}\n"
        "  One `- [ ] <step>` line per thing the task needs done (concrete, checkable).\n"
        f"{plan.CRITERIA_HEADING}\n"
        "  The observable end state that makes the task finished (commands to run and the "
        "result that proves it).\n"
        f"{plan.VERIFICATION_HEADING}\n"
        "  Leave empty until the end.\n"
        "While working, tick each step (`- [x]`) as it is done and add steps you discover. "
        "Before you stop for ANY reason, re-read this file, confirm every step is ticked and "
        f"the completion criteria are met, and record in `{plan.VERIFICATION_HEADING}` what you "
        "ran and what it printed. The Stop hook refuses to end the turn otherwise. If the "
        "prompt is only a question, a single step (`- [ ] answer the question`) is enough. "
        "If Jon told you to stop, or a B1-B4 blocker with proof applies, add a line "
        "`Status: STOPPED_BY_JON` or `Status: BLOCKED B<n>` instead of ticking the steps."
    )


def main() -> None:
    try:
        data = json.loads(sys.stdin.read())
    except json.JSONDecodeError:
        sys.exit(0)

    session_id = data.get("session_id") or ""
    path = plan.plan_path(session_id).replace("\\", "/")
    if os.path.isfile(path):
        sys.exit(0)

    json.dump(
        {
            "hookSpecificOutput": {
                "hookEventName": "UserPromptSubmit",
                "additionalContext": _instruction(path),
            }
        },
        sys.stdout,
    )
    sys.exit(0)


if __name__ == "__main__":
    main()
