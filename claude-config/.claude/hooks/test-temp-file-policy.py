"""Exercise guard-temp-file-policy.py in both directions.

A scratch-looking name for a NEW file in a repo is blocked; a file git already tracks is
committed source and is never blocked, whatever its name looks like (editing
datrix-cli's tracked ``commands/check.py`` once was).

Run:  d:\\datrix\\.venv\\Scripts\\python.exe d:\\datrix\\.claude\\hooks\\test-temp-file-policy.py
"""

import json
import os
import subprocess
import sys

HOOK = os.path.join(r"d:\datrix\.claude\hooks", "guard-temp-file-policy.py")
BLOCK, ALLOW = 2, 0
fails: list[str] = []


def run(tool: str, path: str) -> int:
    payload = {"tool_name": tool, "tool_input": {"file_path": path}}
    completed = subprocess.run(
        [sys.executable, HOOK], input=json.dumps(payload), capture_output=True, text=True
    )
    return completed.returncode


def check(label: str, got: int, want: int) -> None:
    ok = got == want
    if not ok:
        fails.append(f"{label}: exit {got} want {want}")
    print(f"  {'PASS' if ok else 'FAIL'}  {label}")


TRACKED = r"D:\datrix\datrix-cli\src\datrix_cli\commands\check.py"
assert os.path.isfile(TRACKED), f"fixture precondition: {TRACKED} must exist and be tracked"

check("an edit of a tracked file with a scratch-looking name", run("Edit", TRACKED), ALLOW)
check(
    "a new scratch script beside it",
    run("Write", r"D:\datrix\datrix-cli\src\datrix_cli\commands\check2.py"),
    BLOCK,
)
check("a new log file in a repo", run("Write", r"D:\datrix\datrix\scripts\run.log"), BLOCK)
check("a scratch file in the sanctioned .tmp", run("Write", r"D:\datrix\.tmp\check2.py"), ALLOW)
check("an ordinary new source file", run("Write", r"D:\datrix\datrix-common\src\datrix_common\new_module.py"), ALLOW)
check("a non-file tool", run("Read", r"D:\datrix\datrix\scripts\run.log"), ALLOW)

if fails:
    print(f"FAIL ({len(fails)})")
    for line in fails:
        print("  -", line)
    sys.exit(1)
print("all checks passed")
