"""Exercise gate-stop-exhaustion.py end to end with synthetic payloads.

Both directions, on purpose. The BLOCK cases use the verbatim text of the real
failure this gate was written for -- a gate that cannot catch the sentence that
caused it is decoration. The ALLOW cases are the expensive ones: a gate that
fires on an answer to Jon's own question, or on a report of success that happens
to contain the word "remaining", teaches evasive phrasing and costs more than
the dodge did.
"""
import json
import os
import subprocess
import sys
import tempfile

H = r"d:\datrix\.claude\hooks"
SID = "TESTSESSION-exhaustion"
TRANSCRIPT = r"D:\datrix\.tmp\exhaustion-test-transcript.jsonl"
STATE = os.path.join(tempfile.gettempdir(), "datrix-stop-exhaustion", f"{SID}.json")

fails = []


def check(label, got, want):
    ok = got == want
    print(f"  {'PASS' if ok else 'FAIL'}  {label}  (got {got!r}, want {want!r})")
    if not ok:
        fails.append(f"{label}: got {got!r}, want {want!r}")


def transcript(assistant_text, user_text="continue with the task"):
    os.makedirs(os.path.dirname(TRANSCRIPT), exist_ok=True)
    with open(TRANSCRIPT, "w", encoding="utf-8") as f:
        f.write(json.dumps({"type": "user",
                            "message": {"content": [{"type": "text", "text": user_text}]}}) + "\n")
        f.write(json.dumps({"type": "assistant",
                            "message": {"content": [{"type": "text", "text": assistant_text}]}}) + "\n")
    return TRANSCRIPT


def gate(assistant_text, user_text="continue with the task"):
    reset()
    payload = {"session_id": SID, "transcript_path": transcript(assistant_text, user_text)}
    p = subprocess.run([sys.executable, os.path.join(H, "gate-stop-exhaustion.py")],
                       input=json.dumps(payload), capture_output=True, text=True)
    return p.returncode


def reset():
    if os.path.isfile(STATE):
        os.remove(STATE)


# --- BLOCK: the verbatim sentences that ended the real turn -----------------
print("blocks the real failure:")
check("'Out of runway to keep debugging this safely' -> BLOCKED",
      gate("Out of runway to keep debugging this safely, so here is exactly "
           "where it stands. The extern service still produces nothing."), 2)
check("'running low on context' -> BLOCKED",
      gate("I am running low on context, so I will summarize the state now."), 2)
check("'near the end of my context window' -> BLOCKED",
      gate("I'm near the end of my context window; here is what I found."), 2)
check("'**Where it stops:**' heading -> BLOCKED",
      gate("I made progress on the resolver.\n\n"
           "**Where it stops:** the extern service produces no compose entry."), 2)
check("'**Remaining after that:**' heading -> BLOCKED",
      gate("Landed the capability and its tests.\n\n"
           "**Remaining after that:** build the image, port the PAT step."), 2)
check("'Next up:' heading -> BLOCKED",
      gate("Fixed the parser defect.\n\nNext up: wire the release leg."), 2)
check("'to keep the repo in a clean state' -> BLOCKED",
      gate("Stopping here to keep the repo in a clean state."), 2)

# --- ALLOW: Jon set the terms of the turn -----------------------------------
print("\nstays out of the way when Jon asked:")
check("Jon said 'don't continue with work' -> allowed",
      gate("**Remaining:** the extern service still produces nothing.",
           "Don't continue with work. What happens when you run low on context?"), 0)
check("Jon asked 'why did you stop?' -> allowed",
      gate("I ran low on context and stopped. That was not a legitimate exit.",
           "I don't get it. Why did you stop?"), 0)
check("Jon asked for status -> allowed",
      gate("Still to fix: the compose entry and the NSG port.",
           "what's left on the login BFF?"), 0)
check("Jon said stop -> allowed",
      gate("Next up: the release leg.", "stop here for today"), 0)

# --- ALLOW: innocent prose, quoting, negation, proven blockers --------------
print("\nstays out of the way otherwise:")
check("success report containing the word 'remaining' -> allowed",
      gate("All 57 tests pass and the remaining 12 warnings are pre-existing "
           "and unrelated to this change."), 0)
check("QUOTING the rule -> allowed",
      gate("The contract says \"Running low on context is not an exit either\" "
           "and I am treating it as binding, so I kept going and landed the fix."), 0)
check("negated -> allowed",
      gate("Nothing is still to fix: every item you authorized is green."), 0)
check("proven B2 blocker -> allowed",
      gate("**Remaining:** the image distribution choice.\n\n"
           "B2 - UNDECIDABLE: registry vs build-on-VM. Attempted at "
           "_external_infra.py:181; both are defensible and nothing in the docs "
           "settles it. Recommendation: build-on-VM."), 2 if False else 0)
check("filed task path -> allowed",
      gate("Next up: handled by .tasks/phase-72/task-04-login-bff-image.md"), 0)
check("ordinary finished turn -> allowed",
      gate("Landed the resolver and its 12 tests; datrix-codegen-docker green."), 0)

# --- fail-open --------------------------------------------------------------
print("\nfails open:")
p = subprocess.run([sys.executable, os.path.join(H, "gate-stop-exhaustion.py")],
                   input="not json", capture_output=True, text=True)
check("malformed payload -> allowed", p.returncode, 0)
p = subprocess.run([sys.executable, os.path.join(H, "gate-stop-exhaustion.py")],
                   input=json.dumps({"session_id": SID,
                                     "transcript_path": r"D:\datrix\.tmp\nope.jsonl"}),
                   capture_output=True, text=True)
check("missing transcript -> allowed", p.returncode, 0)

# --- never unkillable -------------------------------------------------------
print("\nnever unkillable:")
reset()
payload = {"session_id": SID, "transcript_path": transcript("Out of runway; stopping here.")}
# _MAX_BLOCKS refusals, then the gate gives up and clears its counter. Asserting
# on the 7th specifically, not on "the last of 8": the 8th starts a FRESH cycle
# and blocks again by design, so a test that ran 8 and expected 0 at the end was
# asserting the wrong thing -- which is exactly what the first version did.
codes = []
for _ in range(7):
    p = subprocess.run([sys.executable, os.path.join(H, "gate-stop-exhaustion.py")],
                       input=json.dumps(payload), capture_output=True, text=True)
    codes.append(p.returncode)
check("blocks _MAX_BLOCKS times", codes[:6], [2] * 6)
check("then gives up on the next", codes[6], 0)

reset()
if os.path.isfile(TRANSCRIPT):
    os.remove(TRANSCRIPT)
print("\n" + ("ALL PASS" if not fails else "FAILURES:\n  " + "\n  ".join(fails)))
sys.exit(1 if fails else 0)
