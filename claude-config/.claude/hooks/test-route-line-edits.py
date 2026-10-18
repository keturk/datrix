"""Exercise route-line-edits.py end to end: every Write/Edit guard judges an edit_lines call.

The refusal case uses a real guard on a real framework file: an edit_lines call that would add a
TODO comment to datrix-common's package initializer must be refused by guard-code-standards,
exactly as the same change made with Edit is. The file is only planned against -- the hook never
writes, and neither does this test. The allow cases matter as much: a clean edit, a call the
planner itself refuses (the server refuses it with a better message), and any other tool must
all pass untouched.
"""
import importlib.util
import json
import os
import subprocess
import sys

H = r"d:\datrix\.claude\hooks"
SID = "TESTSESSION-route-line-edits"
TOOL = "mcp__datrix-edit__edit_lines"
FIXTURE = r"d:\datrix\datrix-common\src\datrix_common\__init__.py"

sys.path.insert(0, r"d:\datrix\datrix\scripts\common\lib")
from datrix_scripts.line_edits import line_hash, load_text_file  # noqa: E402
from pathlib import Path  # noqa: E402

fails = []


def check(label, got, want):
    ok = got == want
    print(f"  {'PASS' if ok else 'FAIL'}  {label}  (got {got!r}, want {want!r})")
    if not ok:
        fails.append(f"{label}: got {got!r}, want {want!r}")


def run(tool, tool_input):
    payload = {"session_id": SID, "transcript_path": r"D:\datrix\.tmp\nonexistent.jsonl", "cwd": r"D:\datrix",
               "hook_event_name": "PreToolUse", "tool_name": tool, "tool_input": tool_input}
    p = subprocess.run([sys.executable, os.path.join(H, "route-line-edits.py")], input=json.dumps(payload),
                       capture_output=True, text=True, timeout=300)
    return p.returncode, (p.stdout or "").strip(), (p.stderr or "").strip()


def insert_after_last(text):
    lines = load_text_file(Path(FIXTURE)).lines
    return {"edits": [{"file_path": FIXTURE, "after": len(lines), "hash": line_hash(lines[-1].text), "text": text}]}


before = Path(FIXTURE).read_bytes()

print("passes a guard's refusal on:")
code, _, err = run(TOOL, insert_after_last("# TODO: finish this later"))
check("edit_lines adding a TODO to framework Python -> blocked (exit 2)", code, 2)
check("the refusal names the file and is the guard's own", "datrix-common/src/datrix_common/__init__.py" in err
      and "TODO" in err, True)

print("lets everything else through:")
check("a clean edit -> allowed", run(TOOL, insert_after_last("VERSION_NOTE: str = 'gate fixture'"))[0], 0)
wrong_hash = insert_after_last("x")
wrong_hash["edits"][0]["hash"] = "zz"
check("a call the planner refuses (wrong hash) -> allowed, the server refuses it", run(TOOL, wrong_hash)[0], 0)
check("a call with no edits -> allowed, the server refuses it", run(TOOL, {})[0], 0)
check("another tool -> allowed", run("Edit", {"file_path": FIXTURE, "old_string": "a", "new_string": "b"})[0], 0)
check("the fixture file was never written", Path(FIXTURE).read_bytes() == before, True)

print("reads its guards from settings.json:")
spec = importlib.util.spec_from_file_location("route_line_edits", os.path.join(H, "route-line-edits.py"))
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
guards = [command for command, _ in module.edit_guards()]
check("every Write|Edit guard is run", any("guard-code-standards.py" in g for g in guards)
      and any("gate-mandatory-reads.py" in g for g in guards), True)
check("the router does not run itself", any("route-line-edits.py" in g for g in guards), False)
check("a JSON deny is a refusal", module._json_refusal(json.dumps(
    {"hookSpecificOutput": {"hookEventName": "PreToolUse", "permissionDecision": "deny"}})), True)
check("a JSON block is a refusal", module._json_refusal(json.dumps({"decision": "block", "reason": "r"})), True)
check("a JSON allow with context is not", module._json_refusal(json.dumps(
    {"hookSpecificOutput": {"hookEventName": "PreToolUse", "additionalContext": "note"}})), False)

print()
if fails:
    print(f"{len(fails)} check(s) failed:")
    for f in fails:
        print(f"  - {f}")
    sys.exit(1)
print("all checks passed")
