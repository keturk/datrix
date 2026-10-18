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

Usage:
    python line_endings.py
    python line_endings.py --repo datrix-codegen-flutter
    python line_endings.py --self-test
    python line_endings.py --debug
"""

from __future__ import annotations

import logging
import subprocess
import sys
import tempfile
from collections.abc import Sequence
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from typing import Final

from datrix_scripts.framework_repos import select_framework_repos
from datrix_scripts.gate_harness import (
    EXIT_PASS,
    EXIT_USAGE,
    EXIT_VIOLATION,
    configure_logging,
    gate_argument_parser,
    harness_self_test,
    report_condition,
    report_fail,
    report_ok,
    write_file,
)
from datrix_scripts.paths import TMP_DIR, WORKSPACE_DIR

logger = logging.getLogger(__name__)

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
            "Expected a readable git checkout. Fix: repair the repository or pass --repo to "
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


def run_self_test() -> bool:
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


def main(argv: Sequence[str] | None = None) -> int:
    parser = gate_argument_parser(__doc__.split("\n", 1)[0])
    parser.add_argument("--repo", action="append", help="Limit the scan to these repo names.")
    args = parser.parse_args(argv)
    configure_logging(args.debug)
    if args.harness_self_test:
        return EXIT_PASS if harness_self_test() else EXIT_VIOLATION
    try:
        if not run_self_test():
            report_fail("line-ending self-test failed; the scan cannot be trusted.")
            return EXIT_VIOLATION
        if args.self_test:
            return EXIT_PASS
        return _run_scan(args.repo)
    except LineEndingGateError as error:
        print(f"ERROR: {error}", file=sys.stderr)
        return EXIT_USAGE


if __name__ == "__main__":
    sys.exit(main())
