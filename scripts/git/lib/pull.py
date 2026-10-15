#!/usr/bin/env python3
"""Pull every workspace repository, then summarize what happened to each one.

Each repository directly under the workspace root is pulled in turn and git's own output
is printed under its name. After the last pull, one summary groups every repository by
outcome:

UPDATED       the pull brought in new commits (old..new and the commit count)
UP TO DATE    nothing to pull
CONFLICT      the pull stopped with unmerged paths (listed); resolve them, then commit
BLOCKED       the pull refused to start because it would overwrite local changes or
              untracked files (listed); nothing was merged -- run /resolve-conflicts.
              Each listed path carries a verdict comparing the local edit (HEAD vs the
              working tree) with the incoming one (HEAD vs the fetched upstream), on HEAD
              line ranges: OVERLAPS (the same lines, within git's 3-line context, changed on
              both sides -- a real conflict), DISJOINT (both changed, different places),
              NOT CHANGED UPSTREAM, NO LOCAL CONTENT CHANGE (mode or line endings only) or
              UNTRACKED (a local file the incoming commits add).
FAILED       anything else (no upstream, network, authentication); git's error is shown

A repository already holding unmerged paths before the pull is reported as CONFLICT:
git refuses the pull, and the unmerged paths are what stand in the way.

Exit codes: 0 every repository updated or up to date, 1 at least one did not,
2 the run could not start.
"""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path

from datrix_scripts.code_index.sources import discover_repos
from datrix_scripts.logging_utils import ColorCodes, colorize
from datrix_scripts.paths import WORKSPACE_DIR

EXIT_ALL_PULLED = 0
EXIT_SOME_NOT_PULLED = 1
EXIT_CANNOT_RUN = 2

PULL_TIMEOUT_SECONDS = 600
GIT_TIMEOUT_SECONDS = 120

# The headers git prints before the tab-indented list of paths a merge would overwrite.
_OVERWRITE_HEADERS = (
    "Your local changes to the following files would be overwritten",
    "The following untracked working tree files would be overwritten",
)
_PATH_LIST_INDENT = "\t"
_ERROR_PREFIXES = ("fatal:", "error:")
_NOT_A_REASON_PREFIXES = ("From ", "hint:")
SUMMARY_RULE = "=" * 72

#: A unified-diff hunk header; group 1/2 are the HEAD-side start line and length.
_HUNK_HEADER = re.compile(r"^@@ -(\d+)(?:,(\d+))? \+\d+(?:,\d+)? @@")
#: Lines of context git merges with; edits closer than this collide.
MERGE_CONTEXT_LINES = 3
UPSTREAM_REF = "@{upstream}"


class PullOutcome(Enum):
    UPDATED = "Updated"
    UP_TO_DATE = "Up to date"
    CONFLICT = "Conflict"
    BLOCKED = "Blocked by local changes"
    FAILED = "Failed"


SUCCESSFUL_OUTCOMES = frozenset({PullOutcome.UPDATED, PullOutcome.UP_TO_DATE})


def outcome_color(outcome: PullOutcome) -> str:
    """Green for a pull that succeeded, red for one that needs attention."""
    return ColorCodes.GREEN if outcome in SUCCESSFUL_OUTCOMES else ColorCodes.RED


class PullError(Exception):
    """A git command needed to classify a pull could not run."""


@dataclass
class RepoPull:
    name: str
    outcome: PullOutcome
    paths: list[str] = field(default_factory=list)
    detail: str = ""


@dataclass
class GitResult:
    returncode: int
    stdout: str
    stderr: str

    @property
    def output(self) -> str:
        return self.stdout + self.stderr


