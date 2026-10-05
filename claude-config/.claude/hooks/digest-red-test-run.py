"""PostToolUse hook: after a red test run, attach a local model's digest of its log.

An agent whose ``test.ps1`` run failed is told, by CLAUDE.md and every fix skill, not to read
``full.log`` and to run ``collect-failure-data.ps1``. Nothing made it do either, and the
local models were never asked. Now the run's own result carries the answer: when a ``test.ps1``
/ ``test-single.ps1`` run's console output reports a package ``[FAILED]`` (or any status other
than ``[PASSED]``) and names its ``Details: <run>\\index.json``, this hook has a local model
list the distinct failures in that run's ``full.log`` (``shared.local_reading.digest_log``) and
adds the list to the tool result as ``additionalContext``, with the pointers to the structured
data the run saved (``failure-data.json`` via ``collect-failure-data.ps1``).

The digest is a lead, never a finding: it cites log lines, and the agent confirms them.

Bounded and fail-open. It never runs on a green run, a run whose log is outside the read
scope, a run whose folder holds ``test.ps1``'s own failure digest (``RUN_DIGEST_NAME`` --
the console output already carries it), or more than ``MAX_RUNS`` runs per call; the model
requests are capped by
``_local_digest``; and any failure -- no model server, an
unreadable log, an import error -- leaves the tool result exactly as it was. Every request is
recorded in the local-model usage log as ``hook:red-test-digest``.
"""

import json
import os
import re
import sys
from pathlib import Path
from typing import TYPE_CHECKING, Final

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

if TYPE_CHECKING:
    from shared.local_llm import LocalLlmSettings

from _hook_log import LIBRARY_DIR  # noqa: E402
from _local_digest import default_settings, digest_of  # noqa: E402

_SHELL_TOOLS: Final = frozenset({"Bash", "PowerShell"})
_TEST_SCRIPT: Final = re.compile(r"\btest(?:-single)?\.ps1\b", re.IGNORECASE)
# A package block in test.ps1's console summary: "[FAILED] <package>" then "  Details: <run>\index.json".
_STATUS_LINE: Final = re.compile(r"^\[(?P<status>[A-Z_]+)\]\s+(?P<package>\S+)\s*$", re.MULTILINE)
_DETAILS_LINE: Final = re.compile(r"^\s*Details:\s+(?P<index>.+?[\\/]index\.json)\s*$", re.MULTILINE)
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


def response_text(response: object) -> str:
    """Every string in a tool response: the console output, whatever shape the harness wraps it in."""
    if isinstance(response, str):
        return response
    if isinstance(response, dict):
        return "\n".join(text for text in map(response_text, response.values()) if text)
    if isinstance(response, list):
        return "\n".join(text for text in map(response_text, response) if text)
    return ""


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


def context_for(console: str, workspace: Path, settings: "LocalLlmSettings") -> str:
    """The additionalContext for a ``test.ps1`` console output; empty when no run is red or digestible."""
    sections: list[str] = []
    undigested = [(package, run) for package, run in red_runs(console) if not (run / RUN_DIGEST_NAME).is_file()]
    for package, run in undigested[:MAX_RUNS]:
        text = digest_of(run / _LOG_NAME, workspace, settings, "digest-red-test-run")
        if not text:
            continue
        structured = run / _FAILURE_DATA_NAME
        pointer = (f"Structured clusters and ready test commands: {structured}" if structured.is_file()
                   else f"Structured clusters: collect-failure-data.ps1 \"{run}\"")
        sections.append(f"Local-model digest of the failing run of {package} ({run / _LOG_NAME}):\n{text}\n{pointer}\n"
                        f"Do not read full.log whole.")
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
    if not _TEST_SCRIPT.search(command):
        sys.exit(0)
    try:
        if LIBRARY_DIR not in sys.path:
            sys.path.insert(0, LIBRARY_DIR)
        from shared.venv import get_datrix_root

        context = context_for(response_text(data.get("tool_response")), get_datrix_root(),
                              default_settings(CALLER))
    except Exception as exc:  # a hook must never fail the tool call it observed
        sys.stderr.write(f"digest-red-test-run: skipped: {type(exc).__name__}: {exc}\n")
        sys.exit(0)
    if context:
        print(json.dumps({"hookSpecificOutput": {"hookEventName": "PostToolUse", "additionalContext": context}}))
    sys.exit(0)


if __name__ == "__main__":
    main()
