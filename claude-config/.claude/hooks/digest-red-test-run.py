"""PostToolUse hook: after a red test, gate or generation run, attach a local model's digest of its log.

An agent whose run failed is told, by CLAUDE.md and every fix skill, not to read the run's log
whole. Nothing made it hold to that, and the local models were never asked. Now the run's own
result carries the answer, for three shapes of run:

* **Test.** A ``test.ps1`` / ``test-single.ps1`` run whose console output reports a package
  ``[FAILED]`` (or any status other than ``[PASSED]``) and names its ``Details: <run>\\index.json``:
  the digest is of that run's ``full.log``, with the pointers to the structured data the run saved
  (``failure-data.json`` via ``collect-failure-data.ps1``).
* **Gate.** A script run whose console holds a gate's verdict line
  ``[GATE] <name> FAILED exit=<n> log=<path>`` (printed by ``Write-DatrixGateVerdict`` /
  ``Invoke-DatrixPythonScript -Gate``): the digest is of ``<path>``.
* **Generation.** A ``dev/generate.ps1`` run whose "Generation Summary" reports ``Failed: N`` with
  N > 0 and whose console holds ``Log saved to: <path>`` (printed on every exit path): the digest
  is of ``<path>``.

A shape is recognised only from the scripts the command actually ran
(``_command_shape.invoked_scripts``), never from a script it merely names. A local model lists
the distinct failures in the log (``datrix_scripts.local_reading.digest_log``) and the list is
added to the tool result as ``additionalContext``. The digest is a lead, never a finding: it cites
log lines, and the agent confirms them.

Bounded and fail-open. It never runs on a green run, a log outside the read scope, a test run
whose folder holds ``test.ps1``'s own failure digest (``RUN_DIGEST_NAME`` -- the console output
already carries it), or more than ``MAX_RUNS`` logs per call across all shapes; the model requests
are capped by ``_local_digest``; and any failure -- no model server, an unreadable log, an import
error -- leaves the tool result exactly as it was. Every request is recorded in the local-model
usage log as ``hook:red-test-digest``.
"""

import json
import os
import re
import sys
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import TYPE_CHECKING, Final

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

if TYPE_CHECKING:
    from datrix_scripts.local_llm import LocalLlmSettings

from _command_shape import invoked_scripts  # noqa: E402
from _hook_log import add_scripts_lib_to_path  # noqa: E402
from _local_digest import default_settings, digest_of  # noqa: E402

_SHELL_TOOLS: Final = frozenset({"Bash", "PowerShell"})
_TEST_SCRIPTS: Final = frozenset({"test.ps1", "test-single.ps1"})
_GENERATE_SCRIPT: Final = "generate.ps1"
_GENERATE_SCRIPT_DIR: Final = "dev"
# A package block in test.ps1's console summary: "[FAILED] <package>" then "  Details: <run>\index.json".
_STATUS_LINE: Final = re.compile(r"^\[(?P<status>[A-Z_]+)\]\s+(?P<package>\S+)\s*$", re.MULTILINE)
_DETAILS_LINE: Final = re.compile(r"^\s*Details:\s+(?P<index>.+?[\\/]index\.json)\s*$", re.MULTILINE)
# The one verdict line a gate prints last (DatrixPythonScript.psm1, Write-DatrixGateVerdict).
GATE_FAILED_LINE: Final = re.compile(
    r"^\[GATE\]\s+(?P<gate>\S+)\s+FAILED\s+exit=(?P<exit>-?\d+)\s+log=(?P<log>.+?)\s*$", re.MULTILINE
)
# generate.ps1's summary block and the log line its finally block prints on every exit path.
_GENERATION_SUMMARY: Final = "Generation Summary"
_GENERATION_FAILED: Final = re.compile(r"^\s*Failed:\s+(?P<count>\d+)\s*$", re.MULTILINE)
_GENERATION_LOG: Final = re.compile(r"^Log saved to:\s+(?P<log>.+?)\s*$", re.MULTILINE)
_GREEN: Final = "PASSED"
_LOG_NAME: Final = "full.log"
_FAILURE_DATA_NAME: Final = "failure-data.json"
# test.ps1 prints run_digest.py's digest under its summary and saves it under this name in
# the run folder: a run that has one already carries its digest in the console output, so
# the hook asks no model for it again. Kept in step with run_digest.DIGEST_FILENAME by the
# hook's test, which imports both.
RUN_DIGEST_NAME: Final = "digest.txt"

MAX_RUNS: Final = 2
CALLER: Final = "hook:red-test-digest"
_WRITER: Final = "digest-red-test-run"


@dataclass(frozen=True)
class RedLog:
    """One failed run's log to digest: what failed, where its log is, and what to read next."""

    title: str
    log: Path
    pointer: str


def response_text(response: object) -> str:
    """Every string in a tool response: the console output, whatever shape the harness wraps it in."""
    if isinstance(response, str):
        return response
    if isinstance(response, dict):
        return "\n".join(text for text in map(response_text, response.values()) if text)
    if isinstance(response, list):
        return "\n".join(text for text in map(response_text, response) if text)
    return ""