def _run_git(repo: Path, args: list[str], timeout: int) -> GitResult:
    try:
        result = subprocess.run(["git", "-C", str(repo), *args], capture_output=True, timeout=timeout, check=False)
    except subprocess.TimeoutExpired as exc:
        raise PullError(f"'git {' '.join(args)}' in {repo} did not finish within {timeout} s") from exc
    except OSError as exc:
        raise PullError(f"'git {' '.join(args)}' could not start in {repo}: {exc}. Is git on PATH?") from exc
    return GitResult(
        result.returncode,
        result.stdout.decode("utf-8", errors="replace"),
        result.stderr.decode("utf-8", errors="replace"),
    )


def _git_value(repo: Path, args: list[str]) -> str:
    """Stdout of a git query; stderr carries warnings (line endings, hints), never the value."""
    result = _run_git(repo, args, GIT_TIMEOUT_SECONDS)
    if result.returncode != 0:
        raise PullError(f"'git {' '.join(args)}' failed in {repo} (exit {result.returncode}): {result.stderr.strip()}")
    return result.stdout.strip()


def _head(repo: Path) -> str:
    return _git_value(repo, ["rev-parse", "HEAD"])


def _unmerged_paths(repo: Path) -> list[str]:
    listed = _git_value(repo, ["diff", "--name-only", "--diff-filter=U"])
    return [line for line in listed.splitlines() if line]


def overwritten_paths(pull_output: str) -> list[str]:
    """The paths git lists under a 'would be overwritten by merge' refusal, in order."""
    paths: list[str] = []
    in_list = False
    for line in pull_output.splitlines():
        if any(header in line for header in _OVERWRITE_HEADERS):
            in_list = True
            continue
        if in_list and line.startswith(_PATH_LIST_INDENT):
            paths.append(line.strip())
            continue
        in_list = False
    return paths


def hunk_ranges(diff_output: str) -> list[tuple[int, int]]:
    """HEAD-side ``(first, last)`` line ranges of every hunk in a ``--unified=0`` diff.

    A pure insertion (length 0) is the one-line range at the line it follows.
    """
    ranges: list[tuple[int, int]] = []
    for line in diff_output.splitlines():
        match = _HUNK_HEADER.match(line)
        if match is None:
            continue
        start = int(match.group(1))
        length = int(match.group(2)) if match.group(2) is not None else 1
        ranges.append((start, start + max(length, 1) - 1))
    return ranges


def ranges_collide(first: tuple[int, int], second: tuple[int, int]) -> bool:
    """True when two HEAD-side ranges come within git's merge context of each other."""
    return first[0] - MERGE_CONTEXT_LINES <= second[1] and second[0] - MERGE_CONTEXT_LINES <= first[1]


def _format_ranges(ranges: list[tuple[int, int]]) -> str:
    return ", ".join(f"{first}-{last}" for first, last in ranges)


def overlap_verdict(repo: Path, path: str) -> str:
    """How a blocking local edit of *path* relates to the incoming change (see the module docstring)."""
    if _run_git(repo, ["cat-file", "-e", f"HEAD:{path}"], GIT_TIMEOUT_SECONDS).returncode != 0:
        return "UNTRACKED here; the incoming commits add it -- compare the two by hand"
    local = hunk_ranges(_git_value(repo, ["diff", "--unified=0", "HEAD", "--", path]))
    if not local:
        return "NO LOCAL CONTENT CHANGE (mode or line endings only)"
    incoming = hunk_ranges(_git_value(repo, ["diff", "--unified=0", "HEAD", UPSTREAM_REF, "--", path]))
    if not incoming:
        return "NOT CHANGED UPSTREAM"
    collisions = [(mine, theirs) for mine in local for theirs in incoming if ranges_collide(mine, theirs)]
    if collisions:
        pairs = "; ".join(f"local {mine[0]}-{mine[1]} vs incoming {theirs[0]}-{theirs[1]}" for mine, theirs in collisions)
        return f"OVERLAPS upstream at HEAD lines {pairs}"
    return f"DISJOINT: local {_format_ranges(local)} | incoming {_format_ranges(incoming)}"


