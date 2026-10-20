#!/usr/bin/env python3
"""Pull repositories over uncommitted local work: the mechanical half of /resolve-conflicts.

RUN (default), per repository whose upstream is ahead:
  1. Measure: fetch; the tracked overlap (locally modified paths the pull changes) and the untracked
     collisions (untracked paths the pull adds). A path whose only local difference is line endings
     gets its index copy's terminators back (fix_line_endings) and drops out of the overlap.
  2. Shelve ONLY the overlap: ``git stash push -m "resolve-conflicts <repo> <stamp>" -- <paths>``. An
     untracked collision with the upstream bytes is deleted (the pull recreates it); any other is copied
     to <workspace>/.tmp/resolve-conflicts/<repo>/untracked/ first, then deleted.
  3. Pull: ``--ff-only`` when not ahead, ``--no-rebase --no-edit`` when diverged. A conflicting merge of
     committed history stops here: resolve it, commit, then run --finish.
  4. Reapply with ``git stash apply`` (never pop: the entry stays as the safety copy).
  5. Clean apply and nothing set aside differs -> FINISH runs at once. Otherwise the conflicted paths
     keep their markers and <workspace>/.tmp/resolve-conflicts/<repo>/conflicts.md lists each conflict
     hunk with its local, base and incoming text and the working-file line, plus a local model's merge
     draft checked against both sides (a lead: every line either side added must be in it).

FINISH (--finish, after the hand merge), per repository with a shelved entry:
  every shelved or set-aside path is free of conflict markers; the shelved paths are unstaged (index
  only); every line the local edits added is in the working tree (a path named in --merged, where a
  local line was deliberately merged with the incoming change, is reported instead of refused); every
  set-aside untracked file's lines are in the pulled file. Only then the stash entry is dropped and the
  set-aside copies deleted.

Nothing here discards work: no reset of the tree, no checkout of a path, no bare stash, no stash clear.
State per repository lives in <workspace>/.tmp/resolve-conflicts/<repo>/state.json.

Exit codes: 0 every repository up to date or finished; 1 at least one needs a hand merge, has a
pre-existing conflict, or failed; 2 the run could not start.
"""

from __future__ import annotations

import argparse
import difflib
import json
import shutil
import subprocess
import sys
from collections.abc import Sequence
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path

from datrix_scripts.code_index.sources import discover_repos
from datrix_scripts.customer_domain_isolation import TermCorpus, scan_text
from datrix_scripts.framework_repos import framework_repos
from datrix_scripts.local_llm import (
    ChatRequest,
    LocalLlmPool,
    LocalLlmUnavailable,
    add_wrapper_llm_arguments,
    wrapper_llm_settings,
)
from datrix_scripts.local_reading import ReadScopeError, load_workspace_term_corpus
from datrix_scripts.paths import WORKSPACE_DIR
from datrix_scripts.git.fix_line_endings import fix_repo
from datrix_scripts.test.wrappers import GIT_SCRIPTS_DIR, module_main, run_self_test

MODULE = "datrix_scripts.git.resolve_pull"
WRAPPER = "resolve-pull"
LLM_TIMEOUT_SECONDS = 300

EXIT_ALL_DONE = 0
EXIT_NEEDS_ATTENTION = 1
EXIT_CANNOT_RUN = 2

GIT_TIMEOUT_SECONDS = 120
PULL_TIMEOUT_SECONDS = 600
UPSTREAM = "@{upstream}"
STATE_DIR_PARTS = (".tmp", "resolve-conflicts")
STASH_PREFIX = "resolve-conflicts"
CONFLICT_START = "<<<<<<< "
CONFLICT_BASE = "||||||| "
CONFLICT_SPLIT = "======="
CONFLICT_END = ">>>>>>> "
MARKER_PATTERNS = ("-e", "^<<<<<<< ", "-e", "^>>>>>>> ")
EXCLUSIVE = "EXCLUSIVE"
MERGE_TEMPERATURE = 0.1
MERGE_MAX_TOKENS = 4000

