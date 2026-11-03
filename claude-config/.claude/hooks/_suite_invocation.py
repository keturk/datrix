"""Shared whole-suite invocation classifier for `guard-full-suite-runs.py` and
`instruction-surface-gate.ps1` (loaded by `datrix/scripts/common/lib/datrix_scripts/gates/repo_hygiene/instruction_surface_gate.py`).

WHY THIS IS A SIBLING, NOT A LIBRARY MODULE
--------------------------------------------
Every hook runs as bare `python "<path>.py"` (`claude-config/.claude/settings.json`'s
`PreToolUse` entries), which resolves whatever interpreter is first on the system
`PATH` -- never the venv's `D:\\datrix\\.venv\\Scripts\\python.exe` that every
`datrix-*` package is installed into. A hook may therefore import only the
standard library and modules sitting beside it in this same `hooks/` directory
(the precedent: `_command_shape.py`, already imported this way by
`guard-full-suite-runs.py` and `validate-script-invocation.py`).

`instruction-surface-gate.ps1` runs a `datrix_scripts.gates.repo_hygiene`
module under the venv interpreter, and it needs this IDENTICAL
classification -- a whole-suite form the census finds must be the same set of
commands the hook blocks, or the hook and the gate could disagree about what a
whole-suite invocation even is. Duplicating the rules a second time is exactly the
defect class this module exists to close, so the gate loads THIS file by path with
`importlib.util.spec_from_file_location` rather than copying it -- the working
precedent for loading a hooks-directory module from a `datrix/scripts` script
is `datrix/scripts/common/lib/datrix_scripts/ignored_source.py`'s `load_temp_dir_segment`, which loads `_repo_temp_dir_names.py` the same way for the
same reason (the guard that enforces a rule and the gate that audits it must
share one definition).

WHAT THIS ANSWERS, AND WHAT IT DOES NOT
-----------------------------------------
This module answers only "what does this command's suite-runner invocation DO":
which runner of `RUNNERS` the command executes (`_command_shape.invoked_scripts`,
so a command that merely names it is no invocation; a wrapper by file name, its
module by dotted name under `python -m`), what its argument tail looks like,
whether a flag word is an abbreviation of a guarded flag, whether the tail is
narrowed to named tests or feature tags, whether it runs no test at all (a
self-test or a tag listing), and which packages a whole-suite tail would run.
`refusal` turns that into the one verdict both callers apply. It never writes the
block message or the census report -- those stay in `guard-full-suite-runs.py` and
`instruction_surface_gate.py`.

THE FLAGS ARE READ AS THE RUNNER READS THEM
-------------------------------------------
PowerShell binds any unique prefix of a declared parameter (`-Al` is `-All`), and
argparse does the same for a parser built with `allow_abbrev` true. The guard never
guesses which parameter a shortened word would bind: a word that is a strict prefix
of a guarded flag of the runner's family, and not that flag, is refused with the full
spelling to use. A switch written `-Name:$false` (or `:0`) is off and is dropped from
the tail; `-Name:$true` is the plain switch; `-Name:value` is the parameter and its value.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Final

from _command_shape import VIA_PYTHON_MODULE, invoked_scripts

#: `test.ps1` and `affected-gate.ps1` (and their twins and modules): a run of
#: package suites unless narrowed by `-Specific` / `-Keyword` / `-Tag`.
#: `affected-gate` schedules whole-suite `test.ps1 <pkg>` children concurrently --
#: a second door onto the same whole-suite act, blocked under the identical rule.
FAMILY_TEST: Final = "test"
#: `coverage` and `test-gen`: each runs every named package's whole pytest suite
#: unless the tail runs no test (`-SelfTest`).
FAMILY_SUITE_METRICS: Final = "suite-metrics"
#: `error-messages`: runs package suites only with `-Test` (`--test`), after each fix.
FAMILY_ERROR_MESSAGES: Final = "error-messages"

#: Every runner that can start a package's whole test suite, by the name the command
#: executes it under: the wrapper's file name, its POSIX twin's, or the module run with
#: `python -m`. Compared with the whole file name, so `test-single.ps1`,
#: `test-specific-selection-gate.ps1`, `affected-set.ps1` and any other `*.ps1` merely
#: CONTAINING "test" never match.
RUNNERS: Final = {
    "test.ps1": FAMILY_TEST,
    "test.sh": FAMILY_TEST,
    "datrix_scripts.test.test": FAMILY_TEST,
    "datrix_scripts.test_project": FAMILY_TEST,
    "affected-gate.ps1": FAMILY_TEST,
    "affected-gate.sh": FAMILY_TEST,
    "datrix_scripts.test.affected_gate": FAMILY_TEST,
    "coverage.ps1": FAMILY_SUITE_METRICS,
    "coverage.sh": FAMILY_SUITE_METRICS,
    "datrix_scripts.metrics.coverage": FAMILY_SUITE_METRICS,
    "test-gen.ps1": FAMILY_SUITE_METRICS,
    "test-gen.sh": FAMILY_SUITE_METRICS,
    "datrix_scripts.metrics.test_gen": FAMILY_SUITE_METRICS,
    "error-messages.ps1": FAMILY_ERROR_MESSAGES,
    "error-messages.sh": FAMILY_ERROR_MESSAGES,
    "datrix_scripts.metrics.error_messages": FAMILY_ERROR_MESSAGES,
}

#: The flags of each family that a guard reads, as PowerShell parameter names
#: (lowercase). Their module spellings are the `--kebab-name` of each; `test_project`
#: names its tag flag `--tags`.
GUARDED_FLAGS: Final = {
    FAMILY_TEST: ("all", "rerun", "specific", "keyword", "tag", "selftest", "listtags", "nosave", "verboseoutput"),
    FAMILY_SUITE_METRICS: ("all", "selftest"),
    FAMILY_ERROR_MESSAGES: ("all", "test", "selftest"),
}
_KEBAB: Final = {
    "selftest": "self-test",
    "listtags": "list-tags",
    "nosave": "no-save",
    "verboseoutput": "verbose-output",
}
_EXTRA_KEBAB: Final = {FAMILY_TEST: ("tags",)}
#: PowerShell's common parameters, which every wrapper (`[CmdletBinding()]`) also declares. Written
#: in full, one binds itself, never a guarded flag it happens to begin (`-Verbose`, `-VerboseOutput`).
PS_COMMON_PARAMETERS: Final = frozenset({
    "verbose", "debug", "erroraction", "warningaction", "informationaction", "progressaction",
    "errorvariable", "warningvariable", "informationvariable", "outvariable", "outbuffer",
    "pipelinevariable",
})

#: The flags that make a `test` tail genuinely targeted: named files/node-IDs
#: (`-Specific`), a keyword expression (`-Keyword`), or feature tags (`-Tag`), and
#: their module spellings. `affected-gate`'s own argument grammar carries none of
#: them, so an affected-gate tail can never look targeted by accident.
NARROWING_FLAGS: Final = ("-specific", "-keyword", "-tag", "--specific", "--keyword", "--tag", "--tags")

#: Flags that widen a run back to whole package suites whatever else narrows it:
#: `-All` names every package, `-Rerun` re-runs whole failing packages.
WIDENING_FLAGS: Final = ("-all", "-rerun", "--all", "--rerun")

#: Flags under which the runner starts no test at all: a self-test, or `test.ps1
#: -ListTags` (`--list-tags`), which only collects and prints feature tags. The flag
#: word ends at whitespace or the end, so `-SelfTest:$false` (dropped by
#: `_normalised_args` before this is read) can never pass for one.
NO_TEST_FLAG_RE: Final = re.compile(
    r"(?:^|\s)(?:-(?:selftest|listtags)|\"?--(?:self-test|list-tags)\"?)(?=\s|$)", re.IGNORECASE
)

#: `error-messages`' switch that runs package suites after each fix.
_TEST_SWITCHES: Final = ("-test", "--test")

#: A `--kebab` flag word holding whitespace (`--specific="a.py b.py"` as one word)
#: is re-quoted whole by `_render_arguments`, so its matcher allows that opening
#: quote. A PowerShell `-Name` never does: quoted, it is a string, not a parameter.
_LONG_FLAG_PREFIX: Final = "--"

#: Stands in for the package list when `-All` was passed.
ALL_SENTINEL: Final = "*ALL-PACKAGES*"

_PACKAGE_RE: Final = re.compile(r"datrix(?:-[a-z0-9]+)*\Z")
_SWITCH_OFF: Final = frozenset({"$false", "0"})
_SWITCH_ON: Final = frozenset({"$true", "1"})
_PS_PARAMETER_RE: Final = re.compile(r"^-(?P<name>[A-Za-z][\w]*):(?P<value>.*)$")


@dataclass(frozen=True)
class Invocation:
    """One suite runner a command executes: its name as run, its family and its argument tail."""

    runner: str
    family: str
    args: tuple[str, ...]

    @property
    def tail(self) -> str:
        return _render_arguments(self.args)


def _normalised_args(args: tuple[str, ...]) -> tuple[str, ...]:
    """The arguments with `-Name:value` resolved as PowerShell binds it.

    `:$false`/`:0` turns a switch off (the word is dropped), `:$true`/`:1` is the plain
    switch, and any other value is the parameter followed by its value."""
    words: list[str] = []
    for word in args:
        bound = _PS_PARAMETER_RE.match(word)
        if bound is None:
            words.append(word)
            continue
        value = bound.group("value")
        if value.lower() in _SWITCH_OFF:
            continue
        words.append(f"-{bound.group('name')}")
        if value.lower() not in _SWITCH_ON:
            words.append(value)
    return tuple(words)


def _render_arguments(args: tuple[str, ...]) -> str:
    """The argument words as one tail, a word holding whitespace (or empty) re-quoted.

    `-Tag "a, b, c, d"` reaches here as the single word `a, b, c, d`; re-quoting it
    keeps it one value for `tag_names`, so the tag cap counts four tags, not one.
    """
    return " ".join(
        f'"{word}"' if not word or any(char.isspace() for char in word) else word
        for word in args
    )


def _runner_name(path: str, via: str) -> str:
    return path.lower() if via == VIA_PYTHON_MODULE else path.rsplit("/", 1)[-1].lower()


def invocations(command: str) -> list[Invocation]:
    """One `Invocation` per runner of `RUNNERS` the command EXECUTES.

    Decided by `_command_shape.invoked_scripts`, never by the runner's name
    appearing in the text: a read (`grep -n Unit .../test.ps1`), a `python -c`
    source string, an `echo`, a commit message or a question handed to another
    script names the runner and runs nothing, so it yields no invocation. Each
    carries the arguments of the one statement that runs the runner, so that
    `test.ps1 A; affected-gate.ps1 -Projects B -SelfTest` cannot let B's
    self-test flag vouch for A's bare full-suite run.
    """
    found: list[Invocation] = []
    for script in invoked_scripts(command):
        name = _runner_name(script.path, script.via)
        family = RUNNERS.get(name)
        if family is not None:
            found.append(Invocation(name, family, _normalised_args(script.args)))
    return found


def invocation_tails(command: str) -> list[str]:
    """The argument tail of every `test`-family runner the command executes."""
    return [run.tail for run in invocations(command) if run.family == FAMILY_TEST]


def _module_spellings(family: str) -> dict[str, str]:
    """Each guarded flag's module spelling (`selftest` -> `self-test`), with the family's extras."""
    spellings = {_KEBAB.get(name, name): name for name in GUARDED_FLAGS[family]}
    spellings.update({extra: extra for extra in _EXTRA_KEBAB.get(family, ())})
    return spellings


def abbreviated_flags(run: Invocation) -> list[str]:
    """`<written> (write <full>)` for every word that is a strict prefix of a guarded flag.

    A PowerShell `-Word` is compared with the PowerShell names, a `--word` with the module
    spellings; a word that IS a guarded flag (any case) is no abbreviation."""
    found: list[str] = []
    module_spellings = _module_spellings(run.family)
    for word in run.args:
        if word.startswith(_LONG_FLAG_PREFIX):
            name = word[2:].split("=", 1)[0].lower()
            full_names, prefix = tuple(module_spellings), _LONG_FLAG_PREFIX
        elif word.startswith("-") and len(word) > 1 and word[1].isalpha():
            name = word[1:].lower()
            full_names, prefix = GUARDED_FLAGS[run.family], "-"
            if name in PS_COMMON_PARAMETERS:
                continue
        else:
            continue
        if name in full_names:
            continue
        expansions = [full for full in full_names if full.startswith(name)]
        if expansions:
            found.append(f"{word} (write {' or '.join(prefix + full for full in expansions)})")
    return found


def runs_no_test(tail: str) -> bool:
    """True when this invocation starts no test at all (`-SelfTest`, `-ListTags`)."""
    return bool(NO_TEST_FLAG_RE.search(tail))


def _has_flag(lowered_tail: str, flag: str) -> bool:
    quote = '"?' if flag.startswith(_LONG_FLAG_PREFIX) else ""
    return re.search(rf"(?:^|\s){quote}{re.escape(flag)}(?=[\s=\"]|$)", lowered_tail) is not None


def is_targeted(tail: str) -> bool:
    """True when `tail` narrows to named tests or tags and nothing widens it back.

    `-Specific`, `-Keyword` or `-Tag` narrows; `-All` or `-Rerun` alongside any
    of them still sweeps whole packages, so it is never targeted.
    """
    lowered = tail.lower()
    if any(_has_flag(lowered, flag) for flag in WIDENING_FLAGS):
        return False
    return any(_has_flag(lowered, flag) for flag in NARROWING_FLAGS)


def starts_tests(run: Invocation) -> bool:
    """True when the invocation starts any test: every runner but a self-test or a tag
    listing, and `error-messages` only with `-Test`."""
    if runs_no_test(run.tail):
        return False
    if run.family == FAMILY_ERROR_MESSAGES:
        lowered = run.tail.lower()
        return any(_has_flag(lowered, flag) for flag in _TEST_SWITCHES)
    return True


#: A change touches one or two behaviours; a run naming more tags than this is a
#: sweep assembled from allowed flags. Lives here, not in the guard, so the
#: instruction-surface census flags exactly the forms the guard blocks.
MAX_TAGS_PER_RUN: Final = 3

#: A keyword selects by name fragment inside one package's tests; the same
#: fragment across packages selects whatever happens to match.
MAX_PACKAGES_PER_KEYWORD_RUN: Final = 1

_TAG_VALUE_RE: Final = re.compile(
    r"""(?:^|\s)(?:"""
    r"""-tag\s+(?:"([^"]*)"|'([^']*)'|(\S+))"""
    r"""|"--tags?=([^"]*)"|--tags?=(\S+)"""
    r"""|--tags?\s+(?:"([^"]*)"|'([^']*)'|(\S+)))""",
    re.IGNORECASE,
)


