"""PreToolUse(Bash|PowerShell) hook: no agent ever runs a whole test suite.

THE RULE
--------
Agents run only the tests related to the code they changed -- named test files,
a keyword, or the feature tags those tests carry. A whole package suite is never
an agent's act: not inside a fix, not at a wave boundary, not at a phase
boundary, not as a "quality gate". There is no override, no ticket, and no
exemption for the main session. Jon runs full suites himself, in his own
terminal, where no hook applies.

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
The classification lives in the sibling `_suite_invocation.py`, shared with the
instruction-surface census that keeps agent-facing documents from prescribing a
whole-suite form.

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
import os
import sys
import time
from typing import Final

from _suite_invocation import (
    MAX_PACKAGES_PER_KEYWORD_RUN,
    MAX_TAGS_PER_RUN,
    has_keyword,
    invocation_tails,
    is_targeted,
    packages,
    runs_no_test,
    tag_names,
)

_SCRATCH_DIR: Final = "d:/datrix/.tmp"
_AUDIT_PATH: Final = f"{_SCRATCH_DIR}/full-suite-audit.jsonl"


def _sweep_reason(tail: str) -> str | None:
    """Why a targeted-looking invocation is really a sweep, or None when it is not."""
    tags = tag_names(tail)
    if len(tags) > MAX_TAGS_PER_RUN:
        return (
            f"-Tag names {len(tags)} tags ({', '.join(tags)}); at most {MAX_TAGS_PER_RUN} per "
            "run. Name only the tags of the behaviour you changed."
        )
    if has_keyword(tail) and len(packages(tail)) > MAX_PACKAGES_PER_KEYWORD_RUN:
        return (
            f"-Keyword across {len(packages(tail))} packages; a keyword selects by name fragment "
            "inside ONE package. Across packages, use -Tag with the behaviour's tag."
        )
    return None


def _block_sweep(reasons: list[str]) -> None:
    sys.stderr.write(
        "BLOCKED: this test run is a sweep assembled from targeting flags.\n"
        + "".join(f"  - {reason}\n" for reason in reasons)
        + "\nA targeted flag is not permission to run broadly. Run the test files beside the "
        "code you changed (-Specific) and the one or two tags of the behaviour you changed "
        "(-Tag), only in packages that code reaches -- and no run at all when a static check "
        "(a grep, a read) already answered the question. Routing around this guard with other "
        "flags or several smaller runs is the same violation."
    )
    sys.exit(2)


def _audit(record: dict[str, object]) -> None:
    """Append the blocked attempt. The count of attempts must be a readable fact."""
    try:
        os.makedirs(_SCRATCH_DIR, exist_ok=True)
        with open(_AUDIT_PATH, "a", encoding="utf-8") as handle:
            handle.write(json.dumps(record) + "\n")
    except OSError:
        return


def _block(packages_named: list[str]) -> None:
    named = ", ".join(packages_named)
    sys.stderr.write(
        f"BLOCKED: whole test suite requested ({named}). Agents never run a whole suite -- "
        "not mid-task, not at a wave or phase boundary, not as a quality gate. There is no "
        "override.\n\n"
        "Run the tests related to the code you changed:\n"
        "  - by feature tag, across every package that carries it:\n"
        '      powershell -File "d:/datrix/datrix/scripts/test/test.ps1" datrix-codegen-python '
        "datrix-codegen-java -Tag gateway\n"
        '  - by file (comma-separated, one session):\n'
        '      powershell -File "d:/datrix/datrix/scripts/test/test.ps1" {package} '
        '-Specific "tests/unit/test_a.py,tests/unit/test_b.py"\n'
        "  - to find the tags a package carries (runs nothing):\n"
        '      powershell -File "d:/datrix/datrix/scripts/test/test.ps1" {package} -ListTags\n\n'
        "Pick tags from the behaviour you changed, and include every package whose code "
        "reaches it (a shared-layer change reaches its consumers: run their tests for that "
        "tag too). A behaviour no tagged test covers needs a new test -- write it, tag it, "
        "run it. A test proves the invariant forever; a sweep proves nothing about the "
        "question your change raised."
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

    whole_suite_packages: list[str] = []
    sweep_reasons: list[str] = []
    for tail in invocation_tails(command):
        if runs_no_test(tail):
            continue
        if is_targeted(tail):
            reason = _sweep_reason(tail)
            if reason is not None:
                sweep_reasons.append(reason)
            continue
        whole_suite_packages.extend(packages(tail) or ["<unnamed>"])

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
