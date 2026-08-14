r"""Exercise the three enforcement hooks added for the deployment-loop failure.

Both directions on every hook, on purpose. Over-blocking is the expensive failure
mode here: a gate that fires on innocent prose teaches agents to write evasively,
and a pre-deploy gate that fires on a read-only `az show` makes the cheap rung of
the evidence ladder harder to reach than the expensive one — the exact inversion
the hook exists to prevent.

Run:  d:\datrix\.venv\Scripts\python.exe d:\datrix\.claude\hooks\test-dodge-predeploy-checklist.py
"""

import json
import os
import shutil
import subprocess
import sys
import time

H = r"d:\datrix\.claude\hooks"
STATE = os.path.join(H, ".state")
TMP = r"D:\datrix\.tmp\hookcheck"
PREDEPLOY = r"D:\datrix\.tmp\predeploy"
CHECKLIST_DIR = os.path.join(TMP, "checklists")
SID = "TESTSESSION-hookcheck"

fails = []


def run(hook, payload, env=None):
    merged = {**os.environ, **(env or {})}
    p = subprocess.run(
        [sys.executable, os.path.join(H, hook)],
        input=json.dumps(payload),
        capture_output=True,
        text=True,
        env=merged,
    )
    return p.returncode, (p.stderr or "").strip()


def check(label, got, want):
    if got != want:
        fails.append(f"{label}: exit {got}, expected {want}")


def transcript(messages, name="t.jsonl"):
    """messages: list of (kind, payload). kind 'text' or 'cmd'."""
    os.makedirs(TMP, exist_ok=True)
    path = os.path.join(TMP, name)
    with open(path, "w", encoding="utf-8") as f:
        for kind, payload in messages:
            if kind == "text":
                block = {"type": "text", "text": payload}
            else:
                block = {"type": "tool_use", "name": "Bash", "input": {"command": payload}}
            f.write(json.dumps({"type": "assistant", "message": {"content": [block]}}) + "\n")
    return path


def arm_orchestrator(phase=999):
    run("arm-orchestration-run.py", {"session_id": SID, "prompt": f"/task-orchestrator\n\nPHASE: {phase}"})


def disarm():
    path = os.path.join(STATE, f"orchestration-run-{SID}.json")
    if os.path.isfile(path):
        os.remove(path)


def reset_checklist_state():
    path = os.path.join(STATE, f"checklist-{SID}.json")
    if os.path.isfile(path):
        os.remove(path)


# ---------------------------------------------------------------- dodge language

BLOCK, ALLOW = 2, 0

subagent_cases = [
    ("scope dodge", "The auth bug is out of scope for this task.", BLOCK),
    ("omission: didn't verify", "I did not verify the generated compose file.", BLOCK),
    ("omission: skipped check", "I skipped the validation step to save time.", BLOCK),
    ("omission: not tested", "The new module has not been tested.", BLOCK),
    ("omission: should work", "Wired the new route. It should work.", BLOCK),
    ("omission: assuming", "I am assuming the secret is already in the vault.", BLOCK),
    ("negated omission", "No checks were skipped and nothing was left as-is.", ALLOW),
    ("quoted dodge", 'The rule says never end on "out of scope" — I did not.', ALLOW),
    ("blocker proof", "B1 MISSING_ACCESS — no subscription credential. Tried fix at a.py:12.", ALLOW),
    ("filed task", "Filed .tasks/phase-40/03-fix-seam.md for the independent root cause.", ALLOW),
    ("clean report", "Fixed the seam at compose.py:88; targeted tests pass, output quoted above.", ALLOW),
    # §13 — a security downgrade. Not lifted by a blocker proof: a proof answers
    # "whose work is this", which is not the question a weakened control raises.
    ("downgrade: disabled auth", "I disabled the authorization check on the internal route.", BLOCK),
    ("downgrade: with a B1 proof", "B1 MISSING_ACCESS on the vault. Meanwhile I hardcoded "
                                   "the api key in the template so generation proceeds.", BLOCK),
    ("downgrade: B3 is the one exception", "B3 USER_FORBADE — Jon prohibited the secret store, "
                                           "so the remaining path is less secure; exposure is a "
                                           "credential in app settings. Attempted at ident.py:44.", ALLOW),
    ("downgrade: remediation", "Removed the fixture that bypassed authentication; the guard now "
                               "runs on every route and its test is green.", ALLOW),
    # §14 — an expedient fix.
    ("expedient: quick fix", "Landed a quick fix in the emitter; the real one is a rewrite.", BLOCK),
    ("expedient: harden later", "The generated client works, I will harden it later.", BLOCK),
    ("expedient: smallest CORRECT change is fine", "Wrote the smallest correct change in the "
                                                   "transformer; its targeted test passes.", ALLOW),
]

