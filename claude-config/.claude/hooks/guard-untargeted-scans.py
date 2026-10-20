"""PreToolUse hook: refuse a repo-wide anti-pattern scan that answers no question.

THE INCIDENT
------------
On 2026-09-20, after a builtin had been added and proven -- targeted tests green in
all three touched packages, every language plugin loading, the builtin-claims parity
gate and the customer-domain isolation gate passing -- the agent ran

    powershell -File scripts/scan/semgrep.ps1 datrix-codegen-python datrix-common datrix-codegen-common

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
Each scanner's POSIX twin (`semgrep.sh`, `libcst.sh`, `ast-grep.sh`) and its module run
directly (`-m datrix_scripts.scan.<scanner>`) are the same scan, read in the module's own
flags: `--all` sweeps, `--rule` / `--pattern` target.
Subagents get no marker path at all -- a scan a subagent wants is a scan the main
session decides on, once, at the gate.

The parity cases gate (`parity-cases-gate.ps1`) is the same kind of act: with no `-Tag`
it reads every parity row on every registered target, generating every fixture once per
target -- the whole corpus, which is Jon's run. An agent runs it with `-Tag <tag>` (the
behaviour it changed) or `-SelfTest`; no marker lifts an untagged run.

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

from _command_shape import executable_text, invoked_scripts, leading_token, segments

_SCANNERS = ("semgrep", "libcst", "ast-grep")

_SCANNER_RE = re.compile(
    r"(?<![\w.-])(" + "|".join(re.escape(s) for s in _SCANNERS) + r")\.ps1\b",
    re.IGNORECASE,
)
_ALL_RE = re.compile(r"(?<![\w-])-All\b", re.IGNORECASE)
# A scanner's own self-test reads planted inputs only, never a package: it targets itself.
_TARGETED_RE = re.compile(r"(?<![\w-])-(?:Rule|Pattern|Id|SelfTest)\b", re.IGNORECASE)
_QUESTION_MARKER = "SCAN_QUESTION:"

# Each scanner's POSIX twin by file name, and the module behind both wrappers run directly (`-m`
# alone or closing a group of the interpreter's argument-free flags): both take the module's own
# flags, `--all`, `--rule`, `--pattern`.
_SCANNER_TWINS = {f"{scanner}.sh": scanner for scanner in _SCANNERS}
_SCANNER_MODULE_RE = re.compile(
    r"(?:^|[\s;|&(])-[bdeiopqrsuvx]*m\s*datrix_scripts\.scan\.(?P<module>semgrep|libcst|ast_grep)(?![\w.])(?P<args>.*)",
    re.IGNORECASE,
)
_MODULE_ALL_RE = re.compile(r"(?<![\w-])--all(?![\w-])", re.IGNORECASE)
_MODULE_TARGETED_RE = re.compile(r"(?<![\w-])--(?:rule|pattern|self-test)(?![\w-])", re.IGNORECASE)

# The parity cases gate by file name: the wrapper and its POSIX twin, which runs the same module
# with the module's own flags (`--tag`, `--self-test`).
_PARITY_CASES_SCRIPTS = frozenset({"parity-cases-gate.ps1", "parity-cases-gate.sh"})
# The module behind both wrappers, run directly: `-m` alone or closing a group of the
# interpreter's argument-free flags, with or without a space before the module name.
_PARITY_CASES_MODULE_RE = re.compile(
    r"(?:^|[\s;|&(])-[bdeiopqrsuvx]*m\s*datrix_scripts\.gates\.parity\.parity_cases_gate(?![\w.])(?P<args>.*)",
    re.IGNORECASE,
)
_PARITY_SELECTED_RE = re.compile(r"(?<![\w-])(?:-(?:Tag|SelfTest)|--(?:tag|self-test))(?![\w-])", re.IGNORECASE)

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


def _script_run_by(segment: str) -> str:
    """The ``.ps1`` script this segment EXECUTES, or "" when it executes none."""
    token = leading_token(segment)
    if token.endswith(".ps1"):
        return token
    if token in _EXECUTORS:
        return _script_argument(segment)
    return ""


def _scanner_run_by(segment: str) -> str:
    """The scanner wrapper this segment EXECUTES, or "" when it executes none."""
    match = _SCANNER_RE.search(_script_run_by(segment))
    return match.group(1).lower() if match else ""


def _parity_cases_runs(command: str) -> list[str]:
    """The argument text of every parity cases gate run *command* executes: the wrapper, its
    POSIX twin, or the module run directly -- never a path another program merely names."""
    runs = [
        " ".join(script.args)
        for script in invoked_scripts(command)
        if script.path.rsplit("/", 1)[-1].lower() in _PARITY_CASES_SCRIPTS
    ]
    for segment in segments(executable_text(command)):
        match = _PARITY_CASES_MODULE_RE.search(segment)
        if match:
            runs.append(match.group("args"))
    return runs


def _check_parity_cases(command: str) -> None:
    if all(_PARITY_SELECTED_RE.search(arguments) for arguments in _parity_cases_runs(command)):
        return
    sys.stderr.write(
        "BLOCKED: `parity-cases-gate.ps1` (or `parity-cases-gate.sh`, or its module run directly) with "
        "no `-Tag` reads every parity row on every registered target, generating every fixture: the "
        "whole corpus, which is Jon's run.\n\n"
        "Run the rows of the behaviour you changed, `parity-cases-gate.ps1 -Tag <tag>` (`--tag <tag>` "
        "on the `.sh` twin; at most three tags), or the gate's own `-SelfTest` (`--self-test`)."
    )
    sys.exit(2)


def _scanner_runs(command: str) -> list[tuple[str, str, bool]]:
    """Every scanner run *command* executes: ``(scanner, its argument text, whether that text is in
    the module's own --kebab flags)`` -- the ``.ps1`` wrapper, its POSIX twin, or the module run
    directly, never a path another program merely names."""
    runs: list[tuple[str, str, bool]] = []
    for segment in segments(executable_text(command)):
        scanner = _scanner_run_by(segment)
        if scanner:
            runs.append((scanner, segment, False))
        match = _SCANNER_MODULE_RE.search(segment)
        if match:
            runs.append((match.group("module").lower().replace("_", "-"), match.group("args"), True))
    for script in invoked_scripts(command):
        twin = _SCANNER_TWINS.get(script.path.rsplit("/", 1)[-1].lower())
        if twin:
            runs.append((twin, " ".join(script.args), True))
    return runs


def _check(command: str, description: str, is_subagent: bool) -> None:
    _check_parity_cases(command)
    stated = _QUESTION_MARKER in description and bool(description.split(_QUESTION_MARKER, 1)[1].strip())
    for scanner, arguments, module_flags in _scanner_runs(command):
        all_re, targeted_re = (_MODULE_ALL_RE, _MODULE_TARGETED_RE) if module_flags else (_ALL_RE, _TARGETED_RE)
        if all_re.search(arguments):
            _block(
                f"BLOCKED: `{scanner}.ps1 -All` (`--all` on its `.sh` twin or module) sweeps every "
                "package. A corpus sweep is never a per-fix check, with or without a marker."
            )
        if is_subagent:
            _block(
                f"BLOCKED: you are a subagent and may not run `{scanner}.ps1` (its `.sh` twin or "
                "module). A scan is a main-session, phase-boundary decision; report what your "
                "targeted tests proved instead."
            )
        if targeted_re.search(arguments) or stated:
            continue
        _block(
            f"BLOCKED: `{scanner}.ps1` (its `.sh` twin or module) over whole package(s) with no rule "
            "named and no question stated."
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