MERGE_SYSTEM = (
    "You merge one conflict hunk of a file from a code-generator repository. BASE is the text before either "
    "edit, LOCAL is the uncommitted local edit, INCOMING is the upstream commit's edit. Write the merged text "
    "that carries BOTH intents: every line either side added, with each side's removals applied. Answer "
    "with the merged lines only, exactly as they belong in the file: no fence, no commentary. When the two "
    "edits are mutually exclusive (keeping one means dropping the other), answer the single word EXCLUSIVE "
    "followed by one sentence saying why.")


class ResolveError(Exception):
    """A git command the resolution depends on failed; the message carries git's error."""


@dataclass
class RepoState:
    """What RUN did to a repository, so FINISH can verify and undo nothing by accident."""

    stash_message: str
    stashed: list[str]
    untracked_saved: list[str]
    applied: bool
    before_status: list[str]


@dataclass
class RepoReport:
    name: str
    outcome: str
    lines: list[str] = field(default_factory=list)

    @property
    def done(self) -> bool:
        return self.outcome in (OUTCOME_UP_TO_DATE, OUTCOME_FINISHED, OUTCOME_NOTHING)


OUTCOME_UP_TO_DATE = "up to date"
OUTCOME_FINISHED = "finished"
OUTCOME_NOTHING = "nothing to finish"
OUTCOME_NEEDS_MERGE = "NEEDS HAND MERGE"
OUTCOME_CONFLICT = "CONFLICT ALREADY IN PROGRESS"
OUTCOME_FAILED = "FAILED"
OUTCOME_UNFINISHED = "UNFINISHED"


# --- git ----------------------------------------------------------------------------------------------


def _git_run(repo: Path, args: list[str], timeout: int = GIT_TIMEOUT_SECONDS) -> subprocess.CompletedProcess[bytes]:
    try:
        return subprocess.run(["git", "-C", str(repo), *args], capture_output=True, timeout=timeout, check=False)
    except subprocess.TimeoutExpired as exc:
        raise ResolveError(f"'git {' '.join(args)}' in {repo.name} did not finish within {timeout} s") from exc
    except OSError as exc:
        raise ResolveError(f"'git {' '.join(args)}' could not start ({exc}); is git on PATH?") from exc


def _git(repo: Path, args: list[str], timeout: int = GIT_TIMEOUT_SECONDS) -> str:
    result = _git_run(repo, args, timeout)
    if result.returncode != 0:
        error = result.stderr.decode("utf-8", errors="replace").strip()
        raise ResolveError(f"'git {' '.join(args)}' failed in {repo.name} (exit {result.returncode}): {error}")
    return result.stdout.decode("utf-8", errors="replace")


def _git_bytes(repo: Path, args: list[str]) -> bytes | None:
    """A blob's bytes, or None when the object does not exist."""
    result = _git_run(repo, args)
    return result.stdout if result.returncode == 0 else None


def _lines(output: str) -> list[str]:
    return [line for line in output.splitlines() if line]


def _status(repo: Path) -> list[str]:
    return _lines(_git(repo, ["status", "--porcelain", "--untracked-files=all"]))


def _unmerged(repo: Path) -> list[str]:
    return _lines(_git(repo, ["diff", "--name-only", "--diff-filter=U"]))


def _merge_in_progress(repo: Path) -> bool:
    return _git_run(repo, ["rev-parse", "-q", "--verify", "MERGE_HEAD"]).returncode == 0


def _stash_ref(repo: Path, message: str) -> str:
    """The ``stash@{N}`` whose subject ends with ``message``; refuses when it is gone."""
    for line in _lines(_git(repo, ["stash", "list", "--format=%gd%x00%s"])):
        ref, _, subject = line.partition("\x00")
        if subject.endswith(message):
            return ref
    raise ResolveError(f"No stash entry named '{message}' in {repo.name}. It was dropped or renamed by hand; "
                       "check `git stash list` before going on.")


