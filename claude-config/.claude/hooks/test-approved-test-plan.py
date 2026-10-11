"""Exercise guard-approved-test-plan.py with synthetic payloads against a throwaway gate directory.

The gate is worthless if an unapproved module slips through, if another session is blocked,
or if the agent can approve itself. All three directions are asserted below.

Run: python .claude/hooks/test-approved-test-plan.py
"""
import json
import os
import shutil
import subprocess
import sys
import tempfile

HOOK = os.path.join(os.path.dirname(os.path.realpath(__file__)), "guard-approved-test-plan.py")
BLOCK, ALLOW = 2, 0
SESSION = "session-under-test"
OTHER_SESSION = "another-session"
fails: list[str] = []

workspace = tempfile.mkdtemp(prefix="approval-gate-selftest-")
gate_dir = os.path.join(workspace, "gate")
tests_root = os.path.join(workspace, "pkg", "tests")
os.makedirs(gate_dir)
os.makedirs(os.path.join(tests_root, "unit", "auth"))
existing_module = os.path.join(tests_root, "unit", "auth", "test_existing.py")
with open(existing_module, "w", encoding="utf-8") as handle:
    handle.write("")
env = dict(os.environ, DATRIX_APPROVAL_GATE_DIR=gate_dir)


def run(payload: dict[str, object]) -> int:
    process = subprocess.run([sys.executable, HOOK], input=json.dumps(payload),
                             capture_output=True, text=True, env=env)
    return process.returncode


def write(path: str, session: str = SESSION, tool: str = "Write") -> int:
    return run({"tool_name": tool, "session_id": session, "tool_input": {"file_path": path}})


def shell(command: str) -> int:
    return run({"tool_name": "PowerShell", "session_id": SESSION, "tool_input": {"command": command}})


def check(label: str, got: int, want: int) -> None:
    ok = got == want
    if not ok:
        fails.append(f"{label}: exit {got} want {want}")
    print(f"  {'PASS' if ok else 'FAIL'}  {label}")


def tests_path(relative: str) -> str:
    return os.path.join(tests_root, *relative.split("/"))


try:
    new_module = tests_path("unit/auth/test_new_table.py")

    print("== not armed: nothing is gated ==")
    check("a new test module", write(new_module), ALLOW)

    print("== arming ==")
    armed_path = os.path.join(gate_dir, "armed.json")
    check("creating the arming file", write(armed_path), ALLOW)
    with open(armed_path, "w", encoding="utf-8") as handle:
        json.dump({"session_id": SESSION, "tests_root": tests_root}, handle)
    check("overwriting the arming file", write(armed_path), BLOCK)
    check("editing the arming file", write(armed_path, tool="Edit"), BLOCK)

    print("== armed, nothing approved ==")
    check("a new test module", write(new_module), BLOCK)
    check("the same module from another session", write(new_module, session=OTHER_SESSION), ALLOW)
    check("an existing test module", write(existing_module), ALLOW)
    check("a non-test module under tests", write(tests_path("unit/auth/helpers.py")), ALLOW)
    check("a test module outside the tests root",
          write(os.path.join(workspace, "other", "tests", "test_x.py")), ALLOW)

    print("== the agent cannot approve itself ==")
    approval = os.path.join(gate_dir, "identity.approved")
    check("writing an approval", write(approval), BLOCK)
    check("a shell copy into the gate", shell(f"Copy-Item plan.txt {approval}"), BLOCK)
    check("a shell removal of the arming file", shell(f"Remove-Item {armed_path}"), BLOCK)
    check("an unrelated shell command", shell("git status --short"), ALLOW)

    print("== armed, approved ==")
    with open(approval, "w", encoding="utf-8") as handle:
        handle.write("# identity cluster\nunit/auth/test_new_table.py  # the decision table\n")
    check("the approved module", write(new_module), ALLOW)
    check("an unlisted module", write(tests_path("unit/auth/test_unlisted.py")), BLOCK)
finally:
    shutil.rmtree(workspace, ignore_errors=True)

if fails:
    print(f"\n{len(fails)} FAILED:")
    for failure in fails:
        print(f"  {failure}")
    sys.exit(1)
print("\nall passed")
