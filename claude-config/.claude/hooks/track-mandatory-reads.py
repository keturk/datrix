"""PostToolUse(Read) hook: record that a mandatory post-compaction doc was read.

Half of the gate armed by `post-compact-context.py`. It observes Read calls and
ticks off the required docs as they are actually read — the other half
(`gate-mandatory-reads.py`) refuses to let any edit through until the list is
clear.

Inert outside a post-compaction window: if there is no state file for this
session, this hook does nothing.

Always exits 0 — it observes, it never blocks.
"""

import json
import os
import sys
from typing import Final

_REPO_ROOT: Final = "d:/datrix"
_STATE_DIR: Final = os.path.join(_REPO_ROOT, ".claude", "hooks", ".state")


def _normalize(path: str) -> str:
    return path.replace("\\", "/").lower().rstrip("/")


def main() -> None:
    try:
        data = json.loads(sys.stdin.read())
    except json.JSONDecodeError:
        sys.exit(0)

    if data.get("tool_name") != "Read":
        sys.exit(0)

    session_id = data.get("session_id", "")
    if not session_id:
        sys.exit(0)

    state_path = os.path.join(_STATE_DIR, f"post-compact-{session_id}.json")
    if not os.path.isfile(state_path):
        sys.exit(0)  # no compaction in this session — gate is not armed

    read_path = _normalize(data.get("tool_input", {}).get("file_path", ""))
    if not read_path:
        sys.exit(0)

    try:
        with open(state_path, encoding="utf-8") as handle:
            state = json.load(handle)
    except (OSError, json.JSONDecodeError):
        sys.exit(0)

    already: list[str] = state.get("read", [])
    for entry in state.get("required", []):
        required = entry.get("path", "")
        # The Read path is absolute; the required path is repo-relative.
        if required and read_path.endswith(_normalize(required)) and required not in already:
            already.append(required)

    state["read"] = already
    try:
        with open(state_path, "w", encoding="utf-8") as handle:
            json.dump(state, handle, indent=2)
    except OSError:
        pass

    sys.exit(0)


if __name__ == "__main__":
    main()
