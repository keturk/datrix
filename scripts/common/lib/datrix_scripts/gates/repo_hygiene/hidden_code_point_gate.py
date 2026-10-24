"""Hidden-code-point gate: no generator source holds a code point a reader cannot see.

A generator's templates and modules are what every generated project is built from, so a code point
that renders as nothing -- a bidi control (Trojan Source, CVE-2021-42574), a zero-width character,
a non-ASCII space, a control -- written raw in one of them makes the source a reviewer reads differ
from the source a compiler reads, in the framework and in every project it emits. What counts as
hidden is ``datrix_common.utils.hidden_text.hidden_in_source``, the one set every escaper reads; this
gate holds the framework's own sources to it.

Every file a commit could publish under ``src/`` of every ``datrix-codegen-*`` git checkout (tracked
files and untracked files git does not ignore, listed by git) is read as UTF-8, and every code point
the predicate flags other than TAB, LF and CR is reported as ``<repo>/<path>:<line>:<column>:
U+HHHH``. Lines are counted on LF alone (U+0085, U+2028 and U+2029 are reported, never taken as line
breaks) and columns in code points, both from 1. A file that is not UTF-8 text cannot be judged, so
it is reported too. The repositories are discovered from disk, so a new generator package is checked
the day it is cloned.

A built-in non-vacuity self-test runs before every scan: every row of the shared hidden-text corpus
(``datrix_testing.hidden_text_corpus``) must be reported at the line and column of each of its hidden
code points, TAB, LF and CR must pass, and planted files (one carrying a hidden code point, one not
UTF-8, one clean) must report exactly the first two.

Run it through ``gates/repo-hygiene/hidden-code-point-gate.ps1`` or its ``.sh`` twin; it runs in gate
mode (``datrix_scripts.gate_log.run_as_gate``) and prints the
``[GATE] hidden-code-point PASSED|FAILED exit=<n> log=<path>`` verdict last.

Exit codes: 0 = no hidden code point (or the self-test passed); 1 = a hidden code point, a file that
is not UTF-8, a failed self-test, or package installs that are not current; 2 = a usage error
(unknown ``--repo`` name, no generator repo found) or a failing git command or file read.
"""

from __future__ import annotations

import argparse
import subprocess
import sys
import tempfile
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Final

from datrix_scripts.dev.arguments import comma_values
from datrix_scripts.framework_repos import PackageMarker, workspace_package_dirs
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
from datrix_scripts.gates.repo_hygiene.gate_options import packages_current
from datrix_scripts.paths import TMP_DIR, WORKSPACE_DIR
from datrix_scripts.test import wrappers

GATE: Final = "hidden-code-point"
MODULE: Final = "datrix_scripts.gates.repo_hygiene.hidden_code_point_gate"
WRAPPER: Final = "hidden-code-point-gate"

#: The directory-name prefix of a generator package; the packages themselves are found on disk.
GENERATOR_REPO_PREFIX: Final = "datrix-codegen-"
SOURCE_DIR: Final = "src"
#: The controls a source file's own line structure is made of: flagged by the predicate, allowed here.
LINE_STRUCTURE: Final = frozenset({"\t", "\n", "\r"})
_LINE_BREAK: Final = "\n"
_LINE_BREAK_BYTE: Final = b"\n"
_SELF_TEST_PREFIX: Final = "hidden-code-point-self-test-"

#: Whether one code point is hidden in source.
HiddenPredicate = Callable[[str], bool]


class HiddenCodePointGateError(Exception):
    """A git command or a file read the gate depends on failed, so no verdict can be given."""


@dataclass(frozen=True)
class Finding:
    """One position in one source file that a reader cannot see, or a file that cannot be read as text."""

    path: str
    line: int
    column: int
    detail: str

    def render(self) -> str:
        return f"{self.path}:{self.line}:{self.column}: {self.detail}"


def code_point_label(char: str) -> str:
    """``U+HHHH`` for *char* (at least four hex digits)."""
    return f"U+{ord(char):04X}"


def scan_text(text: str, path: str, hidden: HiddenPredicate) -> list[Finding]:
    """Every code point of *text* that *hidden* flags, other than TAB, LF and CR, with its position."""
    findings: list[Finding] = []
    for line_number, line in enumerate(text.split(_LINE_BREAK), start=1):
        for column, char in enumerate(line, start=1):
            if char not in LINE_STRUCTURE and hidden(char):
                findings.append(Finding(path, line_number, column, code_point_label(char)))
    return findings


