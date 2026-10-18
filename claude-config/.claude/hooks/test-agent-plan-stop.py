"""Exercise gate-agent-plan-stop.py end to end with synthetic payloads.

Both directions, on purpose. The ALLOW case that matters most is the verbatim reply
of the real failure: an unattended implement-finding session ended correctly on an
APPROVAL_REQUIRED question, this gate refused the stop over its unticked plan steps,
and the session answered by doing four hours of unapproved refactoring across five
packages. The BLOCK cases keep the exit narrow: the marker counts only as the
approval request the contract prescribes -- a line starting `APPROVAL_REQUIRED:` --
never as a word quoted, cited or mentioned in passing.
"""
import json
import os
import subprocess
import sys

H = r"d:\datrix\.claude\hooks"
SID = "TESTSESSION-agent-plan-stop"
PLAN = os.path.join(r"d:\datrix\.agent_output", f"plan-{SID}.md")
STATE = os.path.join(H, ".state", f"planstop-{SID}.json")
TRANSCRIPT = r"D:\datrix\.tmp\agent-plan-stop-test-transcript.jsonl"
MISSING_TRANSCRIPT = r"D:\datrix\.tmp\nonexistent.jsonl"

UNFINISHED_PLAN = """## Steps
- [x] Read the finding and decide whether it still holds
- [ ] Reconcile the excess divergent roles
- [ ] Run targeted tests

## Completion criteria
The gate passes at the pin.

## Verification
"""

FINISHED_PLAN = """## Steps
- [x] answer the question

## Completion criteria
Jon has the answer.

## Verification
- read the log; it printed the status.
"""

BLOCKED_PLAN = UNFINISHED_PLAN + "\nStatus: BLOCKED B1\n"

# The reply that ended the real session's turn, trimmed to its closing paragraph.
REAL_APPROVAL_REPLY = (
    "Jon, the finding still holds and is worse than it says. I made no code changes, and "
    "the finding stays in the inbox.\n\n"
    "**Why I stopped.** The finding's suggested fix is to reconcile the divergences. That "
    "means moving roughly 160-300 parallel functions into the shared layer, role by role, "
    "across python, typescript, typescript-core, angular and flutter.\n\n"
    "APPROVAL_REQUIRED: reconcile the language-axis behaviour-parity excess (309 failing "
    "roles against a pin of 146, all from code written since the pin, mostly the `dgen/` "
    "refactor). That is about 160+ role reconciliations across 5 codegen packages, many "
    "sessions of work. Approve the full reconciliation, or name the subset of "
    "roles/packages to do first."
)

fails = []


def check(label, got, want):
    ok = got == want
    print(f"  {'PASS' if ok else 'FAIL'}  {label}  (got {got!r}, want {want!r})")
    if not ok:
        fails.append(f"{label}: got {got!r}, want {want!r}")


def write_plan(text):
    os.makedirs(os.path.dirname(PLAN), exist_ok=True)
    with open(PLAN, "w", encoding="utf-8") as f:
        f.write(text)


def transcript_saying(text):
    os.makedirs(os.path.dirname(TRANSCRIPT), exist_ok=True)
    with open(TRANSCRIPT, "w", encoding="utf-8") as f:
        f.write(json.dumps({"type": "assistant",
                            "message": {"content": [{"type": "text", "text": text}]}}) + "\n")
    return TRANSCRIPT


def reset(*extra):
    for path in (STATE, PLAN, *extra):
        if os.path.isfile(path):
            os.remove(path)


def gate(plan_text, reply=None, transcript=MISSING_TRANSCRIPT):
    """Run the gate once on a fresh state; return ("block", reason) or ("allow", "")."""
    reset()
    write_plan(plan_text)
    payload = {"session_id": SID, "transcript_path": transcript}
    if reply is not None:
        payload["last_assistant_message"] = reply
    p = subprocess.run([sys.executable, os.path.join(H, "gate-agent-plan-stop.py")],
                       input=json.dumps(payload), capture_output=True, text=True)
    out = (p.stdout or "").strip()
    if not out:
        return "allow", ""
    decision = json.loads(out)
    return decision.get("decision", "allow"), decision.get("reason", "")


print("allows an approval request:")
check("verbatim real reply, unticked plan -> allowed",
      gate(UNFINISHED_PLAN, REAL_APPROVAL_REPLY)[0], "allow")
check("approval line read from the transcript fallback -> allowed",
      gate(UNFINISHED_PLAN, None, transcript_saying(REAL_APPROVAL_REPLY))[0], "allow")
check("approval line as a list item -> allowed",
      gate(UNFINISHED_PLAN, "Done with the python half.\n\n- APPROVAL_REQUIRED: the "
           "typescript half needs a new shared module, ~400 lines.")[0], "allow")

print("keeps the other exits:")
check("every step ticked and verified -> allowed", gate(FINISHED_PLAN, "Jon, done.")[0], "allow")
check("Status: BLOCKED B1 -> allowed", gate(BLOCKED_PLAN, "Jon, blocked.")[0], "allow")

print("blocks everything else:")
check("unticked plan, no approval request -> blocked",
      gate(UNFINISHED_PLAN, "Jon, the finding still holds. I made no code changes.")[0],
      "block")
check("marker only quoted as inline code -> blocked",
      gate(UNFINISHED_PLAN, "Waiting on `APPROVAL_REQUIRED: the rest` before continuing.")[0],
      "block")
check("marker mentioned mid-sentence -> blocked",
      gate(UNFINISHED_PLAN, "This needs no APPROVAL_REQUIRED: it is in scope.")[0], "block")
check("bare marker with no request after it -> blocked",
      gate(UNFINISHED_PLAN, "Stopping here.\nAPPROVAL_REQUIRED:")[0], "block")
check("marker inside a fenced block -> blocked",
      gate(UNFINISHED_PLAN, "Quoting the skill:\n```\nAPPROVAL_REQUIRED: what, why\n```")[0],
      "block")

print("names the exit in its refusal:")
decision, reason = gate(UNFINISHED_PLAN, "Jon, I stopped.")
check("refusal tells the agent how to end on an approval request",
      "APPROVAL_REQUIRED:" in reason, True)

reset(TRANSCRIPT)
print()
if fails:
    print(f"{len(fails)} check(s) failed:")
    for f in fails:
        print(f"  - {f}")
    sys.exit(1)
print("all checks passed")
