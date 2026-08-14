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

FOUR FAMILIES, DELIBERATELY SEPARATE
------------------------------------
`_SCOPE_DODGE`         — "this isn't mine": out of scope, someone else's, future work.
`_OMISSION`            — "I didn't do it": skipped, not verified, should work, assumed.
`_SECURITY_DOWNGRADE`  — "I made it less safe": disabled the auth check, relaxed
                         the validation, hardcoded the credential, insecure default.
`_EXPEDIENT`           — "I shipped the small version": quick fix for now, minimal
                         change to get it green, harden it later, to save context.

They are different failures. A scope dodge reassigns the work; an omission
confesses it was never done and then ends the turn anyway; the last two ship the
WRONG work and describe it accurately, which is why neither is excused by a
blocker proof or a filed task the way the first two are.

The last two exist because the failure they catch is invisible to every other
check in the harness. A weakened control and a "temporary" fix both leave a green
suite behind — the suite proves the code does what it was written to do, and says
nothing about whether that was the right thing to write. The contract states both
rules in prose (execution-contract §13 and §14); prose in context competes with
everything else in context and can lose. A blocked Stop cannot be forgotten past.

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

# "I made it less safe." Execution-contract §13: never propose or implement a
# less secure option when a more secure one is available, and never disable or
# loosen a control to turn a red check green. Every alternative names an ACT
# (a control turned off, a secret hardcoded, a trade explicitly taken) rather
# than a topic word -- "security" and "auth" alone appear constantly in honest
# reports and would make this gate useless noise.
_SECURITY_DOWNGRADE: Final = (
    # A control turned off or turned down. Verb AND security noun both required,
    # within one clause of each other.
    r"(?:disabl\w+|turn(?:ed|ing)? off|switch(?:ed|ing)? off|bypass\w*|circumvent\w*"
    r"|weaken\w*|loosen\w*|relax\w*|suppress\w+|opt(?:ed|ing)? out of|widen\w+"
    r"|drop(?:ped|ping)?|comment(?:ed|ing)? out)"
    r"[^.\n]{0,36}?"
    r"\b(?:auth|auth[nz]|authentication|authorization|authorisation|tls|ssl|https"
    r"|certificate\w*|cert (?:check|validation|verification)|signature \w*(?:check|validation)"
    r"|csrf|cors|encryption|sandbox\w*|permission checks?|rate[- ]?limit\w*"
    r"|security (?:check|control|gate|scan|rule|header)s?|access control\w*"
    r"|tenant isolation|input validation)\b"
    # The trade named outright.
    r"|less[- ]secure|least secure|weaker (?:option|default|setting|primitive)"
    r"|insecure (?:default|fallback|option|but|because|for now|to keep)"
    r"|(?:simpler|easier|faster) but (?:less secure|insecure|unauthenticated)"
    # Specific downgrades that are never acceptable.
    r"|hard[- ]?cod\w+[^.\n]{0,28}?"
    r"\b(?:secret|password|credential|token|api[- ]?key|private key|connection string)"
    r"|(?:allow\w*|permit\w*|accept\w*)[^.\n]{0,20}?\b(?:anonymous|unauthenticated)\b"
    r"|fail(?:s|ed|ing)? open"
    r"|0\.0\.0\.0/0"
    r"|verify\s*=\s*false|reject ?unauthorized\s*[:=]\s*false"
)

