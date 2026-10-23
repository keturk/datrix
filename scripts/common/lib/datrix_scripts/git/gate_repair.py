"""Hand a pre-stage gate failure to a Claude agent, then re-run the gates and carry on.

The module behind the repair step of ``git/commit-and-push.ps1``. A gate that finds problems in the
pending changes (lint, PolyString round trips, design/task references) used to end the whole run
with a report. Now ``run_with_repair`` gives each such failure to a Claude Code agent -- Sonnet 5.5
at medium effort by default -- and re-runs every check afterwards; the commit and push proceed only
once the checks pass.

WHAT IS AND IS NOT HANDED OVER
    Only a ``GateViolation`` is repaired: a gate that ran, trusted its own self-test and found
    problems in pending files whose fix is an edit to those files. A gate that could not run, or
    whose self-test failed, is a broken tool rather than a defect in the pending changes, so it ends
    the run as before. Two gates never raise a ``GateViolation``. The customer-domain check redacts
    the matched term on purpose, and an agent opening the flagged file would send that term to a
    model service. The ignored-source check is fixed by editing a ``.gitignore`` rule or the
    exemption file, which is a control's own configuration; an unattended agent must not be the one
    to loosen it, so a person decides.

WHAT THE AGENT CAN DO
    Read, search and edit files in the workspace, under the workspace's own CLAUDE.md, hooks and
    guards -- and nothing else: no shell, so it cannot stage, commit, push or run this script. The
    re-check is the proof the repair worked, not the agent's word.
"""

from __future__ import annotations

import tempfile
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Final, TypeVar

from datrix_scripts.claude_cli import AgentRequest, AgentRunError, agent_command, run_agent
from datrix_scripts.gate_harness import UsageError

DEFAULT_REPAIR_ATTEMPTS: Final = 3
DEFAULT_REPAIR_MODEL: Final = "claude-sonnet-5-5"
DEFAULT_REPAIR_EFFORT: Final = "medium"
DEFAULT_REPAIR_TIMEOUT_MS: Final = 1_800_000

# The built-in tools the agent gets: reading, searching and editing files. No shell, so no git.
REPAIR_TOOLS: Final = "Read,Edit,Write,Grep,Glob"
REPAIR_PERMISSION_MODE: Final = "acceptEdits"
# Read-only MCP tools, let through without a prompt: the code index answers where a name is defined and
# used (and so which import fixes an undefined name), and a local model reads a large file for a question.
REPAIR_MCP_TOOLS: Final = (
    "mcp__datrix-code-index__find_canonical",
    "mcp__datrix-code-index__find_symbol",
    "mcp__datrix-code-index__find_references",
    "mcp__datrix-code-index__outline",
    "mcp__datrix-code-index__search",
    "mcp__datrix-local-llm__ask_files",
)

# Lines of code shown either side of a flagged line, and the most places shown. Past the cap the brief says
# how many were left out; the report still lists every one.
EXCERPT_RADIUS: Final = 6
EXCERPT_MAX_LOCATIONS: Final = 40

_T = TypeVar("_T")


class GateRunError(RuntimeError):
    """A pre-stage gate or its repair ended the run."""


@dataclass(frozen=True)
class GateLocation:
    """One place a gate flagged: an absolute file path and a 1-based line."""

    path: Path
    line: int


class GateViolation(GateRunError):
    """A gate ran and found problems in the pending changes -- the failures an agent can repair.

    ``gate`` names the check; ``str(violation)`` is its full report, with every file and line;
    ``locations`` are the same places as data, so the repair brief can carry the code around them.
    """

    def __init__(self, gate: str, report: str, locations: tuple[GateLocation, ...] = ()) -> None:
        super().__init__(report)
        self.gate = gate
        self.locations = locations


class GateRepairError(GateRunError):
    """The repair agent could not run, timed out, or reported an error."""