def scan_file(file: Path, path: str, hidden: HiddenPredicate) -> list[Finding]:
    """The findings of one file, or one finding at the first byte that is not UTF-8.

    Raises:
        HiddenCodePointGateError: The file cannot be read.
    """
    try:
        data = file.read_bytes()
    except OSError as error:
        raise HiddenCodePointGateError(
            f"cannot read {file}: {error}. Expected a readable source file. Fix: restore its permissions or remove it."
        ) from error
    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError as error:
        before = data[: error.start]
        line = before.count(_LINE_BREAK_BYTE) + 1
        column = error.start - (before.rfind(_LINE_BREAK_BYTE) + 1) + 1
        detail = (
            f"not UTF-8 text (byte 0x{data[error.start]:02X} at byte offset {error.start}: {error.reason}); "
            "a source file is read as UTF-8 so every code point in it can be judged. Fix: re-encode it as UTF-8."
        )
        return [Finding(path, line, column, detail)]
    return scan_text(text, path, hidden)


def generator_repos(workspace: Path) -> list[Path]:
    """Every ``datrix-codegen-*`` git checkout in *workspace* that has a ``src/`` tree, sorted by name."""
    return [
        repo
        for repo in workspace_package_dirs(workspace, any_of=frozenset({PackageMarker.GIT}))
        if repo.name.startswith(GENERATOR_REPO_PREFIX) and (repo / SOURCE_DIR).is_dir()
    ]


def source_files(repo: Path) -> list[str]:
    """Every file under *repo*'s ``src/`` a commit could publish (tracked, or untracked and not ignored).

    Raises:
        HiddenCodePointGateError: ``git ls-files`` failed.
    """
    args = ["ls-files", "-z", "--cached", "--others", "--exclude-standard", "--", SOURCE_DIR]
    result = subprocess.run(["git", "-C", str(repo), *args], capture_output=True, check=False)
    if result.returncode != 0:
        detail = (result.stderr or result.stdout).decode("utf-8", errors="replace").strip()
        raise HiddenCodePointGateError(
            f"git {' '.join(args)} failed in {repo} (exit {result.returncode}): {detail}. Expected a readable "
            "git checkout. Fix: repair the repository or pass -Repo to scan the others."
        )
    listed = result.stdout.decode("utf-8", errors="surrogateescape").split("\0")
    # A tracked file deleted from the working tree has no content left to publish.
    return list(dict.fromkeys(path for path in listed if path and (repo / path).is_file()))


def scan_repo(repo: Path, hidden: HiddenPredicate) -> tuple[int, list[Finding]]:
    """How many files *repo*'s ``src/`` publishes, and the findings over them."""
    files = source_files(repo)
    findings = [finding for path in files for finding in scan_file(repo / path, f"{repo.name}/{path}", hidden)]
    return len(files), findings


def _hidden_predicate() -> HiddenPredicate:
    """The shared predicate, imported once the package installs are known to be current."""
    from datrix_common.utils.hidden_text import hidden_in_source

    return hidden_in_source


def _positions(findings: list[Finding]) -> list[tuple[int, int, str]]:
    return [(finding.line, finding.column, finding.detail) for finding in findings]


def _corpus_reported_at_its_positions(hidden: HiddenPredicate) -> bool:
    from datrix_testing.hidden_text_corpus import HIDDEN_TEXT_CORPUS

    passed = True
    for row in HIDDEN_TEXT_CORPUS:
        found = _positions(scan_text(row.text, row.row_id, hidden))
        expected = [(1, offset + 1, code_point_label(row.text[offset])) for offset in row.hidden_offsets]
        label = f"corpus row {row.row_id} is reported at {expected}"
        passed = report_condition(found == expected, label, f"got {found}") and passed
    return passed


def _line_structure_and_positions(hidden: HiddenPredicate) -> bool:
    clean = "a\tb\r\nc\n"
    found_clean = scan_text(clean, "line-structure", hidden)
    passed = report_condition(not found_clean, "TAB, LF and CR pass", f"got {[f.render() for f in found_clean]}")
    # U+2028 is reported on the line it sits on, never taken as a line break.
    text = f"a{chr(0x2028)}b\nc{chr(0x202E)}\n"
    found = _positions(scan_text(text, "positions", hidden))
    expected = [(1, 2, "U+2028"), (2, 2, "U+202E")]
    return report_condition(found == expected, f"lines count LF alone: {expected}", f"got {found}") and passed


def _planted_files_reported(hidden: HiddenPredicate) -> bool:
    TMP_DIR.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(dir=TMP_DIR, prefix=_SELF_TEST_PREFIX, ignore_cleanup_errors=True) as scratch:
        root = Path(scratch)
        hidden_file = write_file(root / "hidden.py", f"x = 'a{chr(0x200B)}b'\n")
        clean_file = write_file(root / "clean.py", "x = 'ab'\n")
        latin1_file = root / "latin1.txt"
        latin1_file.write_bytes(b"ok\ncaf\xe9\n")
        found = [
            (finding.path, finding.line, finding.column, finding.detail.split(" ", 1)[0])
            for file in (hidden_file, clean_file, latin1_file)
            for finding in scan_file(file, file.name, hidden)
        ]
    expected = [("hidden.py", 1, 7, "U+200B"), ("latin1.txt", 2, 4, "not")]
    return report_condition(
        found == expected, "planted files report the hidden code point and the non-UTF-8 byte only", f"got {found}"
    )


