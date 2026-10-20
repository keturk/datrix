"""Give each modified file back the line endings its index copy has.

The module behind ``git/fix-line-endings.ps1`` (and its ``.sh`` twin). An editor or tool that writes a file back with the other line-ending style turns a two-line
edit into a whole-file rewrite: the real change disappears in the diff. For every file with
unstaged modifications, this reads the file's own index blob (``git show :<path>``, read-only)
and rewrites ONLY the line terminators of the working copy to match it. Content is never
touched and nothing is reverted, staged or checked out.

Skipped and named (never rewritten): a binary blob, a blob that itself mixes CRLF and LF,
and a file whose working copy already matches.

``--self-test`` restores the endings in a real repository in a temporary directory, and runs the census
that no git script runs a form that discards local work.

Exit codes: 0 = done (or a clean ``--dry-run``, or a passing self-test), 1 = a self-test check failed,
2 = a git command failed or a bad argument.
"""

from __future__ import annotations

import argparse
import contextlib
import io
import subprocess
import sys
from collections.abc import Sequence
from enum import Enum
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Final

from datrix_scripts.dev.arguments import comma_values
from datrix_scripts.framework_repos import framework_repos
from datrix_scripts.git.forbidden_forms import check_no_git_script_runs_a_forbidden_form
from datrix_scripts.paths import WORKSPACE_DIR
from datrix_scripts.test.wrappers import GIT_SCRIPTS_DIR, module_main, run_self_test

MODULE: Final = "datrix_scripts.git.fix_line_endings"
WRAPPER: Final = "fix-line-endings"

EXIT_OK: Final[int] = 0
EXIT_ERROR: Final[int] = 2
CRLF: Final[bytes] = b"\r\n"
LF: Final[bytes] = b"\n"
NUL: Final[bytes] = b"\0"
GIT_RAW: Final[tuple[str, ...]] = ("git", "-c", "core.autocrlf=false")


class Style(Enum):
    """The line-ending style of a byte string."""

    CRLF = "crlf"
    LF = "lf"
    MIXED = "mixed"
    NONE = "none"
    BINARY = "binary"


def style_of(data: bytes) -> Style:
    if NUL in data:
        return Style.BINARY
    total = data.count(LF)
    crlf = data.count(CRLF)
    if total == 0:
        return Style.NONE
    if crlf == total:
        return Style.CRLF
    return Style.LF if crlf == 0 else Style.MIXED


def convert(data: bytes, style: Style) -> bytes:
    as_lf = data.replace(CRLF, LF)
    return as_lf.replace(LF, CRLF) if style is Style.CRLF else as_lf


def _git(repo: Path, *args: str) -> bytes:
    return subprocess.run([*GIT_RAW, *args], cwd=repo, check=True, capture_output=True).stdout


def modified_files(repo: Path) -> list[str]:
    """Paths with unstaged modifications relative to the index."""
    out = _git(repo, "diff", "--name-only", "--diff-filter=M").decode("utf-8")
    return [line for line in out.splitlines() if line]


def fix_repo(repo: Path, dry_run: bool) -> int:
    """Fix one repository; return how many files were (or would be) rewritten."""
    fixed = 0
    for relative in modified_files(repo):
        blob_style = style_of(_git(repo, "show", f":{relative}"))
        path = repo / relative
        current = path.read_bytes()
        if blob_style in (Style.BINARY, Style.NONE):
            continue
        if blob_style is Style.MIXED:
            print(f"{repo.name}: SKIPPED {relative} (its index copy mixes CRLF and LF; nothing to match)")
            continue
        wanted = convert(current, blob_style)
        if wanted == current:
            continue
        fixed += 1
        verb = "would restore" if dry_run else "restored"
        print(f"{repo.name}: {verb} {blob_style.value.upper()} in {relative} (working copy was {style_of(current).value})")
        if not dry_run:
            path.write_bytes(wanted)
    return fixed


