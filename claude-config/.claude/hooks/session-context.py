"""SessionStart hook: arm the mandatory-read gate, and rebuild context after a compaction.

Two entry conditions, one owner. Both end in the same place — no Write/Edit until
the governing documents have actually been read — because the hole they close is
the same hole:

  COMPACT  — the summary discards everything the agent read. An instruction to
             "re-read the docs afterwards" competes with the task in flight and
             loses exactly when context is most crowded.
  STARTUP  — a fresh session never read them in the first place. CLAUDE.md is
  RESUME     re-injected from disk by the harness; the larger architecture and
  CLEAR      agent-rule docs are NOT, and nothing asked for them. A session that
             never compacts could therefore edit framework source all day having
             read neither. That is not hypothetical: session 0d87c146 made 66
             edits across datrix-codegen-azure source, templates and tests, with
             zero compactions and zero reads of either gated doc.

Two mechanisms, fired from here:

  1. INJECT — after a COMPACTION only, the small highest-authority docs are
     emitted verbatim into the fresh window. Nothing to remember, nothing to obey.
     A fresh session does not pay this: it still has CLAUDE.md, and inlining 40KB
     into every question-only session is a tax with no defect behind it.

  2. ARM THE GATE — the large docs cannot be inlined affordably, so instead a
     state file lists them. `gate-mandatory-reads.py` (PreToolUse on Write/Edit)
     BLOCKS every edit until `track-mandatory-reads.py` (PostToolUse on Read) has
     seen each one read. The agent cannot proceed by forgetting.

Arming is free. It costs nothing in a session that never edits, and two reads in
one that does — the gate fires on the first edit, not on session start.

WHEN THE READ LEDGER RESETS
  compact / clear — context is gone, so prior reads no longer count: reset.
  startup         — nothing read yet: arm fresh.
  resume          — the prior context comes back with it, so its reads still
                    stand. Never overwrite an existing ledger, or a resumed
                    session pays for the same two docs twice.

Output contract: for SessionStart, ONLY `hookSpecificOutput.additionalContext`
reaches the model. Plain stdout goes to the debug log.
"""

import json
import os
import re
import sys
import time
from typing import Final

_REPO_ROOT: Final = "d:/datrix"
_STATE_DIR: Final = os.path.join(_REPO_ROOT, ".claude", "hooks", ".state")

# Sources whose context is genuinely gone, so the read ledger must start empty.
_RESETTING_SOURCES: Final = ("compact", "clear")

# Emitted verbatim into the post-compaction window. Small, and the highest
# authority in the repo — worth their tokens on every compaction.
_INLINE_DOCS: Final = (
    (".claude/skills/_shared/execution-contract.md", "EXECUTION CONTRACT"),
    (
        "datrix/docs/architecture/design-principles-cheat-sheet.md",
        "DESIGN PRINCIPLES CHEAT SHEET",
    ),
)

# Too large to inline. These are ENFORCED instead: no Write/Edit until read.
_GATED_DOCS: Final = (
    ("datrix/docs/architecture/architecture-cheat-sheet.md", "Architecture cheat sheet"),
    (
        "datrix-common/docs/contributing/ai-agent-rules.md",
        "Agent rules (read its sub-docs under ai-agent-rules/ as the work requires)",
    ),
)

# How far back a task file counts as "the work in flight".
_ACTIVE_TASK_MAX_AGE_S: Final = 24 * 60 * 60
_MAX_ACTIVE_TASKS_SHOWN: Final = 8

_COMPLETED_HEADING_RE: Final = re.compile(r"^#\s+COMPLETED:", re.MULTILINE)


def _abs(rel_path: str) -> str:
    return os.path.join(_REPO_ROOT, rel_path.replace("/", os.sep))


def _read(rel_path: str) -> str:
    try:
        with open(_abs(rel_path), encoding="utf-8") as handle:
            return handle.read()
    except OSError:
        return ""


def _inline_section() -> str:
    """Verbatim text of the small mandatory docs."""
    blocks: list[str] = []
    for rel_path, label in _INLINE_DOCS:
        body = _read(rel_path)
        if not body:
            continue
        blocks.append(f"===== {label} — {rel_path} =====\n\n{body.strip()}")
    return "\n\n".join(blocks)


def _existing_gated_docs() -> list[tuple[str, str]]:
    """Only gate on docs that actually exist — never demand reading a missing file."""
    return [(p, label) for p, label in _GATED_DOCS if os.path.isfile(_abs(p))]


def _task_status_line(task_path: str) -> str:
    """`<name> — COMPLETED|OPEN`, from the task file's own heading."""
    try:
        with open(task_path, encoding="utf-8") as handle:
            head = handle.read(2048)
    except OSError:
        return ""
    state = "COMPLETED" if _COMPLETED_HEADING_RE.search(head) else "OPEN"
    return f"{os.path.basename(task_path)} — {state}"