# --- state --------------------------------------------------------------------------------------------


def _state_dir(repo: Path) -> Path:
    return WORKSPACE_DIR.joinpath(*STATE_DIR_PARTS, repo.name)


def _load_state(repo: Path) -> RepoState | None:
    path = _state_dir(repo) / "state.json"
    if not path.is_file():
        return None
    return RepoState(**json.loads(path.read_text(encoding="utf-8")))


def _save_state(repo: Path, state: RepoState) -> None:
    directory = _state_dir(repo)
    directory.mkdir(parents=True, exist_ok=True)
    (directory / "state.json").write_text(json.dumps(asdict(state), indent=2) + "\n", encoding="utf-8")


# --- run ----------------------------------------------------------------------------------------------


@dataclass(frozen=True)
class Measure:
    ahead: int
    behind: int
    overlap: list[str]
    collisions: list[str]


def _modified_tracked(status: list[str]) -> set[str]:
    return {line[3:].split(" -> ")[-1] for line in status if not line.startswith("??")}


def _untracked(status: list[str]) -> set[str]:
    return {line[3:] for line in status if line.startswith("??")}


def _content_changed(repo: Path, path: str) -> bool:
    """False when the local difference of a tracked path is only line endings or mode."""
    return bool(_git(repo, ["diff", "--unified=0", "--ignore-cr-at-eol", "HEAD", "--", path]).strip())


def measure(repo: Path) -> Measure:
    counts = _git(repo, ["rev-list", "--left-right", "--count", f"HEAD...{UPSTREAM}"]).split()
    incoming = set(_lines(_git(repo, ["diff", "--name-only", "HEAD", UPSTREAM])))
    added = set(_lines(_git(repo, ["diff", "--name-only", "--diff-filter=A", "HEAD", UPSTREAM])))
    status = _status(repo)
    overlap = sorted(_modified_tracked(status) & incoming)
    if any(not _content_changed(repo, path) for path in overlap):
        fix_repo(repo, dry_run=False)
        overlap = sorted(_modified_tracked(_status(repo)) & incoming)
    return Measure(int(counts[0]), int(counts[1]), overlap, sorted(_untracked(status) & added))


def _set_aside(repo: Path, collisions: list[str]) -> list[str]:
    """Delete each untracked collision, keeping a copy of every one whose bytes differ from upstream."""
    saved: list[str] = []
    for path in collisions:
        local = repo / path
        if local.read_bytes() != _git_bytes(repo, ["show", f"{UPSTREAM}:{path}"]):
            copy = _state_dir(repo) / "untracked" / path
            copy.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(local, copy)
            saved.append(path)
        local.unlink()
    return saved


def _pull(repo: Path, ahead: int) -> subprocess.CompletedProcess[bytes]:
    args = ["pull", "--ff-only"] if ahead == 0 else ["pull", "--no-rebase", "--no-edit"]
    return _git_run(repo, args, PULL_TIMEOUT_SECONDS)


def resolve_repo(repo: Path, drafter: MergeDrafter | None) -> RepoReport:
    if _load_state(repo) is not None:
        return RepoReport(repo.name, OUTCOME_UNFINISHED, ["an earlier run shelved work here: finish the hand merge, "
                                                         "then run with --finish"])
    if _unmerged(repo):
        return RepoReport(repo.name, OUTCOME_CONFLICT, _unmerged(repo))
    _git(repo, ["fetch", "--quiet"], PULL_TIMEOUT_SECONDS)
    found = measure(repo)
    if found.behind == 0:
        return RepoReport(repo.name, OUTCOME_UP_TO_DATE)
    before = _status(repo)
    message = f"{STASH_PREFIX} {repo.name} {datetime.now():%Y%m%d-%H%M%S}"
    state = RepoState(message, found.overlap, [], applied=not found.overlap, before_status=before)
    _save_state(repo, state)
    if found.overlap:
        _git(repo, ["stash", "push", "-m", message, "--", *found.overlap])
    state.untracked_saved = _set_aside(repo, found.collisions)
    _save_state(repo, state)
    pulled = _pull(repo, found.ahead)
    if pulled.returncode != 0:
        return _after_failed_pull(repo, state, pulled)
    return _reapply(repo, state, drafter)