def fix_repos(repos: Sequence[Path], names: Sequence[str], dry_run: bool) -> int:
    """Fix the repositories of *repos* named by *names* (every one when *names* is empty); the exit code."""
    selected = list(repos)
    if names:
        by_name = {repo.name: repo for repo in repos}
        unknown = sorted(set(names) - set(by_name))
        if unknown:
            print(f"Unknown repository {unknown}. Expected one of: {', '.join(sorted(by_name))}.")
            return EXIT_ERROR
        selected = [by_name[name] for name in names]
    total = 0
    for repo in selected:
        try:
            total += fix_repo(repo, dry_run)
        except subprocess.CalledProcessError as exc:
            stderr = exc.stderr.decode("utf-8", errors="replace").strip() if exc.stderr else ""
            print(f"{repo.name}: git {' '.join(exc.cmd[len(GIT_RAW):])} failed (exit {exc.returncode}): {stderr}")
            return EXIT_ERROR
    print(f"{total} file(s) {'would be ' if dry_run else ''}given back their index line endings.")
    return EXIT_OK


_FIXTURE_IDENTITY: Final = ("-c", "user.name=fix-line-endings-self-test", "-c",
                            "user.email=self-test@example.invalid", "-c", "commit.gpgsign=false")


def _check_working_copies_get_their_index_endings_back() -> None:
    with TemporaryDirectory() as raw:
        repo = Path(raw) / "alpha"
        repo.mkdir()
        files = {"lf.txt": b"one\ntwo\n", "crlf.txt": b"one\r\ntwo\r\n", "mixed.txt": b"one\r\ntwo\n"}
        for name, data in files.items():
            (repo / name).write_bytes(data)
        subprocess.run([*GIT_RAW, *_FIXTURE_IDENTITY, "init", "-q"], cwd=repo, check=True, capture_output=True)
        for args in (("add", "-A"), ("commit", "-q", "-m", "fixture")):
            subprocess.run([*GIT_RAW, *_FIXTURE_IDENTITY, *args], cwd=repo, check=True, capture_output=True)
        edited = {"lf.txt": b"one\r\nTWO\r\n", "crlf.txt": b"one\nTWO\n", "mixed.txt": b"one\nTWO\n"}
        for name, data in edited.items():
            (repo / name).write_bytes(data)
        with contextlib.redirect_stdout(io.StringIO()) as preview:
            previewed = fix_repos([repo], ["alpha"], dry_run=True)
        untouched = {name: (repo / name).read_bytes() for name in edited}
        with contextlib.redirect_stdout(io.StringIO()) as printed:
            restored = fix_repos([repo], [], dry_run=False)
            refused = fix_repos([repo], ["beta"], dry_run=False)
        after = {name: (repo / name).read_bytes() for name in edited}
    assert previewed == EXIT_OK and untouched == edited, f"a dry run wrote: {untouched}"
    assert "alpha: would restore LF in lf.txt (working copy was crlf)" in preview.getvalue(), preview.getvalue()
    assert restored == EXIT_OK and after == {"lf.txt": b"one\nTWO\n", "crlf.txt": b"one\r\nTWO\r\n",
                                              "mixed.txt": b"one\nTWO\n"}, after
    assert "SKIPPED mixed.txt" in printed.getvalue() and "2 file(s) given back" in printed.getvalue(), printed.getvalue()
    assert refused == EXIT_ERROR and "Unknown repository ['beta']. Expected one of: alpha." in printed.getvalue()


def build_parser() -> argparse.ArgumentParser:
    """The options of ``git/fix-line-endings.ps1``: one per wrapper parameter, spelled exactly."""
    parser = argparse.ArgumentParser(description="Give each modified file back the line endings its index copy has.",
                                     allow_abbrev=False)
    parser.add_argument("--repo", action="append", default=[],
                        help="Repository directory name (repeatable, or comma-separated). Default: every framework repo.")
    parser.add_argument("--dry-run", action="store_true", help="List the files; write nothing.")
    parser.add_argument("--self-test", action="store_true",
                        help="Restore endings in a temporary repository, and run the forbidden-forms census.")
    parser.set_defaults(debug=False)
    return parser


def _run(args: argparse.Namespace) -> int:
    if args.self_test:
        checks = [_check_working_copies_get_their_index_endings_back, check_no_git_script_runs_a_forbidden_form]
        return run_self_test(checks, wrapper=WRAPPER, module=MODULE, parser=build_parser(), folder=GIT_SCRIPTS_DIR)
    return fix_repos(framework_repos(WORKSPACE_DIR), comma_values(args.repo), args.dry_run)


def main(argv: Sequence[str] | None = None) -> int:
    """Entry point."""
    return module_main(build_parser(), _run, argv)


if __name__ == "__main__":
    sys.exit(main())