def run_with_repair(
    check: Callable[[], _T],
    repair: Callable[[GateViolation, int], None],
    attempts: int,
) -> _T:
    """Run *check*; on a ``GateViolation`` call *repair* and run it again, up to *attempts* repairs.

    Returns what *check* returns once it passes. With ``attempts`` of 0 the first violation is raised
    unchanged. After the last repair a still-failing check raises its violation with a note saying how
    many repairs ran. Any other exception leaves at once, with no repair.
    """
    for attempt in range(1, attempts + 2):
        try:
            return check()
        except GateViolation as violation:
            if attempts == 0:
                raise
            if attempt > attempts:
                raise GateViolation(
                    violation.gate,
                    f"{violation}\nThe repair agent ran {attempts} time(s) and the gate still fails.",
                    violation.locations,
                ) from violation
            repair(violation, attempt)
    raise AssertionError("unreachable: the last attempt returns or raises")


def code_excerpts(locations: tuple[GateLocation, ...]) -> str:
    """The code around each flagged line, numbered, with ``>`` on the flagged line.

    Read here, so the agent starts from the code instead of spending turns opening it. A file that cannot
    be read is named with the reason; the report still lists its finding.
    """
    unique = list(dict.fromkeys(locations))
    sections: list[str] = []
    for location in unique[:EXCERPT_MAX_LOCATIONS]:
        try:
            lines = location.path.read_text(encoding="utf-8", errors="replace").splitlines()
        except OSError as exc:
            sections.append(f"--- {location.path}:{location.line} (unreadable: {exc.strerror or exc})")
            continue
        first = max(1, location.line - EXCERPT_RADIUS)
        last = min(len(lines), location.line + EXCERPT_RADIUS)
        body = "\n".join(
            f"{'>' if number == location.line else ' '} {number:>5} | {lines[number - 1]}"
            for number in range(first, last + 1)
        )
        sections.append(f"--- {location.path}:{location.line}\n{body}")
    if len(unique) > EXCERPT_MAX_LOCATIONS:
        sections.append(f"[{len(unique) - EXCERPT_MAX_LOCATIONS} more flagged place(s) not shown; the report lists them]")
    return "\n\n".join(sections)


def repair_prompt(
    violation: GateViolation, workspace: Path, attempt: int, attempts: int, previous_summary: str | None
) -> str:
    """The agent's brief: the gate, its full report, what to change and what never to touch."""
    earlier = (
        f"\nThis is repair {attempt} of {attempts}. The previous repair ended with this summary, "
        f"and the gate still failed afterwards -- do not repeat it:\n{previous_summary}\n"
        if previous_summary
        else ""
    )
    return (
        f"The Datrix commit script stopped before committing anything: its '{violation.gate}' gate "
        f"found problems in the uncommitted changes under {workspace}. Fix them at the source so the "
        "gate passes. The script re-runs every gate itself when you finish and then commits and "
        "pushes, so do not stage, commit or push, and you have no shell to do so.\n"
        f"{earlier}\n"
        "Follow the workspace CLAUDE.md. Read the files it requires before your first edit.\n\n"
        "Rules:\n"
        "- Change the files the report names, and only what the fix itself needs. Do not fix "
        "anything else you notice.\n"
        "- Fix the cause. A suppression (`# noqa`) belongs only where the report says a finding "
        "can be genuinely required, with the reason written beside it.\n"
        "- Never edit a gate, its scanner, an exemption file, a baseline or a term corpus "
        "(anything under datrix/scripts/gates, datrix/scripts/config or "
        "datrix/scripts/common/lib), and never loosen a rule to make the gate pass.\n"
        "- If a finding cannot be fixed within those rules, leave it and say so.\n\n"
        "Finding things: the code around each flagged line is below, so start from it. To learn where a "
        "name is defined or used, or which import fixes an undefined name, ask the code index "
        "(find_symbol, find_references, find_canonical, outline, search) instead of grepping. To "
        "understand a large file, ask_files (a local model) can read it for you; its answer is a lead, "
        "so open the lines it cites before you rely on them.\n\n"
        "Finish with a short summary: each change as file:line, then anything you left unfixed and why.\n\n"
        "<<<GATE_REPORT>>>\n"
        f"{violation}\n"
        "<<<END_GATE_REPORT>>>\n\n"
        "<<<FLAGGED_CODE>>>\n"
        f"{code_excerpts(violation.locations) or '(the report names no file and line)'}\n"
        "<<<END_FLAGGED_CODE>>>\n"
    )


