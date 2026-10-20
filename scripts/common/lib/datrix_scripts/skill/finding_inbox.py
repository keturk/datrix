"""The exact half of /implement-finding: the skill-assist commands finding-select and finding-close
(``datrix_scripts.skill.assist_cli``), which ``skill/implement-finding.ps1``
(``datrix_scripts.skill.implement_finding``) runs around each fix session, one finding at a time.

The skill decides whether a finding still holds and fixes it; this module decides nothing about the
code. It does the parts that must not rest on a model's word:

SELECT
    The first N findings files of the inbox (``*.md`` directly in the folder, by name).

CLOSE
    Deletes the finding file, but not while another findings file in the folder names it (deleting
    it would leave that pointer dangling). Given the fix session's stream log (``--session-log``,
    the ``.stream.jsonl`` a headless step writes), it also requires the session's last foreground
    proving run -- a ``test.ps1`` run, or a ``*-gate.ps1`` run for code no ``test.ps1`` reaches
    (the scripts tree hosts no test suite) -- to have passed: a fix with no passing proving run is
    not proven, so the finding stays.

Exit codes (the skill-assist ones): 0 deleted (``select``: done); 1 the request is unusable (the
message says why); 2 not deleted -- the message names what is missing.
"""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass
from pathlib import Path

from datrix_scripts.skill.chain import event_blocks, tool_result_text
from datrix_scripts.skill.common import EXIT_CHECK_FAILED, EXIT_FAILED, EXIT_OK, AssistError, read_text

LOG = logging.getLogger(__name__)

EXIT_DELETED = EXIT_OK
EXIT_UNUSABLE = EXIT_FAILED
EXIT_KEPT = EXIT_CHECK_FAILED

DEFAULT_COUNT = 10
FINDINGS_DIR_PARTS = ("reports", "finding")
SHELL_TOOLS = frozenset({"Bash", "PowerShell"})

_TEST_COMMAND = re.compile(r"(?<![\w-])test\.ps1", re.IGNORECASE)
_GATE_COMMAND = re.compile(r"(?<![\w-])[\w-]+-gate\.ps1", re.IGNORECASE)
# A listing runs nothing, and a self-test proves the gate or its harness, not the changed code.
_NOT_A_TEST_RUN = re.compile(r"-(?:ListTags|SelfTest|HarnessSelfTest)\b", re.IGNORECASE)
# Every gate prints one last line, "[GATE] <name> PASSED|FAILED exit=<n> log=<path>"
# (Invoke-DatrixPythonScript -Gate / Write-DatrixGateVerdict / datrix_scripts.gate_log.run_as_gate),
# whatever its exit code reached the shell.
_GATE_VERDICT = re.compile(r"^\[GATE\]\s+\S+\s+(PASSED|FAILED)\s+exit=(-?\d+)\s", re.MULTILINE)
_GATE_PASSED = "PASSED"
# test.ps1 prints "[FAIL] Tests failed for <pkg>" and "Failed: N"; pytest prints "N failed" / "N errors".
_FAILURE_TEXT = re.compile(r"\[FAIL\]|\bFailed: [1-9]|\b[1-9]\d* (?:failed|errors?)\b", re.IGNORECASE)
# A pipe hands the shell the exit code of the filter, not of test.ps1, so a piped run's exit code proves
# nothing; it passes only on test.ps1's own closing verdict, which a tail keeps and a head or grep drops.
_PIPE = re.compile(r"(?<!\|)\|(?!\|)")
# test.ps1's last summary line: "Total: N | Passed: N | Failed: N" (package counts).
_SUMMARY = re.compile(r"^\s*Total: (\d+) \| Passed: (\d+) \| Failed: (\d+)\s*$", re.MULTILINE)


@dataclass(frozen=True)
class TestRun:
    command: str
    failure: str

    @property
    def passed(self) -> bool:
        return not self.failure


def finding_files(directory: Path, count: int) -> list[Path]:
    """The first ``count`` ``*.md`` files directly in ``directory``, by name."""
    if not directory.is_dir():
        raise AssistError(f"Findings folder '{directory}' does not exist. Pass --dir with an existing folder.")
    if count < 1:
        raise AssistError(f"--count must be at least 1 (got {count}).")
    return sorted(path for path in directory.glob("*.md") if path.is_file())[:count]


def findings_dir(workspace: Path, given: str) -> Path:
    """The findings folder: ``given`` when set, else ``<workspace>/reports/finding``."""
    return Path(given).resolve() if given else workspace.joinpath(*FINDINGS_DIR_PARTS)


def referrers(finding: Path) -> list[str]:
    """The other findings files beside ``finding`` that name it, whose pointer its deletion would break."""
    return sorted(other.name for other in finding.parent.glob("*.md")
                  if other.is_file() and other != finding and finding.stem in read_text(other))


