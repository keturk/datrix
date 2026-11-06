"""Whether the decision advisor has handed the current question to Jon.

Jon's order: an agent with a question delegates it to the `decision-advisor` agent (Opus,
high effort,`.claude/agents/decision-advisor.md`) and acts on its recommendation; only when
the advisor cannot recommend anything does the agent ask Jon. The advisor says so with a line
`VERDICT: ASK_JON` in its result.

`advisor_verdict` reads the session transcript and answers for the stretch since Jon's last
message: a verdict given before Jon last spoke belongs to an earlier question. Feedback a Stop
hook feeds back to the agent is written as a user message too; it is not Jon speaking and does
not end the stretch, and neither is a frame the harness writes (a subagent hand-back, a
task-notification, a system reminder).

The Agent tool runs the advisor in the background: the dispatch's tool result then holds only
`agentId: <id>`, and the report arrives later as a hand-back frame `<agent-message from="<id>">`
or a `<task-notification>` naming the task id and the dispatch's tool-use id, written as a
`queue-operation` entry (`content`), a `queued_command` attachment (`prompt`) or user text. The
verdict is read from the tool result and from each frame that answers a dispatch of this
stretch, and only from the report's first `VERDICT:` line; a frame naming any other id is
ignored, so no other subagent's report or pasted text can hand a question to Jon.

A skill whose purpose is to put a question to Jon is exempt too: `/discuss-finding` brings him a
decision he asked to discuss, so its questions, a choice through `AskUserQuestion` or an open one
in prose, go to him directly (`Verdict.JON_DISCUSSION`). The session is in such a discussion from
the skill's invocation, typed or through the Skill tool, until another skill is invoked; Jon's
plain follow-ups stay in it.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from enum import Enum
from typing import Final

from _report_language import content_blocks, is_jon_speaking

ADVISOR_AGENT: Final = "decision-advisor"
_DISPATCH_TOOLS: Final = frozenset({"Agent", "Task"})
_VERDICT_LINE_RE: Final = re.compile(r"^[ \t>*_`-]*VERDICT[*_`]*:", re.MULTILINE)
_ASK_JON_RE: Final = re.compile(r"[ \t>*_`-]*VERDICT[*_`]*:[ \t*_`]*ASK_JON\b")
# The id of the agent a dispatch launched: `agentId: <id>` when it runs in the background, the
# hand-back sender when its tool result points at the hand-back it was delivered as.
_AGENT_ID_RE: Final = re.compile(
    r'^agentId:[ \t]*([\w-]+)|delivered to you as a message from "([\w-]+)"', re.MULTILINE
)
_HANDBACK_RE: Final = re.compile(
    r'<agent-message from="(?P<agent>[\w-]+)">\n(?P<body>.*?)(?:</agent-message>|\Z)', re.DOTALL
)
_TAG_RE: Final = {
    tag: re.compile(rf"<{tag}>(.*?)</{tag}>", re.DOTALL) for tag in ("task-id", "tool-use-id", "result")
}

#: Skills that exist to put a question to Jon; their questions skip the advisor.
JON_DISCUSSION_SKILLS: Final = frozenset({"discuss-finding"})
# A skill invocation as the transcript records it: Jon's typed command, or the expanded body the
# harness writes for either form (a scoped skill's directory sits under its own `skills` folder).
_INVOKED_SKILL_RE: Final = re.compile(
    r"\A\s*(?:<command-message>[^<]*</command-message>\s*)?<command-name>/(?:[\w./-]+:)?(?P<typed>[\w-]+)</command-name>"
    r"|\A\s*Base directory for this skill: [^\n]*[\\/]skills[\\/](?P<body>[\w-]+)\s*$",
    re.MULTILINE,
)


class Verdict(Enum):
    """What the advisor said about the current question."""

    ASK_JON = "ask_jon"
    NOT_ASK_JON = "not_ask_jon"
    UNREADABLE = "unreadable"
    JON_DISCUSSION = "jon_discussion"


def _result_text(block: dict[str, object]) -> str:
    content = block.get("content")
    if isinstance(content, str):
        return content
    if not isinstance(content, list):
        return ""
    return "\n".join(
        str(part.get("text", "")) for part in content if isinstance(part, dict)
    )


def _says_ask_jon(report: str) -> bool:
    """The report's own verdict line, its first one, is ASK_JON; a later quoted line is not."""
    first = _VERDICT_LINE_RE.search(report)
    return first is not None and bool(_ASK_JON_RE.match(report, first.start()))


def _frame_texts(entry: dict[str, object], blocks: list[dict[str, object]]) -> list[str]:
    """Texts that may open with a hand-back or task-notification frame the harness wrote."""
    texts: list[str] = []
    if entry.get("type") == "queue-operation" and isinstance(entry.get("content"), str):
        texts.append(str(entry["content"]))
    attachment = entry.get("attachment")
    if isinstance(attachment, dict) and isinstance(attachment.get("prompt"), str):
        texts.append(str(attachment["prompt"]))
    if entry.get("type") == "user":
        texts.extend(str(block.get("text", "")) for block in blocks if block.get("type") == "text")
    return [text.lstrip() for text in texts]


