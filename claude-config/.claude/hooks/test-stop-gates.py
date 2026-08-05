"""Exercise the stop-enforcement hooks end to end with synthetic payloads.

Both directions are covered on purpose: that the gate BLOCKS a `/task-orchestrator`
run ending above zero, and that it stays OUT OF THE WAY of everything else — a
planning run above all. Over-blocking is the failure mode that cost a session:
`/operationalize-design` finished its five phases, was refused its Stop over the task
files it had just authored, and started implementing a phase nobody scheduled.
"""
import json
import os
import subprocess
import sys

H = r"d:\datrix\.claude\hooks"
STATE = os.path.join(H, ".state")
SID = "TESTSESSION-gatecheck"
SPATH = os.path.join(STATE, f"orchestration-run-{SID}.json")
TRANSCRIPT = r"D:\datrix\.tmp\stopgate-test-transcript.jsonl"
MISSING_TRANSCRIPT = r"D:\datrix\.tmp\nonexistent.jsonl"

fails = []

# The disk-truth assertions run against a FIXTURE phase, not the live ledger. Pinning a
# real phase number is what rotted the previous version: it asserted on phase 8 until
# phase 8 reached 10/10, after which it proved nothing and still printed PASS. And with
# every task in the workspace COMPLETED there is no live phase left that can exercise a
# block at all.
#
# Phase 999 does not exist, so `phase-status.ps1` exits 2 and writes NOTHING (verified) —
# the snapshot the gate reads back at this exact path is the one written here. The gate's
# real subprocess, parsing, counting, and blocking all run; only the ledger is synthetic.
ARM_PHASE = 999
SNAPSHOT = rf"D:\datrix\.tmp\tasks\phase-{ARM_PHASE}-stopgate.json"
FIXTURE_DIR = r"D:\datrix\.tmp\stopgate-fixture"
ARM_PROMPT = f"/task-orchestrator\n\nPHASE: {ARM_PHASE}"
# The same skill invoked through the Skill tool: the prompt is the EXPANDED body.
ARM_PROMPT_EXPANDED = (
    "Base directory for this skill: d:\\datrix\\.claude\\skills\\task-orchestrator\n\n"
    f"# Task Orchestrator\n\nPHASE: {ARM_PHASE}"
)


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


def prompt(text):
    run("arm-orchestration-run.py", {"session_id": SID, "prompt": text})


def arm():
    prompt(ARM_PROMPT)


def transcript_saying(text):
    """A one-message transcript, so the solicitation guard has something to read."""
    os.makedirs(os.path.dirname(TRANSCRIPT), exist_ok=True)
    with open(TRANSCRIPT, "w", encoding="utf-8") as f:
        f.write(json.dumps({"type": "assistant",
                            "message": {"content": [{"type": "text", "text": text}]}}) + "\n")
    return TRANSCRIPT


def stop_gate(transcript=MISSING_TRANSCRIPT):
    return run("gate-orchestration-stop.py",
               {"session_id": SID, "transcript_path": transcript})


def task_file(name, body):
    """A real file on disk, so the gate's blocker-proof reader has something to read."""
    os.makedirs(FIXTURE_DIR, exist_ok=True)
    path = os.path.join(FIXTURE_DIR, name)
    with open(path, "w", encoding="utf-8") as f:
        f.write(body)
    return path


def snapshot(tasks):
    """Stand in for `phase-status.ps1` output at the path the gate reads back."""
    os.makedirs(os.path.dirname(SNAPSHOT), exist_ok=True)
    with open(SNAPSHOT, "w", encoding="utf-8") as f:
        json.dump({"phase": ARM_PHASE, "tasks": tasks}, f)


def check(label, got, want):
    ok = got == want
    if not ok:
        fails.append(f"{label}: got {got!r} want {want!r}")
    print(f"  {'PASS' if ok else 'FAIL'}  {label}  -> {got!r}")


print(f"== arming: /task-orchestrator, and nothing else (phase {ARM_PHASE}) ==")
reset()
arm()
check("/task-orchestrator ARMS", state().get("status"), "running")
check("  phase captured from PHASE: line", state().get("phases"), [ARM_PHASE])
check("  marked verifiable", state().get("verifiable"), True)

reset()
prompt(ARM_PROMPT_EXPANDED)
check("expanded skill body ARMS (Skill-tool invocation)", state().get("status"), "running")
check("  phase captured", state().get("phases"), [ARM_PHASE])

for other in ("/operationalize-design\n\nDOCUMENT: d:/x.md",
              "/generate-tasks\n\nDESIGN: d:/x.md",
              "Base directory for this skill: d:\\datrix\\.claude\\skills\\operationalize-design",
              "/execute-tasks-parallel\n\nPHASE: 8",
              "/codegen-fix-loop",
              "/opus-work fix the azure generator",
              "keep going, finish phase 8"):
    reset()
    prompt(other)
    check(f"{other.splitlines()[0][:44]!r} does NOT arm", state().get("status"), None)

print("\n== a planning run is never held to its own output ==")
# The observed failure: five phases of /operationalize-design done, 5 task files
# authored, Stop refused because those 5 were not COMPLETED.
reset()
prompt("/operationalize-design\n\nDOCUMENT: d:/x.md")
rc, _ = stop_gate()
check("Stop ALLOWED after authoring a phase", rc, 0)

