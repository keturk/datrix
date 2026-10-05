"""Shared helpers for the session plan file (`inject-agent-plan.py`, `gate-agent-plan-stop.py`).

Every session owns exactly one plan file, `D:/datrix/.agent_output/plan-<session_id>.md`,
holding the steps the task needs and how it will be judged complete. The UserPromptSubmit
hook tells the agent to write it; the Stop hook refuses to end the turn until the file
exists and every step in it is ticked and verified.
"""

from __future__ import annotations

import os
import re
from typing import Final

REPO_ROOT: Final = "d:/datrix"
PLAN_DIR: Final = os.path.join(REPO_ROOT, ".agent_output")
STATE_DIR: Final = os.path.join(REPO_ROOT, ".claude", "hooks", ".state")

STEPS_HEADING: Final = "## Steps"
CRITERIA_HEADING: Final = "## Completion criteria"
VERIFICATION_HEADING: Final = "## Verification"


def safe_id(session_id: str) -> str:
    return re.sub(r"[^A-Za-z0-9_-]", "_", session_id or "unknown")


def plan_path(session_id: str) -> str:
    return os.path.join(PLAN_DIR, f"plan-{safe_id(session_id)}.md")


def state_path(kind: str, session_id: str) -> str:
    return os.path.join(STATE_DIR, f"{kind}-{safe_id(session_id)}.json")
