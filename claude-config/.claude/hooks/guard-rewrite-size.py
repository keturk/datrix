r"""PreToolUse(Write|Edit|NotebookEdit) hook: a mass rewrite of tests is sized before it is done.

A session that converts or rewrites dozens of test files has left the task it was given: that is
growth, and growth is measured and put to the decision advisor first (CLAUDE.md, "Scope is what
was asked"). Rewriting committed azure tests onto new fixture projects ran to dozens of files
before anyone had counted them.

The edit that would take a session past `MAX_TEST_FILES_BEFORE_SIZING` distinct test files is
refused until a `decision-advisor` has been dispatched in the session with the count (the census,
times the rate measured so far) and its recommendation. `record-fixture-edits.py` keeps the list
of files edited; editing a file already on it is never refused. Jon's `DATRIX_NO_SUBAGENTS=1`
means no advisor can be consulted, so nothing is refused then. Fails open.

Exit codes:
  0 - allow
  2 - block (stderr becomes feedback to Claude)
"""

from __future__ import annotations

import json
import sys
from typing import Any, Final

from _advisor import ADVISOR_AGENT, advisor_consulted, subagents_forbidden
from _fixture_probe import is_test_file, normalise, read_edits

MAX_TEST_FILES_BEFORE_SIZING: Final = 25


def _paths(tool_input: Any) -> list[str]:
    if not isinstance(tool_input, dict):
        return []
    found = [tool_input.get("file_path"), tool_input.get("notebook_path")]
    return [normalise(path) for path in found if isinstance(path, str) and path]


def main() -> None:
    try:
        data = json.loads(sys.stdin.read())
    except json.JSONDecodeError:
        sys.exit(0)
    paths = [path for path in _paths(data.get("tool_input")) if is_test_file(path)]
    if not paths or subagents_forbidden():
        sys.exit(0)
    recorded = read_edits(str(data.get("session_id") or ""))["tests"]
    if all(path in recorded for path in paths) or len(recorded) < MAX_TEST_FILES_BEFORE_SIZING:
        sys.exit(0)
    if advisor_consulted(str(data.get("transcript_path") or "")) is not False:
        sys.exit(0)
    sys.stderr.write(
        f"BLOCKED: this session has edited {len(recorded)} distinct test files and no size was put "
        "to the decision advisor. A rewrite this wide is growth beyond the failing tests.\n"
        "Count what is left (the scan's item count times the rate measured so far, in tokens and "
        f'agent minutes) and dispatch the Agent tool with subagent_type "{ADVISOR_AGENT}": the '
        "question, that count, the options and your recommendation. On `VERDICT: RECOMMEND` act on "
        "it and record it; only on `VERDICT: ASK_JON` ask Jon."
    )
    sys.exit(2)


if __name__ == "__main__":
    try:
        main()
    except SystemExit:
        raise
    except Exception:  # noqa: BLE001 - a guard must never wedge a session
        sys.exit(0)