def failure_reason(pull_output: str) -> str:
    """The line that says why a pull failed: git's last fatal/error line, else its first message line.

    Fetch progress ("From <url>" and the indented ref updates) and the indented or ``hint:``
    advice git appends are skipped, so a refusal such as "There is no tracking information
    for the current branch." is reported rather than the example command printed after it.
    """
    lines = [line for line in pull_output.splitlines() if line.strip()]
    errors = [line.strip() for line in lines if line.startswith(_ERROR_PREFIXES)]
    if errors:
        return errors[-1]
    messages = [line for line in lines if not line[0].isspace() and not line.startswith(_NOT_A_REASON_PREFIXES)]
    return messages[0].strip() if messages else "git pull exited non-zero with no output"


def classify(repo: Path, before: str, pull: GitResult) -> RepoPull:
    """Decide the outcome of one pull from git's exit code, output and repository state."""
    unmerged = _unmerged_paths(repo)
    if unmerged:
        return RepoPull(repo.name, PullOutcome.CONFLICT, unmerged)
    if pull.returncode != 0:
        blocked = overwritten_paths(pull.output)
        if blocked:
            verdicts = [f"{path}  [{overlap_verdict(repo, path)}]" for path in blocked]
            return RepoPull(repo.name, PullOutcome.BLOCKED, verdicts)
        return RepoPull(repo.name, PullOutcome.FAILED, detail=failure_reason(pull.output))
    after = _head(repo)
    if after == before:
        return RepoPull(repo.name, PullOutcome.UP_TO_DATE)
    count = _git_value(repo, ["rev-list", "--count", f"{before}..{after}"])
    return RepoPull(repo.name, PullOutcome.UPDATED, detail=f"{before[:9]}..{after[:9]}, {count} commit(s)")


def pull_repo(repo: Path) -> RepoPull:
    print(f"Pulling {repo.name}...", flush=True)
    try:
        before = _head(repo)
        pull = _run_git(repo, ["pull"], PULL_TIMEOUT_SECONDS)
        if pull.output.strip():
            print(pull.output.rstrip(), flush=True)
        result = classify(repo, before, pull)
    except PullError as exc:
        result = RepoPull(repo.name, PullOutcome.FAILED, detail=str(exc))
    print(colorize(f"{repo.name}: {result.outcome.value}", outcome_color(result.outcome)), flush=True)
    print(flush=True)
    return result


def render_summary(results: list[RepoPull]) -> str:
    lines = [SUMMARY_RULE, f"Pull summary: {len(results)} repositories", SUMMARY_RULE]
    for outcome in PullOutcome:
        group = [result for result in results if result.outcome is outcome]
        if not group:
            continue
        color = outcome_color(outcome)
        lines.append(colorize(f"{outcome.value} ({len(group)}):", color))
        for result in group:
            lines.append(colorize(f"  {result.name}", color) + (f"  ({result.detail})" if result.detail else ""))
            lines.extend(f"      {path}" for path in result.paths)
    failed = sum(1 for result in results if result.outcome not in SUCCESSFUL_OUTCOMES)
    lines.append(SUMMARY_RULE)
    if failed:
        lines.append(colorize(f"{failed} repositories need attention.", ColorCodes.RED))
    else:
        lines.append(colorize("All repositories pulled.", ColorCodes.GREEN))
    return "\n".join(lines)


def main(argv: list[str]) -> int:
    for stream in (sys.stdout, sys.stderr):
        stream.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[union-attr]
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.parse_args(argv)
    workspace = WORKSPACE_DIR
    repos = discover_repos(workspace)
    if not repos:
        print(colorize(f"ERROR: no git repositories found directly under {workspace}; expected the datrix-* "
                       "package checkouts there.", ColorCodes.RED), file=sys.stderr)
        return EXIT_CANNOT_RUN
    results = [pull_repo(repo) for repo in repos]
    print(render_summary(results))
    return EXIT_ALL_PULLED if all(r.outcome in SUCCESSFUL_OUTCOMES for r in results) else EXIT_SOME_NOT_PULLED


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
