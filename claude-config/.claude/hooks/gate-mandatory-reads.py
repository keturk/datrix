"""PreToolUse(Write|Edit|NotebookEdit) hook: no edits until the mandatory docs
have been read IN THIS SESSION (or, after a compaction, re-read since it).

Two ways to arrive here, one rule. A fresh session never read the docs at all; a
compacted one had them discarded. Either way an instruction to "read the docs
first" competes with whatever task is in flight and loses, so the harness enforces
it instead: a blocked tool call cannot be forgotten past.

TWO INDEPENDENT SIGNALS, BECAUSE EACH ONE HAS A HOLE
----------------------------------------------------
`PreToolUse` and `PostToolUse` are DOCUMENTED to fire for tool calls inside
subagents, so this gate runs there too. Knowing *what the agent has read* is the
hard part, and neither available signal is sufficient alone:

  A. STATE FILE — written by session-context.py on SessionStart (every source:
     startup, resume, clear, compact), ticked off by track-mandatory-reads.py on
     each Read.
     Hole: SessionStart firing inside a SUBAGENT that auto-compacts mid-task is
     NOT documented. Subagents are exactly where a silent compaction does the
     most damage, because nobody is watching.

  B. TRANSCRIPT — every agent, main or sub, gets `transcript_path` in its hook
     input pointing at its OWN transcript (the same assumption check-agent-report.py
     already relies on in production). A compaction leaves a `type: user` entry
     with `isCompactSummary: true`; Reads after it are the post-compaction reads.
     Hole: the transcript JSONL schema is internal and Anthropic warns it can
     change between releases. A field rename would make this signal go quiet.
     It is also silent for a session that never compacted — signal A alone covers
     the fresh-session case.

So the gate ORs them. Either signal arms it, and a doc counts as read if EITHER
signal saw the Read. If the transcript schema changes, sessions stay enforced by
the state file; if SessionStart never fires in a subagent, the transcript still
catches a compaction there. Neither failure can wedge the session: an
unrecognized transcript and a missing state file both mean "not armed", which
fails OPEN, not closed.

The rule, in one line:

    if a mandatory doc has not been Read in this session — or, after a
    compaction, not re-read since it — then editing is blocked.

Arming costs nothing until the first edit, so question-only sessions pay nothing.

Writes to the sanctioned scratch dirs are exempt: an agent may legitimately need
to investigate after a compaction, and those paths cannot reach product code.

Exit codes:
  0 — allow
  2 — block (stderr becomes feedback to Claude)
"""

import json
import os
import sys
from typing import Final

_REPO_ROOT: Final = "d:/datrix"
_STATE_DIR: Final = os.path.join(_REPO_ROOT, ".claude", "hooks", ".state")

# Must be read before any edit, and re-read after any compaction. Keep this list
# SHORT — every entry is a tax on the first edit of every session. Small,
# high-authority docs are injected verbatim by session-context.py after a
# compaction instead of being gated here.
_REQUIRED_DOCS: Final = (
    ("datrix/docs/architecture/architecture-cheat-sheet.md", "Architecture cheat sheet"),
    (
        "datrix-common/docs/contributing/ai-agent-rules.md",
        "Agent rules (read its sub-docs under ai-agent-rules/ as the work requires)",
    ),
)

# Mirrors CLAUDE.md § Temporary File Policy — scratch space stays reachable.
_EXEMPT_PREFIXES: Final = (
    "d:/datrix/.scripts/",
    "d:/datrix/.test-output/",
    "d:/datrix/.tmp/",
)
_EXEMPT_SEGMENTS: Final = ("/scratchpad/", "/appdata/local/temp/")


def _normalize(path: str) -> str:
    return path.replace("\\", "/").lower()


def _is_exempt(path: str) -> bool:
    return path.startswith(_EXEMPT_PREFIXES) or any(s in path for s in _EXEMPT_SEGMENTS)


def _required_docs() -> list[tuple[str, str]]:
    """Only gate on docs that exist — never demand a read of a missing file."""
    return [
        (p, label)
        for p, label in _REQUIRED_DOCS
        if os.path.isfile(os.path.join(_REPO_ROOT, p.replace("/", os.sep)))
    ]


