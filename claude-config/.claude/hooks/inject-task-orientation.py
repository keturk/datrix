"""PostToolUse(Read) hook: answer a task's ``## Orientation`` block when an agent reads the task file.

An implementer reads its task file first, always. A task can say, in an ``## Orientation`` block,
what the implementer needs to know about code it will NOT edit -- who calls this, how a test builds
that, what this module is for -- and this hook answers it at that moment, so the agent does not read
the files to find out. Measured: 57% of the source and test tokens implementing agents read were on
files they never edited.

Facts (``symbol``, ``refs``, ``outline``, ``canonical``) are exact answers from the code index.
Explanations (``explain``) are a local model's cited reading of the files named, and are marked as
leads. An entry that does not resolve -- a symbol another task renamed -- is reported as a stale
premise, which is information the agent needs before it edits (``tasks.task_orientation``).

Once per task per agent (``.state/task-orientation-<session>-<agent>.json``): a task read again after
a long run is not answered again. Fail-open: a task with no block, a ranged read, a missing index, no
model server -- none changes the read, and any failure leaves the tool result as it was. Every model
request is recorded in the local-model usage log as ``hook:task-orientation``.
"""

import json
import os
import re
import sys
from pathlib import Path
from typing import TYPE_CHECKING, Final

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from _hook_log import LIBRARY_DIR  # noqa: E402
from _local_digest import default_settings  # noqa: E402

if TYPE_CHECKING:
    from shared.local_llm import LocalLlmSettings

CALLER: Final = "hook:task-orientation"
_TASK_FILE: Final = re.compile(r"[\\/]\.tasks[\\/]phase-\d+[\\/](task-\d+-\d+[^\\/]*)\.md$", re.IGNORECASE)
_STATE_DIR: Final = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".state")


def _library() -> None:
    if LIBRARY_DIR not in sys.path:
        sys.path.insert(0, LIBRARY_DIR)


def _state_path(session: str, agent: str) -> str:
    safe = "".join(c for c in f"{session}-{agent}" if c.isalnum() or c in "-_")[:96] or "unknown"
    return os.path.join(_STATE_DIR, f"task-orientation-{safe}.json")


def _told(state: str) -> list[str]:
    try:
        with open(state, encoding="utf-8") as handle:
            told = json.load(handle)
    except (OSError, ValueError):
        return []
    return [str(entry) for entry in told] if isinstance(told, list) else []


def _mark_told(state: str, task: Path) -> None:
    told = [*_told(state), str(task)]  # read before the file is opened for writing, which empties it
    try:
        os.makedirs(_STATE_DIR, exist_ok=True)
        with open(state, "w", encoding="utf-8") as handle:
            json.dump(told, handle)
    except OSError as exc:
        sys.stderr.write(f"inject-task-orientation: could not record the notice in {state}: {exc}\n")


def orientation_for(task: Path, workspace: Path, settings: "LocalLlmSettings") -> str:
    """The resolved ``## Orientation`` of ``task`` as text for an agent; empty when it has none."""
    _library()
    from code_index.session import open_session
    from shared.local_llm import LocalLlmPool
    from shared.local_reading import ReadScope, ask_files
    from tasks.task_orientation import OrientationItem, orientation_lines, resolve_orientation

    lines = orientation_lines(task)
    if not lines:
        return ""
    scope = ReadScope(workspace)
    pool = LocalLlmPool(settings, report=lambda _line: None)

    def ask(item: OrientationItem) -> str:
        return ask_files(scope, pool, list(item.paths), item.question).render()

    session = open_session(workspace)
    try:
        session.refresh()
        resolved = resolve_orientation(lines, session.conn, ask)
    finally:
        session.close()
    match = _TASK_FILE.search(str(task))
    task_id = "-".join(match.group(1).split("-")[:3]) if match else task.stem
    return resolved.render(task_id)


def decide(payload: dict[str, object], workspace: Path, settings: "LocalLlmSettings") -> str:
    """The additionalContext for this Read, or the empty string."""
    tool_input = payload.get("tool_input")
    if str(payload.get("tool_name", "")) != "Read" or not isinstance(tool_input, dict):
        return ""
    offset = tool_input.get("offset")
    if isinstance(offset, int) and offset > 1:
        return ""  # a ranged read of the middle of the file: the agent already has the task
    raw = str(tool_input.get("file_path", ""))
    if not _TASK_FILE.search(raw) or not Path(raw).is_file():
        return ""
    task = Path(raw).resolve()
    state = _state_path(str(payload.get("session_id", "")), str(payload.get("agent_id", "")) or "main")
    if str(task) in _told(state):
        return ""
    text = orientation_for(task, workspace, settings)
    if text:
        _mark_told(state, task)
    return text


def main() -> None:
    try:
        payload = json.loads(sys.stdin.read())
    except (json.JSONDecodeError, OSError):
        sys.exit(0)
    if not isinstance(payload, dict):
        sys.exit(0)
    try:
        _library()
        from shared.venv import get_datrix_root

        context = decide(payload, get_datrix_root(), default_settings(CALLER))
    except Exception as exc:  # a hook must never fail the tool call it observed
        sys.stderr.write(f"inject-task-orientation: skipped: {type(exc).__name__}: {exc}\n")
        sys.exit(0)
    if context:
        print(json.dumps({"hookSpecificOutput": {"hookEventName": "PostToolUse", "additionalContext": context}}))
    sys.exit(0)


if __name__ == "__main__":
    main()
