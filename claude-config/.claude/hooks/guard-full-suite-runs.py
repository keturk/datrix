"""PreToolUse(Bash|PowerShell) hook: no agent ever runs a whole test suite.

THE RULE
--------
Agents run only the tests related to the code they changed -- named test files,
a keyword, or the feature tags those tests carry. A whole package suite is never
an agent's act: not inside a fix, not at a wave boundary, not at a phase
boundary, not as a "quality gate". There is no override, no ticket, and no
exemption for the main session. Jon runs full suites himself, in his own
terminal, where no hook applies.

An invocation is a statement that EXECUTES the runner, as
`_command_shape.invoked_scripts` reads it; its flags are that statement's
arguments. A command that only names `test.ps1` -- a read of the script, a
`python -c` source string, an `echo`, a question or commit message handed to
another program -- runs no test and is never refused.

A `test.ps1` invocation is TARGETED (allowed) when it carries `-Specific`,
`-Keyword`, or `-Tag` and neither `-All` nor `-Rerun` -- and is not a SWEEP
assembled from those flags: a `-Tag` list longer than `MAX_TAGS_PER_RUN`, or a
`-Keyword` across more than one package, is blocked as a sweep. (The runner
itself also refuses a tag or keyword selection above a fixed share of a
package's test tree -- `datrix_common.testing.feature_tags`.) Everything else is a
whole-suite run: a bare package name, several package names, `-All`, `-Rerun`,
or a tier sweep (`-Unit` / `-Integration` / `-E2E` / `-Fast` / `-Slow`).
`affected-gate.ps1` schedules whole-suite `test.ps1` children, so every
invocation of it is a whole-suite run too. The only shapes that start no test at
all -- `affected-gate.ps1 -SelfTest` and `test.ps1 -ListTags` -- are allowed.
`test.sh`, the runner's POSIX twin (`bash test.sh <pkg> --tag x`, `./test.sh`), and
the modules behind both (`python -m datrix_scripts.test.test`) are classified by the
same rules over their `--kebab` flags. `coverage` and `test-gen` (wrapper, twin or
module) run each named package's whole suite unless given `-SelfTest`, and
`error-messages` does with `-Test`; each is refused under the same rule.

A flag word that is an abbreviation of a flag the guard reads (`-Al`, `-Ta`, `--li`)
is refused with the full spelling: the shell binds it to whichever parameter it
prefixes, so the guard never guesses. `-SelfTest:$false` turns the switch off and is
read as no self-test at all.

The runner table and the classification live in the sibling `_suite_invocation.py`
(`RUNNERS`, `refusal`), shared with the instruction-surface census that keeps
agent-facing documents from prescribing a whole-suite form.

WHY A HARD BLOCK
----------------
Whole suites cost tens of minutes each (the installable packages sum to over an
hour sequentially) and were bought as reassurance, as a discovery mechanism
mid-task, and as a per-wave "gate" -- after a written rule, a per-dispatch
reminder, and a main-session ticket each failed to stop it. A test related to
the change answers the question the change raises; a sweep answers questions
nobody asked, at N times the cost.

`test-single.ps1` is inherently single and is never touched. So is every other
`*.ps1` whose name merely contains "test".

Every blocked attempt is appended to d:/datrix/.tmp/full-suite-audit.jsonl, so
the count is a fact Jon can read rather than something to notice in a transcript.

Exit codes:
  0 -- allow
  2 -- block (stderr becomes feedback to Claude)
"""

import json
import sys
import time
from typing import Final

from _hook_log import append_record
from _suite_invocation import (
    REFUSE_ABBREVIATION,
    REFUSE_SWEEP,
    REFUSE_WHOLE_SUITE,
    invocations,
    refusal,
)

_SCRATCH_DIR: Final = "d:/datrix/.tmp"
_AUDIT_PATH: Final = f"{_SCRATCH_DIR}/full-suite-audit.jsonl"


def _block_abbreviations(words: list[str]) -> None:
    sys.stderr.write(
        "BLOCKED: a test-runner flag is abbreviated: " + ", ".join(words) + ".\n"
        "The shell binds a shortened flag to whichever parameter it prefixes, so no guard can tell "
        "what it runs. Write every flag in full."
    )
    sys.exit(2)


def _block_sweep(reasons: list[str]) -> None:
    sys.stderr.write(
        "BLOCKED: this test run is a sweep assembled from targeting flags.\n"
        + "".join(f"  - {reason}\n" for reason in reasons)
        + "Run -Specific on the files you changed and -Tag for the behaviour you changed, only in "
        "packages it reaches. Several smaller runs adding up to a sweep are the same violation."
    )
    sys.exit(2)


def _audit(record: dict[str, object]) -> None:
    """Append the blocked attempt. The count of attempts must be a readable fact.

    Capped like every hook log (``_hook_log.py``); a lost line is reported on stderr and
    never stops the block that follows."""
    append_record(_AUDIT_PATH, record, "guard-full-suite-runs")


def _block(packages_named: list[str]) -> None:
    named = ", ".join(packages_named)
    sys.stderr.write(
        f"BLOCKED: whole test suite requested ({named}); agents never run one, no override.\n"
        "Run the tests of what you changed, in every package it reaches:\n"
        '  test.ps1 <pkg-a> <pkg-b> -Tag <tag>   |   test.ps1 <pkg> -Specific "tests/a.py,tests/b.py"\n'
        "  test.ps1 <pkg> -ListTags lists a package's tags. An untested behaviour needs a new tagged test."
    )
    sys.exit(2)


def main() -> None:
    try:
        data = json.loads(sys.stdin.read())
    except json.JSONDecodeError:
        sys.exit(0)

    if data.get("tool_name") not in ("Bash", "PowerShell"):
        sys.exit(0)

    command = data.get("tool_input", {}).get("command", "")
    if not isinstance(command, str) or not command:
        sys.exit(0)

    found: dict[str, list[str]] = {REFUSE_ABBREVIATION: [], REFUSE_SWEEP: [], REFUSE_WHOLE_SUITE: []}
    for run in invocations(command):
        refused = refusal(run)
        if refused is not None:
            found[refused.kind].extend(refused.details)
    whole_suite_packages = found[REFUSE_WHOLE_SUITE]
    sweep_reasons = found[REFUSE_SWEEP]

    if found[REFUSE_ABBREVIATION]:
        _block_abbreviations(found[REFUSE_ABBREVIATION])

    if sweep_reasons and not whole_suite_packages:
        _audit(
            {
                "ts": int(time.time()),
                "session_id": data.get("session_id", ""),
                "agent_id": data.get("agent_id", ""),
                "reasons": sweep_reasons,
                "command": command[:400],
                "decision": "block-sweep",
            }
        )
        _block_sweep(sweep_reasons)

    if not whole_suite_packages:
        sys.exit(0)

    _audit(
        {
            "ts": int(time.time()),
            "session_id": data.get("session_id", ""),
            "agent_id": data.get("agent_id", ""),
            "packages": whole_suite_packages,
            "command": command[:400],
            "decision": "block",
        }
    )
    _block(whole_suite_packages)


if __name__ == "__main__":
    main()