def tag_names(tail: str) -> list[str]:
    """The feature tags a `-Tag` (`--tag`, `--tags`) argument names (comma-separated, quoted or bare)."""
    names: list[str] = []
    for match in _TAG_VALUE_RE.finditer(tail):
        value = next(group for group in match.groups() if group is not None)
        names.extend(name.strip() for name in value.split(",") if name.strip())
    return names


def has_keyword(tail: str) -> bool:
    """True when the invocation selects by `-Keyword` (`--keyword`)."""
    lowered = tail.lower()
    return any(_has_flag(lowered, flag) for flag in ("-keyword", "--keyword"))


def packages(tail: str) -> list[str]:
    """Package names this invocation would run whole suites for.

    Handles both `test.ps1 pkg-a pkg-b` (bare positional names) and
    `affected-gate.ps1 -Projects pkg-a,pkg-b` (a flagged, comma-joined list) with
    the SAME tokenizer: splitting on whitespace/comma/semicolon/pipe and keeping
    only tokens matching the `datrix(-...)*` package-name shape already drops
    the `-projects`/`-all` flag tokens themselves (they fail `_PACKAGE_RE`), so
    no `affected-gate`-specific parsing branch is needed. `=` splits too, so the
    `--projects=pkg-a` a `test.sh` caller may write yields its package.
    """
    lowered = tail.lower()
    if any(_has_flag(lowered, flag) for flag in ("-all", "--all")):
        return [ALL_SENTINEL]

    found: list[str] = []
    for raw in re.split(r"[\s,;|=]+", tail):
        token = raw.strip("\"'()").rstrip("\\/").lstrip(".").lstrip("\\/").lower()
        if not token or "/" in token or "\\" in token:
            continue
        if _PACKAGE_RE.fullmatch(token):
            found.append(token)
    return found