for label, text, want in subagent_cases:
    code, _ = run("check-agent-report.py", {"transcript_path": transcript([("text", text)])})
    check(f"subagent/{label}", code, want)

# The same vocabulary must now police the MAIN loop — but only in an armed run.
disarm()
code, _ = run(
    "gate-orchestration-stop.py",
    {"session_id": SID, "transcript_path": transcript([("text", "I skipped the seam census.")])},
)
check("mainloop/unarmed does not block", code, ALLOW)

arm_orchestrator()
code, err = run(
    "gate-orchestration-stop.py",
    {"session_id": SID, "transcript_path": transcript([("text", "I skipped the seam census.")])},
)
check("mainloop/armed blocks omission", code, BLOCK)
if code == BLOCK and "dodge" not in err.lower():
    fails.append("mainloop: block message does not name the dodge")

arm_orchestrator()
code, _ = run(
    "gate-orchestration-stop.py",
    {"session_id": SID, "transcript_path": transcript([("text", "B2 UNDECIDABLE — two designs; recommending A.")])},
)
check("mainloop/armed allows blocker proof", code, ALLOW)
disarm()

# --------------------------------------------------------------------- predeploy


def predeploy_payload(command):
    return {"tool_name": "PowerShell", "tool_input": {"command": command}}


def write_artifact(name, **overrides):
    os.makedirs(PREDEPLOY, exist_ok=True)
    body = {
        "targets": ["deploy-staging.ps1"],
        "analyzed_at_epoch": int(time.time()),
        "seams": [
            {
                "name": "compose env interpolation",
                "produced_by": ".env + pipeline vars",
                "consumed_by": "docker-compose.yml ${...}",
                "unsatisfied": [],
            }
        ],
        "checks": ["what-if: no changes"],
        "verdict": "clear",
        "reason": "test fixture",
    }
    body.update(overrides)
    path = os.path.join(PREDEPLOY, name)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(body, f)
    return path


def clear_artifacts():
    if os.path.isdir(PREDEPLOY):
        shutil.rmtree(PREDEPLOY, ignore_errors=True)


clear_artifacts()

# Never blocked: not a deploy, or an upper rung of the evidence ladder.
for label, command in [
    ("read-only az list", "az group list -o table"),
    ("read-only az show", "az webapp show --name api -g rg"),
    ("what-if", "az deployment group create -g rg --template-file m.bicep --what-if"),
    ("dry run script", "powershell -File deploy-staging.ps1 -WhatIf"),
    ("terraform plan", "terraform plan -out=tf.plan"),
    ("ordinary command", "git status --short"),
]:
    code, _ = run("guard-predeploy-analysis.py", predeploy_payload(command))
    check(f"predeploy/allows {label}", code, ALLOW)

# Blocked without a fresh, complete, matching artifact.
for label, command in [
    ("deploy script", "powershell -File deploy-staging.ps1"),
    ("az deployment create", "az deployment group create -g rg --template-file m.bicep"),
    ("kubectl apply", "kubectl apply -f k8s/"),
    ("terraform apply", "terraform apply -auto-approve"),
]:
    code, err = run("guard-predeploy-analysis.py", predeploy_payload(command))
    check(f"predeploy/blocks {label}", code, BLOCK)

