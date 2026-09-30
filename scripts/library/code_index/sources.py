"""Which files the code index covers, and what module each one is.

The file set is what git sees in every repository at the workspace root -- tracked files
that still exist, plus untracked files no ``.gitignore`` excludes -- so build output,
caches and virtual environments are left out by each repository's own ignore rules
rather than by a list kept here.
"""

from __future__ import annotations

import fnmatch
import json
import os
import subprocess
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from pathlib import Path, PurePosixPath

# The configuration file, beside every other scripts configuration file.
CONFIG_PATH = Path(__file__).resolve().parents[2] / "config" / "code-index.json"

# Where each machine keeps its index, relative to the workspace root.
INDEX_DIR_NAME = ".code-index"
INDEX_DB_NAME = "index.db"
SUMMARIES_DB_NAME = "summaries.db"
# Written by the PostToolUse hook record-search-usage.py (which spells the same path),
# read by ``code_index.usage``.
USAGE_LOG_NAME = "usage.jsonl"

# The logic map's database, which the index rewrites whenever the marker set changes.
LOGIC_MAP_DB = PurePosixPath(".logic-map") / "markers.db"

PYTHON_SUFFIX = ".py"
PACKAGE_INIT = "__init__.py"
GIT_DIR_NAME = ".git"
GIT_TIMEOUT_SECONDS = 60
GIT_LIST_WORKERS = 8


class CodeIndexError(RuntimeError):
    """The index cannot be built or queried as asked; the message says what to change."""


@dataclass(frozen=True)
class CodeIndexConfig:
    """The contents of ``code-index.json``."""

    exclude: tuple[str, ...]
    module_roots: tuple[str, ...]
    summarize: tuple[str, ...]

    def is_excluded(self, rel_path: str) -> bool:
        return any(fnmatch.fnmatchcase(rel_path, pattern) for pattern in self.exclude)

    def is_summarized(self, rel_path: str) -> bool:
        return any(fnmatch.fnmatchcase(rel_path, pattern) for pattern in self.summarize)


@dataclass(frozen=True)
class SourceFile:
    """One file the index covers, as found on disk now."""

    rel_path: str  # workspace-relative, forward slashes
    repo: str
    abs_path: Path
    size: int
    mtime_ns: int


def _string_list(data: dict[str, object], key: str, path: Path) -> tuple[str, ...]:
    value = data.get(key)
    if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
        raise CodeIndexError(
            f"{path}: '{key}' must be a list of fnmatch patterns (strings), got {value!r}. "
            f"Expected keys: exclude, module_roots, summarize."
        )
    return tuple(value)


def load_config(path: Path = CONFIG_PATH) -> CodeIndexConfig:
    """Read the index configuration; raise CodeIndexError when it is missing or malformed."""
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except OSError as exc:
        raise CodeIndexError(f"Cannot read the code index configuration {path}: {exc}") from exc
    except ValueError as exc:
        raise CodeIndexError(f"The code index configuration {path} is not valid JSON: {exc}") from exc
    if not isinstance(data, dict):
        raise CodeIndexError(f"The code index configuration {path} must be a JSON object.")
    return CodeIndexConfig(
        exclude=_string_list(data, "exclude", path),
        module_roots=_string_list(data, "module_roots", path),
        summarize=_string_list(data, "summarize", path),
    )


def index_dir(workspace: Path) -> Path:
    return workspace / INDEX_DIR_NAME


def discover_repos(workspace: Path) -> list[Path]:
    """Every git repository directly under the workspace root, by name."""
    return sorted(
        child for child in workspace.iterdir()
        if child.is_dir() and (child / GIT_DIR_NAME).exists()
    )


def _git_python_files(repo: Path) -> list[str]:
    """Repository-relative paths of the Python files git sees in ``repo``."""
    command = [
        "git", "-C", str(repo), "ls-files", "--cached", "--others", "--exclude-standard",
        "-z", "--", f"*{PYTHON_SUFFIX}",
    ]
    try:
        result = subprocess.run(command, capture_output=True, timeout=GIT_TIMEOUT_SECONDS, check=False)
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise CodeIndexError(f"Listing the files of {repo} with git failed: {exc}. Is git on PATH?") from exc
    if result.returncode != 0:
        detail = result.stderr.decode("utf-8", errors="replace").strip()
        raise CodeIndexError(f"'git ls-files' failed in {repo} (exit {result.returncode}): {detail}")
    listed = result.stdout.decode("utf-8", errors="surrogateescape").split("\0")
    # A tracked file deleted from the working tree is still listed; only what exists counts.
    return sorted({path for path in listed if path})


def list_sources(workspace: Path, config: CodeIndexConfig) -> dict[str, SourceFile]:
    """Every file the index covers right now, keyed by workspace-relative path."""
    repos = discover_repos(workspace)
    if not repos:
        raise CodeIndexError(
            f"No git repository found under {workspace}. The index covers the repositories "
            f"checked out directly under the workspace root."
        )
    with ThreadPoolExecutor(max_workers=GIT_LIST_WORKERS) as pool:
        listings = list(pool.map(_git_python_files, repos))
    sources: dict[str, SourceFile] = {}
    for repo, paths in zip(repos, listings):
        for repo_path in paths:
            rel_path = f"{repo.name}/{repo_path}"
            if config.is_excluded(rel_path):
                continue
            abs_path = repo / repo_path
            try:
                stat = os.stat(abs_path)
            except FileNotFoundError:
                continue
            sources[rel_path] = SourceFile(rel_path, repo.name, abs_path, stat.st_size, stat.st_mtime_ns)
    return sources


def module_name(rel_path: str, config: CodeIndexConfig) -> str:
    """The dotted module name ``rel_path`` is imported as.

    Computed from the nearest ancestor directory matching a ``module_roots`` pattern, or
    from the repository directory when none matches. A package's ``__init__.py`` is the
    package itself.
    """
    parts = PurePosixPath(rel_path).parts
    root_len = 1
    for depth in range(len(parts) - 1, 0, -1):
        ancestor = "/".join(parts[:depth])
        if any(fnmatch.fnmatchcase(ancestor, pattern) for pattern in config.module_roots):
            root_len = depth
            break
    module_parts = list(parts[root_len:])
    if module_parts[-1] == PACKAGE_INIT:
        module_parts.pop()
    else:
        module_parts[-1] = module_parts[-1].removesuffix(PYTHON_SUFFIX)
    # An __init__.py directly in a root is the package named by the root directory.
    return ".".join(module_parts) or parts[root_len - 1]


def is_package_init(rel_path: str) -> bool:
    return PurePosixPath(rel_path).name == PACKAGE_INIT