def _after_failed_pull(repo: Path, state: RepoState, pulled: subprocess.CompletedProcess[bytes]) -> RepoReport:
    error = (pulled.stdout + pulled.stderr).decode("utf-8", errors="replace").strip().splitlines()
    if _merge_in_progress(repo) and _unmerged(repo):
        return RepoReport(repo.name, OUTCOME_NEEDS_MERGE, [
            "the merge of committed history conflicted in: " + ", ".join(_unmerged(repo)),
            "resolve each with Edit, `git add` it, `git commit --no-edit`, then run with --finish "
            "(it reapplies the shelved paths)"])
    return RepoReport(repo.name, OUTCOME_FAILED, [*error[-3:], "the shelved work is still in the stash entry "
                                                  f"'{state.stash_message}'; run with --finish to reapply it"])


def _reapply(repo: Path, state: RepoState, drafter: MergeDrafter | None) -> RepoReport:
    if not state.applied:
        _git_run(repo, ["stash", "apply", _stash_ref(repo, state.stash_message)])
        state.applied = True
        _save_state(repo, state)
    conflicted = sorted(set(_unmerged(repo)) & set(state.stashed))
    differing = [p for p in state.untracked_saved if _saved_copy(repo, p).read_bytes() != _read(repo / p)]
    if not conflicted and not differing:
        return finish_repo(repo, merged=set())
    packet = write_packet(repo, state, conflicted, differing, drafter)
    lines = [f"conflicted: {', '.join(conflicted)}"] if conflicted else []
    lines += [f"set-aside untracked file differs from the pulled one: {', '.join(differing)}"] if differing else []
    return RepoReport(repo.name, OUTCOME_NEEDS_MERGE, [*lines, f"packet: {packet}",
                                                        "merge with Edit, then run with --finish"])


def _saved_copy(repo: Path, path: str) -> Path:
    return _state_dir(repo) / "untracked" / path


def _read(path: Path) -> bytes:
    return path.read_bytes() if path.is_file() else b""


# --- the conflict packet ------------------------------------------------------------------------------


@dataclass(frozen=True)
class Hunk:
    line: int
    local: tuple[str, ...]
    base: tuple[str, ...]
    incoming: tuple[str, ...]


def _text(data: bytes | None) -> str:
    return (data or b"").decode("utf-8", errors="replace")


def conflict_hunks(local: str, base: str, incoming: str, work: Path) -> list[Hunk]:
    """The diff3 conflict hunks of a three-way merge, computed on copies in ``work`` (never the repo)."""
    work.mkdir(parents=True, exist_ok=True)
    files = [work / "local", work / "base", work / "incoming"]
    for path, text in zip(files, (local, base, incoming)):
        path.write_text(text, encoding="utf-8", newline="")
    merged = subprocess.run(["git", "merge-file", "-p", "--diff3", "-L", "local", "-L", "base", "-L", "incoming",
                             *map(str, files)], capture_output=True, check=False, timeout=GIT_TIMEOUT_SECONDS)
    return parse_diff3(merged.stdout.decode("utf-8", errors="replace").splitlines())


def parse_diff3(lines: list[str]) -> list[Hunk]:
    hunks: list[Hunk] = []
    sides: list[list[str]] = []
    start = 0
    for number, line in enumerate(lines, start=1):
        if line.startswith(CONFLICT_START):
            sides, start = [[]], number
        elif sides and line.startswith(CONFLICT_BASE):
            sides.append([])
        elif sides and line == CONFLICT_SPLIT:
            sides.append([])
        elif sides and line.startswith(CONFLICT_END):
            base = sides[1] if len(sides) == 3 else []
            hunks.append(Hunk(start, tuple(sides[0]), tuple(base), tuple(sides[-1])))
            sides = []
        elif sides:
            sides[-1].append(line)
    return hunks