code, _ = run("guard-predeploy-analysis.py", {"tool_name": "Read", "tool_input": {"command": "deploy.ps1"}})
check("predeploy/ignores non-shell tools", code, ALLOW)

write_artifact("ok.json")
code, _ = run("guard-predeploy-analysis.py", predeploy_payload("powershell -File deploy-staging.ps1"))
check("predeploy/allows with fresh census", code, ALLOW)

code, _ = run("guard-predeploy-analysis.py", predeploy_payload("powershell -File deploy-prod.ps1"))
check("predeploy/blocks non-matching target", code, BLOCK)

clear_artifacts()
write_artifact("stale.json", analyzed_at_epoch=int(time.time()) - 60 * 60 * 5)
code, err = run("guard-predeploy-analysis.py", predeploy_payload("powershell -File deploy-staging.ps1"))
check("predeploy/blocks stale census", code, BLOCK)
if code == BLOCK and "stale" not in err.lower():
    fails.append("predeploy: stale artifact not reported as stale")

clear_artifacts()
write_artifact("noseams.json", seams=[])
check(
    "predeploy/blocks empty census",
    run("guard-predeploy-analysis.py", predeploy_payload("powershell -File deploy-staging.ps1"))[0],
    BLOCK,
)

clear_artifacts()
write_artifact(
    "unsat.json",
    seams=[
        {
            "name": "config store",
            "produced_by": "bicep outputs",
            "consumed_by": "app settings",
            "unsatisfied": ["JWT_PUBLIC_KEY"],
        }
    ],
)
check(
    "predeploy/blocks unexplained unsatisfied seam",
    run("guard-predeploy-analysis.py", predeploy_payload("powershell -File deploy-staging.ps1"))[0],
    BLOCK,
)

clear_artifacts()
write_artifact(
    "explained.json",
    seams=[
        {
            "name": "config store",
            "produced_by": "bicep outputs",
            "consumed_by": "app settings",
            "unsatisfied": ["JWT_PUBLIC_KEY"],
            "explanation": "supplied out-of-band by the vault step; verified present",
        }
    ],
)
check(
    "predeploy/allows explained unsatisfied seam",
    run("guard-predeploy-analysis.py", predeploy_payload("powershell -File deploy-staging.ps1"))[0],
    ALLOW,
)
clear_artifacts()

# --------------------------------------------------------------------- checklist

os.makedirs(CHECKLIST_DIR, exist_ok=True)
with open(os.path.join(CHECKLIST_DIR, "c.json"), "w", encoding="utf-8") as f:
    json.dump(
        {
            "name": "t",
            "applies_to": {"always": True},
            "items": [
                {
                    "id": "tests-claimed",
                    "type": "command_ran",
                    "only_if_reply": "(?i)tests? pass",
                    "pattern": "(?i)test\\.ps1|pytest",
                    "fix": "run the tests",
                }
            ],
        },
        f,
    )
CL_ENV = {"DATRIX_CHECKLIST_DIR": CHECKLIST_DIR}


def checklist(messages, name):
    reset_checklist_state()
    return run(
        "checklist.py",
        {"session_id": SID, "transcript_path": transcript(messages, name)},
        env=CL_ENV,
    )


check(
    "checklist/blocks claim with no act",
    checklist([("text", "All tests pass.")], "c1.jsonl")[0],
    BLOCK,
)
check(
    "checklist/allows claim backed by a real command",
    checklist([("cmd", "test.ps1 datrix-common -Specific a.py"), ("text", "All tests pass.")], "c2.jsonl")[0],
    ALLOW,
)
check(
    "checklist/silent when the claim is absent",
    checklist([("text", "Fixed the seam at compose.py:88.")], "c3.jsonl")[0],
    ALLOW,
)

reset_checklist_state()
check(
    "checklist/never re-blocks an already-blocked stop",
    run(
        "checklist.py",
        {
            "session_id": SID,
            "stop_hook_active": True,
            "transcript_path": transcript([("text", "All tests pass.")], "c4.jsonl"),
        },
        env=CL_ENV,
    )[0],
    ALLOW,
)

