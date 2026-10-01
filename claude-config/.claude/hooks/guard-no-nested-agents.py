"""PreToolUse(Agent|Task): a subagent may not spawn subagents.

THE RULE
--------
The orchestrating session (the one Jon talks to) may dispatch agents. An agent that
was itself dispatched may not dispatch more: a nested fan-out multiplies token cost
with no added coverage (one such child burned >140k tokens almost entirely on
dispatch overhead) and fragments reporting. Depth is one: the session dispatches,
the agents work.

HOW A SUBAGENT IS RECOGNISED
----------------------------
Hook input carries `agent_id` only when the tool call is made from inside a
subagent. The main session has none. The same field already distinguishes the two
in `guard-full-suite-runs.py` and `record-search-usage.py`.

Exit codes:
  0 -- allow (the main session dispatching)
  2 -- block (a subagent dispatching; stderr becomes feedback to it)
"""

from __future__ import annotations

import json
import sys
from typing import Final

_MESSAGE: Final = (
    "NESTED AGENT BLOCKED — you are a subagent, and subagents may not spawn "
    "subagents.\n\n"
    "Do this work yourself, sequentially, with your own tool calls:\n"
    "  - find a definition or its uses: code-index MCP tools "
    "(find_symbol / find_references / outline / search / find_canonical), then Grep/Glob\n"
    "  - read a large file or a log: ask_files / digest_log, then a ranged Read of "
    "the cited lines\n"
    "  - more work than fits: finish what you can, fix the root cause, and report "
    "the expansion — the orchestrator that dispatched you owns any further fan-out\n\n"
    "There is no override. A nested fan-out multiplies token cost without adding "
    "coverage."
)


def main() -> None:
    try:
        data = json.loads(sys.stdin.read())
    except json.JSONDecodeError:
        sys.exit(0)
    if not data.get("agent_id"):
        sys.exit(0)
    sys.stderr.write(_MESSAGE)
    sys.exit(2)


if __name__ == "__main__":
    main()
