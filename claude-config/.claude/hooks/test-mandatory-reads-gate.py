"""Exercise session-context.py + track-mandatory-reads.py + gate-mandatory-reads.py.

The three hooks are one mechanism: SessionStart arms a read ledger, PostToolUse(Read)
ticks it off, PreToolUse(Write|Edit) refuses until it is clear. Asserting them
separately proves nothing, so every case below drives the real files end to end.

The regression that motivated this file: the gate was armed ONLY by a compaction, so
a session that never compacted could edit framework source from end to end having
read neither gated doc. Session 0d87c146 did exactly that — 66 edits into
datrix-codegen-azure, zero reads. Cases marked THE INCIDENT cover it.

Both directions are asserted. A gate that never fires is worthless; a gate that
fires on a scratch file, on an already-compliant session, or that cries schema
drift on every fresh session is worse than worthless, because it trains the reader
to route around it.
"""
import json
import os
import subprocess
import sys
import tempfile

HOOKS = r"d:\datrix\.claude\hooks"
STATE_DIR = os.path.join(HOOKS, ".state")
SESSION = "TEST-mandatory-reads-gate"
STATE_FILE = os.path.join(STATE_DIR, f"mandatory-reads-{SESSION}.json")
DRIFT_FILE = os.path.join(STATE_DIR, "schema-drift.json")

ARCH = "d:/datrix/datrix/docs/architecture/architecture-cheat-sheet.md"
RULES = "d:/datrix/datrix-common/docs/contributing/ai-agent-rules.md"
SOURCE = r"d:\datrix\datrix-codegen-azure\src\datrix_codegen_azure\generators\bicep.py"
SCRATCH = r"d:\datrix\.tmp\probe.json"

BLOCK, ALLOW = 2, 0
fails = []


def run(hook, payload):
    p = subprocess.run([sys.executable, os.path.join(HOOKS, hook)],
                       input=json.dumps(payload), capture_output=True, text=True)
    return p.returncode, p.stdout, p.stderr


def start(source):
    return run("session-context.py", {"session_id": SESSION, "source": source})


def read_doc(path):
    return run("track-mandatory-reads.py",
               {"tool_name": "Read", "session_id": SESSION, "tool_input": {"file_path": path}})


def edit(path, transcript=""):
    code, _out, err = run("gate-mandatory-reads.py", {
        "tool_name": "Edit", "session_id": SESSION,
        "transcript_path": transcript, "tool_input": {"file_path": path},
    })
    return code, err


def check(label, got, want):
    ok = got == want
    if not ok:
        fails.append(f"{label}: got {got!r} want {want!r}")
    print(f"  {'PASS' if ok else 'FAIL'}  {label}")


def ledger():
    with open(STATE_FILE, encoding="utf-8") as handle:
        return json.load(handle)


def cleanup():
    for path in (STATE_FILE, DRIFT_FILE):
        if os.path.isfile(path):
            os.remove(path)


def transcript_with_compaction():
    """A minimal transcript carrying a compaction marker and no Reads after it."""
    handle = tempfile.NamedTemporaryFile("w", suffix=".jsonl", delete=False, encoding="utf-8")
    handle.write(json.dumps({"type": "user", "isCompactSummary": True}) + "\n")
    handle.close()
    return handle.name


# A pre-existing drift flag would make the canary assertions meaningless, and
# leaving one behind would banner every future session. Stash it, restore at exit.
saved_drift = None
if os.path.isfile(DRIFT_FILE):
    with open(DRIFT_FILE, encoding="utf-8") as h:
        saved_drift = h.read()

cleanup()