def _active_tasks(now: float) -> list[str]:
    """Task files touched recently, newest first. A pointer, not a conclusion."""
    found: list[tuple[float, str]] = []
    for package in os.listdir(_REPO_ROOT):
        tasks_dir = os.path.join(_REPO_ROOT, package, ".tasks")
        if not os.path.isdir(tasks_dir):
            continue
        for root, _dirs, files in os.walk(tasks_dir):
            for name in files:
                if not name.endswith(".md"):
                    continue
                path = os.path.join(root, name)
                try:
                    mtime = os.path.getmtime(path)
                except OSError:
                    continue
                if now - mtime <= _ACTIVE_TASK_MAX_AGE_S:
                    found.append((mtime, path))

    found.sort(reverse=True)
    lines: list[str] = []
    for _mtime, path in found[:_MAX_ACTIVE_TASKS_SHOWN]:
        status = _task_status_line(path)
        if not status:
            continue
        rel = os.path.relpath(path, _REPO_ROOT).replace(os.sep, "/")
        lines.append(f"  {rel}\n    {status}")
    return lines


_PHASE_DIR_RE: Final = re.compile(r"^phase-(\d{1,3})$", re.IGNORECASE)


def _pending_by_phase() -> dict[int, tuple[int, int]]:
    """{phase: (pending, total)} counted from task-file headings across every package."""
    counts: dict[int, tuple[int, int]] = {}
    for package in os.listdir(_REPO_ROOT):
        tasks_dir = os.path.join(_REPO_ROOT, package, ".tasks")
        if not os.path.isdir(tasks_dir):
            continue
        for entry in os.listdir(tasks_dir):
            match = _PHASE_DIR_RE.match(entry)
            phase_dir = os.path.join(tasks_dir, entry)
            if not match or not os.path.isdir(phase_dir):
                continue
            phase = int(match.group(1))
            pending, total = counts.get(phase, (0, 0))
            for name in os.listdir(phase_dir):
                if not name.startswith("task-") or not name.endswith(".md"):
                    continue
                total += 1
                try:
                    with open(os.path.join(phase_dir, name), encoding="utf-8") as handle:
                        head = handle.read(2048)
                except OSError:
                    continue
                if not _COMPLETED_HEADING_RE.search(head):
                    pending += 1
            counts[phase] = (pending, total)
    return counts


def _ledger_section() -> str:
    """The task ledger as disk truth — the one fact a compaction must not blur.

    A compaction re-injects the CONTRACT (prose the agent already agreed with and
    stopped anyway). What it loses is the LEDGER: how much work is actually left. An
    agent that resumes believing it is near the end writes a summary; one that resumes
    reading "45 of 61 pending" dispatches the next wave. So the number is restored
    alongside the rules, straight off the task files, owing nothing to the summary.

    Compaction only. A fresh session has no run in flight, and opening one by
    announcing another run's backlog invents pressure that belongs to nobody.
    """
    counts = {p: v for p, v in _pending_by_phase().items() if v[0]}
    if not counts:
        return ""
    lines = [
        f"  phase {phase:02d}: {pending} of {total} tasks NOT finished"
        for phase, (pending, total) in sorted(counts.items(), reverse=True)
    ]
    total_pending = sum(pending for pending, _ in counts.values())
    return (
        "===== TASK LEDGER — DISK TRUTH =====\n\n"
        f"{total_pending} task(s) are not COMPLETED right now:\n\n"
        + "\n".join(lines)
        + "\n\nIf a run is in flight, this is what finished means — every one of them "
        "COMPLETED or carrying a valid B1-B4 proof. A green test suite, a clean "
        "summary, and a phase boundary are not exits, and neither is handing a "
        "decision to Jon (that is rung 3: spawn a Fable adjudicator). The Stop hook "
        "reads these same files and will refuse a turn that ends above zero."
    )


def state_path(session_id: str) -> str:
    return os.path.join(_STATE_DIR, f"mandatory-reads-{session_id}.json")


def _arm_gate(session_id: str, source: str, gated: list[tuple[str, str]]) -> None:
    """Write the state file that `gate-mandatory-reads.py` enforces.

    A `resume`/`startup` never clobbers an existing ledger: the reads it records
    are still valid, and rewriting them would charge a resumed session twice for
    docs already in its context.
    """
    if not session_id or not gated:
        return
    path = state_path(session_id)
    if source not in _RESETTING_SOURCES and os.path.isfile(path):
        return
    os.makedirs(_STATE_DIR, exist_ok=True)
    state = {
        "source": source,
        "required": [{"path": p, "label": label} for p, label in gated],
        "read": [],
    }
    with open(path, "w", encoding="utf-8") as handle:
        json.dump(state, handle, indent=2)


