"""Shared vocabulary for detecting a report that ends on a dodge.

Imported by BOTH stop gates, which were previously asymmetric in a way that
produced the failure this module exists to fix:

  - `check-agent-report.py` (SubagentStop) rejected a SUBAGENT that ended on
    "out of scope" / "left as-is" / "should be tracked separately".
  - `gate-orchestration-stop.py` (Stop) checked only two things: unresolved task
    files, and offers to pause.

So the one agent talking directly to Jon was the only agent in the system
allowed to make excuses. A long Azure-deployment run reported "I skipped this,
I didn't do this" turn after turn and the harness had no opinion at all, while
every subagent under it was held to a far stricter standard.

TWO FAMILIES, DELIBERATELY SEPARATE
-----------------------------------
`_SCOPE_DODGE` — "this isn't mine": out of scope, someone else's, future work.
`_OMISSION`    — "I didn't do it": skipped, not verified, should work, assumed.

They are different failures. A scope dodge reassigns the work; an omission
confesses it was never done and then ends the turn anyway. The second is what a
manual deploy loop produces, and it was entirely uncovered.

FALSE POSITIVES ARE THE EXPENSIVE FAILURE
-----------------------------------------
A gate that fires on innocent prose teaches agents to write evasively, which
costs more than the dodge did. Three suppressors, all applied before matching:

  1. QUOTED SPANS — code fences, inline code, and quoted text are blanked. An
     agent citing the rule ("never end on 'out of scope'") is documenting it,
     not doing it. This module's own docstring would trip the gate otherwise.
  2. NEGATION — "no steps were skipped", "nothing left as-is" are the opposite
     of a dodge.
  3. PROOF MARKERS — a B1-B4 blocker with proof, a filed task path, or
     EXPANSION_REQUIRED is a legitimate exit and suppresses the whole check.

Callers add a fourth: scope. Neither gate runs this on every session.
"""

from __future__ import annotations

import json
import re
from typing import Final

# "This isn't my work." Kept tight — the fuller list lives in the execution
# contract and is judged by the orchestrator, not by a regex.
_SCOPE_DODGE: Final = (
    r"out of scope"
    r"|outside (?:the |of )?(?:current )?scope"
    r"|beyond the scope"
    r"|not part of (?:this|the) task"
    r"|should be tracked separately"
    r"|tracked as a separate"
    r"|would require broader changes"
    r"|categorically behavioral"
    r"|environmental issue"
    r"|not my (?:file|package|problem)"
    r"|someone else'?s? (?:problem|job|responsibility)"
    r"|left as[- ]is"
    r"|leaving (?:it|this|that) as[- ]is"
    r"|future work"
    r"|not yet wired"
    r"|dual path"
    r"|recommend(?:ed|ing)? a follow[- ]up"
    r"|defer(?:red|ring)? to a follow[- ]up"
)

# "I didn't do it." The family a manual deploy loop actually produces. Every
# alternative names an ACT that was skipped or a claim made without evidence —
# never a bare adjective, which is what would catch innocent prose.
_OMISSION: Final = (
    # A first-person `skipped` needs no object list. The object of a skip is an
    # arbitrary noun phrase — "the seam census", "the route inventory", "preflight" —
    # and an enumerated list will always be one phrase short of the report that
    # actually shipped. "I skipped" is high-signal on its own; the negation and
    # quoting suppressors carry the false-positive load.
    r"(?:i|we) (?:have |had )?skipped\b"
    r"|(?:i|we) (?:did ?n[o']?t|have ?n[o']?t|had ?n[o']?t)"
    r"\s+(?:run|ran|verif\w+|check\w*|test\w*|read|validat\w+|confirm\w*|execut\w+)"
    r"|(?:skipped|skipping) (?:the |this |that |these |those )?"
    r"(?:test\w*|check\w*|verification|validation|step\w*|analysis|gate\w*|scan\w*)"
    r"|(?:was|were|is|are|remains?) (?:still )?(?:not |un)(?:verified|validated|tested|confirmed)"
    r"|(?:have|has) not been (?:verified|validated|tested|run|checked|confirmed)"
    r"|without (?:verifying|validating|testing|checking|running|reading)"
    r"|manual (?:step|steps|verification) (?:is |are |still )?(?:pending|remaining|required|outstanding)"
    r"|i (?:am |'m )?assum(?:e|ing)"
    r"|(?:it |this |that )?should (?:work|be fine|succeed)"
    r"|(?:i was |i am |i'm )?unable to (?:verify|check|test|run|confirm)"
    r"|could ?n[o']?t (?:verify|check|test|run|confirm)"
    r"|(?:presumably|in theory) (?:this |it )?(?:works|will work)"
)

_DODGE_RE: Final = re.compile(rf"\b(?:{_SCOPE_DODGE}|{_OMISSION})\b", re.IGNORECASE)

