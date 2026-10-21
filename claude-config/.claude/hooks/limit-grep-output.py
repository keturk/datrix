"""PreToolUse(Grep) hook: a content search with no ``head_limit`` gets a smaller default one.

Grep's own default is 250 matching lines, and a content search for a common word returns
all 250 -- most of them unrelated -- into the agent's context, where every later turn pays
for them again. This hook rewrites the call's input so a content search without an explicit
``head_limit`` returns at most ``DEFAULT_HEAD_LIMIT`` lines; an agent that needs more says so
with ``head_limit`` (``0`` for unlimited) or pages with ``offset``. Other output modes
(file lists, counts) are small already and pass unchanged.

It only rewrites a search rooted inside the workspace, where Claude Code lets the agent read
without a prompt anyway: the rewrite is answered with ``permissionDecision: allow`` (the
form ``updatedInput`` requires), so it must never be the thing that grants a read the
permission system would have asked about. Passive otherwise: anything it cannot evaluate
exits 0 and the call proceeds as sent.
"""

import json
import os
import sys
from typing import Final

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from _hook_log import WORKSPACE  # noqa: E402

DEFAULT_HEAD_LIMIT: Final = 60
CONTENT_MODE: Final = "content"


def _inside_workspace(path: str, cwd: str) -> bool:
    resolved = os.path.realpath(os.path.join(cwd, path) if path else cwd)
    root = os.path.realpath(WORKSPACE)
    try:
        return os.path.commonpath([os.path.normcase(resolved), os.path.normcase(root)]) == os.path.normcase(root)
    except ValueError:  # different drives on Windows
        return False


def rewritten_input(payload: dict[str, object]) -> dict[str, object]:
    """The Grep input with the default ``head_limit`` added, or an empty dict to leave the call as sent."""
    tool_input = payload.get("tool_input")
    if payload.get("tool_name") != "Grep" or not isinstance(tool_input, dict):
        return {}
    if tool_input.get("output_mode") != CONTENT_MODE or "head_limit" in tool_input:
        return {}
    cwd = str(payload.get("cwd") or os.getcwd())
    if not _inside_workspace(str(tool_input.get("path") or ""), cwd):
        return {}
    return {**tool_input, "head_limit": DEFAULT_HEAD_LIMIT}


def main() -> None:
    try:
        payload = json.loads(sys.stdin.read())
    except (json.JSONDecodeError, OSError):
        sys.exit(0)
    if not isinstance(payload, dict):
        sys.exit(0)
    updated = rewritten_input(payload)
    if not updated:
        sys.exit(0)
    json.dump({
        "hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "permissionDecision": "allow",
            "permissionDecisionReason": (
                f"content search capped at {DEFAULT_HEAD_LIMIT} lines; pass head_limit (0 = all) for more"
            ),
            "updatedInput": updated,
        }
    }, sys.stdout)
    sys.exit(0)


if __name__ == "__main__":
    main()
