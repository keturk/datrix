r"""PreToolUse hook: every Write/Edit guard judges an ``edit_lines`` call before it runs.

``edit_lines`` (the ``datrix-edit`` MCP server) changes files without an ``old_string``, so the
guards written for ``Edit`` would never see it. This hook plans the call with the server's own
code (``datrix_scripts.line_edits.plan_edits``, nothing written), turns each file's change into
the ``Edit`` payload a guard expects -- ``old_string`` -> ``new_string`` over the lines it touches
(``guard_edit``) -- and runs every hook that ``settings.json`` registers on PreToolUse for
``Edit``, with the same session fields. The guard set is read from the registration, so a guard
added for Edit applies here with no change to this file.

The first refusal wins: a guard's exit 2 is passed on as this hook's exit 2 (its message
prefixed with the file), and a guard's JSON ``deny``/``ask``/``block`` answer is passed on as it
is. An edit the planner itself refuses (a wrong hash, a bad range) is allowed through: the server
refuses it with the lines now there, and writes nothing.

Fails CLOSED when the planner cannot be loaded or a guard cannot be run: unlike the other hooks,
this one is the only way the guards see these edits, and refusing costs one tool call -- Edit
still works.

Exit codes:
  0 — allow (or a guard's JSON refusal on stdout)
  2 — block (message on stderr)
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from pathlib import Path
from typing import Final

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from _hook_log import WORKSPACE, add_scripts_lib_to_path  # noqa: E402
from _tool_names import LINE_EDIT_TOOL  # noqa: E402

SETTINGS: Final = os.path.join(WORKSPACE, ".claude", "settings.json")
GUARDED_TOOL: Final = "Edit"
DEFAULT_TIMEOUT_SECONDS: Final = 60
REFUSING_DECISIONS: Final = frozenset({"deny", "ask"})
_OWN_NAME: Final = os.path.basename(__file__)


def _refuse(message: str) -> None:
    print(f"edit_lines: {message}", file=sys.stderr)
    sys.exit(2)


def edit_guards(settings_path: str = SETTINGS) -> list[tuple[str, int]]:
    """(command, timeout) of every PreToolUse hook registered for Edit, in registration order."""
    with open(settings_path, encoding="utf-8") as handle:
        settings = json.load(handle)
    guards: list[tuple[str, int]] = []
    for block in settings.get("hooks", {}).get("PreToolUse", []):
        matcher = str(block.get("matcher", ""))
        if not matcher or not re.fullmatch(matcher, GUARDED_TOOL):
            continue
        for hook in block.get("hooks", []):
            command = str(hook.get("command", ""))
            if command and _OWN_NAME not in command:
                guards.append((command, int(hook.get("timeout", DEFAULT_TIMEOUT_SECONDS))))
    return guards


def edit_payloads(data: dict[str, object]) -> list[tuple[str, dict[str, object]]]:
    """(shown path, Edit-shaped payload) per file the call changes; [] when the planner refuses it."""
    add_scripts_lib_to_path()
    from datrix_scripts.line_edits import LineEditError, guard_edit, plan_edits
    from datrix_scripts.paths import WORKSPACE_DIR

    tool_input = data.get("tool_input")
    edits = tool_input.get("edits") if isinstance(tool_input, dict) else None
    try:
        changes = plan_edits(Path(WORKSPACE_DIR), edits)
    except LineEditError:
        return []
    payloads: list[tuple[str, dict[str, object]]] = []
    for change in changes:
        old, new = guard_edit(change)
        payload = {key: value for key, value in data.items() if key not in ("tool_name", "tool_input")}
        payload["tool_name"] = GUARDED_TOOL
        payload["tool_input"] = {"file_path": str(change.path), "old_string": old, "new_string": new,
                                 "replace_all": False}
        payloads.append((change.shown, payload))
    return payloads


def _json_refusal(stdout: str) -> bool:
    try:
        answer = json.loads(stdout)
    except json.JSONDecodeError:
        return False
    if not isinstance(answer, dict):
        return False
    specific = answer.get("hookSpecificOutput")
    decision = specific.get("permissionDecision") if isinstance(specific, dict) else None
    return decision in REFUSING_DECISIONS or answer.get("decision") == "block"


def run_guard(command: str, timeout: int, shown: str, payload: dict[str, object]) -> None:
    """Run one guard on one file's payload; pass its refusal on and exit, or return to continue."""
    try:
        result = subprocess.run(command, shell=True, input=json.dumps(payload), capture_output=True, text=True,
                                timeout=timeout, check=False)
    except (OSError, subprocess.TimeoutExpired) as exc:
        _refuse(f"the guard `{command}` could not judge {shown} ({exc}); nothing was changed. "
                "Retry, or make this change with Edit.")
    if result.returncode == 2:
        _refuse(f"{shown}: {result.stderr.strip()}")
    if result.stdout.strip() and _json_refusal(result.stdout.strip()):
        sys.stdout.write(result.stdout)
        sys.exit(0)


def main() -> None:
    try:
        data = json.loads(sys.stdin.read())
    except json.JSONDecodeError:
        sys.exit(0)
    if not isinstance(data, dict) or data.get("tool_name") != LINE_EDIT_TOOL:
        sys.exit(0)
    try:
        guards = edit_guards()
        payloads = edit_payloads(data)
    except (OSError, ValueError, ImportError) as exc:
        _refuse(f"the Write/Edit guards could not be run over this call ({type(exc).__name__}: {exc}); "
                "nothing was changed. Make this change with Edit.")
    for shown, payload in payloads:
        for command, timeout in guards:
            run_guard(command, timeout, shown, payload)
    sys.exit(0)


if __name__ == "__main__":
    main()