rc, _ = stop_gate(transcript_saying(
    "Five phases done, 5 task files written. Would you like me to continue?"))
check("  even when the summary solicits (unarmed = no opinion)", rc, 0)

# The interactive shape that defeated the old name-list exemption: the planning prompt
# is followed by Jon answering a decision gate. That answer must not arm anything.
reset()
prompt("/operationalize-design\n\nDOCUMENT: d:/x.md")
prompt("A1. This is not the Docker target. It is a hybrid running containers on Azure.")
check("answering a decision gate does not arm", state().get("status"), None)
rc, _ = stop_gate()
check("  Stop still ALLOWED", rc, 0)

print("\n== what counts as Jon stopping ==")
for text, want in [
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
    prompt(text)
    check(f"{text[:46]!r}", state().get("status"), want)

print("\n== a stop does not latch for the rest of the session ==")
reset()
arm()
prompt("stop")
check("after 'stop'", state().get("status"), "stopped_by_user")
rc, _ = stop_gate()
check("  Stop ALLOWED while stopped_by_user", rc, 0)
prompt("ok now finish phase 8")
check("next non-stop prompt un-latches", state().get("status"), "idle")
arm()
check("re-invoking the skill RE-ARMS", state().get("status"), "running")

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

print("\n== gate-orchestration-stop: counts the ledger, not the summary ==")
PENDING = task_file("task-999-01.md", "# Task 999-01: Pending\n\nNo How Solved yet.\n")
BLOCKED = task_file(
    "task-999-02.md",
    "# Task 999-02: Blocked\n\n## How Solved\n\nAttempted the fix at src/x.py:41; the "
    "endpoint requires a credential that does not exist in this workspace.\n"
    "Blocker: B1 MISSING_ACCESS\n",
)
DONE = task_file("task-999-03.md", "# COMPLETED: Task 999-03\n\n## How Solved\n\nDone.\n")

reset()
arm()
snapshot([
    {"task_id": "task-999-01", "task_path": PENDING, "is_completed": False},
    {"task_id": "task-999-03", "task_path": DONE, "is_completed": True},
])
rc, err = stop_gate()
check("armed + a pending task -> STOP BLOCKED", rc, 2)
check("  counts it off disk", "1 task(s) are still neither COMPLETED" in err, True)
check("  names the pending task", "task-999-01" in err, True)
if err:
    print("    hook said:", err.splitlines()[0][:110])
check("  block counter recorded", state().get("blocks"), 1)
check("  progress baseline stored", state().get("last_unresolved"), 1)

print("\n== a valid B1-B4 proof is a terminal outcome, not a pending task ==")
reset()
arm()
snapshot([
    {"task_id": "task-999-02", "task_path": BLOCKED, "is_completed": False},
    {"task_id": "task-999-03", "task_path": DONE, "is_completed": True},
])
rc, _ = stop_gate()
check("blocker proof -> Stop ALLOWED", rc, 0)
check("  run marked complete", state().get("status"), "complete")

print("\n== block budget resets on progress, not on patience ==")
reset()
arm()
snapshot([{"task_id": "task-999-01", "task_path": PENDING, "is_completed": False}])
s = dict(state())
s["blocks"] = 39
s["last_unresolved"] = 9999
with open(SPATH, "w", encoding="utf-8") as f:
    json.dump(s, f)
stop_gate()
check("unresolved dropped -> counter reset", state().get("blocks"), 1)

print("\n== the cap bounds a WEDGED run, never a healthy one ==")
s = dict(state())
s["blocks"] = 40
with open(SPATH, "w", encoding="utf-8") as f:
    json.dump(s, f)
rc, _ = stop_gate()
check("block cap reached -> gate gives up", rc, 0)
check("  and says so", state().get("status"), "gate_exhausted")

print("\n== a fully resolved phase releases the run ==")
reset()
arm()
snapshot([{"task_id": "task-999-03", "task_path": DONE, "is_completed": True}])
rc, _ = stop_gate()
check("0 pending -> Stop ALLOWED", rc, 0)
check("  run marked complete", state().get("status"), "complete")

print("\n== unreadable disk truth fails OPEN ==")
reset()
arm()
if os.path.isfile(SNAPSHOT):
    os.remove(SNAPSHOT)
rc, _ = stop_gate()
check("no snapshot -> Stop ALLOWED (never wedges)", rc, 0)

print("\n== armed with no PHASE: line -> solicitation guard only ==")
reset()
prompt("/task-orchestrator\n\nTASKS: D:\\datrix\\datrix-common\\.tasks\\phase-08\\task-08-03.md")
check("armed", state().get("status"), "running")
check("  not verifiable from disk", state().get("verifiable"), False)
rc, _ = stop_gate(transcript_saying("Wave 1 is green. Shall I continue with wave 2?"))
check("offering to pause -> BLOCKED", rc, 2)
rc, _ = stop_gate(transcript_saying("Wave 1 is green; dispatching wave 2 now."))
check("getting on with it -> allowed", rc, 0)

reset()
for stale in (TRANSCRIPT, SNAPSHOT, PENDING, BLOCKED, DONE):
    if os.path.isfile(stale):
        os.remove(stale)
if os.path.isdir(FIXTURE_DIR):
    os.rmdir(FIXTURE_DIR)
print("\n" + ("ALL PASS" if not fails else "FAILURES:\n  " + "\n  ".join(fails)))
sys.exit(1 if fails else 0)
