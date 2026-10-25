r"""PreToolUse(Bash|PowerShell) hook: a test run is its own call, and it follows a probe.

Two defects cost whole suite runs and Jon's time:

1. A test run chained with edits, probes or reads in one command (`sed ...; probe; test.ps1`).
   When the run fails, the chained steps cannot be told apart from the run's own failure, and the
   run starts before the step before it is known good. A command that runs `test.ps1` /
   `test-single.ps1` / `test.sh` is that run and nothing else, apart from a leading `cd`, and
   output filters on its pipeline (`| tail`).

2. A test run that follows an edit of a fixture project (`tests/fixtures/[projects/]<name>/`
   `.dtrx` / `.dcfg`) with no `dev/probe-fixture.ps1` run since that edit. The probe analyzes the
   project in seconds and prints the real error; the suite run found the same error minutes
   later, one guess at a time (`_fixture_probe.py`).

Both are refused with what to do instead. A command that only names the runner (a read, an
`echo`, a `-ListTags` listing) runs no test and is never refused. Fails open.

Exit codes:
  0 - allow
  2 - block (stderr becomes feedback to Claude)
"""

from __future__ import annotations

import json
import sys

from _command_shape import invoked_scripts, leading_token
from _fixture_probe import PROBE_COMMAND, read_edits, unprobed
from _suite_invocation import invocation_tails, runs_no_test

_CHANGE_DIRECTORY: frozenset[str] = frozenset({"cd", "set-location", "pushd", "sl"})
_RUNNER_NAMES: frozenset[str] = frozenset({"test-single.ps1", "test-single.sh"})
_STATEMENT_SEPARATORS: frozenset[str] = frozenset({";", "\n"})
_QUOTES: frozenset[str] = frozenset({'"', "'"})


def statements(command: str) -> list[str]:
    """Split on `;`, newline, `&&` and `||` outside quotes; a single `|` stays inside its statement."""
    parts: list[str] = []
    current: list[str] = []
    quote = ""
    index = 0
    while index < len(command):
        char = command[index]
        pair = command[index : index + 2]
        if quote:
            quote = "" if char == quote else quote
            current.append(char)
        elif char in _QUOTES:
            quote = char
            current.append(char)
        elif char in _STATEMENT_SEPARATORS or pair in ("&&", "||"):
            parts.append("".join(current))
            current = []
            index += 1 if char in _STATEMENT_SEPARATORS else 2
            continue
        else:
            current.append(char)
        index += 1
    parts.append("".join(current))
    return [part for part in parts if part.strip()]


def runs_a_test(command: str) -> bool:
    """True when the command executes a test runner that starts tests."""
    if any(not runs_no_test(tail) for tail in invocation_tails(command)):
        return True
    return any(script.path.rsplit("/", 1)[-1].lower() in _RUNNER_NAMES for script in invoked_scripts(command))


def other_work(command: str) -> list[str]:
    """The statements of a test-run command that are neither the run nor a leading `cd`."""
    work = [part.strip() for part in statements(command) if leading_token(part) not in _CHANGE_DIRECTORY]
    return [part for part in work if not runs_a_test(part)]


def _block(reason: str) -> None:
    sys.stderr.write(f"BLOCKED: {reason}\n")
    sys.exit(2)


def main() -> None:
    try:
        data = json.loads(sys.stdin.read())
    except json.JSONDecodeError:
        sys.exit(0)
    if data.get("tool_name") not in ("Bash", "PowerShell"):
        sys.exit(0)
    command = data.get("tool_input", {}).get("command", "")
    if not isinstance(command, str) or not command or not runs_a_test(command):
        sys.exit(0)

    extra = other_work(command)
    if extra:
        shown = "; ".join(part[:80] for part in extra[:3])
        _block(
            "a test run is its own call. This command also runs: "
            f"{shown}. Run those first, in their own calls, read what they print, and then run "
            "the tests alone (a leading `cd` and an output filter on the run's pipeline are fine)."
        )

    stale = unprobed(read_edits(str(data.get("session_id") or ""))["projects"])
    if stale:
        listed = "\n".join(f"  - {directory}" for directory in stale)
        _block(
            "fixture projects edited in this session were not probed since their last edit:\n"
            f"{listed}\nProbe each one and read what it prints before the suite run:\n  {PROBE_COMMAND}"
        )
    sys.exit(0)


if __name__ == "__main__":
    try:
        main()
    except SystemExit:
        raise
    except Exception:  # noqa: BLE001 - a guard must never wedge a session
        sys.exit(0)