def _test_command(block: dict[str, object]) -> str:
    """The command of a foreground shell call that runs tests or a gate; empty for any other tool call."""
    tool_input = block.get("input")
    if block.get("name") not in SHELL_TOOLS or not isinstance(tool_input, dict):
        return ""
    command = str(tool_input.get("command", ""))
    proving = _TEST_COMMAND.search(command) or _GATE_COMMAND.search(command)
    if tool_input.get("run_in_background") or not proving or _NOT_A_TEST_RUN.search(command):
        return ""
    return command


def _gate_failure(command: str, output: str) -> str:
    """Why the gate calls in ``command`` did not pass; empty when ``output`` keeps a PASSED exit=0
    verdict line for every gate call and no other verdict -- the verdict a piped run's exit code cannot give."""
    verdicts = _GATE_VERDICT.findall(output)
    if any(verdict != _GATE_PASSED or int(code) != 0 for verdict, code in verdicts):
        return "a gate verdict line reports FAILED"
    if len(verdicts) < len(_GATE_COMMAND.findall(command)):
        return "its output kept no '[GATE] <name> PASSED exit=0' verdict line for each gate call"
    return ""


def _verdicts_all_pass(command: str, output: str) -> bool:
    """Whether ``output`` keeps test.ps1's summary line for every invocation in ``command``, each one
    with every package passed -- the verdict a piped run's exit code cannot give."""
    verdicts = _SUMMARY.findall(output)
    if len(verdicts) < len(_TEST_COMMAND.findall(command)):
        return False
    return all(int(total) == int(passed) and int(failed) == 0 for total, passed, failed in verdicts)


def _failure_reason(command: str, block: dict[str, object]) -> str:
    """Why a test or gate run did not pass; empty when it passed."""
    output = tool_result_text(block)
    if block.get("is_error"):
        return "it exited non-zero"
    if _TEST_COMMAND.search(command):
        if _FAILURE_TEXT.search(output):
            return "its output reports failed or erroring tests"
        if _PIPE.search(command) and not _verdicts_all_pass(command, output):
            return ("its output was piped through a filter that hides test.ps1's exit code, and the output "
                    "kept no all-passed 'Total: N | Passed: N | Failed: 0' summary for each test.ps1 call")
    if _GATE_COMMAND.search(command):
        return _gate_failure(command, output)
    return ""


def test_runs(session_log: Path) -> list[TestRun]:
    """Every foreground ``test.ps1`` or ``*-gate.ps1`` run in a step's stream log, in order, with whether
    it passed.

    A run passed when its tool result is not an error (a non-zero exit) and every tool it calls passed:
    a ``test.ps1`` call when its output reports no failed or erroring test and -- when its output is
    piped through a filter, which replaces test.ps1's exit code with the filter's -- the output still
    carries test.ps1's summary line for every invocation, each reporting every package passed; a gate
    call when its output keeps the gate's ``[GATE] <name> PASSED exit=0`` verdict line for every gate
    call and no FAILED one. A run of gates alone is judged by their verdict lines, never by the text of
    the checks they run (a gate's fixtures print failures on purpose). ``-ListTags``, ``-SelfTest`` and
    ``-HarnessSelfTest`` runs are not proving runs.
    """
    if not session_log.is_file():
        raise AssistError(f"Session log '{session_log}' does not exist. Pass the step's .stream.jsonl.")
    pending: dict[str, str] = {}
    runs: list[TestRun] = []
    for line in read_text(session_log).splitlines():
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            continue
        if not isinstance(event, dict):
            continue
        for block in event_blocks(event, "tool_use"):
            command = _test_command(block)
            if command:
                pending[str(block.get("id"))] = command
        for block in event_blocks(event, "tool_result"):
            command = pending.pop(str(block.get("tool_use_id")), "")
            if command:
                runs.append(TestRun(command, _failure_reason(command, block)))
    return runs


def close_finding(finding: Path, session_log: Path | None) -> tuple[str, int]:
    """Delete ``finding`` when nothing still names it and, given a session log, its last test or gate run passed."""
    if not finding.is_file():
        return f"Finding '{finding}' does not exist. Pass an existing findings file.", EXIT_UNUSABLE
    reasons = [f"{name} still names it: remove that pointer first" for name in referrers(finding)]
    if session_log is not None:
        runs = test_runs(session_log)
        if not runs:
            reasons.append("the fix session ran no foreground test.ps1 or *-gate.ps1, so the fix is not proven")
        elif not runs[-1].passed:
            reasons.append(f"the fix session's last test run did not pass ({runs[-1].failure}): {runs[-1].command}")
    if reasons:
        return "\n".join([f"Not deleted: {finding}", *(f"  - {reason}" for reason in reasons)]), EXIT_KEPT
    finding.unlink()
    LOG.info("Deleted finding %s", finding)
    return f"Deleted: {finding}", EXIT_DELETED