# No configs at all is the common case and must cost nothing and block nothing.
empty = os.path.join(TMP, "empty-checklists")
os.makedirs(empty, exist_ok=True)
check(
    "checklist/no configs is silent",
    run(
        "checklist.py",
        {"session_id": SID, "transcript_path": transcript([("text", "All tests pass.")], "c5.jsonl")},
        env={"DATRIX_CHECKLIST_DIR": empty},
    )[0],
    ALLOW,
)

# A malformed config must be skipped, never enforced.
bad = os.path.join(TMP, "bad-checklists")
os.makedirs(bad, exist_ok=True)
with open(os.path.join(bad, "broken.json"), "w", encoding="utf-8") as f:
    f.write("{ this is not json")
check(
    "checklist/malformed config fails open",
    run(
        "checklist.py",
        {"session_id": SID, "transcript_path": transcript([("text", "All tests pass.")], "c6.jsonl")},
        env={"DATRIX_CHECKLIST_DIR": bad},
    )[0],
    ALLOW,
)

# ------------------------------------------------- the LIVE configs, not fixtures
#
# The fixture cases above prove the ENGINE works. These prove the configs actually
# shipped in `.claude/checklists/` are safe, which is a different question and the
# more dangerous one: `general.json` is `always: true`, so a careless edit to it
# blocks the Stop of every session in the workspace, on every turn, for any reply
# that happens to contain the words "tests pass".

live_cases = [
    ("ran tests then reported pass", [("cmd", "test.ps1 datrix-common -Specific a.py"), ("text", "All tests pass.")], ALLOW),
    ("ran a hook test file then reported pass", [("cmd", "python .claude/hooks/test-stop-gates.py"), ("text", "All checks pass.")], ALLOW),
    ("ordinary reply with no claim", [("text", "Changed the seam at compose.py:88.")], ALLOW),
    ("the word test used innocently", [("text", "I updated the test guidelines doc.")], ALLOW),
    ("deploy word without a deploy claim", [("text", "The deployment docs were updated.")], ALLOW),
    ("claims passing tests that never ran", [("text", "All tests pass.")], BLOCK),
    ("claims a deployment that never ran", [("text", "The service is live and the deployment succeeded.")], BLOCK),
]

for index, (label, messages, want) in enumerate(live_cases):
    reset_checklist_state()
    code, _ = run(
        "checklist.py",
        {"session_id": SID, "transcript_path": transcript(messages, f"live{index}.jsonl")},
    )
    check(f"live-config/{label}", code, want)

# ------------------------------------------------------------------ skill record

run("record-active-skill.py", {"session_id": SID, "prompt": "/fix-codegen-azure please"})
recorded = os.path.join(STATE, f"skill-{SID}.json")
with open(recorded, encoding="utf-8") as f:
    if json.load(f).get("skill") != "fix-codegen-azure":
        fails.append("record-active-skill: typed form not detected")

run(
    "record-active-skill.py",
    {"session_id": SID, "prompt": "Base directory for this skill: d:\\datrix\\.claude\\skills\\task-orchestrator\n\n# Task Orchestrator"},
)
with open(recorded, encoding="utf-8") as f:
    if json.load(f).get("skill") != "task-orchestrator":
        fails.append("record-active-skill: expanded-body form not detected")

run("record-active-skill.py", {"session_id": SID, "prompt": "now fix the other thing"})
with open(recorded, encoding="utf-8") as f:
    if json.load(f).get("skill") != "":
        fails.append("record-active-skill: stale skill not cleared on a plain prompt")

# ------------------------------------------------------------------------ report

disarm()
reset_checklist_state()
shutil.rmtree(TMP, ignore_errors=True)
clear_artifacts()

if fails:
    print(f"FAIL ({len(fails)})")
    for line in fails:
        print("  -", line)
    sys.exit(1)
print("PASS - all hook checks green (block and over-block directions)")
