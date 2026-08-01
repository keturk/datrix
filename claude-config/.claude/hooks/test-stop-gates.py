"""Exercise the stop-enforcement hooks end to end with synthetic payloads."""
import json
import os
import subprocess
import sys

H = r"d:\datrix\.claude\hooks"
STATE = os.path.join(H, ".state")
SID = "TESTSESSION-gatecheck"
SPATH = os.path.join(STATE, f"orchestration-run-{SID}.json")
TASK = r"D:\datrix\datrix-common\.tasks\phase-08\task-08-03.md"
fails = []


def run(hook, payload):
    p = subprocess.run([sys.executable, os.path.join(H, hook)],
                       input=json.dumps(payload), capture_output=True, text=True)
    return p.returncode, (p.stderr or "").strip()


def state():
    try:
        with open(SPATH, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def reset():
    if os.path.isfile(SPATH):
        os.remove(SPATH)


def arm():
    run("observe-task-activity.py",
        {"session_id": SID, "tool_name": "Edit", "tool_input": {"file_path": TASK}})


def check(label, got, want):
    ok = got == want
    if not ok:
        fails.append(f"{label}: got {got!r} want {want!r}")
    print(f"  {'PASS' if ok else 'FAIL'}  {label}  -> {got!r}")


print("== observe-task-activity: arms on mutation, ignores inspection ==")
reset()
run("observe-task-activity.py", {"session_id": SID, "tool_name": "PowerShell",
    "tool_input": {"command": 'powershell -File "d:/datrix/datrix/scripts/tasks/phase-status.ps1" 8'}})
check("read-only phase-status does NOT arm", state().get("status"), None)

run("observe-task-activity.py", {"session_id": SID, "tool_name": "Read",
    "tool_input": {"file_path": TASK}})
check("reading a task file does NOT arm", state().get("status"), None)

arm()
check("editing a task file ARMS", state().get("status"), "running")
check("  phase captured", state().get("phases_observed"), [8])

reset()
run("observe-task-activity.py", {"session_id": SID, "tool_name": "PowerShell",
    "tool_input": {"command": 'powershell -File "d:/datrix/datrix/scripts/tasks/complete.ps1" "task-08-05.md"'}})
check("complete.ps1 ARMS (bare filename)", state().get("status"), "running")
check("  phase from filename", state().get("phases_observed"), [8])

reset()
run("observe-task-activity.py", {"session_id": SID, "tool_name": "Agent",
    "tool_input": {"prompt": r"Execute D:\datrix\datrix-codegen-aws\.tasks\phase-08\task-08-11.md"}})
check("agent dispatch with task path ARMS", state().get("status"), "running")

print("\n== arm-orchestration-run: what counts as Jon stopping ==")
for prompt, want in [
    ("hold on, check the azure module first", "running"),
    ("pause - is mypy really needed here?", "running"),
    ("stop working on typescript, do python instead", "running"),
    ("Why did you stop? Who told you to stop? I see 112 incomplete tasks. "
     "You don't stop. You don't stop.", "running"),
    ("You don't stop.", "running"),
    ("you dont stop", "running"),
    ("Why did you stop?", "running"),
    ("don't stop!", "running"),
    ("keep going", "running"),
    ("stop", "stopped_by_user"),
    ("ok stop for now", "stopped_by_user"),
    ("stop the run", "stopped_by_user"),
    ("stand down", "stopped_by_user"),
]:
    reset()
    arm()
    run("arm-orchestration-run.py", {"session_id": SID, "prompt": prompt})
    check(f"{prompt[:46]!r}", state().get("status"), want)

print("\n== a stop does not latch for the rest of the session ==")
reset()
arm()
run("arm-orchestration-run.py", {"session_id": SID, "prompt": "stop"})
check("after 'stop'", state().get("status"), "stopped_by_user")
run("arm-orchestration-run.py", {"session_id": SID, "prompt": "ok now finish phase 8"})
check("next non-stop prompt un-latches", state().get("status"), "idle")
arm()
check("resuming task work RE-ARMS", state().get("status"), "running")

print("\n== gate-decision-escalation ==")
reset()
rc, _ = run("gate-decision-escalation.py", {"session_id": SID,
            "tool_input": {"questions": [{"question": "Which typing for gateway_terminates_tls?"}]}})
check("not armed -> allowed", rc, 0)
arm()
rc, err = run("gate-decision-escalation.py", {"session_id": SID,
              "tool_input": {"questions": [{"question": "Which typing for gateway_terminates_tls?"}]}})
check("armed -> DENIED", rc, 2)
check("  names rung 3", "Fable adjudicator" in err, True)
rc, _ = run("gate-decision-escalation.py", {"session_id": SID,
            "tool_input": {"questions": [{"question": "Fable returned ASK_USER on the axis choice."}]}})
check("armed + Fable ASK_USER -> allowed", rc, 0)

print("\n== gate-orchestration-stop: disk truth, no phase named ==")
reset()
arm()
rc, err = run("gate-orchestration-stop.py",
              {"session_id": SID, "transcript_path": r"D:\datrix\.tmp\nonexistent.jsonl"})
check("armed by observation + pending tasks -> STOP BLOCKED", rc, 2)
check("  counts pending off disk", "still neither COMPLETED" in err, True)
if err:
    print("    hook said:", err.splitlines()[0][:110])
check("  block counter recorded", state().get("blocks"), 1)
check("  progress baseline stored", isinstance(state().get("last_unresolved"), int), True)

print("\n== block budget resets on progress, not on patience ==")
s = state()
s["blocks"] = 39
s["last_unresolved"] = 9999
with open(SPATH, "w", encoding="utf-8") as f:
    json.dump(s, f)
run("gate-orchestration-stop.py", {"session_id": SID, "transcript_path": "x"})
check("unresolved dropped -> counter reset", state().get("blocks"), 1)

reset()
print("\n" + ("ALL PASS" if not fails else "FAILURES:\n  " + "\n  ".join(fails)))
sys.exit(1 if fails else 0)
