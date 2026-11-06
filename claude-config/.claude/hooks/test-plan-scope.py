"""Exercise guard-plan-scope.py end to end with synthetic payloads.

The failure this holds: a `/fix-test-suites` session wrote `scripts: test/failure-ledger.ps1,
test/test.ps1` and `paths: d:/datrix/**`. The guard split on spaces only and compared raw entries,
so the locked scope named no script and no file, and it refused the job's first script as "not part
of Jon's order" when working every repo and running their suites is exactly what that skill orders.

Both directions, on purpose: every spelling of an entry reaches the same scope, a call outside the
scope is still refused, and only a workspace-wide skill lifts the fence.
"""
import json
import os
import subprocess
import sys

H = r"d:\datrix\.claude\hooks"
SID = "TESTSESSION-plan-scope"
PLAN = os.path.join(r"d:\datrix\.agent_output", f"plan-{SID}.md")
STATE = os.path.join(H, ".state", f"scope-{SID}.json")
TRANSCRIPT = r"D:\datrix\.tmp\plan-scope-test-transcript.jsonl"
MISSING_TRANSCRIPT = r"D:\datrix\.tmp\nonexistent.jsonl"
LEDGER = 'powershell -File "d:/datrix/datrix/scripts/test/failure-ledger.ps1" -Status'
SPLIT = 'powershell -File "d:/datrix/datrix/scripts/dev/split-module.ps1" a.py'
COMMON_SOURCE = r"D:\datrix\datrix-common\src\datrix_common\x.py"

fails = []


def check(label, got, want):
    ok = got == want
    print(f"  {'PASS' if ok else 'FAIL'}  {label}  (got {got!r}, want {want!r})")
    if not ok:
        fails.append(f"{label}: got {got!r}, want {want!r}")


def reset(*extra):
    for path in (STATE, PLAN, *extra):
        if os.path.isfile(path):
            os.remove(path)


def transcript(*entries):
    os.makedirs(os.path.dirname(TRANSCRIPT), exist_ok=True)
    with open(TRANSCRIPT, "w", encoding="utf-8") as f:
        for entry in entries:
            f.write(json.dumps(entry) + "\n")
    return TRANSCRIPT


def jon(text):
    return {"type": "user", "message": {"content": [{"type": "text", "text": text}]}}


def typed_skill(name):
    return {"type": "user", "message": {"content": (
        f"<command-message>{name}</command-message>\n<command-name>/{name}</command-name>\n"
        "<command-args>x/index.json</command-args>")}}


def skill_body(name):
    return {"type": "user", "isMeta": True, "message": {"content": [{"type": "text", "text": (
        f"Base directory for this skill: d:\\datrix\\.claude\\skills\\{name}\n\n# {name}\n")}]}}


def run_guard(payload):
    run = subprocess.run([sys.executable, os.path.join(H, "guard-plan-scope.py")],
                         input=json.dumps(payload), capture_output=True, text=True)
    return "block" if run.returncode == 2 else "allow"


def guard(scope_lines, tool_name, tool_input, transcript_path=MISSING_TRANSCRIPT):
    """Run the guard once on a fresh lock; return "allow" or "block"."""
    reset()
    os.makedirs(os.path.dirname(PLAN), exist_ok=True)
    with open(PLAN, "w", encoding="utf-8") as f:
        f.write(f"## Steps\n- [ ] step\n\n## Scope\n{scope_lines}\n\n## Verification\n")
    return run_guard({"session_id": SID, "transcript_path": transcript_path, "tool_name": tool_name, "tool_input": tool_input})


def shell(command):
    return "PowerShell", {"command": command}


def edit(path):
    return "Edit", {"file_path": path}


print("script entries, every spelling")
for spelling in ("failure-ledger", "failure-ledger, test", "test/failure-ledger.ps1, test/test.ps1",
                 r"test\failure-ledger.ps1", "Failure-Ledger.PS1"):
    check(f"`scripts: {spelling}` admits failure-ledger", guard(f"paths: **\nscripts: {spelling}", *shell(LEDGER)), "allow")
check("a script not named is refused", guard("paths: **\nscripts: failure-ledger, test", *shell(SPLIT)), "block")

