"""Show the git status of every directory under the workspace root.

The module behind ``git/status.ps1`` (and its ``.sh`` twin). Each directory directly under the
workspace root (as PowerShell's ``Get-ChildItem -Directory`` lists them: hidden ones left out, links
to directories included) is reported on one line: ``<name>: clean``, ``<name>: has changes`` or
``<name>: not a git repo``. With ``--detailed``, a repository with changes also shows its branch, how
many commits it is ahead of or behind its upstream, and ``git status --short``. Every git call only
reads.

``--self-test`` reports a temporary workspace of real repositories (clean, with changes and ahead of
its upstream, and a plain directory), and runs the census that no git script runs a form that
discards local work.

Exit codes: 0 = reported (or a passing self-test); 1 = a self-test check failed.
"""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
from collections.abc import Iterator, Sequence
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Final

from datrix_scripts.cleanup_utils import children
from datrix_scripts.gate_harness import WRAPPER_DEBUG_FLAG, write_files
from datrix_scripts.git.forbidden_forms import check_no_git_script_runs_a_forbidden_form
from datrix_scripts.logging_utils import ColorCodes, colorize
from datrix_scripts.paths import WORKSPACE_DIR
from datrix_scripts.test.wrappers import GIT_SCRIPTS_DIR, module_main, run_self_test

MODULE: Final = "datrix_scripts.git.status"
WRAPPER: Final = "status"
EXIT_REPORTED: Final = 0
GIT_DIR: Final = ".git"
# The tracking line of ``git status --porcelain --branch`` when the branch is only ahead, or only behind.
_AHEAD: Final = re.compile(r"\[ahead (\d+)\]")
_BEHIND: Final = re.compile(r"\[behind (\d+)\]")


def _git_lines(repo: Path, *args: str) -> list[str]:
    """Stdout lines of a read-only git query; git's own errors reach the console as they always have."""
    result = subprocess.run(["git", "-C", str(repo), *args], stdout=subprocess.PIPE, check=False,
                            text=True, encoding="utf-8", errors="replace")
    return result.stdout.splitlines()


def _details(repo: Path) -> list[str]:
    branch = "".join(_git_lines(repo, "branch", "--show-current"))
    lines = [colorize(" Details:", ColorCodes.CYAN), colorize(f" Branch: {branch}", ColorCodes.GRAY)]
    tracking = next(iter(_git_lines(repo, "status", "--porcelain", "--branch")), "")
    for pattern, word in ((_AHEAD, "Ahead"), (_BEHIND, "Behind")):
        match = pattern.search(tracking)
        if match:
            lines.append(colorize(f" {word}: {match.group(1)} commit(s)", ColorCodes.GRAY))
    lines.append(colorize(" Changed files:", ColorCodes.GRAY))
    lines.extend(colorize(f" {line}", ColorCodes.GRAY) for line in _git_lines(repo, "status", "--short"))
    lines.append("")
    return lines


def status_lines(workspace: Path, detailed: bool) -> Iterator[str]:
    """The report of every directory directly under *workspace*, one directory at a time."""
    for directory in (entry for entry in children(workspace, include_hidden=False) if entry.is_dir()):
        if not (directory / GIT_DIR).exists():
            yield colorize(f"{directory.name}: not a git repo", ColorCodes.DARK_GRAY)
        elif not "".join(_git_lines(directory, "status", "--porcelain")).strip():
            yield colorize(f"{directory.name}: clean", ColorCodes.GREEN)
        else:
            yield colorize(f"{directory.name}: has changes", ColorCodes.YELLOW)
            if detailed:
                yield from _details(directory)


_FIXTURE_IDENTITY: Final = ("-c", "user.name=status-self-test", "-c", "user.email=self-test@example.invalid",
                            "-c", "commit.gpgsign=false")


def _fixture_git(cwd: Path, *args: str) -> None:
    subprocess.run(["git", *_FIXTURE_IDENTITY, *args], cwd=cwd, check=True, capture_output=True)


def _check_every_directory_is_reported() -> None:
    with TemporaryDirectory() as raw:
        root = Path(raw)
        workspace = root / "workspace"
        _fixture_git(root, "init", "-q", "--bare", "-b", "main", "remote.git")
        _fixture_git(root, "clone", "-q", "remote.git", str(workspace / "beta"))
        _fixture_git(root, "clone", "-q", "remote.git", str(workspace / "Alpha"))
        for repo in (workspace / "beta", workspace / "Alpha"):
            write_files(repo, {"a.txt": "a\n"})
            _fixture_git(repo, "add", "-A")
            _fixture_git(repo, "commit", "-q", "-m", "one")
        _fixture_git(workspace / "beta", "push", "-q", "origin", "main")
        _fixture_git(workspace / "beta", "commit", "-q", "--allow-empty", "-m", "two")
        write_files(workspace / "beta", {"a.txt": "changed\n", "new.txt": "n\n"})
        (workspace / "gamma").mkdir()
        (workspace / "notes.txt").write_text("not a directory\n", encoding="utf-8")
        plain = list(status_lines(workspace, detailed=False))
        detailed = list(status_lines(workspace, detailed=True))
    assert plain == ["Alpha: clean", "beta: has changes", "gamma: not a git repo"], plain
    beta = detailed[detailed.index("beta: has changes"):]
    assert beta == ["beta: has changes", " Details:", " Branch: main", " Ahead: 1 commit(s)", " Changed files:",
                    "  M a.txt", " ?? new.txt", "", "gamma: not a git repo"], beta


def build_parser() -> argparse.ArgumentParser:
    """The options of ``git/status.ps1``: one per wrapper parameter, spelled exactly."""
    parser = argparse.ArgumentParser(description="Show the git status of every directory under the workspace root.",
                                     allow_abbrev=False)
    parser.add_argument("--detailed", action="store_true",
                        help="For a repository with changes: branch, ahead/behind and the changed files.")
    parser.add_argument(WRAPPER_DEBUG_FLAG, dest="debug", action="store_true", help="Debug logging.")
    parser.add_argument("--self-test", action="store_true",
                        help="Report a temporary workspace of real repositories, and run the forbidden-forms census.")
    return parser


def _run(args: argparse.Namespace) -> int:
    if args.self_test:
        checks = [_check_every_directory_is_reported, check_no_git_script_runs_a_forbidden_form]
        return run_self_test(checks, wrapper=WRAPPER, module=MODULE, parser=build_parser(), folder=GIT_SCRIPTS_DIR)
    for line in status_lines(WORKSPACE_DIR, args.detailed):
        print(line, flush=True)
    return EXIT_REPORTED


def main(argv: Sequence[str] | None = None) -> int:
    """Entry point."""
    return module_main(build_parser(), _run, argv)


if __name__ == "__main__":
    sys.exit(main())
