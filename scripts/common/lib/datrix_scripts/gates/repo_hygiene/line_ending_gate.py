"""Line-ending gate: every framework repo normalizes text to LF, and none commits a CRLF line.

A repo with no ``.gitattributes`` rule leaves line endings to each machine's ``core.autocrlf``.
With ``core.autocrlf=false`` (this workspace's setting), a file an editor or a bulk edit rewrote
with CRLF line endings is committed as CRLF: the diff shows every line changed, ``git blame``
loses its history, and the same file differs byte-for-byte between checkouts. A package once had
forty-two modified files switched to CRLF in its working tree by one bulk edit, one commit away
from rewriting all of them.

Two facts per repo, both read from git, never from a hand-rolled attribute matcher:

1. ``policy`` -- ``git check-attr text eol`` on a probe path no per-extension rule names resolves
   to ``text: auto`` and ``eol: lf``: the catch-all ``* text=auto eol=lf`` rule is in force, so a
   CRLF working-tree file is normalized to LF when it is staged.
2. ``committed-crlf`` -- ``git ls-files --eol`` reports no tracked file whose index blob is
   ``i/crlf`` or ``i/mixed``: no CRLF line is already committed.

Every framework repo (the showcase repo and every ``datrix-*`` git checkout) is discovered from
disk, so a new package is checked the day it is cloned. A built-in non-vacuity self-test runs
before every scan: a scratch repo with no attributes and a CRLF file staged must report both
facts, a binary file carrying CR LF bytes must not be reported, and the same files staged under
the catch-all rule must report nothing.

Run it through ``gates/repo-hygiene/line-ending-gate.ps1`` or its ``.sh`` twin; it runs in gate mode
(``datrix_scripts.gate_log.run_as_gate``) and prints the
``[GATE] line-ending PASSED|FAILED exit=<n> log=<path>`` verdict last.

Exit codes: 0 = every scanned repo holds both facts (or the self-test passed); 1 = a violation, or
the self-test failed; 2 = a usage error (unknown ``--repo`` name, no framework repo found) or a
failing git command.
"""

from __future__ import annotations

import argparse
import logging
import subprocess
import sys
import tempfile
from collections.abc import Sequence
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from typing import Final

from datrix_scripts.dev.arguments import comma_values
from datrix_scripts.framework_repos import select_framework_repos
from datrix_scripts.gate_harness import (
    EXIT_PASS,
    EXIT_USAGE,
    EXIT_VIOLATION,
    WRAPPER_DEBUG_FLAG,
    print_command,
    report_condition,
    report_fail,
    report_ok,
    write_file,
)
from datrix_scripts.gate_log import gate_child, run_as_gate
from datrix_scripts.paths import TMP_DIR, WORKSPACE_DIR
from datrix_scripts.test import wrappers

logger = logging.getLogger(__name__)

GATE: Final = "line-ending"
MODULE: Final = "datrix_scripts.gates.repo_hygiene.line_ending_gate"
WRAPPER: Final = "line-ending-gate"

#: A path no per-extension attribute line names, so only the catch-all ``*`` rule decides it.
PROBE_PATH: Final = "line-ending-probe.no-registered-extension"
REQUIRED_TEXT: Final = "auto"
REQUIRED_EOL: Final = "lf"
CATCH_ALL_RULE: Final = "* text=auto eol=lf"
#: ``git ls-files --eol`` index states that mean a CRLF line is committed.
COMMITTED_CRLF_STATES: Final = frozenset({"i/crlf", "i/mixed"})
_ATTRIBUTES_FILE: Final = ".gitattributes"
_PROBED_ATTRIBUTES: Final = ("text", "eol")
_SELF_TEST_PREFIX: Final = "line-endings-self-test-"
_CRLF_TEXT: Final = "first line\r\nsecond line\r\n"
_CRLF_BINARY: Final = b"\x00\x01binary\r\n\x00\r\n"


class LineEndingGateError(Exception):
    """A git command the gate depends on failed, so no verdict can be given."""


class Rule(StrEnum):
    POLICY = "policy"
    COMMITTED_CRLF = "committed-crlf"