# Only the scope family, for callers that want the original narrower check.
_SCOPE_DODGE_RE: Final = re.compile(rf"\b(?:{_SCOPE_DODGE})\b", re.IGNORECASE)

# A negated dodge is not a dodge: "no steps were skipped", "nothing left as-is".
_NEGATION_LOOKBACK: Final = 32
_NEGATION_RE: Final = re.compile(
    r"\b(no|not|never|without|avoid(?:ed|ing)?|isn'?t|aren'?t|wasn'?t|"
    r"weren'?t|nothing|none|zero)\b[^.]*$",
    re.IGNORECASE,
)

# Quoting a phrase is not committing it.
_QUOTED_SPAN_RE: Final = re.compile(
    r"```.*?```"  # fenced code
    r"|`[^`\n]*`"  # inline code
    r"|\"[^\"\n]*\""  # straight double quotes
    r"|“[^”\n]*”",  # curly double quotes
    re.DOTALL,
)

# Markers that make an otherwise-flagged report a legitimate exit.
_PROOF_RE: Final = re.compile(
    r"("
    r"\bB[1-4]\b\s*[:\-—]"  # blocker code with proof
    r"|\bblocker_code\b"
    r"|\bEXPANSION_REQUIRED\b"
    r"|\bMISSING_ACCESS\b|\bUNDECIDABLE\b|\bUSER_FORBADE\b|\bFENCED_SURFACE\b"
    r"|\.tasks[/\\][\w\-./\\]+\.md"  # a real filed task file path
    r"|\bdisposition\b\s*[\"':]*\s*\"?FILED\"?"
    r")",
    re.IGNORECASE,
)


def strip_quoted(text: str) -> str:
    """Blank out quoted and code spans so cited phrases are not read as speech."""
    return _QUOTED_SPAN_RE.sub(" ", text)


def carries_proof(text: str) -> bool:
    """True when the report carries a legitimate-exit marker."""
    return bool(_PROOF_RE.search(text))


def find_dodge(text: str, pattern: re.Pattern[str] | None = None) -> str:
    """First dodge phrase that is neither quoted nor negated, or ''."""
    stripped = strip_quoted(text)
    for match in (pattern or _DODGE_RE).finditer(stripped):
        window = stripped[max(0, match.start() - _NEGATION_LOOKBACK) : match.start()]
        if _NEGATION_RE.search(window):
            continue
        return match.group(0)
    return ""


def last_assistant_text(transcript_path: str) -> str:
    """Concatenated text of the final assistant message in a transcript."""
    try:
        with open(transcript_path, encoding="utf-8") as handle:
            lines = handle.readlines()
    except OSError:
        return ""

    for line in reversed(lines):
        try:
            entry = json.loads(line)
        except json.JSONDecodeError:
            continue

        if entry.get("type") != "assistant":
            continue

        content = entry.get("message", {}).get("content", [])
        if isinstance(content, str):
            return content

        parts = [
            block.get("text", "")
            for block in content
            if isinstance(block, dict) and block.get("type") == "text"
        ]
        text = "\n".join(parts).strip()
        if text:
            return text

    return ""


# The remedy text is identical for both gates, so it lives with the vocabulary.
DODGE_REMEDY: Final = (
    "Per .claude/skills/_shared/execution-contract.md, that is NOT a blocker. "
    "It is the work.\n\n"
    "There are exactly four legitimate blockers:\n"
    "  B1 MISSING_ACCESS  - needs a credential/endpoint/resource you cannot obtain\n"
    "  B2 UNDECIDABLE     - two genuinely defensible designs, expensive to reverse\n"
    "  B3 USER_FORBADE    - the only correct fix was explicitly prohibited\n"
    "  B4 FENCED_SURFACE  - root cause is on a surface the user explicitly excluded\n\n"
    "Everything else is work: root cause unclear -> keep reading. Root cause in "
    "another package -> go fix it there. Bigger than estimated -> do it. "
    "Pre-existing -> it is yours now. 'Behavioral/environmental' -> prove it with "
    "the verbatim error text, or fix it. No test -> write one. 'Should be tracked "
    "separately' -> THERE IS NO OTHER AGENT.\n\n"
    "If you SKIPPED a check rather than reassigned the work: go run it now. An "
    "unverified claim is not a result. 'Should work' is not evidence - read the "
    "file, run the check, and report what it actually said.\n\n"
    "Do ONE of these, then finish:\n"
    "  1. DO IT. (This is the default and almost always the right answer.)\n"
    "  2. FILE IT - create a real tracked task file and cite its path, if it is "
    "genuinely an independent root cause.\n"
    "  3. PROVE A BLOCKER - give all four: verbatim error text; the fix you "
    "actually wrote and ran (file:line); why it failed; and the B1-B4 code. "
    "Analysis alone is not an attempt.\n\n"
    "Do not rephrase to slip past this check. The rule is the behavior, not the "
    "wordlist."
)
