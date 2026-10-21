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
        f"First, Write `{path}` with `{plan.STEPS_HEADING}` (`- [ ] <step>` lines), "
        f"`{plan.CRITERIA_HEADING}` (what proves it done) and an empty "
        f"`{plan.VERIFICATION_HEADING}`. Tick steps as done; before stopping, fill "
        f"`{plan.VERIFICATION_HEADING}` with what you ran and what it printed, or add "
        "`Status: STOPPED_BY_JON` / `Status: BLOCKED B<n>`. The Stop hook enforces it. "
        "A question needs one step: `- [ ] answer the question`."
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
