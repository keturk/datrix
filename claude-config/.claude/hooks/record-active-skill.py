r"""UserPromptSubmit hook: record which skill is active. Passive — never blocks.

`checklist.py` needs to know which skill a turn belongs to so a checklist can be
scoped to one. That information exists only in the prompt, and only at this event.

DELIBERATELY SEPARATE FROM `arm-orchestration-run.py`
----------------------------------------------------
That hook arms the orchestration Stop gate, and its narrowness is load-bearing and
hard-won: it fires for `/task-orchestrator` and NOTHING else, because a broader
signal once armed a planning run, which read the resulting Stop refusal as
authorization and began implementing a phase nobody had scheduled.

This hook must not inherit any of that. It writes to its own state file, arms
nothing, and blocks nothing — recording `skill: operationalize-design` has no
consequence unless a checklist config opts into that name. Keeping the two apart
is what lets skill scoping exist at all without reopening that failure.

Both invocation forms are recognised, as they reach the hook with different text:
  - typed in the CLI            -> `/fix-codegen-azure …`
  - invoked via the Skill tool  -> the EXPANDED skill body, which opens with
    `Base directory for this skill: d:\datrix\.claude\skills\fix-codegen-azure`

A prompt naming no skill CLEARS the record rather than leaving the last one to
rot: a follow-up message is not a fresh invocation of whatever ran an hour ago.

Exit codes:
  0 — always
"""

from __future__ import annotations

import json
import os
import re
import sys
from typing import Final

_REPO_ROOT: Final = "d:/datrix"
_STATE_DIR: Final = os.path.join(_REPO_ROOT, ".claude", "hooks", ".state")

_SKILL_RE: Final = re.compile(
    r"(?:^|[\s\"'(`])/([a-z][a-z0-9-]{2,60})\b"
    r"|[\\/]skills[\\/]([a-z][a-z0-9-]{2,60})\b",
    re.IGNORECASE,
)

# Built-in CLI commands are not skills and must not scope a checklist.
_NOT_SKILLS: Final = frozenset(
    {"help", "clear", "config", "status", "model", "compact", "resume", "cost",
     "login", "logout", "init", "review", "vim", "doctor", "memory", "fast"}
)


def _state_path(session_id: str) -> str:
    safe = re.sub(r"[^A-Za-z0-9_-]", "_", session_id or "unknown")
    return os.path.join(_STATE_DIR, f"skill-{safe}.json")


def _detect(prompt: str) -> str:
    for match in _SKILL_RE.finditer(prompt):
        name = (match.group(1) or match.group(2) or "").lower()
        if name and name not in _NOT_SKILLS:
            return name
    return ""


def main() -> None:
    try:
        data = json.loads(sys.stdin.read())
    except json.JSONDecodeError:
        sys.exit(0)

    prompt = data.get("prompt") or ""
    path = _state_path(data.get("session_id") or "")

    try:
        os.makedirs(_STATE_DIR, exist_ok=True)
        with open(path, "w", encoding="utf-8") as handle:
            json.dump({"skill": _detect(prompt)}, handle, indent=2)
    except OSError:
        pass

    sys.exit(0)


if __name__ == "__main__":
    main()