@dataclass(frozen=True)
class Violation:
    """One line-ending fact that does not hold in one repo."""

    repo: str
    rule: Rule
    #: The path the fact was read on: the tracked file, or :data:`PROBE_PATH` for the policy.
    path: str
    detail: str

    def render(self) -> str:
        return f"{self.repo}: [{self.rule}] {self.path}: {self.detail}"


def _git(repo: Path, args: Sequence[str]) -> bytes:
    """Run a git command in *repo* with ``core.autocrlf`` pinned off; return raw stdout."""
    result = subprocess.run(
        ["git", "-C", str(repo), "-c", "core.autocrlf=false", *args],
        capture_output=True,
        check=False,
    )
    if result.returncode != 0:
        detail = (result.stderr or result.stdout).decode("utf-8", errors="replace").strip()
        raise LineEndingGateError(
            f"git {' '.join(args)} failed in {repo} (exit {result.returncode}): {detail}. "
            "Expected a readable git checkout. Fix: repair the repository or pass -Repo to "
            "scan the others."
        )
    return result.stdout


def _probe_attributes(repo: Path) -> dict[str, str]:
    """The ``text`` and ``eol`` attribute values git resolves for :data:`PROBE_PATH`."""
    raw = _git(repo, ["check-attr", "-z", *_PROBED_ATTRIBUTES, "--", PROBE_PATH])
    fields = raw.decode("utf-8", errors="surrogateescape").split("\0")
    # -z output is a flat sequence of (path, attribute, value) triples.
    attributes = {fields[index + 1]: fields[index + 2] for index in range(0, len(fields) - 2, 3)}
    missing = sorted(set(_PROBED_ATTRIBUTES) - attributes.keys())
    if missing:
        raise LineEndingGateError(
            f"git check-attr in {repo} reported no value for {', '.join(missing)} "
            f"(output {raw!r}). Expected one value per requested attribute. Fix: check the "
            "installed git version supports 'check-attr -z'."
        )
    return attributes


def policy_violations(repo: Path) -> list[Violation]:
    """A violation unless the catch-all LF rule decides a path no other rule names."""
    attributes = _probe_attributes(repo)
    text, eol = attributes["text"], attributes["eol"]
    if text == REQUIRED_TEXT and eol == REQUIRED_EOL:
        return []
    return [
        Violation(
            repo=repo.name,
            rule=Rule.POLICY,
            path=PROBE_PATH,
            detail=(
                f"a path no per-extension rule names resolves to text={text}, eol={eol}; "
                f"expected text={REQUIRED_TEXT}, eol={REQUIRED_EOL}. Fix: add the line "
                f"'{CATCH_ALL_RULE}' to {_ATTRIBUTES_FILE} at the repo root."
            ),
        )
    ]


def committed_crlf_violations(repo: Path) -> list[Violation]:
    """One violation per tracked file whose index blob holds a CRLF line."""
    raw = _git(repo, ["ls-files", "--eol", "-z"])
    violations: list[Violation] = []
    for entry in raw.decode("utf-8", errors="surrogateescape").split("\0"):
        if "\t" not in entry:
            continue
        states, path = entry.split("\t", 1)
        index_state = states.split()[0]
        if index_state in COMMITTED_CRLF_STATES:
            violations.append(
                Violation(
                    repo=repo.name,
                    rule=Rule.COMMITTED_CRLF,
                    path=path,
                    detail=(
                        f"committed with {index_state.removeprefix('i/')} line endings; "
                        "expected LF. Fix: with the catch-all rule in place, run "
                        f"'git add --renormalize -- {path}' and commit."
                    ),
                )
            )
    return violations


def scan_repo(repo: Path) -> list[Violation]:
    """Every line-ending violation in one repo."""
    return [*policy_violations(repo), *committed_crlf_violations(repo)]


def _plant_scratch_repo(root: Path, attributes: str | None) -> Path:
    """A scratch git repo with a CRLF text file and a CR LF-bearing binary file staged."""
    _git(root, ["init", "-q"])
    if attributes is not None:
        write_file(root / _ATTRIBUTES_FILE, attributes)
    (root / "notes.txt").write_bytes(_CRLF_TEXT.encode("utf-8"))
    (root / "image.bin").write_bytes(_CRLF_BINARY)
    _git(root, ["add", "--all"])
    return root