def _schema_canary() -> str:
    """Report transcript-marker drift — as detected by the gate, never by this hook.

    This hook CANNOT detect drift itself, and must not try. The harness appends the
    compaction record (`compact_boundary` / `isCompactSummary`) to the transcript
    *after* SessionStart(compact) returns, so scanning the live transcript here reads
    a file that does not yet contain the marker being looked for. An earlier version
    did exactly that and reported "THE GUARD HAS GONE DARK" on every compaction while
    the guard was in fact healthy — a false alarm every time, which trains the reader
    to ignore the one alarm that will ever be true.

    The honest check lives in gate-mandatory-reads.py, where signal A (state file) and
    signal B (transcript) are observable together and the transcript is long flushed:
    A-armed-by-a-compaction but B-blind is real drift. It drops the flag file this
    function reports.
    """
    flag_path = os.path.join(_STATE_DIR, "schema-drift.json")
    if not os.path.isfile(flag_path):
        return ""

    return (
        "===== WARNING: THE SUBAGENT COMPACTION GUARD HAS GONE DARK =====\n\n"
        "gate-mandatory-reads.py recorded transcript-marker drift: a compaction was "
        "confirmed by the state file, but the transcript scan could not see it.\n\n"
        "Consequence: signal B is dark for SUBAGENTS (the main session is still "
        "enforced by the state file). A subagent that compacts mid-task will silently "
        "edit code without re-reading the mandatory docs.\n\n"
        "This is a defect to fix now, not later: find the new marker field in the "
        "transcript JSONL, update `_is_compaction_entry` in "
        ".claude/hooks/gate-mandatory-reads.py, and delete "
        f"{flag_path}. Tell Jon."
    )


def _gated_listing(gated: list[tuple[str, str]]) -> str:
    return "\n".join(f"  {i}. {p}\n     {label}" for i, (p, label) in enumerate(gated, 1))


def _compaction_context(gated: list[tuple[str, str]], now: float) -> str:
    parts: list[str] = [
        "THE CONTEXT WAS JUST COMPACTED. Everything you had read is gone from "
        "your context — do not act on any recollection of a file's contents. "
        "The governing documents are restored below."
    ]

    for section in (_schema_canary(), _inline_section()):
        if section:
            parts.append(section)

    if gated:
        parts.append(
            "===== MANDATORY READS — ENFORCED =====\n\n"
            "These are too large to inline. Read each of them with the Read tool "
            "NOW, before you resume work:\n\n"
            f"{_gated_listing(gated)}\n\n"
            "This is not advisory. Write, Edit, and NotebookEdit are BLOCKED by a "
            "PreToolUse hook until every file above has been read in this "
            "post-compaction window. Reading them first costs you one step; "
            "discovering the block costs you a turn."
        )

    ledger = _ledger_section()
    if ledger:
        parts.append(ledger)

    tasks = _active_tasks(now)
    if tasks:
        parts.append(
            "===== WORK IN FLIGHT (task files touched in the last 24h) =====\n\n"
            "A filesystem heuristic, not a record of what THIS session was doing — "
            "confirm against the conversation summary before acting on it.\n\n"
            + "\n".join(tasks)
        )

    return "\n\n".join(parts)


def _fresh_session_context(gated: list[tuple[str, str]]) -> str:
    """Short by design. The gate does the work; this only says where it is."""
    if not gated:
        return ""
    parts = [
        "===== MANDATORY READS — ENFORCED =====\n\n"
        "Read these with the Read tool before your first Write/Edit in this session:\n\n"
        f"{_gated_listing(gated)}\n\n"
        "This is not advisory. Write, Edit, and NotebookEdit are BLOCKED by a "
        "PreToolUse hook until every file above has been read.\n\n"
        "CLAUDE.md is injected into your context automatically; these two are not, "
        "and nothing else will ask you for them. Until this gate existed, a session "
        "that never compacted could edit framework source from end to end having read "
        "neither — which is exactly what happened, 66 edits deep, in "
        "datrix-codegen-azure.\n\n"
        "Answering a question costs nothing here: the block fires on the first edit, "
        "not now."
    ]
    canary = _schema_canary()
    if canary:
        parts.insert(0, canary)
    return "\n\n".join(parts)


def main() -> None:
    try:
        data = json.loads(sys.stdin.read())
    except json.JSONDecodeError:
        sys.exit(0)

    source = data.get("source") or "startup"
    gated = _existing_gated_docs()
    _arm_gate(data.get("session_id", ""), source, gated)

    context = (
        _compaction_context(gated, time.time())
        if source == "compact"
        else _fresh_session_context(gated)
    )
    if not context:
        sys.exit(0)

    print(
        json.dumps(
            {
                "hookSpecificOutput": {
                    "hookEventName": "SessionStart",
                    "additionalContext": context,
                }
            }
        )
    )
    sys.exit(0)


if __name__ == "__main__":
    main()
