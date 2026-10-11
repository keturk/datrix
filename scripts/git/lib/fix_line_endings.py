#!/usr/bin/env python3
"""Give each modified file back the line endings its index copy has.

An editor or tool that writes a file back with the other line-ending style turns a two-line
edit into a whole-file rewrite: the real change disappears in the diff. For every file with
unstaged modifications, this reads the file's own index blob (``git show :<path>``, read-only)
and rewrites ONLY the line terminators of the working copy to match it. Content is never
touched and nothing is reverted, staged or checked out.

Skipped and named (never rewritten): a binary blob, a blob that itself mixes CRLF and LF,
and a file whose working copy already matches.

Exit codes: 0 = done (or a clean ``--dry-run``), 2 = a git command failed or a bad argument.

Usage:
    python fix_line_endings.py [--repo NAME ...] [--dry-run]
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from collections.abc import Sequence
from enum import Enum
from pathlib import Path
from typing import Final

from datrix_scripts.framework_repos import framework_repos
from datrix_scripts.paths import WORKSPACE_DIR

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


def parse_args(argv: Sequence[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--repo", action="append", default=[], help="Repository directory name. Repeatable. Default: every framework repo.")
    parser.add_argument("--dry-run", action="store_true", help="List the files; write nothing.")
    return parser.parse_args(argv)


def main(argv: Sequence[str]) -> int:
    args = parse_args(argv)
    repos = framework_repos(WORKSPACE_DIR)
    if args.repo:
        by_name = {repo.name: repo for repo in repos}
        unknown = sorted(set(args.repo) - set(by_name))
        if unknown:
            print(f"Unknown repository {unknown}. Expected one of: {', '.join(sorted(by_name))}.")
            return EXIT_ERROR
        repos = [by_name[name] for name in args.repo]
    total = 0
    for repo in repos:
        try:
            total += fix_repo(repo, args.dry_run)
        except subprocess.CalledProcessError as exc:
            stderr = exc.stderr.decode("utf-8", errors="replace").strip() if exc.stderr else ""
            print(f"{repo.name}: git {' '.join(exc.cmd[len(GIT_RAW):])} failed (exit {exc.returncode}): {stderr}")
            return EXIT_ERROR
    print(f"{total} file(s) {'would be ' if args.dry_run else ''}given back their index line endings.")
    return EXIT_OK


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
