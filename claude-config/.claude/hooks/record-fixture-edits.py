r"""PostToolUse hook: record the fixture projects and test files a session edits. Passive.

`guard-test-run-discipline.py` refuses a test run that follows an edit of a fixture project with
no probe since, and `guard-rewrite-size.py` refuses the edit that takes a session past
`MAX_TEST_FILES_BEFORE_SIZING` distinct test files without a sizing consult. Both read the record
this hook keeps (`_fixture_probe.py`). It arms nothing and blocks nothing.

Exit codes:
  0 - always
"""

from __future__ import annotations

import json
import sys
from typing import Any

from _fixture_probe import is_test_file, normalise, project_dir, read_edits, write_edits


def _edited_paths(tool_input: Any) -> list[str]:
    """Every file path an Edit / Write / NotebookEdit / edit_lines call names."""
    if not isinstance(tool_input, dict):
        return []
    paths = [tool_input.get("file_path"), tool_input.get("notebook_path")]
    edits = tool_input.get("edits")
    if isinstance(edits, list):
        paths.extend(edit.get("file_path") for edit in edits if isinstance(edit, dict))
    return [normalise(path) for path in paths if isinstance(path, str) and path]


def main() -> None:
    try:
        data = json.loads(sys.stdin.read())
    except json.JSONDecodeError:
        return
    paths = _edited_paths(data.get("tool_input"))
    if not paths:
        return
    session_id = str(data.get("session_id") or "")
    edits = read_edits(session_id)
    changed = False
    for path in paths:
        directory = project_dir(path)
        if directory is not None and directory not in edits["projects"]:
            edits["projects"].append(directory)
            changed = True
        if is_test_file(path) and path not in edits["tests"]:
            edits["tests"].append(path)
            changed = True
    if changed:
        write_edits(session_id, edits)


if __name__ == "__main__":
    try:
        main()
    except Exception:  # noqa: BLE001 - a recorder must never wedge a session
        pass
    sys.exit(0)