def _entries(transcript_path: str) -> list[dict[str, object]]:
    try:
        with open(transcript_path, encoding="utf-8", errors="ignore") as handle:
            lines = handle.readlines()
    except OSError:
        return []

    entries: list[dict[str, object]] = []
    for line in lines:
        try:
            entries.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return entries


def _is_compaction_entry(entry: dict[str, object]) -> bool:
    """True for either marker the harness writes when it compacts a context.

    Two independent field names are accepted, because a compaction writes BOTH a
    `system`/`compact_boundary` entry and a `user`/`isCompactSummary` entry. Reading
    either one keeps signal B alive if a release renames the other.
    """
    return bool(entry.get("isCompactSummary")) or entry.get("subtype") == "compact_boundary"


def _last_compaction_index(entries: list[dict[str, object]]) -> int:
    """Index of the most recent compaction entry, or -1 if never compacted."""
    for i in range(len(entries) - 1, -1, -1):
        if _is_compaction_entry(entries[i]):
            return i
    return -1


def _paths_read_after(entries: list[dict[str, object]], start: int) -> set[str]:
    """Normalized file_paths of every Read tool call made after `start`."""
    read_paths: set[str] = set()
    for entry in entries[start + 1 :]:
        if entry.get("type") != "assistant":
            continue
        message = entry.get("message")
        if not isinstance(message, dict):
            continue
        content = message.get("content")
        if not isinstance(content, list):
            continue
        for block in content:
            if not isinstance(block, dict) or block.get("type") != "tool_use":
                continue
            if block.get("name") != "Read":
                continue
            tool_input = block.get("input")
            if not isinstance(tool_input, dict):
                continue
            path = tool_input.get("file_path")
            if isinstance(path, str) and path:
                read_paths.add(_normalize(path))
    return read_paths


def _block(outstanding: list[tuple[str, str]], is_subagent: bool, compacted: bool) -> None:
    listing = "\n".join(f"  {i}. {p}\n     {label}" for i, (p, label) in enumerate(outstanding, 1))

    # A compacted SUBAGENT may never have received the SessionStart injection, so
    # its only channel is this message. Carry the contract essentials in it —
    # a subagent that compacts mid-task is the case nobody is watching.
    subagent_note = (
        "\nYOU ARE A SUBAGENT AND YOUR CONTEXT WAS COMPACTED MID-TASK. Re-read your "
        "task/dispatch prompt too — your instructions were summarized, not preserved. "
        "The execution contract still binds you: the default outcome is that the "
        "problem is FIXED. Compaction is not a blocker (it is not B1-B4), it is not a "
        "reason to return partial work, and 'context was lost' is not a valid report. "
        "Re-read, re-orient, finish the job.\n"
        if is_subagent and compacted
        else ""
    )

    if compacted:
        headline = (
            "BLOCKED: this context was compacted and you have not re-read the mandatory "
            "documents since.\n\n"
            "Compaction discarded every file you had read. You are about to edit code "
            "against a summary of the rules rather than the rules themselves — that is "
            "how architecture and agent-rule violations get in. Do not trust any "
            "recollection you have of these files' contents.\n"
        )
    else:
        headline = (
            "BLOCKED: you have not read the mandatory documents in this session.\n\n"
            "CLAUDE.md was injected into your context automatically; these were not, "
            "and nothing else in the session will ask you for them. You are about to "
            "edit code against rules you have not seen — that is how architecture and "
            "agent-rule violations get in. Having read these in an EARLIER session "
            "does not count: they change, and you do not have them now.\n"
        )

    sys.stderr.write(
        f"{headline}{subagent_note}\n"
        "Read these with the Read tool, then retry the edit:\n\n"
        f"{listing}\n\n"
        "The block clears automatically once each file above has been read. It "
        "cannot be argued with, and rephrasing the edit will not get past it.\n\n"
        "(Scratch files under D:\\datrix\\.tmp\\, .scripts\\, and .test-output\\ remain "
        "writable if you need to investigate first.)"
    )
    sys.exit(2)