print("path entries, every spelling")
for spelling in ("datrix-*/src/**", "datrix-common/**, datrix-cli/**", "d:/datrix/**", "D:/datrix/datrix-*/src/**", r"d:\datrix\datrix-*\src\**"):
    check(f"`paths: {spelling}` admits a package source file", guard(f"paths: {spelling}\nscripts: test", *edit(COMMON_SOURCE)), "allow")
check("a file outside the paths is refused", guard("paths: datrix-cli/**\nscripts: test", *edit(COMMON_SOURCE)), "block")
check("a workspace glob stops at the workspace", guard("paths: d:/datrix/**\nscripts: test", *edit(r"C:\Users\x\notes.md")), "block")
check("the scratchpad stays writable", guard("paths: datrix-cli/**\nscripts: test", *edit(r"C:\t\scratchpad\x.md")), "allow")

print("a lock written by the old parser still reads")
reset()
os.makedirs(os.path.dirname(STATE), exist_ok=True)
with open(STATE, "w", encoding="utf-8") as f:
    json.dump({"paths": ["d:/datrix/**"], "scripts": ["test/failure-ledger.ps1,", "test/test.ps1,"]}, f)
check("the locked entries are read canonically",
      run_guard({"session_id": SID, "tool_name": "PowerShell", "tool_input": {"command": LEDGER}}), "allow")

print("workspace-wide skill")
narrow = "paths: datrix-cli/**\nscripts: test"
typed = transcript(typed_skill("fix-test-suites"), skill_body("fix-test-suites"))
check("/fix-test-suites runs any script", guard(narrow, *shell(LEDGER), typed), "allow")
check("/fix-test-suites edits any repo", guard(narrow, *edit(COMMON_SOURCE), typed), "allow")
followed = transcript(typed_skill("fix-test-suites"), skill_body("fix-test-suites"), jon("keep going"))
check("a later message of Jon's keeps the skill", guard(narrow, *shell(LEDGER), followed), "allow")
check("the Skill tool form counts", guard(narrow, *shell(LEDGER), transcript(skill_body("fix-test-suites"))), "allow")
other = transcript(typed_skill("fix-cli"), skill_body("fix-cli"))
check("a package skill stays fenced", guard(narrow, *shell(LEDGER), other), "block")
later = transcript(typed_skill("fix-test-suites"), typed_skill("fix-cli"))
check("the latest skill decides", guard(narrow, *shell(LEDGER), later), "block")
quoted = transcript(jon("why did <command-name>/fix-test-suites</command-name> fail?"))
check("a quoted command is no invocation", guard(narrow, *shell(LEDGER), quoted), "block")
finding = transcript(typed_skill("implement-finding"), skill_body("implement-finding"))
check("/implement-finding edits a package the scope left out", guard(narrow, *edit(COMMON_SOURCE), finding), "allow")
check("/implement-finding runs any script", guard(narrow, *shell(LEDGER), finding), "allow")
batch = transcript(typed_skill("implement-finding"))
check("a batch session's typed form counts", guard(narrow, *edit(COMMON_SOURCE), batch), "allow")
after = transcript(typed_skill("implement-finding"), typed_skill("fix-cli"))
check("a package skill after /implement-finding is fenced", guard(narrow, *edit(COMMON_SOURCE), after), "block")

print("scope reset")


def widened_plan(transcript_path):
    """A lock on datrix-cli, a plan since widened to datrix-common, and an edit in datrix-common."""
    guard("paths: datrix-cli/**\nscripts: test", *edit(r"D:\datrix\datrix-cli\src\x.py"))
    with open(PLAN, "w", encoding="utf-8") as f:
        f.write("## Steps\n- [ ] step\n\n## Scope\npaths: datrix-common/**\nscripts: test\n\n## Verification\n")
    tool_name, tool_input = edit(COMMON_SOURCE)
    return run_guard({"session_id": SID, "transcript_path": transcript_path, "tool_name": tool_name, "tool_input": tool_input})


check("a plan edit cannot widen the lock", widened_plan(transcript(jon("keep going"))), "block")
check("Jon's scope reset reads the plan afresh", widened_plan(transcript(jon("scope reset"))), "allow")

reset(TRANSCRIPT)
print()
if fails:
    print(f"{len(fails)} check(s) failed:")
    for f in fails:
        print(f"  - {f}")
    sys.exit(1)
print("all checks passed")
