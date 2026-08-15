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
     with `isCompactSummary: true` and a `type: system` entry with
     `subtype: compact_boundary`; Reads after them are the post-compaction reads.
     Hole: the transcript JSONL schema is internal and Anthropic warns it can
     change between releases. A rename of BOTH fields would make this signal go
     quiet — so a third marker this repo owns is read alongside them (see
     `_self_owned_compaction_marker`), which no upstream rename can take away.
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

# The harness records every hook invocation as a `type: attachment` entry naming
# the event it fired for. This exact name is written when — and only when —
# SessionStart fired with source=compact, so its presence in a transcript is proof
# that THIS transcript compacted, owed to nothing Anthropic can rename.
_COMPACT_SESSION_START_HOOK: Final = "SessionStart:compact"


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


def _upstream_compaction_marker(entry: dict[str, object]) -> bool:
    """True for either marker the HARNESS writes when it compacts a context.

    Two independent field names are accepted, because a compaction writes BOTH a
    `system`/`compact_boundary` entry and a `user`/`isCompactSummary` entry. Reading
    either one keeps signal B alive if a release renames the other. These are the
    fields the drift check watches, because these are the fields that can drift.
    """
    return bool(entry.get("isCompactSummary")) or entry.get("subtype") == "compact_boundary"


def _self_owned_compaction_marker(entry: dict[str, object]) -> bool:
    """True for the compaction record THIS REPO owns, immune to an upstream rename.

    The harness logs each hook invocation as an attachment carrying the hook's name;
    `SessionStart:compact` is written only when SessionStart fired with source=compact.
    Two properties make it the right ground truth:

      * it survives a rename of `isCompactSummary`/`compact_boundary`, so signal B
        degrades rather than going dark, and
      * it is STRUCTURAL — an attachment field, not a text sentinel — so an agent
        that merely READS this hook's source cannot forge one into its transcript.

    It does not replace the upstream markers: SessionStart is not documented to fire
    inside a subagent, so a compacting subagent may have only the upstream pair. That
    is exactly why a rename of the pair must still be reported (`_check_marker_drift`).
    """
    if entry.get("type") != "attachment":
        return False
    attachment = entry.get("attachment")
    if not isinstance(attachment, dict):
        return False
    return attachment.get("hookName") == _COMPACT_SESSION_START_HOOK


def _is_compaction_entry(entry: dict[str, object]) -> bool:
    """True for any evidence that the context was compacted at this point."""
    return _upstream_compaction_marker(entry) or _self_owned_compaction_marker(entry)


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


def _transcript_signal(transcript_path: str) -> tuple[bool, set[str], bool, bool]:
    """Signal B — the caller's own transcript.

    Returns (compacted, paths Read since, upstream marker seen, self-owned marker
    seen). The last two are what `_check_marker_drift` compares; they are computed
    over the WHOLE transcript, not just since the last compaction, because the
    question they answer is "does this schema still exist at all".
    """
    entries = _entries(transcript_path)
    upstream_seen = any(_upstream_compaction_marker(e) for e in entries)
    self_seen = any(_self_owned_compaction_marker(e) for e in entries)
    compacted_at = _last_compaction_index(entries)
    if compacted_at < 0:
        return False, set(), upstream_seen, self_seen
    return True, _paths_read_after(entries, compacted_at), upstream_seen, self_seen


def _check_marker_drift(upstream_seen: bool, self_seen: bool, session_id: str) -> None:
    """Compare the two transcript markers AGAINST EACH OTHER, and flag a rename.

    The comparison must be non-circular, and the obvious formulation is not. An
    earlier version inferred drift from the state file: `source == "compact"` and no
    marker found. That is unsound — `source` is written once at SessionStart and is
    sticky for the rest of the session, so it says nothing about the transcript being
    scanned, and the check re-ran on EVERY edit thereafter. It duly fired three times
    in one session whose transcript had never compacted, then went quiet when that
    session did compact and the markers turned up exactly where they should be. An
    alarm that fires when nothing is wrong is worse than no alarm: the flag file is
    sticky, so every later session opened with a warning about a healthy guard.

    The sound test compares two independent transcript-side facts:

      SELF-OWNED marker present  — proof that THIS transcript compacted (§
                                   `_self_owned_compaction_marker`; ours, unrenameable)
      UPSTREAM marker absent     — the harness's own fields are no longer being written

    Both together mean a rename, and nothing else does. Either alone is normal: a
    transcript with neither simply never compacted, and a transcript with both is
    healthy. When the upstream fields ARE present the flag is cleared, so a fixed or
    misfired alarm stops nagging without anyone deleting a file by hand.

    Note what this does NOT weaken: with `_is_compaction_entry` now reading the
    self-owned marker too, an upstream rename no longer blinds the main session at
    all. It stays reportable because SessionStart is not documented to fire inside a
    SUBAGENT, so a compacting subagent can still see only the upstream pair — the
    case nobody is watching, and the reason to fix a rename promptly.
    """
    flag_path = os.path.join(_STATE_DIR, "schema-drift.json")

    if upstream_seen or not self_seen:
        if upstream_seen and os.path.isfile(flag_path):
            try:
                os.remove(flag_path)  # healthy again — retract the alarm
            except OSError:
                pass
        return

    if not session_id or os.path.isfile(flag_path):
        return  # already reported; do not re-announce on every edit

    try:
        os.makedirs(_STATE_DIR, exist_ok=True)
        with open(flag_path, "w", encoding="utf-8") as handle:
            json.dump({"session_id": session_id, "signal": "transcript"}, handle, indent=2)
    except OSError:
        return

    print(
        json.dumps(
            {
                "systemMessage": (
                    "HOOK SCHEMA DRIFT: this transcript compacted (its SessionStart:compact "
                    "record proves it), but neither harness compaction marker "
                    "(isCompactSummary / compact_boundary) appears anywhere in it — the "
                    "transcript JSONL schema has changed. gate-mandatory-reads.py still "
                    "covers the main session via its own SessionStart:compact record, but a "
                    "SUBAGENT that compacts mid-task has only the renamed markers and can "
                    "now edit code without re-reading the mandatory docs. Find the new field "
                    "in the transcript JSONL and update _upstream_compaction_marker() in "
                    ".claude/hooks/gate-mandatory-reads.py. Tell Jon."
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
    tx_armed, tx_reads, tx_upstream, tx_self = _transcript_signal(
        data.get("transcript_path", "")
    )

    _check_marker_drift(tx_upstream, tx_self, data.get("session_id", ""))

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
