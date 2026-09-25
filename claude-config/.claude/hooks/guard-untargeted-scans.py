"""PreToolUse hook: refuse a repo-wide anti-pattern scan that answers no question.

THE INCIDENT
------------
On 2026-09-20, after a builtin had been added and proven -- targeted tests green in
all three touched packages, every language plugin loading, the builtin-claims parity
gate and the customer-domain isolation gate passing -- the agent ran

    powershell -File scripts/dev/semgrep.ps1 datrix-codegen-python datrix-common datrix-codegen-common

because "run the relevant static scan / repo gate" is rung 4 of the static-analysis
ladder. It could not name a rule the scan might trip, a failure it was chasing, or a
decision its result would change. It ran for more than ten minutes, was moved to the
background, and was then WAITED ON with a `sleep` poll loop -- a second rule broken to
service the first. Total value delivered: none. Jon's time spent on it: real.

THE RULE
--------
CLAUDE.md, Budget: a check is bought for a QUESTION, never for a rung. A whole-package
or `-All` anti-pattern scan (`semgrep.ps1`, `libcst.ps1`, `ast-grep.ps1`) is a
phase-boundary / quality-gate act. Inside a fix it is allowed only when the call
itself says what it is for:

  * `-Rule <name>` (or `-Pattern` / `-Id`) -- a targeted scan for a named rule, or
  * `SCAN_QUESTION: <text>` in the command description, naming the defect class the
    scan targets and why the targeted tests cannot answer it.

Neither marker lifts an `-All` run: sweeping every package is never a per-fix act.
Subagents get no marker path at all -- a scan a subagent wants is a scan the main
session decides on, once, at the gate.

Reading any of these scripts is never blocked: read-only segments are dropped before
the command is inspected (`_command_shape`).

Exit codes:
  0 -- allow
  2 -- block (stderr becomes feedback to Claude)
"""

from __future__ import annotations

import json
import re
import shlex
import sys

from _command_shape import executable_text, leading_token, segments

_SCANNERS = ("semgrep", "libcst", "ast-grep")

_SCANNER_RE = re.compile(
    r"(?<![\w.-])(" + "|".join(re.escape(s) for s in _SCANNERS) + r")\.ps1\b",
    re.IGNORECASE,
)
_ALL_RE = re.compile(r"(?<![\w-])-All\b", re.IGNORECASE)
_TARGETED_RE = re.compile(r"(?<![\w-])-(?:Rule|Pattern|Id)\b", re.IGNORECASE)
_QUESTION_MARKER = "SCAN_QUESTION:"

_EXECUTORS = frozenset({"powershell", "pwsh", "cmd", "bash", "sh", "zsh", "start"})

_WHY = (
    "\n\nCLAUDE.md, Budget: 'A check is bought for a question, never for a rung.' "
    "A repo-wide anti-pattern scan inside a fix answers nothing the targeted tests "
    "and the registration/parity gates have not already answered, and it costs "
    "minutes of Jon's time. It belongs at the phase boundary / quality gate, run "
    "once over the changed packages.\n\n"
    "If you can name the rule this scan would trip, run that rule: "
    "`semgrep.ps1 <package> -Rule <name>`. If you can name the question it answers "
    "and why the targeted tests cannot, re-issue with `SCAN_QUESTION: <the question>` in the "
    "command description. If you can do neither, the scan is punctuation -- skip it "
    "and report the verification you already have."
)


def _block(msg: str) -> None:
    sys.stderr.write(msg + _WHY)
    sys.exit(2)


def _script_argument(segment: str) -> str:
    """The first non-flag argument after the executable -- the script it runs."""
    try:
        tokens = shlex.split(segment, posix=False)
    except ValueError:
        tokens = segment.split()
    for token in tokens[1:]:
        if token.startswith("-"):
            continue
        return token
    return ""


def _scanner_run_by(segment: str) -> str:
    """The scanner wrapper this segment EXECUTES, or "" when it executes none."""
    token = leading_token(segment)
    script = ""
    if token.endswith(".ps1"):
        script = token
    elif token in _EXECUTORS:
        script = _script_argument(segment)
    match = _SCANNER_RE.search(script)
    return match.group(1).lower() if match else ""


def _check(command: str, description: str, is_subagent: bool) -> None:
    for segment in segments(executable_text(command)):
        scanner = _scanner_run_by(segment)
        if not scanner:
            continue
        if _ALL_RE.search(segment):
            _block(
                f"BLOCKED: `{scanner}.ps1 -All` sweeps every package. A corpus sweep is "
                "never a per-fix check, with or without a marker."
            )
        if is_subagent:
            _block(
                f"BLOCKED: you are a subagent and may not run `{scanner}.ps1`. A scan "
                "is a main-session, phase-boundary decision; report what your targeted "
                "tests proved instead."
            )
        if _TARGETED_RE.search(segment):
            continue
        if _QUESTION_MARKER in description and description.split(_QUESTION_MARKER, 1)[1].strip():
            continue
        _block(
            f"BLOCKED: `{scanner}.ps1` over whole package(s) with no rule named and no "
            "question stated."
        )


def main() -> None:
    try:
        data = json.loads(sys.stdin.read())
    except json.JSONDecodeError:
        sys.exit(0)

    tool_input = data.get("tool_input", {})
    command = tool_input.get("command", "")
    if command:
        _check(command, tool_input.get("description", ""), bool(data.get("agent_id")))

    sys.exit(0)


if __name__ == "__main__":
    main()