def sweep_reason(tail: str) -> str | None:
    """Why a targeted-looking `test` tail is really a sweep, or None when it is not."""
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


REFUSE_ABBREVIATION: Final = "abbreviation"
REFUSE_SWEEP: Final = "sweep"
REFUSE_WHOLE_SUITE: Final = "whole-suite"


@dataclass(frozen=True)
class Refusal:
    """Why an invocation is refused: its kind and the detail the message names."""

    kind: str
    details: tuple[str, ...]


def refusal(run: Invocation) -> Refusal | None:
    """The one verdict on an invocation, shared by the guard and the census; None allows it.

    An abbreviated guarded flag is refused before anything is read from the tail. A run
    that starts no test is allowed. A `test`-family run narrowed to named tests or tags
    is allowed unless it is a sweep; every other run that starts tests is a whole-suite run.
    """
    abbreviations = abbreviated_flags(run)
    if abbreviations:
        return Refusal(REFUSE_ABBREVIATION, tuple(abbreviations))
    if not starts_tests(run):
        return None
    if run.family == FAMILY_TEST and is_targeted(run.tail):
        reason = sweep_reason(run.tail)
        return Refusal(REFUSE_SWEEP, (reason,)) if reason is not None else None
    return Refusal(REFUSE_WHOLE_SUITE, tuple(packages(run.tail) or [f"<unnamed {run.runner}>"]))
