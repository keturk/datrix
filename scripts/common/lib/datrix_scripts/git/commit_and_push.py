"""Commit every dirty Datrix repo as themed change sets, then push each repo once.

The module behind ``git/commit-and-push.ps1`` (and its ``.sh`` twin).

WHY THEMED SETS RATHER THAN ONE COMMIT PER REPO
    History is read to answer "when did this behavior change?" and "which commit broke
    it?". Sweeping an unrelated fix into a large feature commit hides it, and a message
    covering a dozen unrelated changes cannot fit a short subject. Each repo's dirty
    paths are split by area (see ``theme_of``) -- a generator and its tests share one
    commit, an unrelated docs edit gets another -- capped by ``--max-commits-per-repo``.

MESSAGE SOURCE
    * **Local machines** (preferred) -- the Ollama server on each machine of the local
      network. What each one holds and can load is discovered, never configured. Models
      already in memory are used first; a model is loaded only when none is. A model that
      fails hands over to the next.
    * **Claude Code CLI** -- the ``claude`` command, run as a pure text call with no
      tools. Used when no local host is usable (or ``--message-source claude``).

No intermediate ``commit-messages.json`` file is written.

PRE-STAGE CHECKS
    Customer-domain isolation, ignored source, PolyString case round-trips, design/task
    references and Python lint run across every dirty repo before a message is generated or
    anything is staged; one hit fails the whole run with nothing committed. ``--self-test``
    proves the first of them on a planted customer term (the corpus holds only digests) over
    real repositories in a temporary workspace, and runs the census that no git script runs a
    form that discards local work.

Exit codes: 0 = committed and pushed (or a dry run, a clean workspace, a passing self-test);
1 = a check or git command failed (``ERROR: ...``), or a self-test check failed; 2 = a bad argument.
"""

from __future__ import annotations

import argparse
import contextlib
import io
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Final

from datrix_scripts.customer_domain_isolation import (
    CorpusError,
    Violation,
    corpus_path,
    hash_term,
    load_term_corpus,
    pending_files,
    scan_paths,
    self_test,
)
from datrix_scripts.design_task_references import ReferenceScanError
from datrix_scripts.design_task_references import scan_paths as design_task_scan_paths
from datrix_scripts.design_task_references import self_test as design_task_self_test
from datrix_scripts.ignored_source import (
    IgnoredSourceGateError,
    ShadowedPath,
    StrayTempDir,
    exemption_path,
    load_exemptions,
    load_temp_dir_segment,
    scan_for_commit,
)
from datrix_scripts.ignored_source import self_test as ignored_source_self_test
from datrix_scripts.framework_repos import framework_repos
from datrix_scripts.gate_harness import UsageError, write_files
from datrix_scripts.git.forbidden_forms import check_no_git_script_runs_a_forbidden_form
from datrix_scripts.git.gate_repair import (
    DEFAULT_REPAIR_ATTEMPTS,
    DEFAULT_REPAIR_EFFORT,
    DEFAULT_REPAIR_MODEL,
    DEFAULT_REPAIR_TIMEOUT_MS,
    REPAIR_EFFORTS,
    GateRepairer,
    GateRunError,
    GateViolation,
    check_repair_command_and_prompt,
    check_repair_loop_does_not_repair_other_failures,
    check_repair_loop_gives_up_after_the_last_attempt,
    check_repair_loop_retries_until_the_gate_passes,
    check_repair_loop_with_no_attempts_raises_the_violation_unchanged,
    run_with_repair,
)
from datrix_scripts.local_llm import (
    DEFAULT_GENERATE_TIMEOUT_MS,
    DEFAULT_LOAD_TIMEOUT_MS,
    ChatRequest,
    LocalLlmPool,
    LocalLlmSettings,
    LocalLlmUnavailable,
    add_wrapper_machines_argument,
    wrapper_machines,
)
from datrix_scripts.paths import WORKSPACE_DIR
from datrix_scripts.polystring_case_roundtrip import (
    PolyStringGateError,
    RepoResult,
)
from datrix_scripts.polystring_case_roundtrip import scan_for_commit as polystring_scan_for_commit
from datrix_scripts.polystring_case_roundtrip import self_test as polystring_self_test
from datrix_scripts.python_lint_correctness import (
    Finding as LintFinding,
)
from datrix_scripts.python_lint_correctness import LintGateError
from datrix_scripts.python_lint_correctness import scan_pending as lint_scan_pending
from datrix_scripts.python_lint_correctness import self_test as lint_self_test
from datrix_scripts.test.wrappers import GIT_SCRIPTS_DIR, module_main, run_self_test

MODULE: Final = "datrix_scripts.git.commit_and_push"
WRAPPER: Final = "commit-and-push"
EXIT_FAILED: Final = 1

TEXT_SNIPPET_EXTENSIONS = {
    ".cfg",
    ".dcfg",
    ".dtrx",
    ".ini",
    ".j2",
    ".js",
    ".json",
    ".md",
    ".ps1",
    ".py",
    ".sql",
    ".toml",
    ".ts",
    ".tsx",
    ".txt",
    ".yaml",
    ".yml",
}

# Git identity used for the commits this script creates.
GIT_USER_EMAIL = "kercan@outlook.com"
GIT_USER_NAME = "Kamil Ercan Turkarslan"

# Git's empty tree. Every repository resolves this object without it ever being
# written, which makes it the one diff base available in a repo that has no
# commit yet. See diff_base().
EMPTY_TREE_OBJECT = "4b825dc642cb6eb9a060e54bf8d69288fbee4904"

# Sampling temperature for local models: low, because a commit message should restate
# the diff, not improvise on it. Reasoning stays off (ChatRequest.think defaults to
# False): a commit message needs no visible reasoning, and a reasoning pass multiplies
# generate time.
LOCAL_TEMPERATURE = 0.2

MESSAGE_SOURCE_AUTO = "auto"
MESSAGE_SOURCE_LOCAL = "local"
MESSAGE_SOURCE_CLAUDE = "claude"

# Hard cap on a commit subject. The model is told the limit up front; an overrun is
# regenerated once with the actual length shown, which works where restating the rule
# does not.
SUBJECT_LIMIT = 72

# Themed change sets. A dirty repo is split into one commit per theme so an unrelated
# fix is never buried inside a large feature commit, and so each message describes one
# coherent change and fits a short subject.
REPO_ROOT_THEME = "repo root"
OTHER_THEME = "other changes"

# Directories that hold areas rather than being one. They are stepped through to find
# the theme, so src/<package>/generators/x.py and tests/unit/generators/test_x.py share
# the "generators" theme and a feature lands in one commit with its tests.
THEME_CONTAINER_DIRS = frozenset(
    {"src", "tests", "test", "unit", "unit_core", "integration", "e2e", "scripts", "examples"}
)

# Directory directly under src/ that is the package itself, not an area (src/<package>/...).
SRC_DIR = "src"

# Test-file affixes stripped so tests/unit/test_activation.py joins the "activation"
# theme of src/<package>/activation.py.
TEST_FILE_PREFIX = "test_"
TEST_FILE_SUFFIXES = ("_test", ".test", ".spec")

# A change set's git queries name its paths on the command line. Windows caps a command
# line at ~32K characters, so past this budget the prompt context covers the paths that
# fit and says how many more there are. Staging and committing read the exact path list
# from a file, so they are never narrowed.
MAX_PATHSPEC_CHARS = 20000

# A message-generating backend: (user_prompt, system_prompt) -> raw model text.
Generator = Callable[[str, str], str]


@dataclass(frozen=True)
class ChangeEntry:
    """One dirty path from ``git status``, with every path its commit must include.

    ``stage_paths`` is what ``git commit`` is told to include; ``add_paths`` is the
    subset ``git add`` can match. A path already gone from both disk and index is only
    ever named to ``git commit`` (HEAD still knows it), never to ``git add`` (which
    rejects a path matching nothing). Two records carry such a path: a staged rename
    (``old -> new``), whose old path is committed so its deletion lands with the new
    one, and a staged deletion (index status ``D``), which is already fully staged.
    The converse is a path staged as new and then deleted from disk (``AD``, ``RD``,
    ``CD``): it is only ever named to ``git add``, which unstages it, and never to
    ``git commit``, since neither HEAD nor the index knows it after that add.
    """

    path: str
    stage_paths: tuple[str, ...]
    add_paths: tuple[str, ...]


@dataclass(frozen=True)
class ChangeGroup:
    """One themed change set: what to describe and exactly what to commit."""

    name: str
    entries: tuple[ChangeEntry, ...]

    @property
    def add_paths(self) -> list[str]:
        return list(dict.fromkeys(p for entry in self.entries for p in entry.add_paths))

    @property
    def stage_paths(self) -> list[str]:
        return list(dict.fromkeys(p for entry in self.entries for p in entry.stage_paths))


@dataclass(frozen=True)
class DirtyRepo:
    """Change context for one change set of one repo -- what the model describes."""

    name: str
    path: Path
    branch: str
    porcelain: str
    name_status: str
    diff_stat: str
    diff_sample: str
    untracked_note: str
    scope: str
    scope_files: int
    omitted_files: int