def run_planted_repos() -> bool:
    """Non-vacuity: both rules fire on an unprotected repo and neither fires under the rule."""
    print("=== Line-ending self-test: planted scratch repos ===")
    TMP_DIR.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(
        dir=TMP_DIR, prefix=_SELF_TEST_PREFIX, ignore_cleanup_errors=True
    ) as scratch:
        bare_root = Path(scratch) / "bare"
        guarded_root = Path(scratch) / "guarded"
        bare_root.mkdir()
        guarded_root.mkdir()
        bare = scan_repo(_plant_scratch_repo(bare_root, attributes=None))
        guarded = scan_repo(_plant_scratch_repo(guarded_root, attributes=f"{CATCH_ALL_RULE}\n"))
    found = sorted((violation.rule, violation.path) for violation in bare)
    expected = sorted([(Rule.POLICY, PROBE_PATH), (Rule.COMMITTED_CRLF, "notes.txt")])
    passed = report_condition(
        found == expected,
        "a repo with no attributes reports the policy and the staged CRLF text file only",
        f"got {[violation.render() for violation in bare]}",
    )
    return report_condition(
        not guarded,
        f"the same files staged under '{CATCH_ALL_RULE}' report nothing",
        f"got {[violation.render() for violation in guarded]}",
    ) and passed


def _check_planted_repos_report_exactly_their_defects() -> None:
    assert run_planted_repos(), "the planted scratch repos did not report exactly their defects"


def _run_scan(wanted: list[str] | None) -> int:
    try:
        repos = select_framework_repos(WORKSPACE_DIR, wanted)
    except ValueError as error:
        print(f"ERROR: {error}", file=sys.stderr)
        return EXIT_USAGE
    if not repos:
        print(f"ERROR: no framework repo found under {WORKSPACE_DIR}.", file=sys.stderr)
        return EXIT_USAGE
    violations = [violation for repo in repos for violation in scan_repo(repo)]
    for violation in violations:
        report_fail(violation.render())
    if violations:
        report_fail(f"{len(violations)} line-ending violation(s) across {len(repos)} repo(s).")
        return EXIT_VIOLATION
    report_ok(f"every one of {len(repos)} repo(s) normalizes text to LF and commits no CRLF line.")
    return EXIT_PASS


def build_parser() -> argparse.ArgumentParser:
    """The options of ``gates/repo-hygiene/line-ending-gate.ps1``: one per wrapper parameter, spelled exactly."""
    parser = argparse.ArgumentParser(
        prog=WRAPPER,
        description="Every framework repo normalizes text to LF and commits no CRLF line.",
        allow_abbrev=False,
    )
    parser.add_argument(
        "--repo",
        action="append",
        default=None,
        help="Limit the scan to this repo name (repeatable or comma-separated). Default: every framework repo.",
    )
    parser.add_argument(
        "--self-test", action="store_true", help="Run only the planted scratch repos and the wrapper seam checks."
    )
    parser.add_argument(
        WRAPPER_DEBUG_FLAG, dest="debug", action="store_true", help="Log at DEBUG level and print the command first."
    )
    return parser


def _run(args: argparse.Namespace) -> int:
    if args.debug:
        print_command()
    try:
        if args.self_test:
            return wrappers.run_self_test(
                [_check_planted_repos_report_exactly_their_defects],
                wrapper=WRAPPER, module=MODULE, parser=build_parser(), folder=wrappers.REPO_HYGIENE_GATES_DIR,
            )
        if not run_planted_repos():
            report_fail("line-ending self-test failed; the scan cannot be trusted.")
            return EXIT_VIOLATION
        return _run_scan(None if args.repo is None else comma_values(args.repo))
    except LineEndingGateError as error:
        print(f"ERROR: {error}", file=sys.stderr)
        return EXIT_USAGE


def main(argv: Sequence[str] | None = None) -> int:
    """Entry point: the gate in gate mode (a claimed log and the verdict line)."""
    return run_as_gate(GATE, MODULE, gate_child(build_parser, _run), argv)


if __name__ == "__main__":
    sys.exit(main())
