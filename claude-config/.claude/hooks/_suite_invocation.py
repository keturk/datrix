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
narrowed to named tests or feature tags, whether it runs no test at all (a
self-test or a tag listing), and which packages a whole-suite tail would run. It
never decides whether that is ALLOWED -- the block/audit policy stays in
`guard-full-suite-runs.py`, and the census/report policy stays in
`instruction_surface.py`. Splitting it this way is what lets two very different
enforcement points (a live PreToolUse block; a static markdown census) share one
fact without sharing a policy.
"""

from __future__ import annotations

import re
from typing import Final

from _command_shape import is_read_only, segments

#: `test.ps1` OR `affected-gate.ps1`, as their own path segment (or bare, or
#: right after a quote), so `test-single.ps1`, `test-specific-selection-gate.ps1`,
#: `affected-set.ps1` and any other `*.ps1` merely CONTAINING "test" never match.
#: `affected-gate.ps1` schedules whole-suite `test.ps1 <pkg>` children
#: concurrently -- a second door onto the same whole-suite act as a bare
#: `test.ps1` run, and blocked under the identical rule.
TEST_SCRIPT_RE: Final = re.compile(
    r"""(?:^|[/\\"'\s])(?:test|affected-gate)\.ps1\b""", re.IGNORECASE
)

#: The flags that make a `test.ps1` tail genuinely targeted: named files/node-IDs
#: (`-Specific`), a keyword expression (`-Keyword`), or feature tags (`-Tag`).
#: `affected-gate.ps1`'s own argument grammar carries none of them under any
#: spelling, so an affected-gate tail can never look targeted by accident.
NARROWING_FLAGS: Final = ("-specific", "-keyword", "-tag")

#: Flags that widen a run back to whole package suites whatever else narrows it:
#: `-All` names every package, `-Rerun` re-runs whole failing packages.
WIDENING_FLAGS: Final = ("-all", "-rerun")

#: Flags under which the runner starts no test at all: `affected-gate.ps1
#: -SelfTest` runs the scheduler's own pure-function self-test, and `test.ps1
#: -ListTags` only collects and prints feature tags. Checked before targeting and
#: package extraction, so such an invocation is never classified whole-suite.
NO_TEST_FLAG_RE: Final = re.compile(r"(?:^|\s)-(?:selftest|listtags)\b", re.IGNORECASE)

#: Stands in for the package list when `-All` was passed.
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


def runs_no_test(tail: str) -> bool:
    """True when this invocation starts no test at all (`-SelfTest`, `-ListTags`)."""
    return bool(NO_TEST_FLAG_RE.search(tail))


def _has_flag(lowered_tail: str, flag: str) -> bool:
    return re.search(rf"(?:^|\s){re.escape(flag)}\b", lowered_tail) is not None


def is_targeted(tail: str) -> bool:
    """True when `tail` narrows to named tests or tags and nothing widens it back.

    `-Specific`, `-Keyword` or `-Tag` narrows; `-All` or `-Rerun` alongside any
    of them still sweeps whole packages, so it is never targeted.
    """
    lowered = tail.lower()
    if any(_has_flag(lowered, flag) for flag in WIDENING_FLAGS):
        return False
    return any(_has_flag(lowered, flag) for flag in NARROWING_FLAGS)


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
