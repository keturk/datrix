#!/usr/bin/env python
"""Commit every dirty Datrix repo as themed change sets, then push each repo once.

WHY THEMED SETS RATHER THAN ONE COMMIT PER REPO
    History is read to answer "when did this behavior change?" and "which commit broke
    it?". Sweeping an unrelated fix into a large feature commit hides it, and a message
    covering a dozen unrelated changes cannot fit a short subject. Each repo's dirty
    paths are split by area (see ``theme_of``) -- a generator and its tests share one
    commit, an unrelated docs edit gets another -- capped by ``--max-commits-per-repo``.

MESSAGE SOURCE
    * **Local machines** (preferred) -- model servers on the local network. Each machine
      is searched for an Ollama server and OpenAI-compatible servers (vLLM, llama-server),
      and what they serve is discovered, never configured. Models already in memory are
      used first; an Ollama model is loaded only when none is. A model that fails hands
      over to the next.
    * **Claude Code CLI** -- the ``claude`` command, run as a pure text call with no
      tools. Used when no local host is usable (or ``--message-source claude``).

No intermediate ``commit-messages.json`` file is written.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import urllib.error
import urllib.request
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from dev.customer_domain_isolation import (  # noqa: E402
    CorpusError,
    Violation,
    corpus_path,
    load_term_corpus,
    pending_files,
    scan_paths,
    self_test,
)
from test.ignored_source import (  # noqa: E402
    IgnoredSourceGateError,
    ShadowedPath,
    StrayTempDir,
    exemption_path,
    load_exemptions,
    load_temp_dir_segment,
    scan_for_commit,
)
from test.ignored_source import self_test as ignored_source_self_test  # noqa: E402
from test.polystring_case_roundtrip import (  # noqa: E402
    PolyStringGateError,
    RepoResult,
)
from test.polystring_case_roundtrip import scan_for_commit as polystring_scan_for_commit  # noqa: E402
from test.polystring_case_roundtrip import self_test as polystring_self_test  # noqa: E402

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

# The HTTP APIs a local model server can speak. "ollama" is Ollama's native API, which can
# list, report and load models. "openai" is the OpenAI-compatible chat API that vLLM,
# llama.cpp's llama-server and most other inference servers expose; such a server holds
# its models resident already.
LOCAL_API_OLLAMA = "ollama"
LOCAL_API_OPENAI = "openai"

# Machines searched for local model servers, in preference order. What each one runs is
# discovered, not configured: the servers on a machine change (a llama-server container
# once took over the T5820's GPU, leaving the configured Ollama model nowhere to load),
# and a pinned API:URL=MODEL list goes stale the moment they do.
DEFAULT_LOCAL_MACHINES = (
    "10.94.0.100",  # Dell T5820, RTX 3090
    "10.94.0.101",  # Dell T7920, RTX 3090
    "10.94.0.102",  # ASUS GX10, vLLM
)

# Where the servers listen: Ollama on its fixed port, OpenAI-compatible servers on the
# ports vLLM (8000) and llama-server (8080, and 8081 beside another server) use.
OLLAMA_PORT = 11434
OPENAI_COMPATIBLE_PORTS = (8000, 8080, 8081)

# Models Ollama may be asked to LOAD when a machine has nothing resident, best first.
# Loading claims most of a GPU, so it is the last resort: every model already resident
# on any machine is tried before any load. Only models installed on the machine count.
OLLAMA_LOAD_PREFERENCE = ("qwen3-coder:30b-ctx32k",)

# Ollama capability a model needs to answer a prompt; an embedding model lacks it.
OLLAMA_COMPLETION_CAPABILITY = "completion"

# Ollama resolves an untagged model name to this tag.
OLLAMA_DEFAULT_TAG = "latest"

# Output tokens for the readiness request an OpenAI-compatible server is sent before it
# is handed a change set. One token proves the engine answers; listing a model does not
# (vLLM keeps listing its model after its engine has died).
READINESS_MAX_TOKENS = 1

# Ollama capability that means the model reasons before answering. Such a model is
# asked not to (think=false): a commit message needs no visible reasoning, and a
# thinking pass multiplies generate time. Sending think=false to a model WITHOUT this
# capability is an error in Ollama, so it is sent only when the capability is listed.
OLLAMA_THINKING_CAPABILITY = "thinking"

# How long Ollama keeps a model loaded after a request. A run makes one request per
# change set, possibly minutes apart while git runs, and a cold reload of a 20+ GB
# model costs minutes on a slow disk -- so the model stays resident for the run.
OLLAMA_KEEP_ALIVE = "30m"

# Sampling temperature for local models: low, because a commit message should restate
# the diff, not improvise on it.
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
    {"src", "tests", "test", "unit", "unit_core", "integration", "e2e", "scripts", "library", "examples"}
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
class LocalHost:
    """One local model server and one model it can run: the API, where it is, the model."""

    api: str
    base_url: str
    model: str

    def label(self) -> str:
        return f"{self.api} model '{self.model}' at {self.base_url}"


@dataclass(frozen=True)
class ReadyLocalHost:
    """A discovered server/model pair that can be asked for commit messages."""

    host: LocalHost
    thinking: bool
    # Already in memory -- an OpenAI-compatible server's model, or one Ollama has
    # loaded -- as opposed to a model Ollama would have to load first.
    resident: bool


@dataclass(frozen=True)
class ServerSurvey:
    """What one model server on one machine offers."""

    api: str
    base_url: str
    candidates: tuple[ReadyLocalHost, ...]

    def summary(self) -> str:
        resident = [c.host.model for c in self.candidates if c.resident]
        loadable = [c.host.model for c in self.candidates if not c.resident]
        parts = [f"resident {', '.join(resident) or 'none'}"]
        if loadable:
            parts.append(f"loadable {', '.join(loadable)}")
        return f"{self.api} at {self.base_url} ({'; '.join(parts)})"


@dataclass(frozen=True)
class ChangeEntry:
    """One dirty path from ``git status``, with every path its commit must include.

    A staged rename reads ``old -> new``: the theme follows the new path, but the old
    path is committed too so its deletion lands in the same commit. The old path is
    already gone from disk and index, so it is only ever named to ``git commit`` (HEAD
    still knows it), never to ``git add`` (which rejects a path matching nothing).
    """

    path: str
    stage_paths: tuple[str, ...]


@dataclass(frozen=True)
class ChangeGroup:
    """One themed change set: what to describe and exactly what to commit."""

    name: str
    entries: tuple[ChangeEntry, ...]

    @property
    def add_paths(self) -> list[str]:
        return list(dict.fromkeys(entry.path for entry in self.entries))

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


def workspace_root_from_script() -> Path:
    return Path(__file__).resolve().parents[4]


def repo_paths(workspace_root: Path) -> list[Path]:
    """Discover every Datrix git repository in the workspace.

    Discovered rather than hardcoded: Datrix is a multi-language, multi-platform generator,
    so a newly cloned datrix-codegen-<lang> repo must become visible to commit-and-push
    without an edit here. A hardcoded list silently drops the new repo's commits.

    The showcase repo comes first (it anchors the workspace); the datrix-* packages follow
    in sorted order. A directory is a repo only if it carries .git (a directory for a normal
    clone, a file for a worktree or submodule) -- both satisfy exists().
    """
    repos: list[Path] = []

    showcase = workspace_root / "datrix"
    if (showcase / ".git").exists():
        repos.append(showcase)

    for child in sorted(workspace_root.iterdir()):
        if child.name.startswith("datrix-") and (child / ".git").exists():
            repos.append(child)

    return repos


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
    for repo_path in repo_paths(workspace_root):
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
        if status[0] in "RC" and index < len(records):
            source = records[index]
            index += 1
            entries.append(ChangeEntry(path, (path, source)))
        else:
            entries.append(ChangeEntry(path, (path,)))
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
    ``scripts/library/git/x.py`` -> ``git``; a file at the repo root -> the root theme.
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


def qualified_ollama_model(model: str) -> str:
    """Return the model name as Ollama lists it, with the implicit tag made explicit."""
    return model if ":" in model else f"{model}:{OLLAMA_DEFAULT_TAG}"


def parse_local_machine(spec: str) -> str:
    """Validate a --local-machine value: a bare host name or IP address, nothing else.

    The ports and APIs are searched, so a scheme, port or path in the value would be
    ignored at best; it is rejected so a mistyped value never searches the wrong place.
    """
    machine = spec.strip()
    if not machine or any(sep in machine for sep in ("/", ":", "=", " ")):
        raise ScriptError(
            f"Local machine '{spec}' is not a bare host name or IP address. Pass only the "
            f"machine, e.g. {DEFAULT_LOCAL_MACHINES[0]}; its Ollama port {OLLAMA_PORT} and "
            f"OpenAI-compatible ports {', '.join(map(str, OPENAI_COMPATIBLE_PORTS))} are searched."
        )
    return machine


def listed_ollama_models(tags_response: object) -> dict[str, frozenset[str]]:
    """Map each model name in an Ollama ``/api/tags`` response to its capabilities."""
    if not isinstance(tags_response, dict) or not isinstance(tags_response.get("models"), list):
        raise ValueError("expected a JSON object with a 'models' list")
    models: dict[str, frozenset[str]] = {}
    for entry in tags_response["models"]:
        if not isinstance(entry, dict) or not isinstance(entry.get("name"), str):
            continue
        capabilities = entry.get("capabilities")
        listed = capabilities if isinstance(capabilities, list) else []
        models[entry["name"]] = frozenset(str(capability) for capability in listed)
    return models


def loaded_ollama_models(ps_response: object) -> list[str]:
    """The model names in an Ollama ``/api/ps`` response -- the models it holds in memory."""
    if not isinstance(ps_response, dict) or not isinstance(ps_response.get("models"), list):
        raise ValueError("expected a JSON object with a 'models' list")
    return [
        entry["name"]
        for entry in ps_response["models"]
        if isinstance(entry, dict) and isinstance(entry.get("name"), str)
    ]


def listed_openai_models(models_response: object) -> list[str]:
    """The served model ids, in listed order, from an OpenAI-compatible ``/v1/models`` response."""
    if not isinstance(models_response, dict) or not isinstance(models_response.get("data"), list):
        raise ValueError("expected a JSON object with a 'data' list")
    return [
        entry["id"]
        for entry in models_response["data"]
        if isinstance(entry, dict) and isinstance(entry.get("id"), str)
    ]


def fetch_json(uri: str, timeout_ms: int) -> object:
    with urllib.request.urlopen(uri, timeout=max(1, timeout_ms / 1000.0)) as resp:
        return json.loads(resp.read().decode("utf-8"))


def survey_ollama(base_url: str, timeout_ms: int) -> ServerSurvey:
    """List what an Ollama server can answer with: its loaded models, then loadable ones.

    A loaded model costs nothing to use. A model that must be loaded is offered only if
    it is in ``OLLAMA_LOAD_PREFERENCE`` and installed here; whether it fits the GPU is
    learned by loading it (see ``activate_first_host``). Raises OSError or ValueError
    when nothing usable answers.
    """
    capabilities = listed_ollama_models(fetch_json(f"{base_url}/api/tags", timeout_ms))
    loaded = loaded_ollama_models(fetch_json(f"{base_url}/api/ps", timeout_ms))

    def candidate(model: str, resident: bool) -> ReadyLocalHost:
        thinking = OLLAMA_THINKING_CAPABILITY in capabilities[model]
        return ReadyLocalHost(LocalHost(LOCAL_API_OLLAMA, base_url, model), thinking, resident)

    answering = [
        model for model in capabilities if OLLAMA_COMPLETION_CAPABILITY in capabilities[model]
    ]
    resident = [candidate(model, True) for model in loaded if model in answering]
    loadable = [
        candidate(model, False)
        for model in map(qualified_ollama_model, OLLAMA_LOAD_PREFERENCE)
        if model in answering and model not in loaded
    ]
    return ServerSurvey(LOCAL_API_OLLAMA, base_url, tuple(resident + loadable))


def survey_openai(base_url: str, timeout_ms: int) -> ServerSurvey:
    """List the models an OpenAI-compatible server serves; each is resident by definition.

    Such a server does not say whether a model reasons, so every request asks it not to
    (see ``openai_chat_body``). Raises OSError or ValueError when nothing usable answers.
    """
    models = listed_openai_models(fetch_json(f"{base_url}/v1/models", timeout_ms))
    return ServerSurvey(
        LOCAL_API_OPENAI,
        base_url,
        tuple(ReadyLocalHost(LocalHost(LOCAL_API_OPENAI, base_url, m), False, True) for m in models),
    )


def machine_endpoints(machine: str) -> list[tuple[Callable[[str, int], ServerSurvey], str]]:
    """Every (surveyor, base URL) a model server on ``machine`` may listen at."""
    endpoints: list[tuple[Callable[[str, int], ServerSurvey], str]] = [
        (survey_ollama, f"http://{machine}:{OLLAMA_PORT}")
    ]
    endpoints.extend((survey_openai, f"http://{machine}:{port}") for port in OPENAI_COMPATIBLE_PORTS)
    return endpoints


def survey_endpoint(
    surveyor: Callable[[str, int], ServerSurvey], base_url: str, timeout_ms: int
) -> list[ServerSurvey]:
    """Run one survey: the server found at ``base_url``, or nothing if none answered.

    A closed port, a dropped connection, a timeout, and a port serving something other
    than a model API are all normal while searching a machine, so none is an error.
    """
    try:
        return [surveyor(base_url, timeout_ms)]
    except (OSError, ValueError):
        return []


def post_json(uri: str, body: dict[str, object], timeout_ms: int, model: str) -> dict[str, object]:
    """POST one JSON request to a local model server and return the decoded JSON object.

    Every failure is a ScriptError so the host failover can act on it: URLError, a
    timeout, and a connection reset mid-read are all OSError, and an HTTP error's body
    carries the real cause (model not found, GPU out of memory) where str(exc) is only
    "HTTP Error 500".
    """
    req = urllib.request.Request(
        uri,
        data=json.dumps(body).encode("utf-8"),
        headers={"Content-Type": "application/json; charset=utf-8"},
    )
    try:
        with urllib.request.urlopen(req, timeout=max(1, timeout_ms / 1000.0)) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace").strip()
        raise ScriptError(
            f"Request to {uri} for model '{model}' failed with HTTP {exc.code}. "
            f"Server response: {detail or '(empty body)'}"
        ) from exc
    except OSError as exc:
        raise ScriptError(f"Request to {uri} for model '{model}' failed: {exc}") from exc
    except ValueError as exc:
        raise ScriptError(f"{uri} returned a body that is not JSON: {exc}") from exc
    if not isinstance(data, dict):
        raise ScriptError(f"{uri} returned JSON that is not an object for model '{model}'")
    return data


def openai_chat_body(model: str, prompt: str, system: str, max_tokens: int) -> dict[str, object]:
    """One non-streaming chat request for an OpenAI-compatible server.

    Reasoning is switched off through the chat template (``enable_thinking``): a commit
    message needs no visible reasoning, and a reasoning pass multiplies generate time.
    A server whose template has no such switch ignores the variable.
    """
    return {
        "model": model,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": prompt},
        ],
        "max_tokens": max_tokens,
        "temperature": LOCAL_TEMPERATURE,
        "stream": False,
        "chat_template_kwargs": {"enable_thinking": False},
    }


def ready_local_model(host: LocalHost, args: argparse.Namespace) -> None:
    """Prove the model answers before it is handed a change set; raise ScriptError if not.

    Ollama loads on demand: a generate request with no prompt only loads the model (or
    renews a loaded one's keep-alive). Doing that once, under the load timeout, keeps a
    cold load -- minutes for a large model on a slow disk -- from being charged against
    a generate call's timeout, and a model that cannot load (out of GPU memory) is caught
    here. An OpenAI-compatible server is sent a one-token completion: it keeps listing
    its model after its engine has died, so only an answer proves it can serve. Its model
    is already in memory, so it gets the generate timeout, not the load timeout -- a hung
    engine must not hold the run for a cold load's allowance.
    """
    if host.api == LOCAL_API_OLLAMA:
        post_json(
            f"{host.base_url}/api/generate",
            {"model": host.model, "keep_alive": OLLAMA_KEEP_ALIVE},
            args.local_load_timeout_ms,
            host.model,
        )
        return
    uri = f"{host.base_url}/v1/chat/completions"
    data = post_json(
        uri, openai_chat_body(host.model, "ping", "Reply with one word.", READINESS_MAX_TOKENS),
        args.local_timeout_ms, host.model,
    )
    choices = data.get("choices")
    if not isinstance(choices, list) or not choices:
        raise ScriptError(f"{uri} answered a readiness request for model '{host.model}' with no choices")


def discover_local_hosts(args: argparse.Namespace) -> list[ReadyLocalHost]:
    """Search every machine for model servers and return what they offer, best first.

    Every endpoint of every machine is surveyed in parallel, so a machine that drops
    connections costs one timeout, not one per port. Models already in memory on any
    machine come first, in machine order; models Ollama would have to load come last,
    because loading one claims a GPU another server may be using. No load is offered on
    a machine where an OpenAI-compatible server answered: that server holds the machine's
    GPU memory, so the load fails out of memory on a discrete GPU and, on unified memory,
    starves the whole machine. Nothing is loaded here: ``activate_first_host`` readies
    the first candidate, and a later one only when failover reaches it.
    """
    endpoints = [
        (machine, surveyor, base_url)
        for machine in args.local_machines
        for surveyor, base_url in machine_endpoints(machine)
    ]
    with ThreadPoolExecutor(max_workers=len(endpoints)) as pool:
        surveys = list(pool.map(
            lambda endpoint: survey_endpoint(endpoint[1], endpoint[2], args.local_reachable_timeout_ms),
            endpoints,
        ))

    found: list[ServerSurvey] = []
    for machine in args.local_machines:
        on_machine = [s for (m, _, _), hits in zip(endpoints, surveys) if m == machine for s in hits]
        if any(s.api == LOCAL_API_OPENAI for s in on_machine):
            on_machine = [
                ServerSurvey(s.api, s.base_url, tuple(c for c in s.candidates if c.resident))
                for s in on_machine
            ]
        if on_machine:
            print(f"Local machine {machine}: {'; '.join(s.summary() for s in on_machine)}.")
        else:
            ports = ", ".join(str(p) for p in (OLLAMA_PORT, *OPENAI_COMPATIBLE_PORTS))
            print(f"Local machine {machine}: no model server answered on ports {ports}.")
        found.extend(on_machine)

    candidates = [c for survey in found for c in survey.candidates]
    return [c for c in candidates if c.resident] + [c for c in candidates if not c.resident]


def activate_first_host(
    hosts: list[ReadyLocalHost], args: argparse.Namespace
) -> list[ReadyLocalHost]:
    """Drop candidates from the front until one answers; return the survivors."""
    remaining = list(hosts)
    while remaining:
        ready = remaining[0]
        if ready.host.api == LOCAL_API_OLLAMA:
            verb = "Checking" if ready.resident else "Loading"
            print(f"{verb} {ready.host.label()} (up to {args.local_load_timeout_ms // 1000}s)...")
        else:
            print(f"Checking {ready.host.label()} (up to {args.local_timeout_ms // 1000}s)...")
        try:
            ready_local_model(ready.host, args)
            return remaining
        except ScriptError as exc:
            print(f"Warning: {ready.host.label()} cannot serve: {exc}", file=sys.stderr)
            remaining = remaining[1:]
    return remaining


def invoke_ollama_generate(ready: ReadyLocalHost, prompt: str, system: str, args: argparse.Namespace) -> str:
    host = ready.host
    uri = f"{host.base_url}/api/generate"
    body: dict[str, object] = {
        "model": host.model,
        "prompt": prompt,
        "system": system,
        "stream": False,
        "keep_alive": OLLAMA_KEEP_ALIVE,
        "options": {
            "num_predict": args.local_max_tokens,
            "temperature": LOCAL_TEMPERATURE,
        },
    }
    if ready.thinking:
        body["think"] = False
    data = post_json(uri, body, args.local_timeout_ms, host.model)
    response = data.get("response")
    if not isinstance(response, str) or not response.strip():
        raise ScriptError(f"{uri} returned no .response text for model '{host.model}'")
    return response


def invoke_openai_generate(ready: ReadyLocalHost, prompt: str, system: str, args: argparse.Namespace) -> str:
    """One chat completion from an OpenAI-compatible server such as vLLM or llama-server."""
    host = ready.host
    uri = f"{host.base_url}/v1/chat/completions"
    body = openai_chat_body(host.model, prompt, system, args.local_max_tokens)
    data = post_json(uri, body, args.local_timeout_ms, host.model)
    choices = data.get("choices")
    if not isinstance(choices, list) or not choices or not isinstance(choices[0], dict):
        raise ScriptError(f"{uri} returned no choices for model '{host.model}'")
    message = choices[0].get("message")
    content = message.get("content") if isinstance(message, dict) else None
    if not isinstance(content, str) or not content.strip():
        raise ScriptError(
            f"{uri} returned no message content for model '{host.model}' "
            f"(finish_reason={choices[0].get('finish_reason')!r})"
        )
    return content


LOCAL_GENERATORS: dict[str, Callable[[ReadyLocalHost, str, str, argparse.Namespace], str]] = {
    LOCAL_API_OLLAMA: invoke_ollama_generate,
    LOCAL_API_OPENAI: invoke_openai_generate,
}


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


def make_local_generator(args: argparse.Namespace, ready: ReadyLocalHost) -> Generator:
    """Bind one ready local host to a (prompt, system) -> text callable for its API."""
    invoke = LOCAL_GENERATORS[ready.host.api]
    return lambda prompt, system: invoke(ready, prompt, system, args)


def make_claude_generator(args: argparse.Namespace, dr: DirtyRepo) -> Generator:
    """Bind the Claude Code CLI to a (prompt, system) -> text callable for one repo."""
    return lambda prompt, system: invoke_claude_generate(
        repo_path=dr.path,
        model=args.claude_model,
        prompt=prompt,
        timeout_ms=args.claude_timeout_ms,
        system=system,
    )


def describe_backend(args: argparse.Namespace, local_hosts: list[ReadyLocalHost]) -> str:
    """Name the backend the next change set will be sent to."""
    if local_hosts:
        return local_hosts[0].host.label()
    return f"Claude Code CLI model '{args.claude_model}'"


def generate_message_with_failover(
    dr: DirtyRepo, args: argparse.Namespace, local_hosts: list[ReadyLocalHost]
) -> tuple[str, list[ReadyLocalHost]]:
    """Generate one change set's message, returning it with the local hosts still in play.

    A host whose generate call fails is dropped -- for this set and the remaining ones,
    since the cause is server-side and persistent -- and the next host is loaded and takes
    over. Once every host has failed, auto mode hands the set to the Claude Code CLI; a
    forced ``local`` source fails loudly instead of silently leaving the local models.
    """
    remaining = list(local_hosts)
    while remaining:
        ready = remaining[0]
        try:
            return request_commit_message(dr, make_local_generator(args, ready)), remaining
        except ScriptError as exc:
            remaining = activate_first_host(remaining[1:], args)
            if not remaining and args.message_source == MESSAGE_SOURCE_LOCAL:
                raise ScriptError(
                    f"Every usable local host failed for {dr.name} and --message-source=local "
                    f"was forced. Last failure ({ready.host.label()}): {exc}"
                ) from exc
            print(
                f"Warning: {ready.host.label()} failed for {dr.name}: {exc}\n"
                f"Switching to {describe_backend(args, remaining)} "
                "for this and the remaining change sets.",
                file=sys.stderr,
            )
    return request_commit_message(dr, make_claude_generator(args, dr)), remaining


def decide_local_hosts(args: argparse.Namespace) -> list[ReadyLocalHost]:
    """Resolve the ordered local hosts to use; an empty list means the Claude Code CLI."""
    if args.message_source == MESSAGE_SOURCE_CLAUDE:
        print(f"Using Claude Code CLI model '{args.claude_model}'.")
        return []

    hosts = activate_first_host(discover_local_hosts(args), args)
    if hosts:
        print(f"Using {describe_backend(args, hosts)}.")
        return hosts
    if args.message_source == MESSAGE_SOURCE_LOCAL:
        raise ScriptError(
            f"No local model server could answer (searched {', '.join(args.local_machines)}) "
            "but --message-source=local was forced. Start a model server on one of those "
            f"machines (Ollama with one of {', '.join(OLLAMA_LOAD_PREFERENCE)} installed, or "
            "any OpenAI-compatible server), pass other machines (-LocalMachines / "
            "--local-machine), or use message source auto or claude."
        )
    print(f"No local host usable -- falling back to {describe_backend(args, hosts)}.")
    return hosts


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
    add_specs = "\n".join(f":(literal){path}" for path in group.add_paths) + "\n"
    pathspecs = "\n".join(f":(literal){path}" for path in group.stage_paths) + "\n"
    add = run_git_with_files(repo_path, ["add", "-A", "--pathspec-from-file={specs}"], {"specs": add_specs})
    if add.returncode != 0:
        raise ScriptError(f"{name}: git add failed for '{group.name}' ({add.returncode}): {add.stderr or add.stdout}")
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
    raise ScriptError(
        f"PolyString case round-trip check FAILED: {total} pending call(s) re-case a name "
        f"through plain text. Nothing was committed or pushed. Read the case variant off "
        f"the PolyString (.snake/.camel/.pascal/.kebab/.screaming_snake/.simple) instead of "
        f"str()-ing it and calling a to_*_case function; if the value is genuinely plain "
        f"text, drop the str() -- case functions accept any str.\n" + detail
    )


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--message-source",
        choices=[MESSAGE_SOURCE_AUTO, MESSAGE_SOURCE_LOCAL, MESSAGE_SOURCE_CLAUDE],
        default=MESSAGE_SOURCE_AUTO,
        help=(
            "Backend for commit messages: auto (the first usable local host, else Claude), "
            "or force one."
        ),
    )
    parser.add_argument(
        "--local-machine",
        dest="local_machine_specs",
        action="append",
        help=(
            "A machine (host name or IP) to search for local model servers: Ollama on port "
            f"{OLLAMA_PORT}, OpenAI-compatible servers on ports "
            f"{', '.join(map(str, OPENAI_COMPATIBLE_PORTS))}. Repeat to list several, in "
            f"preference order. Default: {', '.join(DEFAULT_LOCAL_MACHINES)}."
        ),
    )
    parser.add_argument(
        "--local-timeout-ms",
        type=int,
        default=180000,
        help="Timeout for each local generate call, with the model already loaded.",
    )
    parser.add_argument(
        "--local-load-timeout-ms",
        type=int,
        default=900000,
        help=(
            "Timeout for loading an Ollama host's model into memory before the first "
            "message. A cold load of a large model from a slow disk takes minutes."
        ),
    )
    parser.add_argument(
        "--local-reachable-timeout-ms",
        type=int,
        default=3000,
        help="Timeout for each request that searches a machine for model servers.",
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
        "--skip-polystring-case-check",
        action="store_true",
        help=(
            "Skip the PolyString case round-trip check. Only for a confirmed false positive: "
            "the check is what keeps to_*_case(str(name)) out of the framework repos."
        ),
    )
    args = parser.parse_args(argv)
    if args.max_commits_per_repo < 1:
        raise ScriptError(
            f"--max-commits-per-repo must be at least 1, got {args.max_commits_per_repo}. "
            "Use 1 to commit each repo as a single change."
        )
    # argparse would append to a list default in place, so the default is applied here.
    # dict.fromkeys drops a repeated machine while keeping the preference order.
    specs = args.local_machine_specs or DEFAULT_LOCAL_MACHINES
    args.local_machines = list(dict.fromkeys(parse_local_machine(spec) for spec in specs))
    return args


def commit_repo(repo_path: Path, args: argparse.Namespace, local_hosts: list[ReadyLocalHost]) -> list[ReadyLocalHost]:
    """Commit one repo as themed change sets, then push once. Returns the hosts still in play."""
    groups = group_changes(survey(repo_path), args.max_commits_per_repo)
    themed = len(groups) > 1
    print(f"{repo_path.name}: {len(groups)} change set(s)")
    for group in groups:
        print(f"  {group.name:<28} {len(group.entries):>5} file(s)")

    made: list[str] = []
    for index, group in enumerate(groups, 1):
        label = f"{repo_path.name} [{index}/{len(groups)}] {group.name}"
        print(f"\nGenerating commit message for {label} via {describe_backend(args, local_hosts)}...")
        dr = collect_group(repo_path, group, args.max_diff_chars_per_commit, themed)
        message, local_hosts = generate_message_with_failover(dr, args, local_hosts)
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
    return local_hosts


def main(argv: list[str]) -> int:
    args = parse_args(argv)
    workspace_root = workspace_root_from_script()

    dirty_repos = find_dirty_repos(workspace_root)
    if not dirty_repos:
        print("No uncommitted changes in any Datrix repo. Nothing to commit.")
        return 0

    if args.skip_customer_domain_check:
        print(
            "WARNING: --skip-customer-domain-check was passed. Customer domain language "
            "is NOT being checked for; anything a pending change carries will be pushed."
        )
    else:
        enforce_customer_domain_isolation(dirty_repos, workspace_root / "datrix")

    if args.skip_ignored_source_check:
        print(
            "WARNING: --skip-ignored-source-check was passed. Files a .gitignore rule "
            "shadows are NOT being checked for; a package whose source is being silently "
            "dropped from every clone will be committed and pushed exactly that way."
        )
    else:
        enforce_ignored_source(dirty_repos, workspace_root / "datrix")

    if args.skip_polystring_case_check:
        print(
            "WARNING: --skip-polystring-case-check was passed. Names re-cased through "
            "plain text are NOT being checked for; any to_*_case(str(name)) a pending "
            "change carries will be pushed."
        )
    else:
        enforce_polystring_case_roundtrips(dirty_repos)

    # Backend selection comes after the checks: loading a large local model can take
    # minutes, and must not be paid for a run that commits nothing.
    local_hosts = decide_local_hosts(args)

    if not args.dry_run:
        set_git_identity()

    for repo_path in dirty_repos:
        local_hosts = commit_repo(repo_path, args, local_hosts)

    if args.dry_run:
        print("Dry run complete; no commits were made.")
    else:
        print("Commit-and-push completed.")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main(sys.argv[1:]))
    except ScriptError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        raise SystemExit(1)