class ScriptError(RuntimeError):
    """Fatal script error."""




def run_git(repo_path: Path, args: list[str], *, check: bool = True) -> str:
    result = subprocess.run(
        ["git", "-c", f"safe.directory={repo_path.as_posix()}", "-C", str(repo_path), *args],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    output = "\n".join(part for part in [result.stdout, result.stderr] if part)
    output = "\n".join(
        line for line in output.splitlines() if not line.lower().startswith("warning:")
    )
    if check and result.returncode != 0:
        raise ScriptError(f"git {' '.join(args)} failed in {repo_path.name}: {output}")
    return output.rstrip()


def truncate_text(text: str, max_chars: int) -> str:
    if not text or len(text) <= max_chars:
        return text
    return text[:max_chars] + "\n[... truncated for prompt size ...]"


def parse_name_status_paths(name_status: str) -> list[str]:
    paths: list[str] = []
    for raw_line in name_status.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        parts = re.split(r"\t+", line)
        if len(parts) < 2:
            continue
        status = parts[0]
        path = parts[-1] if status.startswith("R") or status.startswith("C") else parts[1]
        if path not in paths:
            paths.append(path)
    return paths


def diff_base(repo_path: Path) -> str:
    """The revision to diff a repo's working tree against.

    ``HEAD`` normally. A repo whose first commit has not been made yet has no
    HEAD, and ``git diff HEAD`` fails outright there -- which aborted the whole
    multi-repo run on the one repo whose content is entirely new, before any
    pre-commit check could even be reached. Git's empty tree object exists in
    every repository without being written, so it is the correct base for that
    case: the initial import reads as an all-additions diff instead of an error.
    """
    resolved = run_git(repo_path, ["rev-parse", "--verify", "--quiet", "HEAD"], check=False)
    return "HEAD" if resolved.strip() else EMPTY_TREE_OBJECT


def build_diff_sample(repo_path: Path, name_status: str, max_chars: int, base: str) -> str:
    """Build a balanced diff payload so late files are not lost to prefix truncation."""
    paths = parse_name_status_paths(name_status)
    if not paths:
        return truncate_text(
            run_git(repo_path, ["-c", "core.autocrlf=false", "diff", base]),
            max_chars,
        )

    per_file_limit = max(1800, min(9000, max_chars // max(1, len(paths))))
    sections: list[str] = []
    remaining = max_chars
    for path in paths:
        if remaining <= 0:
            sections.append("[... additional files omitted for prompt size ...]")
            break
        diff = run_git(
            repo_path,
            ["-c", "core.autocrlf=false", "diff", base, "--", path],
            check=False,
        )
        if not diff.strip():
            continue
        section_limit = min(per_file_limit, remaining)
        section = f"--- diff for {path} ---\n{truncate_text(diff, section_limit)}"
        sections.append(section)
        remaining -= len(section) + 2
    return "\n\n".join(sections)


def is_text_path(path: Path) -> bool:
    return path.suffix.lower() in TEXT_SNIPPET_EXTENSIONS


def build_untracked_note(repo_path: Path, untracked_paths: list[str]) -> str:
    if not untracked_paths:
        return ""
    lines = ["", "-- untracked paths and snippets --"]
    for rel in untracked_paths[:30]:
        lines.append(rel)
        file_path = repo_path / rel
        if not is_text_path(file_path) or not file_path.is_file():
            continue
        try:
            text = file_path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        snippet = truncate_text(text.strip(), 2400)
        if snippet:
            lines.append("```")
            lines.append(snippet)
            lines.append("```")
    if len(untracked_paths) > 30:
        lines.append(f"[... {len(untracked_paths) - 30} additional untracked paths omitted ...]")
    return "\n".join(lines)


def find_dirty_repos(workspace_root: Path) -> list[Path]:
    """Return every Datrix repo with uncommitted changes, reporting the clean ones."""
    dirty: list[Path] = []
    for repo_path in framework_repos(workspace_root):
        if run_git(repo_path, ["status", "--porcelain"]).strip():
            dirty.append(repo_path)
        else:
            print(f"{repo_path.name}: clean")
    return dirty


def run_git_stdout(repo_path: Path, args: list[str]) -> str:
    """Return git's stdout byte-for-byte -- for output whose leading whitespace is data.

    ``run_git`` folds stderr in and rstrips, which eats the leading space of the first
    porcelain line: `` M path`` arrives as ``M path`` and the path loses a character.
    Anything parsing ``--porcelain`` columns must come through here.
    """
    result = subprocess.run(
        ["git", "-c", f"safe.directory={repo_path.as_posix()}", "-C", str(repo_path), *args],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    if result.returncode != 0:
        raise ScriptError(
            f"git {' '.join(args)} failed in {repo_path.name}: {(result.stderr or '').strip()}"
        )
    return result.stdout


def survey(repo_path: Path) -> list[ChangeEntry]:
    """Every dirty path in the repo, untracked included, honouring .gitignore.

    This is exactly the set ``git add -A`` would stage, which is what the pre-commit
    checks were run against, so the union of the change sets commits the same content
    a single whole-repo commit would have.
    """
    output = run_git_stdout(
        repo_path,
        ["-c", "core.quotepath=false", "status", "--porcelain=v1", "-z", "--untracked-files=all"],
    )
    # -z: NUL-separated, paths unquoted; a rename/copy record is followed by its source path.
    records = output.split("\0")
    entries: list[ChangeEntry] = []
    index = 0
    while index < len(records):
        record = records[index]
        index += 1
        if not record:
            continue
        status, path = record[:2], record[3:]
        # Staged as new (added, renamed or copied to) but since deleted from disk:
        # ``git add -A`` drops the path from the index, and HEAD never had it, so
        # naming it to ``git commit`` afterwards would match nothing.
        vanishes = status[0] in "ARC" and status[1] == "D"
        new_paths = () if vanishes else (path,)
        if status[0] in "RC" and index < len(records):
            source = records[index]
            index += 1
            entries.append(ChangeEntry(path, (*new_paths, source), (path,)))
        elif status[0] == "A" and vanishes:
            entries.append(ChangeEntry(path, (), (path,)))
        elif status[0] == "D":
            entries.append(ChangeEntry(path, (path,), ()))
        else:
            entries.append(ChangeEntry(path, (path,), (path,)))
    return entries


def theme_stem(filename: str) -> str:
    """A module's theme from its file name: extension and test affixes removed."""
    stem = filename.rsplit(".", 1)[0] if "." in filename.lstrip(".") else filename
    for suffix in TEST_FILE_SUFFIXES:
        if stem.endswith(suffix):
            stem = stem[: -len(suffix)]
            break
    if stem.startswith(TEST_FILE_PREFIX) and len(stem) > len(TEST_FILE_PREFIX):
        stem = stem[len(TEST_FILE_PREFIX) :]
    return stem


def theme_of(path: str) -> str:
    """The area a path belongs to, found by stepping through container directories.

    ``src/<package>/generators/x.py``, ``tests/unit/generators/test_x.py`` -> ``generators``;
    ``src/<package>/activation.py``, ``tests/unit/test_activation.py`` -> ``activation``;
    ``scripts/git/commit-and-push.ps1`` -> ``git``; a file at the repo root -> the root theme.
    """
    parts = [part for part in path.replace("\\", "/").split("/") if part]
    if len(parts) == 1:
        return REPO_ROOT_THEME
    start = 2 if parts[0] == SRC_DIR and len(parts) > 2 else 0
    while start < len(parts) - 1 and parts[start] in THEME_CONTAINER_DIRS:
        start += 1
    remainder = parts[start:]
    return theme_stem(remainder[0]) if len(remainder) == 1 else remainder[0]


def group_changes(entries: list[ChangeEntry], max_commits: int) -> list[ChangeGroup]:
    """Split a repo's dirty paths into themed change sets, capped at ``max_commits``.

    Past the cap, the smallest sets are folded into one so a wide change cannot fan out
    into dozens of one-file commits. Sets are ordered alphabetically with root-level
    files last, since those usually describe the rest.
    """
    buckets: dict[str, list[ChangeEntry]] = {}
    for entry in entries:
        buckets.setdefault(theme_of(entry.path), []).append(entry)
    groups = [ChangeGroup(name, tuple(items)) for name, items in buckets.items()]
    if len(groups) > max_commits:
        by_size = sorted(groups, key=lambda g: (-len(g.entries), g.name))
        kept, folded = by_size[: max_commits - 1], by_size[max_commits - 1 :]
        merged = tuple(entry for group in folded for entry in group.entries)
        print(
            f"  folding {len(folded)} small change set(s) into '{OTHER_THEME}' "
            f"to stay within {max_commits} commits"
        )
        groups = kept + [ChangeGroup(OTHER_THEME, merged)]
    return sorted(
        groups, key=lambda g: (g.name == OTHER_THEME, g.name == REPO_ROOT_THEME, g.name.lower())
    )


def literal_pathspecs_within_budget(paths: list[str]) -> list[str]:
    """Literal pathspecs for as many paths as fit on one command line."""
    specs: list[str] = []
    used = 0
    for path in paths:
        spec = f":(literal){path}"
        if specs and used + len(spec) + 1 > MAX_PATHSPEC_CHARS:
            break
        specs.append(spec)
        used += len(spec) + 1
    return specs


def collect_group(repo_path: Path, group: ChangeGroup, max_diff_chars: int, themed: bool) -> DirtyRepo:
    """Change context for one change set: every git query is scoped to its paths."""
    paths = group.stage_paths
    specs = literal_pathspecs_within_budget(paths)
    limits = ["--", *specs]
    branch = run_git(repo_path, ["branch", "--show-current"], check=False) or "(unknown branch)"
    base = diff_base(repo_path)
    porcelain = run_git(repo_path, ["status", "--porcelain", *limits])
    diff_stat = run_git(repo_path, ["-c", "core.autocrlf=false", "diff", base, "--stat", *limits])
    name_status = run_git(repo_path, ["-c", "core.autocrlf=false", "diff", base, "--name-status", *limits])
    untracked_raw = run_git(repo_path, ["ls-files", "--others", "--exclude-standard", *limits])
    untracked_paths = [line.strip() for line in untracked_raw.splitlines() if line.strip()]
    return DirtyRepo(
        name=repo_path.name,
        path=repo_path,
        branch=branch.strip(),
        porcelain=porcelain.rstrip(),
        name_status=name_status.rstrip(),
        diff_stat=diff_stat.rstrip(),
        diff_sample=build_diff_sample(repo_path, name_status, max_diff_chars, base).rstrip(),
        untracked_note=build_untracked_note(repo_path, untracked_paths),
        scope=group.name if themed else "",
        scope_files=len(group.entries),
        omitted_files=len(paths) - len(specs),
    )


def dirty_repo_bundle(dr: DirtyRepo) -> str:
    parts = [
        f"=== REPO: {dr.name} (branch: {dr.branch}) ===",
        "-- git status --porcelain --",
        dr.porcelain,
        "-- git diff HEAD --name-status --",
        dr.name_status,
        "-- git diff HEAD --stat --",
        dr.diff_stat,
        "-- balanced git diff excerpts --",
        dr.diff_sample,
    ]
    if dr.untracked_note.strip():
        parts.append(dr.untracked_note.rstrip())
    return "\n".join(parts)


def dirty_repo_bundle_lite(dr: DirtyRepo, excerpt_max_chars: int = 3600) -> str:
    parts = [
        f"=== REPO: {dr.name} (branch: {dr.branch}) ===",
        "-- git status --porcelain --",
        dr.porcelain,
        "-- git diff HEAD --name-status --",
        dr.name_status,
        "-- git diff HEAD --stat --",
        dr.diff_stat,
        "-- short diff excerpt --",
        truncate_text(dr.diff_sample, excerpt_max_chars),
    ]
    if dr.untracked_note.strip():
        parts.append(truncate_text(dr.untracked_note.rstrip(), 5000))
    return "\n".join(parts)


def dirty_repo_bundle_paths_only(dr: DirtyRepo) -> str:
    parts = [
        f"=== REPO: {dr.name} (branch: {dr.branch}) ===",
        "-- git status --porcelain --",
        dr.porcelain,
        "-- git diff HEAD --name-status --",
        dr.name_status,
        "-- git diff HEAD --stat --",
        dr.diff_stat,
    ]
    if dr.untracked_note.strip():
        paths_only = [
            line
            for line in dr.untracked_note.splitlines()
            if line and line != "```" and not line.startswith("--")
        ]
        parts.append("-- untracked paths --")
        parts.extend(paths_only[:30])
    return "\n".join(parts)


def resolve_claude_exe() -> str | None:
    """Locate the Claude Code CLI, preferring the cmd/exe shims on Windows."""
    for name in ("claude.cmd", "claude.exe", "claude"):
        path = shutil.which(name)
        if path:
            return path
    return None


# Suppresses the CLI's own commit-attribution section. The commit author is the human running
# this script; strip_attribution_trailers() below removes any trailer a model emits anyway.
CLAUDE_CLI_SETTINGS = json.dumps({"includeCoAuthoredBy": False})


def invoke_claude_generate(
    repo_path: Path,
    model: str,
    prompt: str,
    timeout_ms: int,
    system: str,
) -> str:
    """Generate a commit message with the Claude Code CLI, as a pure text call.

    Everything the model needs is already in ``prompt``, so the call gets no tools at
    all (``--tools ""``). It once ran with ``Bash(git:*)`` under ``acceptEdits`` and
    made the commit itself, returning "Committed as <sha>." as the message -- so the
    capability is removed, not merely discouraged. ``--safe-mode`` and a neutral working
    directory keep the workspace's CLAUDE.md, hooks and skills out of the call, and
    ``--system-prompt`` replaces the coding-agent prompt instead of appending to it.

    The prompt is fed via stdin rather than a ``-p`` argument: a large diff bundle would
    otherwise overflow the OS command-line length limit (~32K characters on Windows).
    """
    exe = resolve_claude_exe()
    if not exe:
        raise ScriptError(
            "Claude Code CLI not found in PATH. Install with "
            "'npm install -g @anthropic-ai/claude-code' or add 'claude' to PATH."
        )
    args = [
        exe,
        "-p",
        "--model",
        model,
        "--output-format",
        "json",
        "--tools",
        "",
        "--safe-mode",
        "--no-session-persistence",
        "--settings",
        CLAUDE_CLI_SETTINGS,
        "--system-prompt",
        system,
    ]
    env = {**os.environ, "NO_COLOR": "1"}
    try:
        with tempfile.TemporaryDirectory(prefix="commit-message-") as neutral_cwd:
            result = subprocess.run(
                args,
                input=prompt,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                cwd=neutral_cwd,
                env=env,
                timeout=max(1, timeout_ms / 1000.0),
            )
    except subprocess.TimeoutExpired as exc:
        raise ScriptError(f"Claude CLI timed out for {repo_path.name}") from exc
    if result.returncode != 0:
        detail = (result.stderr or result.stdout or "").strip()
        raise ScriptError(f"Claude CLI failed ({result.returncode}) for {repo_path.name}: {detail}")
    try:
        data = json.loads(result.stdout)
    except json.JSONDecodeError as exc:
        raise ScriptError(f"Claude CLI returned non-JSON output for {repo_path.name}: {exc}") from exc
    response = data.get("result")
    if not response:
        raise ScriptError(f"Claude CLI returned no .result field for {repo_path.name}")
    return str(response)


# Assistant self-attribution trailers. The commit author is the human running this script, so
# these never belong in the message. Stripped after generation as well as suppressed at the CLI
# (see CLAUDE_CLI_SETTINGS): a model can emit them unprompted, and this pass is backend- and
# CLI-version-independent.
ATTRIBUTION_LINE_PATTERNS = (
    re.compile(r"^\s*co-authored-by:.*noreply@anthropic\.com.*$", re.IGNORECASE),
    re.compile(r"^\s*(?:\W*\s*)?generated with .*claude code.*$", re.IGNORECASE),
)


def strip_attribution_trailers(text: str) -> str:
    kept = [
        line
        for line in text.splitlines()
        if not any(pattern.match(line) for pattern in ATTRIBUTION_LINE_PATTERNS)
    ]
    return "\n".join(kept).strip()


def normalize_message(raw: str) -> str:
    text = re.sub(r"<think>.*?</think>", "", raw, flags=re.DOTALL).strip()
    fence = re.fullmatch(r"```(?:\w+)?\s*\n([\s\S]*?)\n?```", text)
    if fence:
        text = fence.group(1).strip()
    text = text.replace("\r\n", "\n")
    return strip_attribution_trailers(text)


def first_line(text: str) -> str:
    return text.split("\n", 1)[0].strip()


def is_generic_subject(subject: str, repo_name: str) -> bool:
    normalized = re.sub(r"\s+", " ", subject.strip().lower())
    generic_exact = {
        f"update {repo_name.lower()}",
        f"update {repo_name.lower()} files",
        "update files",
        "update code",
        "update source",
        "modify files",
        "modify code",
        "change files",
        "misc updates",
        "various updates",
    }
    if normalized in generic_exact:
        return True
    repoish = re.escape(repo_name.lower())
    return bool(
        re.fullmatch(
            rf"(update|modify|improve|adjust|refactor) ({repoish}|[\w.-]+-repo|repo|repository)",
            normalized,
        )
    )


# Commit messages must be English. Multilingual local models (the default Ollama backend is a
# Qwen build) drift into their other training language mid-paragraph, which produced a committed
# message whose second half was Chinese. A prompt instruction alone does not prevent the drift, so
# any non-Latin script is rejected here: that feeds the retry ladder in request_commit_message()
# and, if drift persists, the deterministic English fallback.
NON_LATIN_SCRIPT_PATTERN = re.compile(
    "["
    "\u0400-\u04ff"  # Cyrillic
    "\u0590-\u05ff"  # Hebrew
    "\u0600-\u06ff"  # Arabic
    "\u0e00-\u0e7f"  # Thai
    "\u3000-\u303f"  # CJK symbols and punctuation
    "\u3040-\u30ff"  # Hiragana and Katakana
    "\u3400-\u4dbf"  # CJK unified ideographs extension A
    "\u4e00-\u9fff"  # CJK unified ideographs
    "\uac00-\ud7af"  # Hangul syllables
    "\uf900-\ufaff"  # CJK compatibility ideographs
    "\uff00-\uffef"  # halfwidth and fullwidth forms
    "]"
)


# A "subject" that reports something the model did rather than describing the change --
# "Committed as b2026ef." was once accepted as a message after the model made the commit
# itself. The model no longer has tools; this rejects the shape regardless of backend.
ACTION_REPORT_SUBJECT_PATTERN = re.compile(
    r"^\s*(committed|pushed|created (a )?commit|staged|done\b|i (have |'ve )?(committed|pushed|created))",
    re.IGNORECASE,
)


def looks_like_path_dump_line(line: str) -> bool:
    stripped = line.strip()
    if stripped.startswith("- "):
        stripped = stripped[2:].strip()
    if not stripped:
        return False
    if re.search(r"(^|[/\\])[\w.-]+\.(py|ps1|md|dtrx|dcfg|j2|ts|tsx|js|json|yml|yaml|toml|sql)\b", stripped):
        return True
    return bool(re.match(r"^[\w.-]+[/\\][\w./\\-]+(?:\s+\([A-Z?]+\))?$", stripped))


def message_quality_problem(text: str, repo_name: str) -> str | None:
    if not text.strip():
        return "empty output"
    if NON_LATIN_SCRIPT_PATTERN.search(text):
        return "output is not written in English"
    if len(text) > 3200:
        return "message is too long"
    subject = first_line(text)
    if not subject:
        return "missing subject"
    if subject.startswith("- "):
        return "subject is a bullet path, not a summary"
    if is_generic_subject(subject, repo_name):
        return "subject is too generic"
    if ACTION_REPORT_SUBJECT_PATTERN.match(subject):
        return "subject reports an action taken instead of describing the change"

    lowered = text.strip().lower()
    chatty_prefixes = (
        "you're ",
        "you are ",
        "it looks ",
        "here's ",
        "here is ",
        "below is ",
        "the following ",
        "this diff ",
        "this code ",
        "this script ",
        "based on ",
        "###",
        "## ",
        "let me know",
        "i'm happy to",
        "would you like",
        "please provide",
        "i can help",
        "need help with",
    )
    if lowered.startswith(chatty_prefixes):
        return "chat-style explanation"
    lines = [line.rstrip() for line in text.splitlines()]
    bullet_lines = [line for line in lines if line.lstrip().startswith("- ")]
    if len(bullet_lines) > 6:
        return "too many bullet lines"
    if bullet_lines and sum(1 for line in bullet_lines if looks_like_path_dump_line(line)) >= max(2, len(bullet_lines) // 2):
        return "file path dump instead of semantic description"
    non_empty_body_lines = [line for line in lines[1:] if line.strip()]
    if non_empty_body_lines and sum(1 for line in non_empty_body_lines if looks_like_path_dump_line(line)) >= max(2, len(non_empty_body_lines) // 2):
        return "file path dump instead of semantic description"
    if any(re.match(r"^\s*\d+\.\s+", line) for line in lines):
        return "numbered analysis list instead of commit message"
    if any(re.match(r"^\s*[*-]\s+\*\*", line) for line in lines):
        return "markdown analysis bullets instead of commit message"
    head = lowered[:1200]
    if re.search(
        r"(comparing two|version control system|pasted a large|your message|"
        r"provided git|git output|git diff output|summary of the changes|"
        r"summary of the test files|here's a breakdown|key features:|"
        r"prerequisites:|sample output|in essence|"
        r"\*\*usage:\*\*|\*\*dependencies:\*\*)",
        head,
    ):
        return "analysis prose instead of commit message"
    return None


def fallback_commit_message(dr: DirtyRepo) -> str:
    """Last-resort message when no backend produced a usable one.

    It states only what git itself reports -- the area and the counts -- and says it was
    written without a model. It never guesses at intent: a canned feature description
    chosen by keyword once committed claims about changes that were never made.
    """
    statuses = [line.split("\t", 1)[0][:1] for line in dr.name_status.splitlines() if "\t" in line]
    untracked = sum(
        1 for line in dr.untracked_note.splitlines() if line and line != "```" and not line.startswith("--")
    )
    counts = {
        "modified": statuses.count("M"),
        "added": statuses.count("A") + untracked,
        "deleted": statuses.count("D"),
        "renamed": statuses.count("R"),
    }
    summary = ", ".join(f"{count} {label}" for label, count in counts.items() if count)
    area = dr.scope or dr.name
    subject = f"Update {area}: {dr.scope_files} file(s)"
    body = (
        f"Changes in {area}: {summary or f'{dr.scope_files} file(s)'}. This message was written "
        "without a language model because no backend produced a usable one; the diff is the "
        "authoritative description."
    )
    return subject + "\n\n" + body


def scope_note(dr: DirtyRepo) -> str:
    if not dr.scope:
        return ""
    omitted = (
        f" The git output below covers the first {dr.scope_files - dr.omitted_files}; "
        f"{dr.omitted_files} more are in the same set."
        if dr.omitted_files
        else ""
    )
    return (
        f"This commit covers the '{dr.scope}' change set ONLY -- {dr.scope_files} file(s).{omitted} "
        "Describe that set and nothing else; the rest of the working tree is committed separately.\n"
    )


def build_user_prompt(dr: DirtyRepo, bundle: str, repair_reason: str | None = None) -> str:
    retry = ""
    if repair_reason:
        retry = (
            f"\nPrevious output was rejected because: {repair_reason}.\n"
            "Write a concrete subject that names the feature, behavior, or contract changed.\n"
        )
    return (
        f"Repository folder name: {dr.name}\n"
        f"{scope_note(dr)}"
        f"{retry}\n"
        "Machine-readable git output only. Write the commit message from this data; "
        "do not describe the format of the data.\n\n"
        "<<<GIT_OUTPUT>>>\n"
        f"{bundle}\n"
        "<<<END_GIT_OUTPUT>>>\n"
    )


SYSTEM_PROMPT = f"""You output ONLY the body of one git commit message. You are not a tutor or reviewer.

Write the entire message in English. Every sentence, including the body, must be English even when GIT_OUTPUT contains other languages. Never switch language part-way through.

GIT_OUTPUT may contain source files and automation scripts. Never write a walkthrough, feature list, README, or "what this script does" article. Never say "the script you've provided" or similar. Write a git log entry: what changed, in imperative mood.

Forbidden in your output: addressing the reader; markdown headings; fenced code blocks; questions; suggestions; tables; explaining what git or a diff is.

Never sign the message or credit yourself. Emit no trailer of any kind: no "Co-Authored-By", no "Generated with", no tool or model attribution. The commit author is the human running this script, and any such line overrides earlier instructions you may hold about signing commits.

Required shape:
Line 1: one short, concrete summary of the semantic change, {SUBJECT_LIMIT} characters or fewer. Name the single most important change; detail belongs in the body. Do not use a generic subject like "Update repo" or a path-only subject.
Line 2: completely empty.
Lines 3+: one short paragraph, 1 to 4 sentences, describing what behavior, contract, validation, generation, or workflow changed and why it matters. Prefer prose over bullets.

Do not list filenames or paths. Git already records changed files. Mention a module or product area only when it explains the behavior, such as "service access parsing" or "product catalog endpoints".

Bullets are allowed only when there are separate semantic areas to describe, and then max 4 bullets. Never use bullets that are just file paths. Whole message max 3200 characters.
"""


def request_commit_message(dr: DirtyRepo, generate: Generator) -> str:
    """Drive the chosen backend through escalating bundles until output passes QA."""
    attempts = [
        ("full", dirty_repo_bundle(dr), SYSTEM_PROMPT),
        (
            "repair-full",
            dirty_repo_bundle(dr),
            SYSTEM_PROMPT
            + "\nIf the prior message was generic or path-only, replace it with a specific semantic summary and prose body. Do not list files.\n",
        ),
        (
            "lite",
            dirty_repo_bundle_lite(dr),
            SYSTEM_PROMPT + "\nGIT_OUTPUT is shortened. Infer intent from paths, stat, snippets, and excerpts, but do not repeat file paths in the output.\n",
        ),
        (
            "paths-only",
            dirty_repo_bundle_paths_only(dr),
            SYSTEM_PROMPT + "\nGIT_OUTPUT has path lists and stats only. Still write a concrete best-effort subject and prose body. Do not output the paths.\n",
        ),
    ]
    last_problem: str | None = None
    for label, bundle, system in attempts:
        if last_problem:
            print(f"Warning: {dr.name} [{dr.scope or 'all'}] retrying with {label}: {last_problem}", file=sys.stderr)
        raw = generate(build_user_prompt(dr, bundle, last_problem), system)
        message = normalize_message(raw)
        problem = message_quality_problem(message, dr.name)
        if problem is None:
            return enforce_subject_limit(dr, message, generate)
        last_problem = problem

    print(
        f"Warning: {dr.name} [{dr.scope or 'all'}] model output still unusable; "
        "using the model-free fallback message.",
        file=sys.stderr,
    )
    return fallback_commit_message(dr)


def enforce_subject_limit(dr: DirtyRepo, message: str, generate: Generator) -> str:
    """Ask once for a shorter subject when it overruns, showing the model the overrun.

    Stating the limit is in the prompt already; showing the actual length is what gets a
    model to cut. This is a targeted rewrite of an otherwise good message, not a trip back
    down the retry ladder, whose later rungs throw away diff context. A rewrite that is
    still over the limit but shorter is kept; the overrun is reported either way.
    """
    subject = first_line(message)
    if len(subject) <= SUBJECT_LIMIT:
        return message
    print(f"  subject is {len(subject)} chars (limit {SUBJECT_LIMIT}) -- asking for a shorter one")
    prompt = (
        f"You wrote this commit message:\n\n{message}\n\n"
        f"Its subject line is {len(subject)} characters; the hard limit is {SUBJECT_LIMIT}. "
        "Rewrite the WHOLE commit message with a shorter subject. Cut detail out of the subject "
        "and move it into the body -- do not abbreviate words or drop vowels. Output only the "
        "commit message."
    )
    shorter = normalize_message(generate(prompt, SYSTEM_PROMPT))
    if message_quality_problem(shorter, dr.name) is None and len(first_line(shorter)) < len(subject):
        message, subject = shorter, first_line(shorter)
    if len(subject) > SUBJECT_LIMIT:
        print(
            f"Warning: {dr.name} [{dr.scope or 'all'}] subject is still {len(subject)} chars "
            f"(limit {SUBJECT_LIMIT}); committing it as written.",
            file=sys.stderr,
        )
    return message


def make_local_generator(args: argparse.Namespace, pool: LocalLlmPool) -> Generator:
    """Bind the local pool to a (prompt, system) -> text callable; the pool fails over itself."""
    return lambda prompt, system: pool.chat(
        ChatRequest(
            system=system,
            user=prompt,
            temperature=LOCAL_TEMPERATURE,
            max_tokens=args.local_max_tokens,
        )
    ).text


def make_claude_generator(args: argparse.Namespace, dr: DirtyRepo) -> Generator:
    """Bind the Claude Code CLI to a (prompt, system) -> text callable for one repo."""
    return lambda prompt, system: invoke_claude_generate(
        repo_path=dr.path,
        model=args.claude_model,
        prompt=prompt,
        timeout_ms=args.claude_timeout_ms,
        system=system,
    )


def describe_backend(args: argparse.Namespace, pool: LocalLlmPool | None) -> str:
    """Name the backend the next change set will be sent to; ``None`` is the Claude Code CLI."""
    if pool is not None:
        return pool.activate().label()
    return f"Claude Code CLI model '{args.claude_model}'"


def generate_message_with_failover(
    dr: DirtyRepo, args: argparse.Namespace, pool: LocalLlmPool | None
) -> tuple[str, LocalLlmPool | None]:
    """Generate one change set's message, returning it with the backend for the next set.

    A local server that fails is dropped by the pool -- for this set and the remaining
    ones, since the cause is server-side and persistent -- and the next one takes over.
    Once none is left, auto mode hands this and every remaining set to the Claude Code
    CLI; a forced ``local`` source fails loudly instead of silently leaving the local
    models.
    """
    if pool is not None:
        try:
            return request_commit_message(dr, make_local_generator(args, pool)), pool
        except LocalLlmUnavailable as exc:
            if args.message_source == MESSAGE_SOURCE_LOCAL:
                raise ScriptError(
                    f"Every usable local host failed for {dr.name} and --message-source=local "
                    f"was forced. {exc}"
                ) from exc
            print(
                f"Warning: no local model is left for {dr.name}: {exc}\n"
                f"Switching to {describe_backend(args, None)} for this and the remaining "
                "change sets.",
                file=sys.stderr,
            )
    return request_commit_message(dr, make_claude_generator(args, dr)), None


def decide_backend(args: argparse.Namespace) -> LocalLlmPool | None:
    """Resolve the local pool to use, readied; ``None`` means the Claude Code CLI."""
    if args.message_source == MESSAGE_SOURCE_CLAUDE:
        print(f"Using {describe_backend(args, None)}.")
        return None

    pool = LocalLlmPool(commit_message_llm_settings(args), report=print)
    try:
        pool.activate()
    except LocalLlmUnavailable as exc:
        if args.message_source == MESSAGE_SOURCE_LOCAL:
            raise ScriptError(
                f"{exc} --message-source=local was forced; start a server, pass other machines "
                "(-LocalMachines / --local-machines), or use message source auto or claude."
            ) from exc
        print(f"No local host usable -- falling back to {describe_backend(args, None)}.")
        return None
    return pool


def set_git_identity() -> None:
    subprocess.run(["git", "config", "--global", "user.email", GIT_USER_EMAIL], check=False)
    subprocess.run(["git", "config", "--global", "user.name", GIT_USER_NAME], check=False)


def clean_git_locks(repo_path: Path) -> None:
    git_dir = repo_path / ".git"
    if not git_dir.exists():
        return
    for lock in git_dir.rglob("*.lock"):
        try:
            lock.unlink()
        except OSError:
            pass


def run_git_with_files(repo_path: Path, args: list[str], files: dict[str, str]) -> subprocess.CompletedProcess[str]:
    """Run git with arguments that name temp files holding ``files``' contents.

    ``args`` refers to each file by its key in ``{}``-format placeholders. The pathspec
    list goes through a FILE, never argv: a regenerated tree is thousands of paths and
    would overflow the Windows command-line limit.
    """
    with tempfile.TemporaryDirectory(prefix="commit-and-push-") as temp_dir:
        paths: dict[str, str] = {}
        for key, content in files.items():
            file_path = Path(temp_dir) / key
            file_path.write_text(content, encoding="utf-8", newline="\n")
            paths[key] = str(file_path)
        return subprocess.run(
            ["git", "-C", str(repo_path), *(arg.format(**paths) for arg in args)],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
        )


def commit_group(repo_path: Path, group: ChangeGroup, message: str) -> str | None:
    """Stage and commit exactly one change set. Returns the short sha, or None if empty.

    ``git add -A`` over the set's literal pathspecs stages its additions, edits and
    deletions. ``git commit --pathspec-from-file`` then commits ONLY those paths (git's
    ``--only`` semantics), so anything else already sitting in the index -- another set,
    or something staged by hand -- can never ride along in this commit.
    """
    name = repo_path.name
    pathspecs = "\n".join(f":(literal){path}" for path in group.stage_paths) + "\n"
    # A set made only of staged deletions has nothing to add, and an empty pathspec
    # file would make ``git add -A`` stage the whole tree.
    if group.add_paths:
        add_specs = "\n".join(f":(literal){path}" for path in group.add_paths) + "\n"
        add = run_git_with_files(
            repo_path, ["add", "-A", "--pathspec-from-file={specs}"], {"specs": add_specs}
        )
        if add.returncode != 0:
            raise ScriptError(
                f"{name}: git add failed for '{group.name}' ({add.returncode}): {add.stderr or add.stdout}"
            )
    # A set made only of paths staged as new and since deleted nets to no change once
    # the add has unstaged them, and an empty pathspec file would make ``git commit``
    # take the whole index.
    if not group.stage_paths:
        return None
    commit = run_git_with_files(
        repo_path,
        ["commit", "-F", "{message}", "--pathspec-from-file={specs}"],
        {"message": message, "specs": pathspecs},
    )
    if commit.returncode == 1 and "nothing" in (commit.stdout + commit.stderr).lower():
        return None
    if commit.returncode != 0:
        raise ScriptError(
            f"{name}: git commit failed for '{group.name}' ({commit.returncode}): "
            f"{commit.stderr or commit.stdout}"
        )
    return run_git(repo_path, ["rev-parse", "--short", "HEAD"])


def push_repo(repo_path: Path) -> None:
    push = subprocess.run(
        ["git", "-C", str(repo_path), "push"],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    if push.returncode != 0:
        raise ScriptError(
            f"{repo_path.name}: git push failed ({push.returncode}): {push.stderr or push.stdout}"
        )


def enforce_customer_domain_isolation(dirty_repos: list[Path], datrix_root: Path) -> None:
    """Refuse the whole run if any pending change carries a registered customer term.

    This is the seam where content actually enters a framework repo: every
    commit in every Datrix repo goes through the ``git add -A`` below. Customer
    and project domain language must never reach one of these repos, and prose
    alone did not stop it -- customer cloud-resource names and paths into a
    customer checkout were committed to a settings file through Claude Code
    permission entries that nobody re-read.

    Checked BEFORE a message is generated or anything is staged, and across ALL
    dirty repos at once: a violation in the last repo must not leave the first
    four already pushed. See ``dev/customer_domain_isolation.py`` for why the
    term corpus holds digests rather than terms, and why reported excerpts are
    redacted.
    """
    failures = self_test()
    if failures:
        raise ScriptError(
            "Customer-domain isolation scanner failed its own self-test, so its verdict "
            "cannot be trusted and no commit is safe to make: " + "; ".join(failures)
        )

    try:
        corpus = load_term_corpus(corpus_path(datrix_root))
    except CorpusError as exc:
        raise ScriptError(f"Customer-domain isolation check could not run: {exc}") from exc

    if corpus.is_empty:
        print(
            "Customer-domain isolation NOT ENFORCED: zero terms registered in "
            f"{corpus_path(datrix_root)}."
        )
        return

    violations: list[Violation] = []
    for repo_path in dirty_repos:
        try:
            violations.extend(scan_paths(repo_path, pending_files(repo_path), corpus))
        except CorpusError as exc:
            raise ScriptError(f"Customer-domain isolation check failed in {repo_path.name}: {exc}") from exc

    if not violations:
        print(f"Customer-domain isolation: clean across {len(dirty_repos)} dirty repo(s).")
        return

    detail = "\n".join(f"  {violation.render()}" for violation in violations)
    raise ScriptError(
        f"Customer-domain isolation FAILED: {len(violations)} pending occurrence(s) of a "
        f"registered customer term. Nothing was committed or pushed. Customer domain "
        f"language must not enter a framework repo -- remove it at the source, then re-run. "
        f"(The matched token is redacted; open the file:line to see it.)\n" + detail
    )


def enforce_ignored_source(dirty_repos: list[Path], datrix_root: Path) -> None:
    """Refuse the whole run if a `.gitignore` rule keeps a source file out of the commit.

    Same seam as the isolation check above, asked in the opposite direction:
    that one asks what a ``git add -A`` must not carry IN, this one asks what it
    silently leaves OUT. An unanchored stock pattern once swallowed a package's
    shipped templates -- the files sat on disk, every test passed, the emitted
    output compiled, and the loss only appeared after a clone, by which point
    the templates were absent from history. ``git add -A`` is where that
    decision is actually made, so this is where it is checked.

    Checked BEFORE a message is generated or anything is staged, and across ALL
    dirty repos at once: a package silently losing a file must not be pushed
    that way because the repo before it committed cleanly. Scoped to the dirty
    repos this run is about to commit -- a clean repo is not this run's
    business, and scanning it would cost time the commit path should not spend.

    See ``test/ignored_source.py`` for why git itself is the oracle and why
    exemptions are scoped to a path rather than granted per rule.
    """
    try:
        exemptions = load_exemptions(exemption_path(datrix_root))
        temp_dir_segment = load_temp_dir_segment(datrix_root)
    except IgnoredSourceGateError as exc:
        raise ScriptError(f"Ignored-source check could not run: {exc}") from exc

    try:
        failures = ignored_source_self_test(exemptions, temp_dir_segment)
    except IgnoredSourceGateError as exc:
        raise ScriptError(f"Ignored-source check could not run its self-test: {exc}") from exc
    if failures:
        raise ScriptError(
            "Ignored-source scanner failed its own non-vacuity self-test, so its verdict "
            "cannot be trusted and no commit is safe to make: " + "; ".join(failures)
        )

    shadowed: list[ShadowedPath] = []
    strays: list[tuple[StrayTempDir, Path]] = []
    for repo_path in dirty_repos:
        try:
            result = scan_for_commit(repo_path, exemptions, temp_dir_segment)
        except IgnoredSourceGateError as exc:
            raise ScriptError(f"Ignored-source check failed in {repo_path.name}: {exc}") from exc
        shadowed.extend(result.violations)
        strays.extend((stray, repo_path) for stray in result.stray_temp_dirs)

    # A stray temp directory is a warning, not a refusal: its contents are
    # already unpublishable, so the commit loses nothing. It is reported once
    # per directory with the delete command, because to this scan's raw output
    # a generated project left inside a repo looks like hundreds of shadowed
    # source files whose "fix" would be an ignore-rule edit or an exemption --
    # both wrong, since the directory should not exist at all.
    if strays:
        print(
            f"Ignored-source: WARNING -- {len(strays)} stray temp director(ies) inside the "
            f"repos being committed. Temp output belongs under D:\\datrix\\.tmp, .scripts or "
            f".test-output, never inside a repo. Not exemptable; delete them:"
        )
        for stray, repo_path in strays:
            print(f"  {stray.render(repo_path)}")

    if not shadowed:
        print(f"Ignored-source: clean across {len(dirty_repos)} dirty repo(s).")
        return

    detail = "\n".join(f"  {entry.render()}" for entry in shadowed)
    raise ScriptError(
        f"Ignored-source check FAILED: {len(shadowed)} file(s) are present on disk but a "
        f".gitignore rule stops 'git add -A' from staging them. Nothing was committed or "
        f"pushed. Committing now would publish a package missing these files, and the loss "
        f"is invisible until someone clones it -- fix the named .gitignore line (anchor the "
        f"pattern to the repo root as '/PATTERN', or narrow it), or, if the output is "
        f"deliberately unpublished, add a scoped entry with a written reason to "
        f"{exemption_path(datrix_root)}.\n"
        + detail
    )


def enforce_polystring_case_roundtrips(dirty_repos: list[Path]) -> None:
    """Refuse the whole run if a pending file re-cases a name through plain text.

    Same seam as the two checks above: ``git add -A`` is where a
    ``to_snake_case(str(node.name))`` -- or its two-step spelling,
    ``x = str(node.name)`` then ``to_snake_case(x)`` -- becomes part of a
    framework package. Every name the generator re-cases is a PolyString that
    already carries ``.snake``/``.pascal``/... ; the round trip throws the
    variants away and hides that the value was a name. A Semgrep rule named
    the shape and it still spread to more than a thousand sites, because an
    advisory nobody has to run is the same as no rule. This one runs on every
    commit and is held at a hard zero with no exemption file.

    Checked BEFORE a message is generated or anything is staged, and across
    ALL dirty repos at once, so a hit in the last repo cannot leave the first
    four already pushed. See ``test/polystring_case_roundtrip.py`` for the
    four shapes and the fix each one wants.
    """
    failures = polystring_self_test()
    if failures:
        raise ScriptError(
            "PolyString case round-trip scanner failed its own non-vacuity self-test, so "
            "its verdict cannot be trusted and no commit is safe to make: "
            + "; ".join(failures)
        )

    results: list[RepoResult] = []
    for repo_path in dirty_repos:
        try:
            results.append(polystring_scan_for_commit(repo_path))
        except PolyStringGateError as exc:
            raise ScriptError(
                f"PolyString case round-trip check failed in {repo_path.name}: {exc}"
            ) from exc

    violating = [result for result in results if result.hits]
    if not violating:
        print(f"PolyString case round-trips: clean across {len(dirty_repos)} dirty repo(s).")
        return

    total = sum(len(result.hits) for result in violating)
    detail = "\n".join(
        f"  {hit.render()}" for result in violating for hit in result.hits
    )
    raise GateViolation(
        "PolyString case round-trip",
        f"PolyString case round-trip check FAILED: {total} pending call(s) re-case a name "
        f"through plain text. Nothing was committed or pushed. Read the case variant off "
        f"the PolyString (.snake/.camel/.pascal/.kebab/.screaming_snake/.simple) instead of "
        f"str()-ing it and calling a to_*_case function; if the value is genuinely plain "
        f"text, drop the str() -- case functions accept any str.\n" + detail,
    )


def enforce_design_task_references(dirty_repos: list[Path]) -> None:
    """Refuse the whole run if a pending file cites a design doc, a task file or an item label.

    Design documents and task files are gitignored and numbered per machine, so
    a committed reference to one -- a task id, a design number, or a lettered
    item label in parentheses or before a colon, in code -- points at nothing
    after a clone, or at a different artifact. ``git add -A`` is where such a reference
    becomes part of history, so this runs the reference gate's own scan, with
    its roots and scopes applied per file, over every dirty repo's pending
    changes. There is no skip switch: a reference cannot be committed.

    Checked BEFORE a message is generated or anything is staged, and across ALL
    dirty repos at once. See ``test/design_task_references.py`` for the shapes.
    """
    if design_task_self_test(quiet=True) != 0:
        raise ScriptError(
            "Design/task reference scanner failed its own non-vacuity self-test, so its "
            "verdict cannot be trusted and no commit is safe to make."
        )

    hits: list[tuple[str, int, str, str]] = []
    for repo_path in dirty_repos:
        workspace_relative = [f"{repo_path.name}/{path}" for path in pending_files(repo_path)]
        try:
            hits.extend(design_task_scan_paths(workspace_relative, str(repo_path.parent)))
        except ReferenceScanError as exc:
            raise ScriptError(f"Design/task reference check failed in {repo_path.name}: {exc}") from exc

    if not hits:
        print(f"Design/task references: clean across {len(dirty_repos)} dirty repo(s).")
        return

    detail = "\n".join(f"  [{label}] {rel}:{lineno}: {line}" for rel, lineno, label, line in hits)
    raise GateViolation(
        "Design/task reference",
        f"Design/task reference check FAILED: {len(hits)} pending line(s) cite a design "
        f"document, a task file or an item label. Nothing was committed or pushed. Those "
        f"files are gitignored and numbered per machine, so the reference dangles after a "
        f"clone. Describe the WORK, not the ticket.\n" + detail,
    )


def enforce_python_lint_correctness(dirty_repos: list[Path]) -> None:
    """Refuse the whole run if a pending ``.py`` file carries a lint finding.

    Same seam as the checks above: ``git add -A`` is where an unused import, an
    undefined name, a test function shadowed by a same-named redefinition (the
    first definition never runs), or a top-level def/class missing its two blank
    lines (E302/E305) becomes part of a framework package. Only each
    dirty repo's pending ``.py`` files are linted, from that repo's root so its own
    ``per-file-ignores`` apply -- the per-change form of "lint only the files you
    edited", enforced rather than remembered. There is no skip switch: a finding
    that is genuinely required is suppressed on its own line with
    ``# noqa: <code>`` and the reason.

    Checked BEFORE a message is generated or anything is staged, and across ALL
    dirty repos at once, so a finding in the last repo cannot leave the first four
    already pushed. See ``test/python_lint_correctness.py``.
    """
    failures = lint_self_test(sys.executable)
    if failures:
        raise ScriptError(
            "Python lint-correctness scanner failed its own non-vacuity self-test, so its "
            "verdict cannot be trusted and no commit is safe to make: " + "; ".join(failures)
        )

    findings: list[tuple[Path, LintFinding]] = []
    for repo_path in dirty_repos:
        try:
            found = lint_scan_pending(sys.executable, repo_path, pending_files(repo_path))
        except LintGateError as exc:
            raise ScriptError(
                f"Python lint-correctness check failed in {repo_path.name}: {exc}"
            ) from exc
        findings.extend((repo_path, finding) for finding in found)

    if not findings:
        print(f"Python lint-correctness: clean across {len(dirty_repos)} dirty repo(s).")
        return

    detail = "\n".join(f"  {repo.name}/{finding.render()}" for repo, finding in findings)
    raise GateViolation(
        "Python lint-correctness",
        f"Python lint-correctness check FAILED: {len(findings)} lint finding(s) in pending "
        f"files. Nothing was committed or pushed. Fix the code (delete the unused import, "
        f"import the undefined name, rename the shadowing definition, put two blank lines "
        f"before and after each top-level def/class); if a finding is "
        f"genuinely required, suppress it on its own line with `# noqa: <code>` and the "
        f"reason.\n" + detail,
    )


def commit_message_llm_settings(args: argparse.Namespace) -> LocalLlmSettings:
    """The local-model settings of ``--local-machines``, ``--local-timeout-ms`` and
    ``--local-load-timeout-ms``; any model in memory (else the load preference), and the shared
    reachability and keep-alive windows."""
    return LocalLlmSettings(
        machines=wrapper_machines(args),
        load_timeout_ms=args.local_load_timeout_ms,
        generate_timeout_ms=args.local_timeout_ms,
    )


def build_parser() -> argparse.ArgumentParser:
    """The options of ``git/commit-and-push.ps1``: one per wrapper parameter, spelled exactly."""
    parser = argparse.ArgumentParser(
        description="Commit every dirty Datrix repo as themed change sets, then push each repo once.",
        allow_abbrev=False,
    )
    parser.add_argument(
        "--message-source",
        choices=[MESSAGE_SOURCE_AUTO, MESSAGE_SOURCE_LOCAL, MESSAGE_SOURCE_CLAUDE],
        default=MESSAGE_SOURCE_AUTO,
        help=(
            "Backend for commit messages: auto (the first usable local host, else Claude), "
            "or force one."
        ),
    )
    local = add_wrapper_machines_argument(parser)
    local.add_argument(
        "--local-timeout-ms",
        type=int,
        default=DEFAULT_GENERATE_TIMEOUT_MS,
        help=f"Timeout for each request to a ready model (default: {DEFAULT_GENERATE_TIMEOUT_MS}).",
    )
    local.add_argument(
        "--local-load-timeout-ms",
        type=int,
        default=DEFAULT_LOAD_TIMEOUT_MS,
        help=(
            "Timeout for loading an Ollama model into memory before its first request "
            f"(default: {DEFAULT_LOAD_TIMEOUT_MS})."
        ),
    )
    parser.add_argument(
        "--local-max-tokens",
        type=int,
        default=896,
        help="Maximum tokens a local model may generate for one message.",
    )
    parser.add_argument("--claude-model", default="sonnet")
    parser.add_argument("--claude-timeout-ms", type=int, default=300000)
    parser.add_argument(
        "--max-diff-chars-per-commit",
        type=int,
        default=45000,
        help="Maximum characters of diff context sent to the model for one change set.",
    )
    parser.add_argument(
        "--max-commits-per-repo",
        type=int,
        default=8,
        help=(
            "Upper bound on themed commits per repo; past it the smallest change sets are "
            "folded into one. 1 commits each repo as a single change."
        ),
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Generate and print commit messages but do not commit or push.",
    )
    parser.add_argument(
        "--skip-customer-domain-check",
        action="store_true",
        help=(
            "Skip the customer-domain isolation check. Only for a confirmed false positive: "
            "the check is what keeps customer names out of the framework repos."
        ),
    )
    parser.add_argument(
        "--skip-ignored-source-check",
        action="store_true",
        help=(
            "Skip the ignored-source check. Only for a confirmed false positive: the check "
            "is what keeps a .gitignore rule from silently deleting a package's source from "
            "every clone."
        ),
    )
    parser.add_argument(
        "--skip-poly-string-case-check",
        dest="skip_polystring_case_check",
        action="store_true",
        help=(
            "Skip the PolyString case round-trip check. Only for a confirmed false positive: "
            "the check is what keeps to_*_case(str(name)) out of the framework repos."
        ),
    )
    parser.add_argument(
        "--gate-repair-attempts",
        type=int,
        default=DEFAULT_REPAIR_ATTEMPTS,
        help=(
            "How many times a failed lint, PolyString or design/task-reference gate is handed to "
            "a Claude agent to fix before the checks are re-run; 0 reports the failure and ends "
            f"the run instead (default: {DEFAULT_REPAIR_ATTEMPTS}). A dry run never repairs."
        ),
    )
    parser.add_argument(
        "--gate-repair-model",
        default=DEFAULT_REPAIR_MODEL,
        help=f"Claude model of the gate repair agent (default: {DEFAULT_REPAIR_MODEL}).",
    )
    parser.add_argument(
        "--gate-repair-effort",
        choices=REPAIR_EFFORTS,
        default=DEFAULT_REPAIR_EFFORT,
        help=f"Effort level of the gate repair agent (default: {DEFAULT_REPAIR_EFFORT}).",
    )
    parser.add_argument(
        "--gate-repair-timeout-ms",
        type=int,
        default=DEFAULT_REPAIR_TIMEOUT_MS,
        help=f"Timeout for each gate repair agent run (default: {DEFAULT_REPAIR_TIMEOUT_MS}).",
    )
    parser.add_argument(
        "--self-test",
        action="store_true",
        help=(
            "Prove the customer-domain check fails the whole run on a planted term, over real "
            "repositories in a temporary workspace, and run the forbidden-forms census."
        ),
    )
    parser.set_defaults(debug=False)
    return parser


def commit_repo(
    repo_path: Path, args: argparse.Namespace, pool: LocalLlmPool | None
) -> LocalLlmPool | None:
    """Commit one repo as themed change sets, then push once. Returns the backend still in play."""
    groups = group_changes(survey(repo_path), args.max_commits_per_repo)
    themed = len(groups) > 1
    print(f"{repo_path.name}: {len(groups)} change set(s)")
    for group in groups:
        print(f"  {group.name:<28} {len(group.entries):>5} file(s)")

    made: list[str] = []
    for index, group in enumerate(groups, 1):
        label = f"{repo_path.name} [{index}/{len(groups)}] {group.name}"
        print(f"\nGenerating commit message for {label} via {describe_backend(args, pool)}...")
        dr = collect_group(repo_path, group, args.max_diff_chars_per_commit, themed)
        message, pool = generate_message_with_failover(dr, args, pool)
        print(f"========== Commit message: {label} ==========")
        print(message)
        print(f"========== end {label} ==========")
        if args.dry_run:
            continue
        clean_git_locks(repo_path)
        sha = commit_group(repo_path, group, message)
        if sha is None:
            print(f"{label}: nothing to commit")
            continue
        print(f"{label}: committed {sha}")
        made.append(sha)

    if made:
        print(f"\nPushing {repo_path.name} ({len(made)} commit(s))...")
        push_repo(repo_path)
        print(f"{repo_path.name}: pushed")
    print("")
    return pool


def run_pre_stage_checks(dirty_repos: list[Path], args: argparse.Namespace, datrix_root: Path) -> None:
    """Every check that must pass across all dirty repos before a message is generated or anything is
    staged; the first that fails raises ``ScriptError`` and ends the whole run."""
    if args.skip_customer_domain_check:
        print(
            "WARNING: --skip-customer-domain-check was passed. Customer domain language "
            "is NOT being checked for; anything a pending change carries will be pushed."
        )
    else:
        enforce_customer_domain_isolation(dirty_repos, datrix_root)

    if args.skip_ignored_source_check:
        print(
            "WARNING: --skip-ignored-source-check was passed. Files a .gitignore rule "
            "shadows are NOT being checked for; a package whose source is being silently "
            "dropped from every clone will be committed and pushed exactly that way."
        )
    else:
        enforce_ignored_source(dirty_repos, datrix_root)

    if args.skip_polystring_case_check:
        print(
            "WARNING: --skip-poly-string-case-check was passed. Names re-cased through "
            "plain text are NOT being checked for; any to_*_case(str(name)) a pending "
            "change carries will be pushed."
        )
    else:
        enforce_polystring_case_roundtrips(dirty_repos)

    enforce_design_task_references(dirty_repos)

    enforce_python_lint_correctness(dirty_repos)


def check_dirty_repos(workspace_root: Path, args: argparse.Namespace) -> list[Path]:
    """The dirty repos once every pre-stage check passes over them; empty when none is dirty."""
    dirty_repos = find_dirty_repos(workspace_root)
    if dirty_repos:
        run_pre_stage_checks(dirty_repos, args, workspace_root / "datrix")
    return dirty_repos


def check_dirty_repos_with_repair(workspace_root: Path, args: argparse.Namespace) -> list[Path]:
    """``check_dirty_repos``, with a gate that found problems in the pending files handed to a Claude agent.

    The agent fixes the files, then the dirty repos are found again and every check re-runs --
    the agent may have changed which repos are dirty -- up to ``--gate-repair-attempts`` times. A dry
    run never repairs: it would edit files while promising to change nothing.
    """
    attempts = 0 if args.dry_run else args.gate_repair_attempts
    repairer = GateRepairer(
        workspace=workspace_root,
        model=args.gate_repair_model,
        effort=args.gate_repair_effort,
        timeout_ms=args.gate_repair_timeout_ms,
        attempts=attempts,
    )
    try:
        return run_with_repair(lambda: check_dirty_repos(workspace_root, args), repairer, attempts)
    except GateViolation:
        if args.dry_run and args.gate_repair_attempts:
            print("Dry run: the gate repair agent was not started.", file=sys.stderr)
        raise


def commit_and_push(workspace_root: Path, args: argparse.Namespace) -> int:
    """Check, commit and push every dirty framework repo under *workspace_root*; the exit code.

    Raises:
        ScriptError: a pre-stage check or a git command failed.
    """
    dirty_repos = check_dirty_repos_with_repair(workspace_root, args)
    if not dirty_repos:
        print("No uncommitted changes in any Datrix repo. Nothing to commit.")
        return 0

    # Backend selection comes after the checks: loading a large local model can take
    # minutes, and must not be paid for a run that commits nothing.
    pool = decide_backend(args)

    if not args.dry_run:
        set_git_identity()

    for repo_path in dirty_repos:
        pool = commit_repo(repo_path, args, pool)

    if args.dry_run:
        print("Dry run complete; no commits were made.")
    else:
        print("Commit-and-push completed.")
    return 0


#: A fictional term no product carries, registered only in the self-test's own corpus (by digest).
_PLANTED_TERM: Final = "quillmarrow"
_PLANTED_FILE: Final = "notes/pending.md"
_FIXTURE_IDENTITY: Final = ("-c", "user.name=commit-and-push-self-test", "-c",
                            "user.email=self-test@example.invalid", "-c", "commit.gpgsign=false")


def _fixture_git(repo: Path, *args: str) -> str:
    return subprocess.run(["git", *_FIXTURE_IDENTITY, *args], cwd=repo, check=True, capture_output=True,
                          text=True).stdout


def _planted_workspace(root: Path, pending: str) -> Path:
    """A workspace whose showcase repo has one commit, a corpus registering ``_PLANTED_TERM`` by digest,
    and *pending* as an uncommitted file."""
    repo = root / "datrix"
    repo.mkdir(parents=True)
    _fixture_git(repo, "init", "-q")
    corpus = {"algorithm": "sha256", "min_token_length": 5,
              "terms": [{"hash": hash_term(_PLANTED_TERM), "hint": "self-test"}]}
    write_files(repo, {corpus_path(repo).relative_to(repo).as_posix(): json.dumps(corpus) + "\n"})
    _fixture_git(repo, "add", "-A")
    _fixture_git(repo, "commit", "-q", "-m", "fixture")
    write_files(repo, {_PLANTED_FILE: pending})
    return root


def _failed_run(workspace: Path, argv: list[str]) -> tuple[str, str, str]:
    """Run commit-and-push over *workspace*, which must fail; its error, the commit count and the staged paths."""
    args = build_parser().parse_args(argv)
    try:
        with contextlib.redirect_stdout(io.StringIO()):
            code = commit_and_push(workspace, args)
    except (ScriptError, GateRunError) as exc:
        repo = workspace / "datrix"
        return (str(exc), _fixture_git(repo, "rev-list", "--count", "HEAD").strip(),
                _fixture_git(repo, "diff", "--cached", "--name-only").strip())
    raise AssertionError(f"commit-and-push over {workspace} finished with exit {code}; expected ScriptError")


def _check_a_planted_customer_term_fails_the_whole_run() -> None:
    with tempfile.TemporaryDirectory() as raw:
        planted = _planted_workspace(Path(raw) / "planted", f"endpoint = {_PLANTED_TERM}-service\n")
        error, commits, staged = _failed_run(planted, [])
        clean = _planted_workspace(Path(raw) / "clean", "endpoint = catalog-service\n")
        control, _, _ = _failed_run(clean, ["--dry-run"])
    assert error.startswith("Customer-domain isolation FAILED: 1 pending occurrence"), error
    assert f"datrix/{_PLANTED_FILE}:1" in error and _PLANTED_TERM not in error, f"not redacted or not located: {error}"
    assert (commits, staged) == ("1", ""), f"the run committed or staged: {commits} commit(s), staged {staged!r}"
    assert "Customer-domain isolation" not in control and "Ignored-source" in control, (
        f"without the planted term the isolation check must pass and the next check run: {control}"
    )


def _check_wrapper_options_reach_the_model_settings() -> None:
    args = build_parser().parse_args(["--local-machines=alpha", "--local-machines=beta", "--local-machines=alpha",
                                      "--local-timeout-ms=5000", "--local-load-timeout-ms=7000"])
    settings = commit_message_llm_settings(args)
    assert (settings.machines, settings.models, settings.generate_timeout_ms, settings.load_timeout_ms) == (
        ("alpha", "beta"), (), 5000, 7000), settings
    defaults = commit_message_llm_settings(build_parser().parse_args([]))
    assert (defaults.generate_timeout_ms, defaults.load_timeout_ms) == (
        DEFAULT_GENERATE_TIMEOUT_MS, DEFAULT_LOAD_TIMEOUT_MS), defaults


def _run(args: argparse.Namespace) -> int:
    if args.self_test:
        checks = [_check_a_planted_customer_term_fails_the_whole_run, _check_wrapper_options_reach_the_model_settings,
                  check_repair_loop_retries_until_the_gate_passes, check_repair_loop_gives_up_after_the_last_attempt,
                  check_repair_loop_with_no_attempts_raises_the_violation_unchanged,
                  check_repair_loop_does_not_repair_other_failures, check_repair_command_and_prompt,
                  check_no_git_script_runs_a_forbidden_form]
        return run_self_test(checks, wrapper=WRAPPER, module=MODULE, parser=build_parser(), folder=GIT_SCRIPTS_DIR)
    if args.max_commits_per_repo < 1:
        raise UsageError(
            f"--max-commits-per-repo must be at least 1, got {args.max_commits_per_repo}. "
            "Use 1 to commit each repo as a single change."
        )
    if args.gate_repair_attempts < 0 or args.gate_repair_timeout_ms < 1:
        raise UsageError(
            f"--gate-repair-attempts must be 0 or more and --gate-repair-timeout-ms at least 1, got "
            f"{args.gate_repair_attempts} and {args.gate_repair_timeout_ms}."
        )
    try:
        return commit_and_push(WORKSPACE_DIR, args)
    except (ScriptError, GateRunError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return EXIT_FAILED


def main(argv: Sequence[str] | None = None) -> int:
    """Entry point."""
    return module_main(build_parser(), _run, argv)


if __name__ == "__main__":
    sys.exit(main())
