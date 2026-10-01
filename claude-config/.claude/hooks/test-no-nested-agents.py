"""Self-test for guard-no-nested-agents.py.

A dispatch from inside a subagent (hook input carries `agent_id`) must be refused for
every spelling of the tool; a dispatch from the main session (no `agent_id`) must pass.
The hook must also be wired in settings.json for exactly the Agent and Task tool names.

Run: D:\\datrix\\.venv\\Scripts\\python.exe .claude/hooks/test-no-nested-agents.py
"""

import json
import re
import subprocess
import sys
from pathlib import Path

_HOOKS = Path(__file__).resolve().parent
_HOOK = _HOOKS / "guard-no-nested-agents.py"
_SETTINGS = _HOOKS.parent / "settings.json"
_BLOCK_EXIT = 2
_ALLOW_EXIT = 0

_CASES: tuple[tuple[str, dict[str, object], int], ...] = (
    ("subagent -> general-purpose", {"tool_name": "Agent", "agent_id": "a1", "tool_input": {"subagent_type": "general-purpose", "prompt": "x"}}, _BLOCK_EXIT),
    ("subagent -> background", {"tool_name": "Agent", "agent_id": "a1", "tool_input": {"prompt": "x", "run_in_background": True}}, _BLOCK_EXIT),
    ("subagent -> legacy Task name", {"tool_name": "Task", "agent_id": "a1", "tool_input": {"prompt": "x"}}, _BLOCK_EXIT),
    ("subagent -> empty input", {"tool_name": "Agent", "agent_id": "a1", "tool_input": {}}, _BLOCK_EXIT),
    ("main session -> general-purpose", {"tool_name": "Agent", "tool_input": {"subagent_type": "general-purpose", "prompt": "x"}}, _ALLOW_EXIT),
    ("main session -> background", {"tool_name": "Agent", "tool_input": {"prompt": "x", "run_in_background": True}}, _ALLOW_EXIT),
    ("main session -> empty agent_id", {"tool_name": "Agent", "agent_id": "", "tool_input": {"prompt": "x"}}, _ALLOW_EXIT),
)


def _run(payload: dict[str, object]) -> tuple[int, str]:
    result = subprocess.run(
        [sys.executable, str(_HOOK)],
        input=json.dumps(payload),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    return result.returncode, result.stderr


def _registered_matchers() -> list[str]:
    settings = json.loads(_SETTINGS.read_text(encoding="utf-8"))
    return [
        block["matcher"]
        for block in settings["hooks"]["PreToolUse"]
        if any(_HOOK.name in hook["command"] for hook in block["hooks"])
    ]


def main() -> int:
    failures: list[str] = []
    for label, payload, want in _CASES:
        code, stderr = _run(payload)
        ok = code == want and (want != _BLOCK_EXIT or "NESTED AGENT BLOCKED" in stderr)
        print(f"  [{'OK  ' if ok else 'FAIL'}] {label}")
        if not ok:
            failures.append(f"{label}: exit {code}, want {want}")

    matchers = _registered_matchers()
    print(f"  registered matchers: {matchers}")
    if len(matchers) != 1:
        failures.append(f"expected exactly one PreToolUse registration, found {matchers}")
    else:
        for tool in ("Agent", "Task"):
            if not re.fullmatch(matchers[0], tool):
                failures.append(f"matcher {matchers[0]!r} does not match tool {tool!r}")

    print()
    if failures:
        print(f"[FAIL] {len(failures)} wrong:")
        for line in failures:
            print(f"  - {line}")
        return 1
    print("[OK] all cases correct")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
