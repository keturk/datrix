"""The exact half of /implement-finding: the skill-assist commands finding-select and finding-close
(skill_assist.py), which skill/implement-finding.ps1 runs around each fix session, one finding at a
time.

The skill decides whether a finding still holds and fixes it; this module decides nothing about the
code. It does the parts that must not rest on a model's word:

SELECT
    The first N findings files of the inbox (``*.md`` directly in the folder, by name).

CLOSE
    Deletes the finding file, but not while another findings file in the folder names it (deleting
    it would leave that pointer dangling). Given the fix session's stream log (``--session-log``,
    the ``.stream.jsonl`` a headless step writes), it also requires the session's last foreground
    ``test.ps1`` run to have passed: a fix with no passing test run is not proven, so the finding
    stays.

Exit codes (the skill-assist ones): 0 deleted (``select``: done); 1 the request is unusable (the
message says why); 2 not deleted -- the message names what is missing.
"""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass
from pathlib import Path

from common import EXIT_CHECK_FAILED, EXIT_FAILED, EXIT_OK, AssistError, read_text

LOG = logging.getLogger(__name__)

EXIT_DELETED = EXIT_OK
EXIT_UNUSABLE = EXIT_FAILED
EXIT_KEPT = EXIT_CHECK_FAILED

DEFAULT_COUNT = 10
FINDINGS_DIR_PARTS = ("reports", "finding")
SHELL_TOOLS = frozenset({"Bash", "PowerShell"})

_TEST_COMMAND = re.compile(r"(?<![\w-])test\.ps1", re.IGNORECASE)
_NOT_A_TEST_RUN = re.compile(r"-(?:ListTags|SelfTest)\b", re.IGNORECASE)
# test.ps1 prints "[FAIL] Tests failed for <pkg>" and "Failed: N"; pytest prints "N failed" / "N errors".
_FAILURE_TEXT = re.compile(r"\[FAIL\]|\bFailed: [1-9]|\b[1-9]\d* (?:failed|errors?)\b", re.IGNORECASE)
# A pipe hands the shell the exit code of the filter, not of test.ps1, so a piped run proves nothing.
_PIPE = re.compile(r"(?<!\|)\|(?!\|)")


@dataclass(frozen=True)
class TestRun:
    command: str
    passed: bool


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


def _blocks(event: dict[str, object], kind: str) -> list[dict[str, object]]:
    """The content blocks of type ``kind`` in one stream event's message."""
    message = event.get("message")
    content = message.get("content") if isinstance(message, dict) else None
    if not isinstance(content, list):
        return []
    return [block for block in content if isinstance(block, dict) and block.get("type") == kind]


def _result_text(block: dict[str, object]) -> str:
    content = block.get("content")
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return "\n".join(str(part.get("text", "")) for part in content if isinstance(part, dict))
    return ""


def _test_command(block: dict[str, object]) -> str:
    """The command of a foreground shell call that runs tests; empty for any other tool call."""
    tool_input = block.get("input")
    if block.get("name") not in SHELL_TOOLS or not isinstance(tool_input, dict):
        return ""
    command = str(tool_input.get("command", ""))
    if tool_input.get("run_in_background") or not _TEST_COMMAND.search(command) or _NOT_A_TEST_RUN.search(command):
        return ""
    return command


def test_runs(session_log: Path) -> list[TestRun]:
    """Every foreground ``test.ps1`` run in a step's stream log, in order, with whether it passed.

    A run passed when its command pipes nothing, its tool result is not an error (a non-zero exit),
    and its output reports no failed or erroring test.
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
        for block in _blocks(event, "tool_use"):
            command = _test_command(block)
            if command:
                pending[str(block.get("id"))] = command
        for block in _blocks(event, "tool_result"):
            command = pending.pop(str(block.get("tool_use_id")), "")
            if command:
                passed = (not block.get("is_error") and not _PIPE.search(command)
                          and not _FAILURE_TEXT.search(_result_text(block)))
                runs.append(TestRun(command, passed))
    return runs


def close_finding(finding: Path, session_log: Path | None) -> tuple[str, int]:
    """Delete ``finding`` when nothing still names it and, given a session log, its last test run passed."""
    if not finding.is_file():
        return f"Finding '{finding}' does not exist. Pass an existing findings file.", EXIT_UNUSABLE
    reasons = [f"{name} still names it: remove that pointer first" for name in referrers(finding)]
    if session_log is not None:
        runs = test_runs(session_log)
        if not runs:
            reasons.append("the fix session ran no foreground test.ps1, so the fix is not proven")
        elif not runs[-1].passed:
            reasons.append(f"the fix session's last test run failed: {runs[-1].command}")
    if reasons:
        return "\n".join([f"Not deleted: {finding}", *(f"  - {reason}" for reason in reasons)]), EXIT_KEPT
    finding.unlink()
    LOG.info("Deleted finding %s", finding)
    return f"Deleted: {finding}", EXIT_DELETED
