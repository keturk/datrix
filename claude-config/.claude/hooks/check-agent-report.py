"""SubagentStop hook: refuse to let a subagent finish on a dodge.

Enforces .claude/skills/_shared/execution-contract.md §7 (banned report vocabulary).

An agent that ends its turn by declaring the problem out of scope, pre-existing,
someone else's, or "to be tracked separately" — WITHOUT either a four-part blocker
proof or a filed task file — has not done its job. This hook blocks the stop and
sends it back to work.

Legitimate exits are preserved. The block is skipped when the final message carries:
  - a blocker code (B1/B2/B3/B4) with proof, or
  - a filed task file path (a defect that was properly FILED), or
  - EXPANSION_REQUIRED (knows the fix, needs the file lock).

Exit codes:
  0 — allow the subagent to stop
  2 — block the stop; stderr is fed back to the subagent, which continues working
"""

import json
import re
import sys

# High-signal dodge phrases. Kept deliberately tight to avoid false positives —
# the fuller list lives in the execution contract and is judged by the orchestrator.
_DODGE_RE = re.compile(
    r"\b("
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
    r")\b",
    re.IGNORECASE,
)

# If a dodge phrase is negated ("no workaround was needed", "nothing left as-is"),
# it is not a dodge. Look back this many chars for a negation cue.
_NEGATION_LOOKBACK = 32
_NEGATION_RE = re.compile(
    r"\b(no|not|never|without|avoid(?:ed|ing)?|isn'?t|aren'?t|wasn'?t|"
    r"weren'?t|nothing|none|zero)\b[^.]*$",
    re.IGNORECASE,
)

# Markers that make an otherwise-flagged report legitimate.
_PROOF_RE = re.compile(
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


def _last_assistant_text(transcript_path: str) -> str:
    """Return the concatenated text of the final assistant message in the transcript."""
    try:
        with open(transcript_path, "r", encoding="utf-8") as handle:
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


def _find_unnegated_dodge(text: str) -> str:
    """Return the first dodge phrase that is not negated, or '' if none."""
    for match in _DODGE_RE.finditer(text):
        window = text[max(0, match.start() - _NEGATION_LOOKBACK) : match.start()]
        if _NEGATION_RE.search(window):
            continue
        return match.group(0)
    return ""


def main() -> None:
    try:
        data = json.loads(sys.stdin.read())
    except json.JSONDecodeError:
        sys.exit(0)

    # Never re-block a stop we already blocked — that would loop forever.
    if data.get("stop_hook_active"):
        sys.exit(0)

    text = _last_assistant_text(data.get("transcript_path", ""))
    if not text:
        sys.exit(0)

    # A report carrying a real blocker proof / filed task / expansion request is fine.
    if _PROOF_RE.search(text):
        sys.exit(0)

    dodge = _find_unnegated_dodge(text)
    if not dodge:
        sys.exit(0)

    sys.stderr.write(
        f'REPORT REJECTED — you are ending your turn on a dodge: "{dodge}".\n\n'
        "Per .claude/skills/_shared/execution-contract.md, that is NOT a blocker. "
        "It is the work.\n\n"
        "There are exactly four legitimate blockers:\n"
        "  B1 MISSING_ACCESS  — needs a credential/endpoint/resource you cannot obtain\n"
        "  B2 UNDECIDABLE     — two genuinely defensible designs, expensive to reverse\n"
        "  B3 USER_FORBADE    — the only correct fix was explicitly prohibited\n"
        "  B4 FENCED_SURFACE  — root cause is on a surface the user explicitly excluded\n\n"
        "Everything else is work: root cause unclear -> keep reading. Root cause in "
        "another package -> go fix it there. Bigger than estimated -> do it. "
        "Pre-existing -> it is yours now. 'Behavioral/environmental' -> prove it with "
        "the verbatim error text, or fix it. No test -> write one. 'Should be tracked "
        "separately' -> THERE IS NO OTHER AGENT.\n\n"
        "Do ONE of these, then finish:\n"
        "  1. FIX IT. (This is the default and almost always the right answer.)\n"
        "  2. FILE IT — create a real tracked task file and cite its path, if it is "
        "genuinely an independent root cause.\n"
        "  3. PROVE A BLOCKER — give all four: verbatim error text; the fix you "
        "actually wrote and ran (file:line); why it failed; and the B1-B4 code. "
        "Analysis alone is not an attempt.\n\n"
        "Do not rephrase to slip past this check. The rule is the behavior, not the "
        "wordlist."
    )
    sys.exit(2)


if __name__ == "__main__":
    main()