def ran_scripts(command: str) -> list[PurePosixPath]:
    """The script files ``command`` executes (``invoked_scripts``), as paths."""
    return [PurePosixPath(script.path) for script in invoked_scripts(command)]


def red_runs(console: str) -> list[tuple[str, Path]]:
    """(package, run folder) for each package block whose status is not PASSED, in output order."""
    blocks = sorted([(m.start(), "status", m) for m in _STATUS_LINE.finditer(console)]
                    + [(m.start(), "details", m) for m in _DETAILS_LINE.finditer(console)], key=lambda b: b[0])
    runs: list[tuple[str, Path]] = []
    package, red = "", False
    for _, kind, match in blocks:
        if kind == "status":
            package, red = match.group("package"), match.group("status") != _GREEN
        elif red and package:
            runs.append((package, Path(match.group("index").strip()).parent))
            red = False
    return runs


def red_test_logs(console: str) -> list[RedLog]:
    """The ``full.log`` of each red ``test.ps1`` package block that test.ps1 did not digest itself."""
    logs: list[RedLog] = []
    for package, run in red_runs(console):
        if (run / RUN_DIGEST_NAME).is_file():
            continue
        structured = run / _FAILURE_DATA_NAME
        pointer = (f"Structured clusters and ready test commands: {structured}" if structured.is_file()
                   else f"Structured clusters: collect-failure-data.ps1 \"{run}\"")
        logs.append(RedLog(f"the failing run of {package}", run / _LOG_NAME,
                           f"{pointer}\nDo not read full.log whole."))
    return logs


def failed_gate_logs(console: str) -> list[RedLog]:
    """The log each ``[GATE] <name> FAILED exit=<n> log=<path>`` line names."""
    return [RedLog(f"the failing {match.group('gate')} gate run (exit {match.group('exit')})",
                   Path(match.group("log")), "Do not read the gate log whole.")
            for match in GATE_FAILED_LINE.finditer(console)]


def failed_generation_logs(console: str) -> list[RedLog]:
    """generate.ps1's log, when its last Generation Summary reports a failed project."""
    summary_at = console.rfind(_GENERATION_SUMMARY)
    if summary_at < 0:
        return []
    failed = _GENERATION_FAILED.search(console, summary_at)
    saved = list(_GENERATION_LOG.finditer(console))
    if failed is None or int(failed.group("count")) == 0 or not saved:
        return []
    return [RedLog(f"the generation run with {failed.group('count')} failed project(s)",
                   Path(saved[-1].group("log")), "Do not read the generation log whole.")]


def red_logs(scripts: list[PurePosixPath], console: str) -> list[RedLog]:
    """Every failed run's log ``console`` reports, for the shapes the scripts that ran can produce."""
    names = {script.name.lower() for script in scripts}
    logs: list[RedLog] = []
    if names & _TEST_SCRIPTS:
        logs += red_test_logs(console)
    if scripts:
        logs += failed_gate_logs(console)
    if any(script.name.lower() == _GENERATE_SCRIPT
           and script.parent.name.lower() in (_GENERATE_SCRIPT_DIR, "") for script in scripts):
        logs += failed_generation_logs(console)
    return logs


def context_for(logs: list[RedLog], workspace: Path, settings: "LocalLlmSettings") -> str:
    """The additionalContext for the failed runs' logs; empty when none is digestible."""
    sections: list[str] = []
    for red in logs[:MAX_RUNS]:
        text = digest_of(red.log, workspace, settings, _WRITER)
        if text:
            sections.append(f"Local-model digest of {red.title} ({red.log}):\n{text}\n{red.pointer}")
    return "\n\n".join(sections)


def main() -> None:
    try:
        data = json.loads(sys.stdin.read())
    except (json.JSONDecodeError, OSError):
        sys.exit(0)
    if not isinstance(data, dict) or str(data.get("tool_name", "")) not in _SHELL_TOOLS:
        sys.exit(0)
    tool_input = data.get("tool_input")
    command = str(tool_input.get("command", "")) if isinstance(tool_input, dict) else ""
    try:
        logs = red_logs(ran_scripts(command), response_text(data.get("tool_response")))
        if not logs:
            sys.exit(0)
        add_scripts_lib_to_path()
        from datrix_scripts.paths import WORKSPACE_DIR

        context = context_for(logs, WORKSPACE_DIR, default_settings(CALLER))
    except Exception as exc:  # a hook must never fail the tool call it observed
        sys.stderr.write(f"{_WRITER}: skipped: {type(exc).__name__}: {exc}\n")
        sys.exit(0)
    if context:
        print(json.dumps({"hookSpecificOutput": {"hookEventName": "PostToolUse", "additionalContext": context}}))
    sys.exit(0)


if __name__ == "__main__":
    main()