def _marker_lines(path: Path) -> list[int]:
    if not path.is_file():
        return []
    text = path.read_text(encoding="utf-8", errors="replace").splitlines()
    return [number for number, line in enumerate(text, start=1) if line.startswith(CONFLICT_START)]


def _added(side: tuple[str, ...], base: tuple[str, ...]) -> list[str]:
    original = {line.strip() for line in base}
    return [line.strip() for line in side if line.strip() and line.strip() not in original]


class MergeDrafter:
    """A local model's merge of one hunk, checked: it must carry every line either side added."""

    def __init__(self, pool: LocalLlmPool, corpus: TermCorpus, repos: set[str]) -> None:
        self._pool = pool
        self._corpus = corpus
        self._repos = repos

    def draft(self, repo: Path, hunk: Hunk) -> str:
        if repo.name not in self._repos:
            return "no draft: only framework repositories are sent to a local model"
        body = "\n".join(["BASE:", *hunk.base, "LOCAL:", *hunk.local, "INCOMING:", *hunk.incoming])
        if scan_text(body, self._corpus):
            return "no draft: the hunk carries a registered customer term"
        try:
            reply = self._pool.chat(ChatRequest(MERGE_SYSTEM, body, MERGE_TEMPERATURE, MERGE_MAX_TOKENS))
        except LocalLlmUnavailable as exc:
            return f"no draft: no local model answered ({exc})"
        return _checked_draft(reply.text.strip("\n"), hunk)


def _checked_draft(text: str, hunk: Hunk) -> str:
    if text.startswith(EXCLUSIVE):
        return f"model reads the edits as mutually exclusive: {text[len(EXCLUSIVE):].strip()} (B2 if true)"
    merged = {line.strip() for line in text.splitlines()}
    missing = [line for line in _added(hunk.local, hunk.base) + _added(hunk.incoming, hunk.base)
               if line not in merged]
    verdict = ("CHECKED: carries every line both sides added" if not missing
               else "UNCHECKED: drops added line(s): " + " | ".join(missing[:4]))
    return f"draft ({verdict}):\n```\n{text}\n```"


def _fenced(title: str, lines: tuple[str, ...]) -> list[str]:
    return [f"{title}:", "```", *lines, "```"]


def _path_section(repo: Path, state: RepoState, path: str, drafter: MergeDrafter | None) -> list[str]:
    ref = _stash_ref(repo, state.stash_message)
    base = _text(_git_bytes(repo, ["show", f"{ref}^1:{path}"]))
    local = _text(_git_bytes(repo, ["show", f"{ref}:{path}"]))
    incoming = _text(_git_bytes(repo, ["show", f"HEAD:{path}"]))
    hunks = conflict_hunks(local, base, incoming, _state_dir(repo) / "work")
    markers = _marker_lines(repo / path)
    lines = [f"## {path}", "", f"{len(hunks)} hunk(s); conflict markers in the working file at line(s) "
             f"{', '.join(map(str, markers)) or 'none'}.", ""]
    for index, hunk in enumerate(hunks, start=1):
        lines += [f"### Hunk {index}", "", *_fenced("LOCAL", hunk.local), *_fenced("BASE", hunk.base),
                  *_fenced("INCOMING", hunk.incoming)]
        if drafter is not None:
            lines += ["", drafter.draft(repo, hunk)]
        lines.append("")
    return lines


def _untracked_section(repo: Path, path: str) -> list[str]:
    pulled = (repo / path).read_text(encoding="utf-8", errors="replace").splitlines()
    saved = _saved_copy(repo, path).read_text(encoding="utf-8", errors="replace").splitlines()
    diff = difflib.unified_diff(pulled, saved, f"pulled/{path}", f"local/{path}", lineterm="")
    return [f"## {path} (untracked local copy set aside)", "", f"Local copy: `{_saved_copy(repo, path)}`. Merge "
            "its additions into the pulled file.", "", "```diff", *diff, "```", ""]