# "I shipped the small version." Execution-contract §14: the size of a fix is set
# by the defect, never by what is left of your context, budget, turn, or patience.
# NOTE what is deliberately NOT here: a bare "minimal change" or "smallest change".
# CLAUDE.md itself instructs "write the smallest CORRECT change" -- flagging that
# phrase would fire the gate on the rule it is enforcing.
_EXPEDIENT: Final = (
    # A change labelled provisional rather than correct.
    r"(?:quick|temporary|temp|interim|stop[- ]?gap|band[- ]?aid|provisional"
    r"|throwaway|short[- ]term|tactical|surgical)\s+"
    r"(?:fix|patch|workaround|solution|change|hack|shim|mitigation|edit)"
    # "...for now", the canonical marker, anchored so it cannot fire on prose
    # about the product ("for now the registry holds two entries").
    r"|(?:fix|patch|change|solution|approach|this|it|them)\s+for now\b"
    r"|for now,?\s+(?:i|we)\b"
    r"|good enough for now|will do for now"
    # Deferring the real fix.
    r"|(?:proper|real|correct|full|complete|long[- ]term|deeper|right)\s+fix\b"
    r"[^.\n]{0,48}?\b(?:later|follow[- ]?up|another (?:task|pass|turn|session)|a future)"
    r"|(?:harden|revisit|tighten|do (?:this|it) properly|clean (?:this|it) up)"
    r"[^.\n]{0,28}?\blater\b"
    r"|until (?:the )?(?:real|proper|full|permanent) (?:fix|solution|implementation)"
    # Sizing the change to the budget instead of to the defect.
    r"|minimal (?:change|fix|edit)[^.\n]{0,44}?\b(?:green|pass(?:ing|es)?|unblock\w*)"
    r"|smallest (?:thing|change|fix) that (?:unblocks|gets|makes|turns)"
    r"|to (?:save|conserve|preserve) (?:context|tokens|budget|time)"
    r"|(?:kept|keeping|made|making) (?:the |this )?(?:change|fix) small(?:er)?\b"
)

_SECURITY_DOWNGRADE_RE: Final = re.compile(rf"(?:{_SECURITY_DOWNGRADE})", re.IGNORECASE)
_EXPEDIENT_RE: Final = re.compile(rf"(?:{_EXPEDIENT})", re.IGNORECASE)

# "I ran out of room." A third family, and the one the contract singles out as
# the MOST seductive: it sounds like engineering prudence, and it is
# unfalsifiable from Jon's side because he cannot see the context meter -- and
# neither can the model, which is what makes it a fabricated resource claim
# rather than a judgment call. Context is COMPACTED; the session continues. An
# agent that stops here has chosen to spend its last tokens on a handover
# document instead of on the fix, and the handover is the one artifact that does
# NOT survive compaction.
_EXHAUSTION: Final = (
    r"(?:running |runn?ing )?low on context"
    r"|out of (?:runway|context|room)"
    r"|(?:near|approaching|close to) (?:the )?(?:end of )?(?:my )?context"
    r"|context (?:window|budget|limit)s? (?:is|are|getting)? ?(?:tight|full|exhausted|nearly)"
    r"|remaining context"
    r"|context (?:is|was) (?:tight|nearly (?:full|gone))"
    r"|limited context"
    r"|to keep (?:this |the )?(?:repo |tree )?(?:in a )?(?:clean|consistent) state"
)

# The section headings a handover wears. The contract names these verbatim:
# "If your draft reply contains a 'remaining', 'still to fix', or 'next up'
# section, you are not finished." Matched as HEADINGS (line-leading, optionally
# bolded/bulleted) rather than anywhere in prose, so "the remaining tests pass"
# is not a hit.
_HANDOVER_SECTION: Final = (
    r"^[\s>*\-#]*\**(?:"
    r"where it stops"
    r"|remaining(?: work| after| items| steps)?"
    r"|still (?:to fix|outstanding|open|left)"
    r"|next up"
    r"|what(?:'|’)?s (?:left|remaining|next)"
    r"|left to do"
    r"|to be (?:done|finished|completed)"
    r"|picking up (?:from )?here"
    r"|hand(?:ing)? ?over"
    r"|follow-?ups?"
    # Up to a short run of trailing words before the colon, so "Remaining after
    # that:" and "Still to fix (customer side):" are caught. Bounded and
    # colon-terminated on the SAME line, which is what keeps "the remaining 12
    # warnings are pre-existing" -- a report of success, no colon -- out.
    r")[^:\n]{0,40}:"
)