def run_self_test(hidden: HiddenPredicate) -> bool:
    """Non-vacuity: every corpus row is reported where it sits, line structure passes, planted files report."""
    print("=== Hidden-code-point self-test ===")
    corpus = _corpus_reported_at_its_positions(hidden)
    structure = _line_structure_and_positions(hidden)
    planted = _planted_files_reported(hidden)
    return corpus and structure and planted


def _check_self_test_reports_every_planted_defect() -> None:
    assert run_self_test(_hidden_predicate()), "the self-test did not report exactly its planted defects"


def _selected_repos(wanted: list[str] | None) -> list[Path]:
    repos = generator_repos(WORKSPACE_DIR)
    if wanted is None:
        return repos
    missing = sorted(set(wanted) - {repo.name for repo in repos})
    if missing:
        raise ValueError(
            f"No generator repo named {', '.join(missing)} under {WORKSPACE_DIR}. "
            f"Known: {', '.join(repo.name for repo in repos)}. Pass one of the known names."
        )
    return [repo for repo in repos if repo.name in set(wanted)]


def _run_scan(wanted: list[str] | None, hidden: HiddenPredicate) -> int:
    try:
        repos = _selected_repos(wanted)
    except ValueError as error:
        print(f"ERROR: {error}", file=sys.stderr)
        return EXIT_USAGE
    if not repos:
        print(
            f"ERROR: no {GENERATOR_REPO_PREFIX}* git checkout with a {SOURCE_DIR}/ tree under {WORKSPACE_DIR}.",
            file=sys.stderr,
        )
        return EXIT_USAGE
    scanned = 0
    findings: list[Finding] = []
    for repo in repos:
        count, repo_findings = scan_repo(repo, hidden)
        scanned += count
        findings.extend(repo_findings)
    for finding in findings:
        report_fail(finding.render())
    if findings:
        report_fail(
            f"{len(findings)} hidden code point(s) or unreadable file(s) in {scanned} source file(s) of "
            f"{len(repos)} repo(s). Fix: write each as an escape of the file's language (a '\\u' escape of "
            "its hex in a string literal), or delete it."
        )
        return EXIT_VIOLATION
    report_ok(f"no hidden code point in {scanned} source file(s) of {len(repos)} generator repo(s).")
    return EXIT_PASS


def build_parser() -> argparse.ArgumentParser:
    """The options of ``gates/repo-hygiene/hidden-code-point-gate.ps1``: one per wrapper parameter, spelled exactly."""
    parser = argparse.ArgumentParser(
        prog=WRAPPER,
        description="No file under a generator package's src/ holds a code point a reader cannot see.",
        allow_abbrev=False,
    )
    parser.add_argument(
        "--repo",
        action="append",
        default=None,
        help="Limit the scan to this generator repo name (repeatable or comma-separated). Default: every one.",
    )
    parser.add_argument(
        "--self-test", action="store_true", help="Run only the non-vacuity self-test and the wrapper seam checks."
    )
    parser.add_argument(
        WRAPPER_DEBUG_FLAG, dest="debug", action="store_true", help="Log at DEBUG level and print the command first."
    )
    return parser


def _run(args: argparse.Namespace) -> int:
    if args.debug:
        print_command()
    if not packages_current():
        return EXIT_VIOLATION
    try:
        if args.self_test:
            return wrappers.run_self_test(
                [_check_self_test_reports_every_planted_defect],
                wrapper=WRAPPER,
                module=MODULE,
                parser=build_parser(),
                folder=wrappers.REPO_HYGIENE_GATES_DIR,
            )
        hidden = _hidden_predicate()
        if not run_self_test(hidden):
            report_fail("hidden-code-point self-test failed; the scan cannot be trusted.")
            return EXIT_VIOLATION
        return _run_scan(None if args.repo is None else comma_values(args.repo), hidden)
    except HiddenCodePointGateError as error:
        print(f"ERROR: {error}", file=sys.stderr)
        return EXIT_USAGE


def main(argv: Sequence[str] | None = None) -> int:
    """Entry point: the gate in gate mode (a claimed log and the verdict line)."""
    return run_as_gate(GATE, MODULE, gate_child(build_parser, _run), argv)


if __name__ == "__main__":
    sys.exit(main())