def write_packet(repo: Path, state: RepoState, conflicted: list[str], differing: list[str],
                 drafter: MergeDrafter | None) -> Path:
    lines = [f"# Conflicts in {repo.name}", "", "For each hunk: replace the marker block in the working file with "
             "text carrying both intents (a draft is a lead; read it against LOCAL and INCOMING). Then run "
             "`resolve-pull.ps1 <repo> -Finish`.", ""]
    for path in conflicted:
        lines += _path_section(repo, state, path, drafter)
    for path in differing:
        lines += _untracked_section(repo, path)
    packet = _state_dir(repo) / "conflicts.md"
    packet.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return packet


# --- finish -------------------------------------------------------------------------------------------


def _missing_local_lines(repo: Path, ref: str, path: str) -> list[str]:
    diff = _git(repo, ["diff", f"{ref}^1", ref, "--", path])
    added = [line[1:].strip() for line in diff.splitlines()
             if line.startswith("+") and not line.startswith("+++") and line[1:].strip()]
    present = {line.strip() for line in _read(repo / path).decode("utf-8", errors="replace").splitlines()}
    return [line for line in added if line not in present]


def _missing_saved_lines(repo: Path, path: str) -> list[str]:
    present = {line.strip() for line in _read(repo / path).decode("utf-8", errors="replace").splitlines()}
    saved = _saved_copy(repo, path).read_text(encoding="utf-8", errors="replace").splitlines()
    return [line.strip() for line in saved if line.strip() and line.strip() not in present]


def _verification_problems(repo: Path, state: RepoState, ref: str, merged: set[str]) -> tuple[list[str], list[str]]:
    """Problems that refuse the drop, and notes that do not."""
    paths = state.stashed + state.untracked_saved
    problems: list[str] = []
    notes: list[str] = []
    marked = _lines(_git_run(repo, ["grep", "-n", *MARKER_PATTERNS, "--", *paths]).stdout.decode("utf-8", "replace")) \
        if paths else []
    problems += [f"conflict marker: {line}" for line in marked]
    for path in state.stashed:
        missing = _missing_local_lines(repo, ref, path)
        target = notes if path in merged else problems
        target += [f"{path}: local line not in the working tree: {line}" for line in missing]
    for path in state.untracked_saved:
        problems += [f"{path}: set-aside local line not in the pulled file: {line}"
                     for line in _missing_saved_lines(repo, path)]
    return problems, notes


def finish_repo(repo: Path, merged: set[str]) -> RepoReport:
    state = _load_state(repo)
    if state is None:
        return RepoReport(repo.name, OUTCOME_NOTHING)
    if _merge_in_progress(repo):
        return RepoReport(repo.name, OUTCOME_NEEDS_MERGE, ["the merge of committed history is not committed yet: "
                                                           "resolve, `git add`, `git commit --no-edit`, then --finish"])
    if not state.applied:
        return _reapply(repo, state, drafter=None)
    if state.stashed:
        _git(repo, ["reset", "-q", "--", *state.stashed])
    ref = _stash_ref(repo, state.stash_message) if state.stashed else ""
    problems, notes = _verification_problems(repo, state, ref, merged) if ref or state.untracked_saved else ([], [])
    if problems:
        return RepoReport(repo.name, OUTCOME_NEEDS_MERGE, [*problems, "nothing dropped; fix these, then --finish "
                                                           "(name a path in --merged when its local line was "
                                                           "deliberately merged with the incoming change)"])
    if ref:
        _git(repo, ["stash", "drop", ref])
    shutil.rmtree(_state_dir(repo))
    return RepoReport(repo.name, OUTCOME_FINISHED, [*notes, *_final_lines(repo, state)])


