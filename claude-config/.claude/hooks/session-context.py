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

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from _mcp_registration import (  # noqa: E402
    CODE_INDEX_SERVER,
    LOCAL_LLM_SERVER,
    is_registered,
    session_directory,
)

_REPO_ROOT: Final = "d:/datrix"
_STATE_DIR: Final = os.path.join(_REPO_ROOT, ".claude", "hooks", ".state")

# Sources whose context is genuinely gone, so the read ledger must start empty.
_RESETTING_SOURCES: Final = ("compact", "clear")

# Emitted verbatim into the post-compaction window. The contract's CORE (the closed
# blocker list, the proof, the exit rules, §14) and the principles sheet are the
# highest authority in the repo — worth their tokens on every compaction. The
# contract's topic files (spend, verification, security, reporting) are read when
# the work calls for them, as CLAUDE.md's lead table says.
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

# Said in every session start: the docs are packs read on demand, and this finds the right one.
_INEEDTOKNOW_NOTE: Final = (
    "Don't know where something is documented? Ask instead of loading docs: "
    f'`powershell -File "{_REPO_ROOT}/datrix/scripts/dev/ineedtoknow.ps1" "<your question>"` '
    "answers from the architecture packs, agent rules and execution contract with the file and "
    "line range to open (a lead: open the lines before acting). The docs are read on demand, "
    "by pack — not all up front."
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

    The honest check lives in gate-mandatory-reads.py, where the transcript is long
    flushed and the two markers can be compared against EACH OTHER: this repo's own
    `SessionStart:compact` record proves the transcript compacted, so if the harness's
    own fields are missing from it, they were renamed. Nothing is inferred from the
    state file's `source`, which is sticky for the whole session and says nothing
    about the transcript. That function drops — and retracts — the flag reported here.
    """
    flag_path = os.path.join(_STATE_DIR, "schema-drift.json")
    if not os.path.isfile(flag_path):
        return ""

    return (
        "===== WARNING: THE HARNESS COMPACTION MARKERS HAVE BEEN RENAMED =====\n\n"
        "gate-mandatory-reads.py compared its two transcript markers: a compaction "
        "provably happened (this repo's own `SessionStart:compact` record is in the "
        "transcript), but neither `isCompactSummary` nor `compact_boundary` appears "
        "anywhere in it.\n\n"
        "Consequence: the main session is still covered — the gate reads the "
        "self-owned record too. A SUBAGENT is not: SessionStart does not fire inside "
        "one, so its only signal is the renamed pair, and a subagent that compacts "
        "mid-task will silently edit code without re-reading the mandatory docs.\n\n"
        "This is a defect to fix now, not later: find the new marker field in the "
        "transcript JSONL and update `_upstream_compaction_marker` in "
        ".claude/hooks/gate-mandatory-reads.py. The flag at "
        f"{flag_path} retracts itself once the markers are readable again."
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
            "discovering the block costs you a turn.\n\n"
            f"{_INEEDTOKNOW_NOTE}"
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
        "not now.\n\n"
        f"{_INEEDTOKNOW_NOTE}"
    ]
    canary = _schema_canary()
    if canary:
        parts.insert(0, canary)
    return "\n\n".join(parts)


def _absent_server_notice(cwd: str, server: str, title: str, script: str, fallback: str) -> str:
    return (
        f"===== {title} — MCP TOOLS ABSENT =====\n\n"
        f"The `{server}` MCP server is not registered for the directory this session started in "
        f"({cwd or 'unknown'}) on this machine, so no `mcp__{server}__*` tool exists here. "
        "Tell Jon once, in your first reply: it is fixed by running "
        f"`powershell -File \"{script}\" -Setup` and reloading the window.\n\n{fallback}"
    )


def _mcp_notices(cwd: str) -> str:
    """Says so for each Datrix MCP server this session lacks; empty when it has them all.

    CLAUDE.md and the agent templates send agents to the code index's and the local
    models' MCP tools, but those tools exist only where `code-index.ps1 -Setup` and
    `local-llm.ps1 -Setup` registered the servers for the session's directory. Without
    this notice a machine that never ran them looks exactly like one that did: every
    agent silently falls back to grep and whole-file reads, and nobody is told why.
    """
    notices: list[str] = []
    if not is_registered(cwd, CODE_INDEX_SERVER):
        script = f"{_REPO_ROOT}/datrix/scripts/dev/code-index.ps1"
        notices.append(_absent_server_notice(
            cwd, CODE_INDEX_SERVER, "CODE INDEX", script,
            "Until then, use the same index from the shell for definitions, uses and outlines: "
            f"`powershell -File \"{script}\" -Symbol <name>`, `-References <dotted.path>`, "
            "`-Outline <path>`, `-Canonical <topic>`."))
    if not is_registered(cwd, LOCAL_LLM_SERVER):
        notices.append(_absent_server_notice(
            cwd, LOCAL_LLM_SERVER, "LOCAL MODELS", f"{_REPO_ROOT}/datrix/scripts/dev/local-llm.ps1",
            "Until then, ask_files and digest_log are unavailable: read files and logs yourself, by "
            "range where you can."))
    return "\n\n".join(notices)


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
    notice = _mcp_notices(session_directory(str(data.get("cwd", ""))))
    context = "\n\n".join(part for part in (context, notice) if part)
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