_EXHAUSTION_RE: Final = re.compile(rf"(?:{_EXHAUSTION})", re.IGNORECASE)
_HANDOVER_RE: Final = re.compile(_HANDOVER_SECTION, re.IGNORECASE | re.MULTILINE)

# Only the scope family, for callers that want the original narrower check.
_SCOPE_DODGE_RE: Final = re.compile(rf"\b(?:{_SCOPE_DODGE})\b", re.IGNORECASE)

# A negated dodge is not a dodge: "no steps were skipped", "nothing left as-is".
_NEGATION_LOOKBACK: Final = 32
_NEGATION_RE: Final = re.compile(
    r"\b(no|not|never|without|avoid(?:ed|ing)?|isn'?t|aren'?t|wasn'?t|"
    r"weren'?t|nothing|none|zero)\b[^.]*$",
    re.IGNORECASE,
)

# REMEDIATION is the opposite of a downgrade, and this repo will be full of it.
# "Removed the branch that disabled TLS verification", "the validator now rejects
# a hardcoded credential", "a guard that would have caught the fail-open path" —
# every one of those describes CLOSING a hole and must not be read as opening
# one. Wider lookback than negation because the remedial verb tends to sit at the
# head of the clause while the security noun sits at the tail.
_REMEDIATION_LOOKBACK: Final = 64
_REMEDIATION_RE: Final = re.compile(
    r"\b(?:remov\w+|delet\w+|replac\w+|revert\w*|fix(?:ed|es|ing)?|repair\w*|clos\w+|"
    r"prevent\w+|reject\w+|refus\w+|forbid\w+|prohibit\w+|ban(?:s|ned|ning)?|"
    r"guard\w*|block(?:s|ed|ing)?|catch\w*|caught|detect\w+|flag(?:s|ged|ging)?|"
    r"stop(?:s|ped|ping)?|no longer|instead of|rather than|would have|used to)\b[^.]*$",
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


def find_exhaustion(text: str) -> str:
    """First unquoted, un-negated context-exhaustion claim, or ''."""
    return find_dodge(text, _EXHAUSTION_RE)


def find_security_downgrade(text: str) -> str:
    """First unquoted claim of having made something LESS secure, or ''.

    Suppressed by quoting, by negation, and by remediation language — reporting
    that you removed a fail-open path must never read as adding one.
    """
    stripped = strip_quoted(text)
    for match in _SECURITY_DOWNGRADE_RE.finditer(stripped):
        start = match.start()
        if _NEGATION_RE.search(stripped[max(0, start - _NEGATION_LOOKBACK) : start]):
            continue
        if _REMEDIATION_RE.search(stripped[max(0, start - _REMEDIATION_LOOKBACK) : start]):
            continue
        return match.group(0)
    return ""


def find_expedient(text: str) -> str:
    """First unquoted, un-negated 'this is the small version' claim, or ''."""
    return find_dodge(text, _EXPEDIENT_RE)


_FORBADE_RE: Final = re.compile(r"\bB3\b|\bUSER_FORBADE\b")


def carries_forbade_exception(text: str) -> bool:
    """True when the report claims the ONE case §13 allows: Jon forbade the secure option.

    §13.1 keeps exactly one door open — B3 USER_FORBADE, where an explicit
    constraint rules the secure option out. Naming B3 does not make the claim
    true (the orchestrator judges the four-part proof); it makes the claim
    ARGUABLE, which is enough that a gate should not sit on top of it.
    """
    return bool(_FORBADE_RE.search(strip_quoted(text)))


def find_handover_section(text: str) -> str:
    """First 'remaining'/'next up'-style SECTION HEADING, or ''.

    Headings only. The contract's own wording is about a *section* of the
    reply, and matching the bare words anywhere in prose would fire on
    "the remaining 12 tests pass" -- a report of success.
    """
    stripped = strip_quoted(text)
    match = _HANDOVER_RE.search(stripped)
    return match.group(0).strip() if match else ""


_PAUSE_REQUEST_RE: Final = re.compile(
    r"\b(?:"
    r"stop|pause|hold (?:on|off)|wait|don'?t continue|do not continue"
    r"|what'?s (?:left|remaining|the status)|status(?: update)?|where are (?:we|you)"
    r"|summar(?:y|ise|ize)|recap|explain|why did you"
    r"|plan\b|options?\b|which (?:one|do you)"
    r")\b",
    re.IGNORECASE,
)


def user_asked_to_pause_or_report(text: str) -> bool:
    """True when Jon's own last turn asked for a stop, a status, or an answer.

    The single most important suppressor here. "Exactly two things end a turn:
    the task is FINISHED, or Jon tells you to stop" -- so when Jon HAS said
    stop, or asked a question, ending the turn is correct and a gate that
    refused it would be training evasive phrasing into every future status
    report. This is scope, not leniency.
    """
    return bool(_PAUSE_REQUEST_RE.search(text))


def last_user_text(transcript_path: str) -> str:
    """Concatenated text of the final user message in a transcript."""
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
        if entry.get("type") != "user":
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

# Neither of the next two is excused by a blocker proof or a filed task: they do
# not describe WHOSE work it is, they describe shipping the wrong work.
SECURITY_REMEDY: Final = (
    "Per .claude/skills/_shared/execution-contract.md §13, security is a ranked "
    "requirement, not a trade-off axis.\n\n"
    "NEVER propose or implement a less secure option when a more secure one is "
    "available. Convenience, brevity, fewer moving parts, one less dependency, "
    "and finishing sooner do NOT outrank it. If the secure option costs more "
    "code, more config, or more time, that cost is the price of the correct "
    "option - not evidence that the weaker one was reasonable.\n\n"
    "  - A difference in security posture SETTLES a design choice. It is not a "
    "B2 tie, it is not a menu for Jon, and it is not yours to trade away.\n"
    "  - A control that cannot evaluate its input DENIES. Fail closed. A guard "
    "that permits on a missing claim, an unknown provider, or an unparseable "
    "policy has turned an unknown into an approval - and no test suite can see "
    "it.\n"
    "  - If a test, build, or deploy fails AGAINST a control, the control is the "
    "requirement and the thing failing it is the defect. Disabling, loosening, "
    "or exempting it to turn red into green is banned - especially when it is "
    "the only thing standing between you and a green suite.\n"
    "  - What the generator EMITS counts double: an insecure default in a "
    "template is one defect per generated project, forever.\n"
    "  - An existing insecure pattern next door is evidence about the neighbour, "
    "not permission.\n\n"
    "Undo the downgrade, implement the secure option, and re-run the check. The "
    "single exception is B3 USER_FORBADE - Jon's explicit constraint rules the "
    "secure option out - and then you say so in one line, name the exposure, and "
    "implement the most secure option compatible with the constraint."
)

EXPEDIENT_REMEDY: Final = (
    "Per .claude/skills/_shared/execution-contract.md §14, the size of a fix is "
    "set by the DEFECT - never by what is left of your context, budget, turn, or "
    "patience.\n\n"
    "There is no later. There is no other agent. A fix labelled temporary is a "
    "permanent fix with a note attached, and the note is the part that "
    "evaporates: what survives a compaction is the code you landed, not the "
    "sentence explaining that it was provisional.\n\n"
    "Saying it honestly does not help. Honesty about a shortcut is not a "
    "substitute for not taking it.\n\n"
    "Economy means reading NARROWLY, never writing a LESSER change (§11.0 "
    "applied to the fix itself). If the correct fix is big, do it and report the "
    "expansion (§4). If context is short, spend it on the CORRECT change - the "
    "smallest correct change, not the smallest change.\n\n"
    "Go back and make the change the defect deserves. The test: if this were the "
    "only change ever made here, would it be right? If the answer needs a 'for "
    "now', an 'until', or a 'then later', it is not the fix."
)
