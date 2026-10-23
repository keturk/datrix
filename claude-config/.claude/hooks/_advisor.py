"""Whether the decision advisor has handed the current question to Jon.

Jon's order: an agent with a question delegates it to the `decision-advisor` agent (Opus,
medium effort, `.claude/agents/decision-advisor.md`) and acts on its recommendation; only when
the advisor cannot recommend anything does the agent ask Jon. The advisor says so with a line
`VERDICT: ASK_JON` in its result.

`advisor_verdict` reads the session transcript and answers for the stretch since Jon's last
message: a verdict given before Jon last spoke belongs to an earlier question. Feedback a Stop
hook feeds back to the agent is written as a user message too; it is not Jon speaking and does
not end the stretch.

Jon can also forbid every subagent, the advisor included (his global instructions). He says so
to the harness with `DATRIX_NO_SUBAGENTS=1` in his user settings' `env`; the advisor cannot be
consulted then, so a question goes straight to him (`Verdict.ADVISOR_FORBIDDEN`).
"""

from __future__ import annotations

import json
import os
import re
from enum import Enum
from typing import Final

ADVISOR_AGENT: Final = "decision-advisor"
_DISPATCH_TOOLS: Final = frozenset({"Agent", "Task"})
_ASK_JON_RE: Final = re.compile(r"^[ \t>*_`-]*VERDICT[*_`]*:[ \t*_`]*ASK_JON\b", re.MULTILINE)
_HOOK_FEEDBACK_PREFIX: Final = "Stop hook feedback"
NO_SUBAGENTS_ENV: Final = "DATRIX_NO_SUBAGENTS"


class Verdict(Enum):
    """What the advisor said about the current question."""

    ASK_JON = "ask_jon"
    NOT_ASK_JON = "not_ask_jon"
    UNREADABLE = "unreadable"
    ADVISOR_FORBIDDEN = "advisor_forbidden"


def subagents_forbidden() -> bool:
    """Jon has forbidden every subagent dispatch, the decision advisor included."""
    return os.environ.get(NO_SUBAGENTS_ENV) == "1"


def _blocks(entry: dict[str, object]) -> list[dict[str, object]]:
    message = entry.get("message")
    if not isinstance(message, dict):
        return []
    content = message.get("content")
    if isinstance(content, str):
        return [{"type": "text", "text": content}]
    if not isinstance(content, list):
        return []
    return [block for block in content if isinstance(block, dict)]


def _result_text(block: dict[str, object]) -> str:
    content = block.get("content")
    if isinstance(content, str):
        return content
    if not isinstance(content, list):
        return ""
    return "\n".join(
        str(part.get("text", "")) for part in content if isinstance(part, dict)
    )


def _is_jon_speaking(blocks: list[dict[str, object]]) -> bool:
    texts = [str(block.get("text", "")).strip() for block in blocks if block.get("type") == "text"]
    spoken = [text for text in texts if text]
    return bool(spoken) and not all(text.startswith(_HOOK_FEEDBACK_PREFIX) for text in spoken)


def _is_advisor_dispatch(block: dict[str, object]) -> bool:
    if block.get("type") != "tool_use" or block.get("name") not in _DISPATCH_TOOLS:
        return False
    tool_input = block.get("input")
    return isinstance(tool_input, dict) and tool_input.get("subagent_type") == ADVISOR_AGENT


def _entries(transcript_path: str) -> list[dict[str, object]] | None:
    try:
        with open(transcript_path, encoding="utf-8") as handle:
            lines = handle.readlines()
    except OSError:
        return None
    entries: list[dict[str, object]] = []
    for line in lines:
        try:
            entry = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(entry, dict):
            entries.append(entry)
    return entries


def advisor_verdict(transcript_path: str) -> Verdict:
    """ASK_JON when an advisor dispatched since Jon's last message returned `VERDICT: ASK_JON`."""
    if subagents_forbidden():
        return Verdict.ADVISOR_FORBIDDEN
    entries = _entries(transcript_path)
    if entries is None:
        return Verdict.UNREADABLE
    dispatch_ids: set[str] = set()
    asked_jon = False
    for entry in entries:
        blocks = _blocks(entry)
        if entry.get("type") == "user" and _is_jon_speaking(blocks):
            dispatch_ids.clear()
            asked_jon = False
            continue
        for block in blocks:
            if _is_advisor_dispatch(block):
                dispatch_ids.add(str(block.get("id", "")))
            elif block.get("type") == "tool_result" and str(block.get("tool_use_id", "")) in dispatch_ids:
                asked_jon = asked_jon or bool(_ASK_JON_RE.search(_result_text(block)))
    return Verdict.ASK_JON if asked_jon else Verdict.NOT_ASK_JON


ADVISOR_REMEDY: Final = (
    f'Put the question to the decision advisor first (Agent tool, subagent_type "{ADVISOR_AGENT}") '
    "with the question, your evidence, the options and your recommendation. On `VERDICT: RECOMMEND` "
    "act on it and record it; only on `VERDICT: ASK_JON` ask Jon its question."
)