def repair_request(
    violation: GateViolation, workspace: Path, model: str, effort: str, timeout_ms: int, prompt: str
) -> AgentRequest:
    """The agent run for one repair: file tools only, in the workspace, on *prompt*."""
    return AgentRequest(
        prompt=prompt,
        model=model,
        effort=effort,
        permission_mode=REPAIR_PERMISSION_MODE,
        tools=REPAIR_TOOLS,
        allowed_tools=REPAIR_MCP_TOOLS,
        cwd=workspace,
        timeout_ms=timeout_ms,
        label=f"'{violation.gate}' gate repair",
    )


@dataclass
class GateRepairer:
    """Repairs gate violations with one Claude Code agent per attempt; remembers the last summary."""

    workspace: Path
    model: str
    effort: str
    timeout_ms: int
    attempts: int
    previous_summary: str | None = None

    def __call__(self, violation: GateViolation, attempt: int) -> None:
        print(
            f"\nGate '{violation.gate}' failed. Repair {attempt} of {self.attempts}: handing it to "
            f"{self.model} at {self.effort} effort (this can take minutes)...",
            flush=True,
        )
        prompt = repair_prompt(violation, self.workspace, attempt, self.attempts, self.previous_summary)
        request = repair_request(violation, self.workspace, self.model, self.effort, self.timeout_ms, prompt)
        try:
            self.previous_summary = run_agent(request)
        except AgentRunError as exc:
            raise GateRepairError(
                f"{exc} Fix the '{violation.gate}' gate's findings by hand, or raise -GateRepairTimeoutMs "
                "if it timed out."
            ) from exc
        print(f"Repair {attempt} finished. Agent summary:\n{self.previous_summary or '(none)'}\n")
        print("Re-running the gates...", flush=True)


def _refused(build: Callable[[], object]) -> bool:
    """Whether *build* raises ``UsageError``."""
    try:
        build()
    except UsageError:
        return True
    return False


def check_repair_loop_retries_until_the_gate_passes() -> None:
    """Two failures then a pass: two repairs, each given the violation and its attempt number."""
    calls = {"check": 0}
    repaired: list[tuple[str, int]] = []

    def check() -> str:
        calls["check"] += 1
        if calls["check"] <= 2:
            raise GateViolation("lint", f"finding {calls['check']}")
        return "clean"

    verdict = run_with_repair(check, lambda violation, attempt: repaired.append((str(violation), attempt)), 3)
    assert verdict == "clean", verdict
    assert repaired == [("finding 1", 1), ("finding 2", 2)], repaired
    assert calls["check"] == 3, calls


def check_repair_loop_gives_up_after_the_last_attempt() -> None:
    """A gate that never passes is raised with the repair count, after exactly *attempts* repairs."""
    repairs: list[int] = []

    def check() -> str:
        raise GateViolation("lint", "unused import")

    try:
        run_with_repair(check, lambda violation, attempt: repairs.append(attempt), 2)
    except GateViolation as exc:
        assert exc.gate == "lint" and "unused import" in str(exc) and "ran 2 time(s)" in str(exc), str(exc)
    else:
        raise AssertionError("a gate that never passes must raise")
    assert repairs == [1, 2], repairs