@dataclass(frozen=True)
class _Frame:
    """A report the harness delivered for a background agent, and the ids that name its dispatch."""

    report: str
    agent_id: str | None
    tool_use_id: str | None

    def answers(self, agent_ids: set[str], dispatch_ids: set[str]) -> bool:
        return self.agent_id in agent_ids or self.tool_use_id in dispatch_ids


def _tag(text: str, tag: str) -> str | None:
    match = _TAG_RE[tag].search(text)
    return match.group(1).strip() if match else None


def _read_frame(text: str) -> _Frame | None:
    """The frame a text opens with; it is matched to its dispatch once the stretch is read.

    A foreground dispatch's hand-back is written before the tool result that names its agent id,
    so a frame cannot be judged where it stands."""
    handback = _HANDBACK_RE.match(text)
    if handback is not None:
        return _Frame(handback.group("body"), handback.group("agent"), None)
    result = _tag(text, "result") if text.startswith("<task-notification>") else None
    if result is None:
        return None
    return _Frame(result, _tag(text, "task-id"), _tag(text, "tool-use-id"))


def _is_advisor_dispatch(block: dict[str, object]) -> bool:
    if block.get("type") != "tool_use" or block.get("name") not in _DISPATCH_TOOLS:
        return False
    tool_input = block.get("input")
    return isinstance(tool_input, dict) and tool_input.get("subagent_type") == ADVISOR_AGENT


def transcript_entries(transcript_path: str) -> list[dict[str, object]] | None:
    """Every JSON object in the transcript, in order; None when it cannot be read."""
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


def _invoked_skill(entry: dict[str, object], blocks: list[dict[str, object]]) -> str | None:
    """The skill a user entry invokes, or None when it invokes none."""
    if entry.get("type") != "user":
        return None
    for block in blocks:
        if block.get("type") != "text":
            continue
        match = _INVOKED_SKILL_RE.search(str(block.get("text", "")))
        if match is not None:
            return match.group("typed") or match.group("body")
    return None


def latest_invoked_skill(entries: list[dict[str, object]]) -> str | None:
    """The skill invoked last in the session, or None when it invoked none."""
    latest: str | None = None
    for entry in entries:
        latest = _invoked_skill(entry, content_blocks(entry)) or latest
    return latest


def _in_jon_discussion(entries: list[dict[str, object]]) -> bool:
    """Whether the latest skill invoked in the session is one that exists to ask Jon."""
    return latest_invoked_skill(entries) in JON_DISCUSSION_SKILLS


def advisor_verdict(transcript_path: str) -> Verdict:
    """ASK_JON when an advisor dispatched since Jon's last message returned `VERDICT: ASK_JON`;
    JON_DISCUSSION when the session is in a skill that exists to ask Jon."""
    entries = transcript_entries(transcript_path)
    if entries is None:
        return Verdict.UNREADABLE
    if _in_jon_discussion(entries):
        return Verdict.JON_DISCUSSION
    dispatch_ids: set[str] = set()
    agent_ids: set[str] = set()
    frames: list[_Frame] = []
    asked_jon = False
    for entry in entries:
        blocks = content_blocks(entry)
        if entry.get("type") == "user" and is_jon_speaking(blocks):
            dispatch_ids.clear()
            agent_ids.clear()
            frames.clear()
            asked_jon = False
            continue
        frames.extend(frame for text in _frame_texts(entry, blocks) if (frame := _read_frame(text)))
        for block in blocks:
            if _is_advisor_dispatch(block):
                dispatch_ids.add(str(block.get("id", "")))
            elif block.get("type") == "tool_result" and str(block.get("tool_use_id", "")) in dispatch_ids:
                text = _result_text(block)
                agent_ids.update("".join(ids) for ids in _AGENT_ID_RE.findall(text))
                asked_jon = asked_jon or _says_ask_jon(text)
    asked_jon = asked_jon or any(
        frame.answers(agent_ids, dispatch_ids) and _says_ask_jon(frame.report) for frame in frames
    )
    return Verdict.ASK_JON if asked_jon else Verdict.NOT_ASK_JON


def advisor_consulted(transcript_path: str) -> bool | None:
    """Whether a `decision-advisor` was dispatched anywhere in the session; None when unreadable."""
    entries = transcript_entries(transcript_path)
    if entries is None:
        return None
    return any(_is_advisor_dispatch(block) for entry in entries for block in content_blocks(entry))


ADVISOR_REMEDY: Final = (
    f'Put the question to the decision advisor first (Agent tool, subagent_type "{ADVISOR_AGENT}") '
    "with the question, your evidence, the options and your recommendation. On `VERDICT: RECOMMEND` "
    "act on it and record it; only on `VERDICT: ASK_JON` ask Jon its question."
)
