"""SessionStart(compact) hook: rebuild the mandatory context after a compaction.

Compaction summarizes the message history. Everything an agent READ is gone —
only the system prompt, CLAUDE.md, and MEMORY.md are re-injected from disk.
An instruction that says "re-read the docs after compacting" therefore competes
with whatever task the agent was mid-way through, and loses exactly when context
is most crowded. So we stop asking, and let the harness do it.

Two mechanisms, both fired from here:

  1. INJECT — the small, highest-authority docs are emitted verbatim into the
     fresh context window. Nothing to remember, nothing to obey.

  2. ARM THE GATE — the large docs cannot be inlined affordably, so instead we
     write a state file listing them. `gate-mandatory-reads.py` (PreToolUse on
     Write/Edit) then BLOCKS all edits until `track-mandatory-reads.py`
     (PostToolUse on Read) has seen every one of them read in this
     post-compaction window. The agent cannot proceed by forgetting.

The gate is inert in sessions that never compacted: no state file, no cost.

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
        with open(_abs(rel_path), "r", encoding="utf-8") as handle:
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
        with open(task_path, "r", encoding="utf-8") as handle:
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


def _arm_gate(session_id: str, gated: list[tuple[str, str]]) -> None:
    """Write the state file that `gate-mandatory-reads.py` enforces."""
    if not session_id or not gated:
        return
    os.makedirs(_STATE_DIR, exist_ok=True)
    state = {
        "required": [{"path": p, "label": label} for p, label in gated],
        "read": [],
    }
    state_path = os.path.join(_STATE_DIR, f"post-compact-{session_id}.json")
    with open(state_path, "w", encoding="utf-8") as handle:
        json.dump(state, handle, indent=2)


def _schema_canary(transcript_path: str) -> str:
    """Warn loudly if the transcript compaction marker has stopped being recognizable.

    The subagent half of the gate (gate-mandatory-reads.py signal B) detects
    compaction by finding an `isCompactSummary` entry in the transcript. That schema
    is internal to Claude Code and Anthropic warns it can change between releases.
    If it changes, signal B goes silently dark — and a silently dead guard is worse
    than no guard.

    This hook runs at the ONE moment we know for certain a compaction just happened.
    So if the marker is not in the transcript, the schema has drifted. Say so, loudly.
    """
    if not transcript_path or not os.path.isfile(transcript_path):
        return ""

    try:
        with open(transcript_path, "r", encoding="utf-8", errors="ignore") as handle:
            for line in handle:
                if '"isCompactSummary"' in line:
                    return ""  # marker still present — signal B is healthy
    except OSError:
        return ""

    return (
        "===== WARNING: THE SUBAGENT COMPACTION GUARD HAS GONE DARK =====\n\n"
        "A compaction just happened, but no `isCompactSummary` marker was found in "
        "the transcript. The transcript schema has changed.\n\n"
        "Consequence: gate-mandatory-reads.py can no longer detect compaction in "
        "SUBAGENTS (it still works in the main session via the state file). A "
        "subagent that compacts mid-task will now silently edit code without "
        "re-reading the mandatory docs.\n\n"
        "This is a defect to fix now, not later: find the new marker field in the "
        "transcript JSONL and update `_last_compaction_index` in "
        ".claude/hooks/gate-mandatory-reads.py. Tell Jon."
    )


def _build_context(gated: list[tuple[str, str]], now: float, transcript_path: str) -> str:
    parts: list[str] = [
        "THE CONTEXT WAS JUST COMPACTED. Everything you had read is gone from "
        "your context — do not act on any recollection of a file's contents. "
        "The governing documents are restored below."
    ]

    canary = _schema_canary(transcript_path)
    if canary:
        parts.append(canary)

    inline = _inline_section()
    if inline:
        parts.append(inline)

    if gated:
        listing = "\n".join(f"  {i}. {p}\n     {label}" for i, (p, label) in enumerate(gated, 1))
        parts.append(
            "===== MANDATORY READS — ENFORCED =====\n\n"
            "These are too large to inline. Read each of them with the Read tool "
            "NOW, before you resume work:\n\n"
            f"{listing}\n\n"
            "This is not advisory. Write, Edit, and NotebookEdit are BLOCKED by a "
            "PreToolUse hook until every file above has been read in this "
            "post-compaction window. Reading them first costs you one step; "
            "discovering the block costs you a turn."
        )

    tasks = _active_tasks(now)
    if tasks:
        parts.append(
            "===== WORK IN FLIGHT (task files touched in the last 24h) =====\n\n"
            "A filesystem heuristic, not a record of what THIS session was doing — "
            "confirm against the conversation summary before acting on it.\n\n"
            + "\n".join(tasks)
        )

    return "\n\n".join(parts)


def main() -> None:
    try:
        data = json.loads(sys.stdin.read())
    except json.JSONDecodeError:
        sys.exit(0)

    # Belt and braces: settings.json already scopes this hook to `compact`.
    if data.get("source") not in ("compact", None):
        sys.exit(0)

    now = time.time()
    gated = _existing_gated_docs()
    _arm_gate(data.get("session_id", ""), gated)

    print(
        json.dumps(
            {
                "hookSpecificOutput": {
                    "hookEventName": "SessionStart",
                    "additionalContext": _build_context(
                        gated, now, data.get("transcript_path", "")
                    ),
                }
            }
        )
    )
    sys.exit(0)


if __name__ == "__main__":
    main()