def check_repair_loop_with_no_attempts_raises_the_violation_unchanged() -> None:
    repairs: list[int] = []

    def check() -> str:
        raise GateViolation("lint", "unused import")

    try:
        run_with_repair(check, lambda violation, attempt: repairs.append(attempt), 0)
    except GateViolation as exc:
        assert str(exc) == "unused import", str(exc)
    else:
        raise AssertionError("zero attempts must raise the first violation")
    assert repairs == [], repairs


def check_repair_loop_does_not_repair_other_failures() -> None:
    """A gate that could not run (not a violation) leaves at once; no agent is started for it."""
    repairs: list[int] = []

    def check() -> str:
        raise GateRunError("the scanner failed its own self-test")

    try:
        run_with_repair(check, lambda violation, attempt: repairs.append(attempt), 3)
    except GateRunError as exc:
        assert not isinstance(exc, GateViolation), exc
    else:
        raise AssertionError("a non-violation failure must propagate")
    assert repairs == [], repairs


def check_code_excerpts_mark_the_flagged_line() -> None:
    """Real files: the flagged line is marked, the window is clipped at the file's ends, a duplicate place is shown
    once, an unreadable file is named, and the brief carries the excerpt."""
    with tempfile.TemporaryDirectory() as raw:
        source = Path(raw) / "a.py"
        source.write_text("".join(f"line {number}\n" for number in range(1, 31)), encoding="utf-8")
        missing = Path(raw) / "gone.py"
        flagged = (GateLocation(source, 15), GateLocation(source, 15), GateLocation(source, 1), GateLocation(missing, 3))
        shown = code_excerpts(flagged)
        brief = repair_prompt(GateViolation("lint", "a.py:15", flagged[:1]), Path(raw), 1, 3, None)
    assert shown.count(f"--- {source}:15\n") == 1, shown
    assert ">    15 | line 15" in shown and "     21 | line 21" in shown and "line 22" not in shown, shown
    assert f"--- {source}:1\n>     1 | line 1" in shown and "line 0" not in shown, shown
    assert f"--- {missing}:3 (unreadable:" in shown, shown
    assert f"<<<FLAGGED_CODE>>>\n--- {source}:15\n" in brief, brief
    assert code_excerpts(()) == "", "no location, no excerpt"


def check_repair_command_and_prompt() -> None:
    """The agent runs on the requested model and effort with file tools only; the brief carries the report."""
    violation = GateViolation("Python lint-correctness", "repo/a.py:1:1 F401 unused import")

    def request(model: str, effort: str) -> AgentRequest:
        return repair_request(violation, Path("D:/ws"), model, effort, 1000, "brief")

    command = agent_command("claude", request("claude-sonnet-5-5", "medium"))
    assert command[command.index("--model") + 1] == "claude-sonnet-5-5", command
    assert command[command.index("--effort") + 1] == "medium", command
    assert command[command.index("--tools") + 1] == REPAIR_TOOLS and "Bash" not in REPAIR_TOOLS, command
    granted = command[command.index("--allowedTools") + 1].split(",")
    assert granted == list(REPAIR_MCP_TOOLS) and all(tool.startswith("mcp__") for tool in granted), command
    assert _refused(lambda: agent_command("claude", request("claude-sonnet-5-5", "huge"))), "an unknown effort must be refused"
    assert _refused(lambda: agent_command("claude", request("", "medium"))), "an empty model must be refused"
    assert _refused(lambda: agent_command("claude.cmd", request("model&calc", "medium"))), (
        "a cmd.exe metacharacter in the model must be refused for a batch shim"
    )
    first = repair_prompt(violation, Path("D:/ws"), 1, 3, None)
    again = repair_prompt(violation, Path("D:/ws"), 2, 3, "removed the import in a.py")
    assert "Python lint-correctness" in first and "repo/a.py:1:1 F401 unused import" in first, first
    assert "previous repair" not in first and "removed the import in a.py" in again, (first, again)