def _state_signal(session_id: str) -> tuple[bool, set[str], str]:
    """Signal A — the SessionStart state file. (armed, docs already read, source)

    `source` is the SessionStart source that armed it — `compact`, `startup`,
    `resume` or `clear`. It changes the wording of the block and decides whether
    the transcript-drift check is meaningful, never whether the gate fires.
    """
    if not session_id:
        return False, set(), ""
    path = os.path.join(_STATE_DIR, f"mandatory-reads-{session_id}.json")
    if not os.path.isfile(path):
        return False, set(), ""
    try:
        with open(path, encoding="utf-8") as handle:
            state = json.load(handle)
    except (OSError, json.JSONDecodeError):
        return False, set(), ""
    source = state.get("source")
    return (
        True,
        {_normalize(p) for p in state.get("read", []) if isinstance(p, str)},
        source if isinstance(source, str) else "",
    )


def _transcript_signal(transcript_path: str) -> tuple[bool, set[str]]:
    """Signal B — the caller's own transcript. (compacted, paths Read since)"""
    entries = _entries(transcript_path)
    compacted_at = _last_compaction_index(entries)
    if compacted_at < 0:
        return False, set()
    return True, _paths_read_after(entries, compacted_at)


def _record_schema_drift(session_id: str) -> None:
    """A COMPACT-armed signal A fired but signal B saw nothing — the marker drifted.

    This is the ONLY place the drift check can honestly run. It cannot run at
    SessionStart(compact): the harness appends the compaction record to the
    transcript *after* that hook returns, so a canary there reads a transcript that
    does not yet contain the marker it is looking for and reports drift on every
    single compaction. A guard that cries wolf every time is a guard nobody reads.

    Here, both signals are observable at once and the transcript is long since
    flushed, so a `compact`-sourced state file with no transcript marker means
    exactly one thing: SessionStart proved a compaction happened, and the
    transcript scan failed to see it. That is real drift, and signal B is dark for
    SUBAGENTS (which have no state file).

    The `compact` qualifier is load-bearing. The state file is now armed on every
    SessionStart, and a `startup`-armed session has no compaction for signal B to
    find — checking there would report drift on every fresh session and retrain the
    reader to ignore the one alarm that will ever be true.
    """
    if not session_id:
        return
    try:
        os.makedirs(_STATE_DIR, exist_ok=True)
        with open(os.path.join(_STATE_DIR, "schema-drift.json"), "w", encoding="utf-8") as handle:
            json.dump({"session_id": session_id, "signal": "transcript"}, handle, indent=2)
    except OSError:
        return

    print(
        json.dumps(
            {
                "systemMessage": (
                    "HOOK SCHEMA DRIFT: a compaction was confirmed by the SessionStart "
                    "state file, but no compaction marker was found in the transcript. "
                    "gate-mandatory-reads.py signal B is now DARK for subagents — a "
                    "subagent that compacts mid-task can edit code without re-reading the "
                    "mandatory docs. Find the new marker field in the transcript JSONL and "
                    "update _is_compaction_entry() in .claude/hooks/gate-mandatory-reads.py. "
                    "Tell Jon."
                )
            }
        )
    )


def main() -> None:
    try:
        data = json.loads(sys.stdin.read())
    except json.JSONDecodeError:
        sys.exit(0)

    if data.get("tool_name") not in ("Write", "Edit", "NotebookEdit"):
        sys.exit(0)

    raw_path = data.get("tool_input", {}).get("file_path", "")
    if raw_path and _is_exempt(_normalize(raw_path)):
        sys.exit(0)

    required = _required_docs()
    if not required:
        sys.exit(0)

    state_armed, state_reads, state_source = _state_signal(data.get("session_id", ""))
    tx_armed, tx_reads = _transcript_signal(data.get("transcript_path", ""))

    if state_armed and state_source == "compact" and not tx_armed:
        _record_schema_drift(data.get("session_id", ""))

    if not (state_armed or tx_armed):
        sys.exit(0)  # neither signal armed — fail open, never wedge the session

    seen = state_reads | tx_reads
    outstanding = [
        (p, label)
        for p, label in required
        if not any(read.endswith(_normalize(p)) for read in seen)
    ]

    if outstanding:
        _block(
            outstanding,
            is_subagent=bool(data.get("agent_id")),
            compacted=tx_armed or state_source == "compact",
        )

    sys.exit(0)


if __name__ == "__main__":
    main()