def _final_lines(repo: Path, state: RepoState) -> list[str]:
    head = _git(repo, ["rev-parse", "--short", "HEAD"]).strip()
    behind = _git(repo, ["rev-list", "--count", f"HEAD..{UPSTREAM}"]).strip()
    before = {line[3:] for line in state.before_status}
    after = {line[3:] for line in _status(repo)}
    lines = [f"HEAD {head}, behind {behind}; shelved and reapplied: {', '.join(state.stashed) or 'none'}"]
    gone = sorted(before - after - set(state.untracked_saved))
    if gone:
        lines.append("no longer modified (local equals incoming, or set aside identical): " + ", ".join(gone))
    return lines


# --- main ---------------------------------------------------------------------------------------------


def _repos(names: list[str]) -> list[Path]:
    found = {repo.name: repo for repo in discover_repos(WORKSPACE_DIR)}
    unknown = [name for name in names if name not in found]
    if unknown:
        raise ResolveError(f"Not git repositories under {WORKSPACE_DIR}: {', '.join(unknown)}. Valid names: "
                           f"{', '.join(sorted(found))}.")
    return [found[name] for name in names] if names else sorted(found.values())


def _drafter(args: argparse.Namespace) -> MergeDrafter | None:
    if args.no_model or args.finish:
        return None
    try:
        corpus = load_workspace_term_corpus(WORKSPACE_DIR)
    except ReadScopeError as exc:
        print(f"No merge drafts: {exc}", file=sys.stderr)
        return None
    pool = LocalLlmPool(wrapper_llm_settings(args), report=lambda line: None)
    return MergeDrafter(pool, corpus, {repo.name for repo in framework_repos(WORKSPACE_DIR)})


def _one(repo: Path, args: argparse.Namespace, drafter: MergeDrafter | None) -> RepoReport:
    try:
        if args.finish:
            return finish_repo(repo, set(args.merged))
        return resolve_repo(repo, drafter)
    except ResolveError as exc:
        return RepoReport(repo.name, OUTCOME_FAILED, [str(exc)])


def build_parser() -> argparse.ArgumentParser:
    """The options of ``git/resolve-pull.ps1``: one per wrapper parameter, spelled exactly."""
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter,
                                     allow_abbrev=False)
    parser.add_argument("positional_repos", nargs="*", metavar="REPO", help="Repository names (as --repo).")
    parser.add_argument("--repo", action="append", default=[],
                        help="Repository name (repeatable). Default: every git repository in the workspace.")
    parser.add_argument("--finish", action="store_true", help="Verify the hand merge, then drop the stash entry")
    parser.add_argument("--merged", action="extend", nargs="*", default=[], help="With --finish: paths whose "
                        "local lines were deliberately merged with the incoming change (reported, not refused)")
    parser.add_argument("--no-model", action="store_true", help="No local-model merge drafts in the packet")
    add_wrapper_llm_arguments(parser, timeout_seconds=LLM_TIMEOUT_SECONDS)
    parser.add_argument("--self-test", action="store_true",
                        help="Run only the wrapper seam checks: the wrapper and its twin are the templates "
                             "rendered with exactly this parser's options.")
    parser.set_defaults(debug=False)
    return parser


def _run(args: argparse.Namespace) -> int:
    if args.self_test:
        return run_self_test([], wrapper=WRAPPER, module=MODULE, parser=build_parser(), folder=GIT_SCRIPTS_DIR)
    try:
        repos = _repos([*args.positional_repos, *args.repo])
    except ResolveError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return EXIT_CANNOT_RUN
    drafter = _drafter(args)
    reports = [_one(repo, args, drafter) for repo in repos]
    for report in reports:
        print(f"{report.name}: {report.outcome}")
        print("".join(f"    {line}\n" for line in report.lines), end="")
    return EXIT_ALL_DONE if all(report.done for report in reports) else EXIT_NEEDS_ATTENTION


def main(argv: Sequence[str] | None = None) -> int:
    """Entry point."""
    return module_main(build_parser(), _run, argv)


if __name__ == "__main__":
    sys.exit(main())
