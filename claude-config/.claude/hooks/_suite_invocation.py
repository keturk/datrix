"""Shared whole-suite invocation classifier for `guard-full-suite-runs.py` and
`instruction-surface-gate.ps1` (loaded by `datrix/scripts/library/test/instruction_surface.py`).

WHY THIS IS A SIBLING, NOT A LIBRARY MODULE
--------------------------------------------
Every hook runs as bare `python "<path>.py"` (`claude-config/.claude/settings.json`'s
`PreToolUse` entries), which resolves whatever interpreter is first on the system
`PATH` -- never the venv's `D:\\datrix\\.venv\\Scripts\\python.exe` that every
`datrix-*` package is installed into. A hook may therefore import only the
standard library and modules sitting beside it in this same `hooks/` directory
(the precedent: `_command_shape.py`, already imported this way by
`guard-full-suite-runs.py` and `validate-script-invocation.py`).

`instruction-surface-gate.ps1` is a `datrix/scripts/library/test/`
module running under the venv interpreter, and it needs this IDENTICAL
classification -- a whole-suite `test.ps1`/`affected-gate.ps1` form the census
finds must be the same set of commands the hook blocks, or the hook and the
gate could disagree about what a whole-suite invocation even is. Duplicating
the regex a second time is exactly the defect class this module exists to
close, so the gate loads THIS file by path with
`importlib.util.spec_from_file_location` rather than copying it -- the working
precedent for loading a hooks-directory module from a `datrix/scripts` script
is `datrix/scripts/library/test/ignored_source.py`'s `load_temp_dir_segment`
(lines 257-283), which loads `_repo_temp_dir_names.py` the same way for the
same reason (the guard that enforces a rule and the gate that audits it must
share one definition).

WHAT THIS ANSWERS, AND WHAT IT DOES NOT
-----------------------------------------
This module answers only "what does this command's test-runner invocation DO":
which script it names, what its argument tail looks like, whether that tail is
narrowed to named tests, whether it runs no suite child at all (a self-test),
and which packages a whole-suite tail would run. It never decides whether that
is ALLOWED -- the ticket/audit/block policy stays in `guard-full-suite-runs.py`,
and the census/report policy stays in `instruction_surface.py`. Splitting it
this way is what lets two very different enforcement points (a live PreToolUse
block; a static markdown census) share one fact without sharing a policy.
"""

from __future__ import annotations

import re
from typing import Final

from _command_shape import is_read_only, segments

#: `test.ps1` OR `affected-gate.ps1`, as their own path segment (or bare, or
#: right after a quote), so `test-single.ps1`, `test-specific-selection-gate.ps1`,
#: `affected-set.ps1` and any other `*.ps1` merely CONTAINING "test" never match.
#: `affected-gate.ps1` schedules `test.ps1 <pkg>` children concurrently under a
#: worker budget and derives its own reverse-dependency closure -- it is a
#: second door onto the same phase-boundary act as a bare `test.ps1` run:
#: before this module, the guard's pattern was `test\.ps1\b` alone, so every
#: affected-gate sweep ran with no ticket, no audit row, and no subagent block.
TEST_SCRIPT_RE: Final = re.compile(
    r"""(?:^|[/\\"'\s])(?:test|affected-gate)\.ps1\b""", re.IGNORECASE
)

#: The only two flags that make a `test.ps1` tail genuinely targeted -- they
#: select named files/node-IDs. `affected-gate.ps1`'s own argument grammar
#: (`affected_gate.py:_parse_args` -- `--projects`, `--all`, `--max-concurrent`,
#: `--workers-per-child`, `--mypy`, `--force`, `--no-carry`, `--output`,
#: `--self-test`, `--debug`) carries neither flag under any spelling, so an affected-gate tail
#: is correctly classified whole-suite by this check alone -- it can never look
#: targeted by accident, and no affected-gate-specific carve-out is needed here.
NARROWING_FLAGS: Final = ("-specific", "-keyword")

#: `affected-gate.ps1 -SelfTest` (`--self-test` on `affected_gate.py`) runs the
#: scheduler's own pure-function self-test suite and launches no `test.ps1`
#: child at all. Checked before targeting/package extraction so a self-test
#: invocation is never even classified as whole-suite -- the same treatment a
#: read-only inspection gets, and required so the guard does not demand a
#: ticket for a command that runs no suite.
SELF_TEST_FLAG_RE: Final = re.compile(r"(?:^|\s)-selftest\b", re.IGNORECASE)

#: Stands in for the package list when `-All` was passed; only a `"*"` ticket
#: can ever cover it.
ALL_SENTINEL: Final = "*ALL-PACKAGES*"

_PACKAGE_RE: Final = re.compile(r"datrix(?:-[a-z0-9]+)*\Z")


def invocation_tails(command: str) -> list[str]:
    """One argument tail per `test.ps1`/`affected-gate.ps1` INVOCATION in `command`.

    Segment-wise, so that `test.ps1 A; affected-gate.ps1 -Projects B -SelfTest`
    cannot let B's self-test flag vouch for A's bare full-suite run, and so that
    an occurrence inside a read-only inspection (`grep -n affected-gate.ps1 ...`)
    is skipped entirely. Identical algorithm to the guard's original
    `_invocation_tails`; only the pattern it walks (`TEST_SCRIPT_RE`, above) grew
    a second alternative.
    """
    tails: list[str] = []
    for segment in segments(command):
        matches = list(TEST_SCRIPT_RE.finditer(segment))
        if not matches or is_read_only(segment):
            continue
        starts = [m.end() for m in matches]
        bounds = [m.start() for m in matches][1:] + [len(segment)]
        tails.extend(segment[start:end] for start, end in zip(starts, bounds))
    return tails


def is_self_test(tail: str) -> bool:
    """True when this invocation runs only a self-test -- no suite child at all."""
    return bool(SELF_TEST_FLAG_RE.search(tail))


def is_targeted(tail: str) -> bool:
    """True when `tail` narrows to named tests (`-Specific`/`-Keyword`)."""
    lowered = tail.lower()
    return any(re.search(rf"(?:^|\s){re.escape(flag)}\b", lowered) for flag in NARROWING_FLAGS)


def packages(tail: str) -> list[str]:
    """Package names this invocation would run whole suites for.

    Handles both `test.ps1 pkg-a pkg-b` (bare positional names) and
    `affected-gate.ps1 -Projects pkg-a,pkg-b` (a flagged, comma-joined list) with
    the SAME tokenizer: splitting on whitespace/comma/semicolon/pipe and keeping
    only tokens matching the `datrix(-...)*` package-name shape already drops
    the `-projects`/`-all` flag tokens themselves (they fail `_PACKAGE_RE`), so
    no `affected-gate`-specific parsing branch is needed.
    """
    lowered = tail.lower()
    if re.search(r"(?:^|\s)-all\b", lowered):
        return [ALL_SENTINEL]

    found: list[str] = []
    for raw in re.split(r"[\s,;|]+", tail):
        token = raw.strip("\"'()").rstrip("\\/").lstrip(".").lstrip("\\/").lower()
        if not token or "/" in token or "\\" in token:
            continue
        if _PACKAGE_RE.fullmatch(token):
            found.append(token)
    return found