try:
    print("== unarmed session: fails OPEN, never wedges ==")
    code, _ = edit(SOURCE)
    check("no ledger, no transcript -> allow", code, ALLOW)
    check("no ledger -> no drift alarm", os.path.isfile(DRIFT_FILE), False)

    print("== THE INCIDENT: fresh session, no compaction ==")
    code, out, _ = start("startup")
    check("SessionStart(startup) exits 0", code, ALLOW)
    check("startup arms the ledger", os.path.isfile(STATE_FILE), True)
    check("ledger records its source", ledger()["source"], "startup")
    check("ledger starts empty", ledger()["read"], [])
    ctx = json.loads(out)["hookSpecificOutput"]["additionalContext"]
    check("startup notice names the cheat sheet", "architecture-cheat-sheet.md" in ctx, True)
    check("startup notice names the agent rules", "ai-agent-rules.md" in ctx, True)
    check("startup does NOT inline the execution contract",
          "===== EXECUTION CONTRACT" in ctx, False)

    code, err = edit(SOURCE)
    check("edit with nothing read -> BLOCK", code, BLOCK)
    check("block names the unread cheat sheet", "architecture-cheat-sheet.md" in err, True)
    check("block names the unread agent rules", "ai-agent-rules.md" in err, True)
    check("block does not claim a compaction happened", "was compacted" in err, False)
    check("block says 'in this session'", "in this session" in err, True)
    check("fresh-session block has no drift alarm", os.path.isfile(DRIFT_FILE), False)

    print("== scratch space stays writable while blocked ==")
    check("workspace .tmp -> allow", edit(SCRATCH)[0], ALLOW)

    print("== reading the docs clears the block ==")
    read_doc(ARCH)
    code, err = edit(SOURCE)
    check("one of two read -> still BLOCK", code, BLOCK)
    check("block no longer lists the doc already read",
          "architecture-cheat-sheet.md" in err, False)
    read_doc(RULES)
    check("both read -> allow", edit(SOURCE)[0], ALLOW)
    check("ledger recorded both reads", len(ledger()["read"]), 2)

    print("== resume preserves the ledger; clear and compact reset it ==")
    start("resume")
    check("resume does not clobber reads", len(ledger()["read"]), 2)
    check("resume leaves the session unblocked", edit(SOURCE)[0], ALLOW)
    start("clear")
    check("clear resets the reads", ledger()["read"], [])
    check("clear re-blocks the edit", edit(SOURCE)[0], BLOCK)

    print("== compaction: reset, inline the contract, keep the old wording ==")
    read_doc(ARCH)
    read_doc(RULES)
    code, out, _ = start("compact")
    check("compact resets the reads", ledger()["read"], [])
    check("compact records its source", ledger()["source"], "compact")
    ctx = json.loads(out)["hookSpecificOutput"]["additionalContext"]
    check("compact inlines the execution contract", "===== EXECUTION CONTRACT" in ctx, True)
    tx = transcript_with_compaction()
    code, err = edit(SOURCE, transcript=tx)
    check("compacted + unread -> BLOCK", code, BLOCK)
    check("compacted block says so", "was compacted" in err, True)

    print("== transcript signal alone arms the gate (the subagent case) ==")
    cleanup()
    code, err = edit(SOURCE, transcript=tx)
    check("no ledger, compacted transcript -> BLOCK", code, BLOCK)
    check("transcript-only block says compacted", "was compacted" in err, True)
    os.remove(tx)

    print("== schema-drift canary fires for compact, stays silent for startup ==")
    cleanup()
    start("startup")
    edit(SOURCE)
    check("startup-armed + no transcript -> NO false drift alarm",
          os.path.isfile(DRIFT_FILE), False)
    cleanup()
    start("compact")
    edit(SOURCE)
    check("compact-armed + no transcript marker -> drift alarm",
          os.path.isfile(DRIFT_FILE), True)

finally:
    cleanup()
    if saved_drift is not None:
        with open(DRIFT_FILE, "w", encoding="utf-8") as h:
            h.write(saved_drift)

print()
if fails:
    print(f"{len(fails)} FAILURE(S):")
    for f in fails:
        print("  - " + f)
    sys.exit(1)
print("all checks passed")
