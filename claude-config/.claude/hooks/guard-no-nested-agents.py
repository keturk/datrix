"""PreToolUse(Agent|Task): a subagent may not spawn subagents.

THE RULE
--------
The orchestrating session (the one Jon talks to) may dispatch agents. An agent that
was itself dispatched may not dispatch more: a nested fan-out multiplies token cost
with no added coverage (one such child burned >140k tokens almost entirely on
dispatch overhead) and fragments reporting. Depth is one: the session dispatches,
the agents work.

THE ONE AGENT A SUBAGENT MAY CALL
---------------------------------
Jon's order: any agent with a question delegates it to the decision advisor
(`.claude/agents/decision-advisor.md`, Fable at high effort) and acts on its
recommendation. A subagent may therefore dispatch `subagent_type: "decision-advisor"`.
The advisor is a leaf: its definition grants read-only tools and no Agent tool, so the
depth stays bounded at two and no fan-out follows from it.

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
import os
import sys
from typing import Final

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from _advisor import ADVISOR_AGENT  # noqa: E402

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
    "A question you cannot settle from the code and docs is the one exception: put it to "
    f'the decision advisor (subagent_type "{ADVISOR_AGENT}") and act on its recommendation.\n\n'
    "There is no other override. A nested fan-out multiplies token cost without adding "
    "coverage."
)


def main() -> None:
    try:
        data = json.loads(sys.stdin.read())
    except json.JSONDecodeError:
        sys.exit(0)
    if not data.get("agent_id"):
        sys.exit(0)
    tool_input = data.get("tool_input")
    if isinstance(tool_input, dict) and tool_input.get("subagent_type") == ADVISOR_AGENT:
        sys.exit(0)
    sys.stderr.write(_MESSAGE)
    sys.exit(2)


if __name__ == "__main__":
    main()
