#!/usr/bin/env python3
"""Suite-input fingerprint derivation for Datrix packages.

A package's FULL suite run is correct for exactly the inputs it read: its
dependency cone's files, the installed third-party distributions, the
interpreter, and whatever paths and executables the run was observed to touch
outside its own cone. This module computes every one of those as a component,
assembles them into one blake2b fingerprint, and diffs two component sets
component by component -- so a gate can decide, without re-running anything,
whether a recorded green run still applies, and say exactly why when it does
not.

Components (the ``inputs.components`` object of a stamped run's index.json):

- ``trees`` -- one git-state digest per package in the cone (see
  :func:`package_cone`): index blob ids for clean files, content digests only
  for the files ``git status`` names as changed (never every file's content).
- ``installed`` -- sorted ``name==version`` of every installed distribution,
  except the editable ``datrix-*`` installs (their trees are ``trees``), plus
  the installed Node dependency state of every cone package that carries a
  ``package.json`` (npm's hidden lockfile, and an untracked ``package-lock.json``).
- ``interpreter`` -- ``sys.version`` and ``sys.platform``.
- ``foreign`` -- observed paths outside every cone tree, keyed
  ``<repo>/<top-level-dir>`` when a git index covers them, or by their exact
  workspace-relative path when none does.
- ``in_cone_ignored`` -- observed paths inside a cone tree that its git index
  does not track (ignored or untracked), each digested on its own.
- ``executables`` -- every executable the run started, content-digested,
  except one resolved under a transient location (the OS temp directory, or
  one of the workspace's own scratch directories -- see
  :func:`datrix_common.testing.runner_plugin.transient_roots`): such an
  executable is an OUTPUT of the run (built or generated from in-cone inputs
  that are already fingerprinted), never one of its inputs, and its own path
  is unstable from run to run.

``ALGORITHM`` is hashed into the fingerprint, so bumping it invalidates every
stamp. ``CARRY_WINDOW_SECONDS`` bounds how old a carried stamp may be. Both are
named constants here, never flags or environment variables: a window an
invocation could widen would defeat its purpose.

This module is a library consumed by the suite runner and the concurrent gate.
Its command line only runs its plain-Python self-test (real temporary git
repositories, no pytest, no stubs):

Usage:
  D:\\datrix\\.venv\\Scripts\\python.exe scripts\\library\\test\\suite_inputs.py --self-test

Exit codes: 0 = self-test passed, 1 = a self-test check failed, 2 = usage error.
"""

from __future__ import annotations

import argparse
import copy
import errno
import glob
import hashlib
import importlib.metadata
import io
import json
import logging
import os
import re
import stat
import subprocess
import sys
import tempfile
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path, PurePosixPath, PureWindowsPath
from typing import ClassVar, Final

if sys.platform == "win32" and __name__ == "__main__":
    if hasattr(sys.stdout, "buffer"):
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    if hasattr(sys.stderr, "buffer"):
        sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

_LIBRARY_DIR = Path(__file__).resolve().parent.parent
if _LIBRARY_DIR.exists() and str(_LIBRARY_DIR) not in sys.path:
    sys.path.insert(0, str(_LIBRARY_DIR))

from test import affected_set  # noqa: E402
from test.affected_set import UsageError  # noqa: E402

from datrix_common.testing.runner_plugin import transient_roots  # noqa: E402

logger = logging.getLogger(__name__)

#: Version of the fingerprint algorithm. Hashed into every fingerprint, so
#: changing it makes every previously recorded stamp non-carriable.
ALGORITHM: Final[str] = "suite-inputs/2"

_SECONDS_PER_HOUR: Final[int] = 60 * 60
_CARRY_WINDOW_HOURS: Final[int] = 24
#: The oldest a recorded green run may be and still stand in for a fresh one.
#: Bounds the drift of inputs no fingerprint can see (registry state,
#: wall-clock-dependent tests, toolchains outside the workspace).
CARRY_WINDOW_SECONDS: Final[int] = _CARRY_WINDOW_HOURS * _SECONDS_PER_HOUR

_EXIT_OK = 0
_EXIT_SELFCHECK_FAILED = 1

_GIT_DIRNAME = ".git"
#: The runner's own output directory inside every package. It is written AFTER
#: the fingerprint is computed (the stamp lands in it), so it is never an
#: input -- counting it would make every stamp invalidate itself in a repository
#: that forgot to ignore it.
_RUNNER_OUTPUT_DIRNAME = ".test_results"
_WHOLE_TREE_PATHSPEC = "."
_RUNNER_OUTPUT_EXCLUDE = f":(top,exclude){_RUNNER_OUTPUT_DIRNAME}"
#: git matches pathspecs as wildcard patterns by default; a subtree scope is a
#: real path, so "[", "*" or "?" in its name must match only themselves.
_LITERAL_PATHSPEC_MAGIC = ":(literal)"
_GIT_LS_FILES_ARGS = ("ls-files", "--stage", "-v", "-z", "--full-name")
#: --no-renames: a staged rename is reported as a deletion plus an addition,
#: one path per record, instead of a two-path record. --untracked-files=all:
#: every untracked file is listed on its own; the default collapses a new
#: directory to one entry whose contents would then go undigested.
_GIT_STATUS_ARGS = ("status", "--porcelain=v1", "-z", "--no-renames", "--untracked-files=all")
_GIT_TOPLEVEL_ARGS = ("rev-parse", "--show-toplevel")
#: ``git ls-files -v`` tags a normally cached entry "H". Every other tag
#: (lowercase = assume-unchanged, "S" = skip-worktree, "M" = unmerged) marks
#: an entry whose working-tree file git status may not report, so it is read
#: from the working tree instead of trusted from the index.
_TRUSTED_INDEX_TAG = "H"
_LS_FILES_META_FIELDS = 4
_STATUS_CODE_WIDTH = 2
_STATUS_PATH_OFFSET = 3
#: Variables that would point git at a repository other than the one ``-C``
#: names. Dropped from every git child's environment.
_GIT_REPOSITORY_ENV_VARS = frozenset(
    {
        "GIT_DIR",
        "GIT_WORK_TREE",
        "GIT_INDEX_FILE",
        "GIT_OBJECT_DIRECTORY",
        "GIT_ALTERNATE_OBJECT_DIRECTORIES",
        "GIT_COMMON_DIR",
        "GIT_NAMESPACE",
        "GIT_CEILING_DIRECTORIES",
        "GIT_DISCOVERY_ACROSS_FILESYSTEM",
    }
)
#: Read-only status queries must not take the index lock or rewrite the
#: index; this runs beside suites and agents that use the same repositories.
_GIT_OPTIONAL_LOCKS_ENV = ("GIT_OPTIONAL_LOCKS", "0")

_READ_CHUNK_BYTES = 1024 * 1024
_KIND_GIT_STATE = "git-state"
_KIND_FILE = "file"
_KIND_LISTING = "listing"
_KIND_INSTALLED = "installed"
_ABSENT = "absent"
_INDEX_ENTRY_PREFIX = "index"
_WORKTREE_ENTRY_PREFIX = "worktree"
#: Windows ERROR_INVALID_NAME: the OS rejects the path string itself as
#: ill-formed (a pseudo-filename like "<unknown>", a stray reserved
#: character, an incomplete UNC form, ...), never merely "not found" or
#: "not a directory". A name no filesystem could ever hold can never hold
#: content, so it is digested exactly like a missing path.
_ERROR_INVALID_NAME = 123

_FRAMEWORK_DIST_PREFIX = "datrix-"
_DIRECT_URL_FILE = "direct_url.json"
_DIST_NAME_SEPARATORS = re.compile(r"[-_.]+")

_NODE_MANIFEST_NAME = "package.json"
_NODE_MODULES_DIRNAME = "node_modules"
#: npm (7 and later) rewrites this on every install: the resolved tree actually
#: present under node_modules, where package-lock.json is the tree requested.
_NODE_HIDDEN_LOCKFILE_NAME = ".package-lock.json"
_NODE_LOCKFILE_NAME = "package-lock.json"
#: Leads every Node line of the installed digest; a Python ``name==version``
#: line can never start with it (a distribution name holds no space).
_NODE_ENTRY_PREFIX = "node"

_COMPONENT_TREES = "trees"
_COMPONENT_INSTALLED = "installed"
_COMPONENT_INTERPRETER = "interpreter"
_COMPONENT_FOREIGN = "foreign"
_COMPONENT_IN_CONE_IGNORED = "in_cone_ignored"
_COMPONENT_EXECUTABLES = "executables"
_COMPONENT_KEYS = frozenset(
    {
        _COMPONENT_TREES,
        _COMPONENT_INSTALLED,
        _COMPONENT_INTERPRETER,
        _COMPONENT_FOREIGN,
        _COMPONENT_IN_CONE_IGNORED,
        _COMPONENT_EXECUTABLES,
    }
)
_INPUTS_ALGORITHM = "algorithm"
_INPUTS_FINGERPRINT = "fingerprint"
_INPUTS_COMPONENTS = "components"
_INPUTS_KEYS = frozenset({_INPUTS_ALGORITHM, _INPUTS_FINGERPRINT, _INPUTS_COMPONENTS})
_INTERPRETER_VERSION = "version"
_INTERPRETER_PLATFORM = "platform"
_INTERPRETER_KEYS = frozenset({_INTERPRETER_VERSION, _INTERPRETER_PLATFORM})

_RECORD_OPENED = "opened"
_RECORD_LISTED = "listed"
_RECORD_DLOPENED = "dlopened"
_RECORD_EXECUTABLES = "executables"
_RECORD_PATH_KINDS = (_RECORD_OPENED, _RECORD_LISTED, _RECORD_DLOPENED)
_RECORD_KEYS = frozenset({*_RECORD_PATH_KINDS, _RECORD_EXECUTABLES})

#: Foreign key of an observed path that is the workspace root itself.
_WORKSPACE_ROOT_KEY = "."
_FORBIDDEN_KEY_PARTS = frozenset({"", ".", ".."})

_BUCKET_COVERED = "covered"
_BUCKET_IN_CONE_IGNORED = "in_cone_ignored"
_BUCKET_FOREIGN = "foreign"

_REASON_ALGORITHM = "algorithm version differs"
_REASON_INSTALLED = "installed dependencies changed"
_REASON_INTERPRETER = "interpreter changed"
_REASON_MALFORMED = "recorded inputs are malformed: {detail}"
_REASON_INCONSISTENT = "recorded fingerprint does not match its recorded components"
_SUBJECT_TREE = "{key} tree"
_SUBJECT_FOREIGN = "foreign tree {key}"
_SUBJECT_IGNORED = "ignored input {key}"
_SUBJECT_EXECUTABLE = "executable {key}"


class SuiteInputsError(UsageError):
    """Invalid usage or an input whose state cannot be established.

    Subclasses affected_set's UsageError, so one ``except UsageError`` covers
    both modules. Raised instead of returning an empty or partial digest: a
    fingerprint that silently skipped an input would vouch for a state nobody
    checked.
    """


# ---------------------------------------------------------------------------
# Git state (index blob ids + the working-tree files git status names).
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class _IndexRecord:
    """One ``git ls-files --stage -v`` record."""

    tag: str
    mode: str
    object_id: str
    path: str


def _git_environment() -> dict[str, str]:
    environment = {
        key: value for key, value in os.environ.items() if key not in _GIT_REPOSITORY_ENV_VARS
    }
    name, value = _GIT_OPTIONAL_LOCKS_ENV
    environment[name] = value
    return environment


def _run_git(repo_root: Path, *args: str) -> str:
    """Run a read-only git command in *repo_root*; its stdout, NUL-separated
    paths decoded without loss (surrogateescape)."""
    try:
        result = subprocess.run(
            ["git", "-C", str(repo_root), *args],
            capture_output=True,
            check=False,
            env=_git_environment(),
        )
    except OSError as exc:
        raise SuiteInputsError(
            f"Cannot run git to read the state of {repo_root}: {exc}. The suite-input "
            f"fingerprint reads every tree through git; put git on PATH and re-run."
        ) from exc
    if result.returncode != 0:
        detail = result.stderr.decode("utf-8", errors="replace").strip()
        raise SuiteInputsError(
            f"`git {' '.join(args)}` failed in {repo_root} (exit {result.returncode}): "
            f"{detail}. Expected a readable git work tree; a tree whose state git cannot "
            f"report is refused rather than digested as empty."
        )
    return result.stdout.decode("utf-8", errors="surrogateescape")


def _git_toplevel(directory: Path) -> Path | None:
    """The work-tree top level git itself reports for *directory*, or None
    when git refuses to treat *directory* as inside any work tree."""
    try:
        result = subprocess.run(
            ["git", "-C", str(directory), *_GIT_TOPLEVEL_ARGS],
            capture_output=True,
            check=False,
            env=_git_environment(),
        )
    except OSError as exc:
        raise SuiteInputsError(
            f"Cannot run git to tell whether {directory} is a repository: {exc}. The "
            f"suite-input fingerprint reads every tree through git; put git on PATH and re-run."
        ) from exc
    if result.returncode != 0:
        logger.debug(
            "git rejects %s as a work tree (exit %d): %s",
            directory,
            result.returncode,
            result.stderr.decode("utf-8", errors="replace").strip(),
        )
        return None
    reported = result.stdout.decode("utf-8", errors="surrogateescape").strip()
    if not reported:
        raise SuiteInputsError(
            f"`git rev-parse --show-toplevel` succeeded in {directory} but printed no path. "
            f"Expected the absolute work-tree root; check the installed git version before "
            f"trusting any fingerprint."
        )
    return Path(reported).resolve()


@dataclass(frozen=True)
class _RepositoryState:
    """One repository's whole-tree index records and ``git status`` paths,
    the runner's output directory excluded."""

    records: tuple[_IndexRecord, ...]
    status_paths: frozenset[str]


def _within_scope(relative: str, scope: str) -> bool:
    """True when the repository-relative *relative* is matched by the literal
    pathspec *scope* ("" = the whole tree): the path itself, or anything under
    it as a directory. Case-sensitive, exactly as git matches a literal
    pathspec even where ``core.ignorecase`` is set."""
    return not scope or relative == scope or relative.startswith(f"{scope}/")


class _RepositoryRoots:
    """Which directories are git work-tree roots, as git itself confirms, and
    each confirmed root's index and status.

    A ``.git`` entry alone proves nothing: git rejects an empty or damaged one,
    and a path under a rejected root must never be sent to ``git ls-files``
    there. A directory is a root only when ``git rev-parse --show-toplevel``
    run in it names that same directory. Each answer is cached, so a directory
    costs at most one git call per instance; an instance lives for one
    fingerprint computation, never across repository changes.

    A repository's index and status are likewise read once per instance, over
    the whole tree, and every subtree digest filters them. A suite that walks
    another package observes thousands of paths in it; asking git once per
    observed path would cost two process launches each.
    """

    def __init__(self) -> None:
        self._confirmed: dict[Path, bool] = {}
        self._states: dict[Path, _RepositoryState] = {}

    def state(self, repo_root: Path) -> _RepositoryState:
        """*repo_root*'s index records and status paths, read on first use.

        Raises:
            SuiteInputsError: if git cannot report the repository's state.
        """
        if repo_root not in self._states:
            pathspec = (_WHOLE_TREE_PATHSPEC, _RUNNER_OUTPUT_EXCLUDE)
            self._states[repo_root] = _RepositoryState(
                records=tuple(_index_records(repo_root, pathspec)),
                status_paths=frozenset(_status_paths(repo_root, pathspec)),
            )
        return self._states[repo_root]

    def is_root(self, directory: Path) -> bool:
        if directory not in self._confirmed:
            self._confirmed[directory] = self._probe(directory)
        return self._confirmed[directory]

    @staticmethod
    def _probe(directory: Path) -> bool:
        if not (directory / _GIT_DIRNAME).exists():
            return False
        toplevel = _git_toplevel(directory)
        if toplevel is None:
            return False
        return os.path.normcase(str(toplevel)) == os.path.normcase(str(directory.resolve()))

    def require_root(self, directory: Path) -> None:
        if not self.is_root(directory):
            raise SuiteInputsError(
                f"{directory} is not the root of a git work tree: git does not report it as "
                f"the top level of one (it has no {_GIT_DIRNAME} entry, or git rejects the one "
                f"it has). Every package in a suite's cone must be its own git repository, so "
                f"its state can be read from its index. Run `git init` there, repair its "
                f"{_GIT_DIRNAME}, or fix the package path."
            )

    def owning(self, path: Path, floor: Path | None = None) -> Path | None:
        """The nearest of *path* and its ancestors that git confirms as a
        work-tree root -- the repository ``git -C <path>`` itself would use --
        or None when there is none (at or below *floor*, when given)."""
        for candidate in (path, *path.parents):
            if floor is not None and len(candidate.parts) < len(floor.parts):
                return None
            if self.is_root(candidate):
                return candidate
        return None


def _index_records(repo_root: Path, pathspec: tuple[str, ...]) -> list[_IndexRecord]:
    output = _run_git(repo_root, *_GIT_LS_FILES_ARGS, "--", *pathspec)
    records: list[_IndexRecord] = []
    for raw in output.split("\0"):
        if not raw:
            continue
        meta, separator, path = raw.partition("\t")
        fields = meta.split(" ")
        if not separator or not path or len(fields) != _LS_FILES_META_FIELDS:
            raise SuiteInputsError(
                f"Unexpected `git ls-files --stage -v` record {raw!r} in {repo_root}. "
                f"Expected '<tag> <mode> <object> <stage>\\t<path>'. Check the installed "
                f"git version before trusting any fingerprint."
            )
        records.append(_IndexRecord(tag=fields[0], mode=fields[1], object_id=fields[2], path=path))
    return records


def _status_paths(repo_root: Path, pathspec: tuple[str, ...]) -> set[str]:
    """Every path ``git status`` names: modified, added, deleted, unmerged, or
    untracked-and-not-ignored."""
    output = _run_git(repo_root, *_GIT_STATUS_ARGS, "--", *pathspec)
    paths: set[str] = set()
    for raw in output.split("\0"):
        if not raw:
            continue
        if len(raw) <= _STATUS_PATH_OFFSET or raw[_STATUS_CODE_WIDTH] != " ":
            raise SuiteInputsError(
                f"Unexpected `git status --porcelain=v1 -z` record {raw!r} in {repo_root}. "
                f"Expected 'XY <path>' (renames are disabled, so one path per record). "
                f"Check the installed git version before trusting any fingerprint."
            )
        paths.add(raw[_STATUS_PATH_OFFSET:])
    return paths


def _content_hex(path: Path) -> str:
    digest = hashlib.blake2b()
    try:
        with path.open("rb") as handle:
            while chunk := handle.read(_READ_CHUNK_BYTES):
                digest.update(chunk)
    except OSError as exc:
        raise SuiteInputsError(
            f"Cannot read {path} to digest it: {exc}. An input that cannot be read "
            f"cannot be vouched for; fix its permissions or remove it."
        ) from exc
    return digest.hexdigest()


def _listing_hex(path: Path) -> str:
    try:
        names = sorted(os.listdir(path))
    except OSError as exc:
        raise SuiteInputsError(
            f"Cannot list {path} to digest it: {exc}. An input that cannot be read "
            f"cannot be vouched for; fix its permissions or remove it."
        ) from exc
    digest = hashlib.blake2b()
    for name in names:
        digest.update(name.encode("utf-8", errors="surrogateescape"))
        digest.update(b"\0")
    return digest.hexdigest()


def _worktree_entry(repo_root: Path, relative: str) -> str:
    """Content entry for a path git named as changed; "" when it is gone."""
    file_path = repo_root / relative
    if not file_path.exists():
        return ""
    if not file_path.is_file():
        raise SuiteInputsError(
            f"git reports {relative!r} in {repo_root} as changed, but it is not a regular "
            f"file (a nested repository or submodule?). Its contents are not covered by "
            f"this repository's index, so the tree cannot be fingerprinted. Expected every "
            f"changed path to be a file; remove the nested checkout or ignore it."
        )
    return f"{_WORKTREE_ENTRY_PREFIX} {_content_hex(file_path)}"


def _git_state_entries(repo_root: Path, scope: str, roots: _RepositoryRoots) -> dict[str, str]:
    """{repo-relative path: entry} for the subtree *scope* ("" = whole tree).

    Clean files are identified by their index mode and blob id without being
    read. Only the files git status names -- plus index entries git flags as
    assume-unchanged/skip-worktree, whose changes status would hide -- are
    read from the working tree. Deleted files drop out. The index and status
    come from *roots*' one whole-tree read of the repository, filtered to
    *scope* exactly as git's literal pathspec would select it.
    """
    state = roots.state(repo_root)
    read_from_worktree = {path for path in state.status_paths if _within_scope(path, scope)}
    entries: dict[str, str] = {}
    for record in state.records:
        if not _within_scope(record.path, scope):
            continue
        if record.tag == _TRUSTED_INDEX_TAG:
            entries[record.path] = f"{_INDEX_ENTRY_PREFIX} {record.mode} {record.object_id}"
        else:
            read_from_worktree.add(record.path)
    for relative in sorted(read_from_worktree):
        if relative in entries:
            del entries[relative]
        worktree_entry = _worktree_entry(repo_root, relative)
        if worktree_entry:
            entries[relative] = worktree_entry
    return entries


def _git_state_digest(entries: dict[str, str]) -> str:
    digest = hashlib.blake2b()
    for relative in sorted(entries):
        digest.update(relative.encode("utf-8", errors="surrogateescape"))
        digest.update(b"\0")
        digest.update(entries[relative].encode("utf-8"))
        digest.update(b"\n")
    return f"{_KIND_GIT_STATE}:{digest.hexdigest()}"


def tree_digest(repo_dir: Path) -> str:
    """Digest of one package tree's tracked-file state.

    Index blob ids for clean files; content digests only for files
    ``git status`` reports modified, added or untracked-and-not-ignored (and
    for index entries flagged assume-unchanged/skip-worktree); deleted files
    drop out. A clean tree is never read -- only its index is listed. The
    runner's own ``.test_results`` directory is excluded.

    Args:
        repo_dir: A package directory that is the root of its own git work tree.

    Returns:
        ``"git-state:<blake2b hex>"``.

    Raises:
        SuiteInputsError: if git does not confirm *repo_dir* as a work-tree
            root, git cannot report its state, or a changed path is not a
            regular file.
    """
    return _tree_digest(repo_dir, _RepositoryRoots())


def _tree_digest(repo_dir: Path, roots: _RepositoryRoots) -> str:
    roots.require_root(repo_dir)
    return _git_state_digest(_git_state_entries(repo_dir, "", roots))


def _is_invalid_name_error(exc: OSError) -> bool:
    """True when *exc* means the OS refused *path*'s name as unnameable --
    Windows' ERROR_INVALID_NAME (winerror 123, e.g. a library that opened
    the pseudo-filename ``<unknown>``) or POSIX's matching ``EINVAL`` --
    never that the entry is merely absent, permission-denied, or otherwise
    unreadable. Those stay fail-closed and keep raising."""
    if getattr(exc, "winerror", None) == _ERROR_INVALID_NAME:
        return True
    return exc.errno == errno.EINVAL


def digest_file(path: Path) -> str:
    """Digest of one observed filesystem entry.

    A regular file digests its content; a directory (an observed listing)
    digests its sorted entry names; a path that no longer exists, or whose
    name the operating system itself rejects as ill-formed (Windows
    ERROR_INVALID_NAME, POSIX EINVAL -- e.g. an ``open`` audit event firing
    for a library's failed attempt to open a pseudo-filename like
    ``<unknown>``), digests as ``"absent"`` -- distinct from an empty file --
    so a vanished input changes the fingerprint instead of silently dropping
    out of it, and a name that can never hold content is exact as absent too.

    Raises:
        SuiteInputsError: if the entry exists but cannot be read for any
            other reason (permission denied, ...), or is neither a regular
            file nor a directory.
    """
    try:
        mode = path.stat().st_mode
    except (FileNotFoundError, NotADirectoryError):
        return _ABSENT
    except OSError as exc:
        if _is_invalid_name_error(exc):
            return _ABSENT
        raise SuiteInputsError(
            f"Cannot stat observed input {path}: {exc}. An input whose state cannot be "
            f"read cannot be vouched for; fix the path or its permissions."
        ) from exc
    if stat.S_ISREG(mode):
        return f"{_KIND_FILE}:{_content_hex(path)}"
    if stat.S_ISDIR(mode):
        return f"{_KIND_LISTING}:{_listing_hex(path)}"
    raise SuiteInputsError(
        f"Observed input {path} is neither a regular file nor a directory (mode "
        f"{stat.filemode(mode)}). Expected a file the suite read or a directory it "
        f"listed; a device, socket or pipe cannot be fingerprinted."
    )


def digest_subtree(path: Path) -> str:
    """Digest of one foreign subtree or path (a ``foreign`` component key).

    When the repository owning *path* tracks anything under it (or git status
    names anything under it), the digest is that subtree's git state, exactly
    as :func:`tree_digest` computes it for a whole package. Otherwise -- an
    ignored path, a path in no repository (including one under a ``.git``
    entry git rejects), or a path that no longer exists -- it is
    :func:`digest_file` of *path* itself.

    Raises:
        SuiteInputsError: see :func:`tree_digest` and :func:`digest_file`.
    """
    return _digest_subtree(path, _RepositoryRoots())


def _digest_subtree(path: Path, roots: _RepositoryRoots) -> str:
    repository = roots.owning(path)
    if repository is not None:
        scope = path.relative_to(repository).as_posix()
        entries = _git_state_entries(repository, "" if scope == _WHOLE_TREE_PATHSPEC else scope, roots)
        if entries:
            return _git_state_digest(entries)
    return digest_file(path)


# ---------------------------------------------------------------------------
# Environment components.
# ---------------------------------------------------------------------------


def _distribution_field(distribution: importlib.metadata.Distribution, field: str) -> str:
    metadata = distribution.metadata
    if field not in metadata or not metadata[field]:
        raise SuiteInputsError(
            f"An installed distribution under {distribution.locate_file('')} has no "
            f"{field} metadata. The installed set cannot be fingerprinted around a broken "
            f"install; reinstall or remove that distribution."
        )
    return str(metadata[field])


def _is_editable_install(distribution: importlib.metadata.Distribution, name: str) -> bool:
    """True for a PEP 610 editable install (``dir_info.editable`` is true)."""
    text = distribution.read_text(_DIRECT_URL_FILE)
    if text is None:
        return False
    try:
        data = json.loads(text)
    except json.JSONDecodeError as exc:
        raise SuiteInputsError(
            f"{_DIRECT_URL_FILE} of installed distribution {name} is not valid JSON: "
            f"{exc}. Reinstall it so its install kind can be read."
        ) from exc
    if not isinstance(data, dict):
        raise SuiteInputsError(
            f"{_DIRECT_URL_FILE} of installed distribution {name} is not a JSON object. "
            f"Reinstall it so its install kind can be read."
        )
    if "dir_info" not in data:
        return False
    dir_info = data["dir_info"]
    return isinstance(dir_info, dict) and "editable" in dir_info and dir_info["editable"] is True


def _python_distribution_entries() -> set[str]:
    """``name==version`` of every distribution on ``sys.path`` (names PEP
    503-normalized), except editable ``datrix-*`` installs."""
    pairs: set[str] = set()
    for distribution in importlib.metadata.distributions():
        name = _DIST_NAME_SEPARATORS.sub("-", _distribution_field(distribution, "Name")).lower()
        version = _distribution_field(distribution, "Version")
        if name.startswith(_FRAMEWORK_DIST_PREFIX) and _is_editable_install(distribution, name):
            continue
        pairs.add(f"{name}=={version}")
    return pairs


def _node_dependency_entries(package_dir: Path, roots: _RepositoryRoots) -> set[str]:
    """The installed Node dependency state of one cone package.

    Empty for a package with no ``package.json``. Otherwise npm's hidden
    lockfile (``node_modules/.package-lock.json``, rewritten by npm 7 and later
    on every install) is digested -- ``"absent"`` when there is none, so a
    removed or never-run install is recorded rather than skipped -- and so is
    the package's own ``package-lock.json`` when its git index does not track
    it; a tracked one is already part of the package's ``trees`` digest.
    ``node_modules`` itself is git-ignored, which is why its state needs a
    component of its own.
    """
    if not (package_dir / _NODE_MANIFEST_NAME).is_file():
        return set()
    roots.require_root(package_dir)
    hidden_lockfile = package_dir / _NODE_MODULES_DIRNAME / _NODE_HIDDEN_LOCKFILE_NAME
    entries = {
        f"{_NODE_ENTRY_PREFIX} {package_dir.name} "
        f"{_NODE_MODULES_DIRNAME}/{_NODE_HIDDEN_LOCKFILE_NAME} {digest_file(hidden_lockfile)}"
    }
    lockfile_pathspec = f"{_LITERAL_PATHSPEC_MAGIC}{_NODE_LOCKFILE_NAME}"
    if not _index_records(package_dir, (lockfile_pathspec,)):
        entries.add(
            f"{_NODE_ENTRY_PREFIX} {package_dir.name} {_NODE_LOCKFILE_NAME} "
            f"{digest_file(package_dir / _NODE_LOCKFILE_NAME)}"
        )
    return entries


def installed_digest(cone_roots: Sequence[str]) -> str:
    """Digest of the installed third-party dependencies a suite runs against.

    Two parts, hashed together as sorted, de-duplicated lines:

    - every distribution on ``sys.path`` as ``name==version`` (names PEP
      503-normalized), excluding editable ``datrix-*`` installs -- their
      source trees are the ``trees`` component already. A ``datrix-*``
      distribution installed any other way stays in the set.
    - for every cone package carrying a ``package.json``, its installed Node
      dependency state: npm's hidden lockfile, and its own ``package-lock.json``
      when git does not track it. The installed ``node_modules`` tree is
      git-ignored, so without this an ``npm install`` would leave the
      fingerprint unchanged.

    Args:
        cone_roots: Absolute package-root paths of the suite's cone, as
            :func:`package_cone` returns them. ``()`` digests the Python
            distributions alone.

    Returns:
        ``"installed:<blake2b hex>"``.

    Raises:
        SuiteInputsError: if a distribution lacks a name or version, its
            ``direct_url.json`` cannot be parsed, a Node cone package is not a
            git work-tree root, or a lockfile cannot be read.
    """
    return _installed_digest(cone_roots, _RepositoryRoots())


def _installed_digest(cone_roots: Sequence[str], roots: _RepositoryRoots) -> str:
    entries = _python_distribution_entries()
    for root in cone_roots:
        entries |= _node_dependency_entries(Path(root), roots)
    digest = hashlib.blake2b("\n".join(sorted(entries)).encode("utf-8"))
    return f"{_KIND_INSTALLED}:{digest.hexdigest()}"


def interpreter() -> dict[str, str]:
    """The interpreter component: ``sys.version`` and ``sys.platform``."""
    return {_INTERPRETER_VERSION: sys.version, _INTERPRETER_PLATFORM: sys.platform}


# ---------------------------------------------------------------------------
# The cone: derived from affected_set's own graphs, never a second scanner.
# ---------------------------------------------------------------------------


def package_cones(workspace: Path) -> dict[str, tuple[str, ...]]:
    """Every package's cone, from ONE scan of the workspace.

    Deriving the graphs scans every package's imports (several seconds on
    the full monorepo), so a caller that needs several cones -- or one cone
    at the start of a run and again at the end -- should call this once and
    pass each cone to :func:`compute_inputs` rather than calling
    :func:`package_cone` repeatedly.

    Args:
        workspace: The Datrix monorepo root.

    Returns:
        Mapping of package name -> sorted absolute package-root paths of its
        cone (see :func:`package_cone`).

    Raises:
        UsageError: from affected_set's discovery or scan.
    """
    graphs = affected_set.build_workspace_graphs(workspace.resolve())
    cones = affected_set.forward_closure(graphs.source_graph, graphs.test_graph, graphs.deferred_graph)
    return {
        name: tuple(str(graphs.packages[member]) for member in sorted(members))
        for name, members in cones.items()
    }


def package_cone(workspace: Path, package: str) -> tuple[str, ...]:
    """Absolute package-root paths in *package*'s cone.

    The cone is *package* plus every package its suite needs to run:
    everything it reaches through SOURCE edges (transitively), and every
    direct TEST/DEFERRED target together with that target's own SOURCE
    reach -- cross-ecosystem edges included. It is
    ``affected_set.forward_closure`` over the SAME graphs the
    reverse-dependency gate builds, and its exact dual: a package is in this
    cone if and only if the gate would schedule *package* when that package
    changes.

    Args:
        workspace: The Datrix monorepo root.
        package: A discovered package name (e.g. "datrix-codegen-python").

    Returns:
        Sorted tuple of absolute package directory paths, always including
        *package* itself.

    Raises:
        SuiteInputsError: if *package* is not a discovered package.
        UsageError: from affected_set's discovery or scan.
    """
    cones = package_cones(workspace)
    if package not in cones:
        raise SuiteInputsError(
            f"Unknown package '{package}'. Discovered packages: {sorted(cones)}. "
            f"Pass a package directory name under {workspace.resolve()}."
        )
    return cones[package]


# ---------------------------------------------------------------------------
# Observed inputs: classification of a run's merged observation record.
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ObservedInputs:
    """A run's observed inputs, classified into the three observed components.

    ``in_cone_ignored`` holds absolute paths inside a cone tree that its git
    index does not track; ``foreign`` holds workspace-relative keys (see
    :func:`classify_observed`); ``executables`` holds absolute executable
    paths.
    """

    in_cone_ignored: frozenset[str]
    foreign: frozenset[str]
    executables: frozenset[str]

    @classmethod
    def from_recorded(cls, inputs: dict[str, object]) -> ObservedInputs:
        """Rebuild the observed inputs a PRIOR run recorded, from its stamped
        ``inputs`` object -- so the current state of exactly the paths it
        observed can be digested again without re-running its suite.

        Raises:
            SuiteInputsError: if *inputs* is not a well-formed stamp.
        """
        parsed = _parse_inputs(inputs, "recorded inputs")
        return cls(
            in_cone_ignored=frozenset(parsed.in_cone_ignored),
            foreign=frozenset(parsed.foreign),
            executables=frozenset(parsed.executables),
        )


def _path_key(path: Path) -> tuple[str, ...]:
    """Case-normalized path parts, for prefix comparison on any OS."""
    return tuple(os.path.normcase(part) for part in path.parts)


def _is_within(key: tuple[str, ...], root_key: tuple[str, ...]) -> bool:
    return key[: len(root_key)] == root_key


def _join_key(parts: tuple[str, ...]) -> str:
    return "/".join(parts) if parts else _WORKSPACE_ROOT_KEY


def _interpreter_environment_roots() -> tuple[Path, ...]:
    """The running interpreter's own installation and environment -- covered
    by the ``installed`` and ``interpreter`` components, never observed
    inputs."""
    prefixes = {sys.prefix, sys.exec_prefix, sys.base_prefix, sys.base_exec_prefix}
    return tuple(Path(prefix).resolve() for prefix in sorted(prefixes))


def _require_absolute_strings(value: object, label: str) -> list[str]:
    if not isinstance(value, list):
        raise SuiteInputsError(
            f"Observed record '{label}' is a {type(value).__name__}; expected a list of "
            f"absolute path strings."
        )
    for item in value:
        if not isinstance(item, str) or not item or not Path(item).is_absolute():
            raise SuiteInputsError(
                f"Observed record '{label}' holds {item!r}; expected only absolute path "
                f"strings. The runner plugin records resolved paths, so this record is "
                f"malformed and cannot be classified."
            )
    return list(value)


def _validated_records(
    records: Mapping[str, object],
) -> tuple[list[tuple[str, str]], frozenset[str]]:
    """(kind, path) pairs of every observed path, and the executable set."""
    if not isinstance(records, Mapping) or set(records) != _RECORD_KEYS:
        present = sorted(map(str, records)) if isinstance(records, Mapping) else type(records).__name__
        raise SuiteInputsError(
            f"Observed record has keys {present}; expected exactly {sorted(_RECORD_KEYS)}. "
            f"A record kind this classifier does not know cannot be vouched for."
        )
    path_records = [
        (kind, raw)
        for kind in _RECORD_PATH_KINDS
        for raw in _require_absolute_strings(records[kind], kind)
    ]
    executables = frozenset(
        str(Path(raw)) for raw in _require_absolute_strings(records[_RECORD_EXECUTABLES], _RECORD_EXECUTABLES)
    )
    return path_records, executables


def _is_unexpanded_glob(kind: str, raw: str) -> bool:
    """A ``glob.glob`` pattern recorded as a listing. The directories the
    glob actually scanned are recorded by their own scandir events, so the
    pattern string itself names nothing on disk."""
    return kind == _RECORD_LISTED and glob.has_magic(raw) and not os.path.lexists(raw)


class _Classifier:
    """Classifies observed paths against the cone trees and git indexes.

    Caches, for the duration of one classification, which directories git
    confirms as repository roots and which relative paths each repository's
    index covers (a tracked file, or a directory holding one).
    """

    def __init__(self, workspace: Path, cone_roots: tuple[str, ...]) -> None:
        self._workspace = workspace.resolve()
        self._workspace_key = _path_key(self._workspace)
        self._cone_roots = tuple(Path(root).resolve() for root in cone_roots)
        self._cone_keys = tuple(_path_key(root) for root in self._cone_roots)
        self._environment_keys = tuple(_path_key(root) for root in _interpreter_environment_roots())
        self._transient_keys = tuple(_path_key(root) for root in transient_roots(self._workspace))
        self._repository_roots = _RepositoryRoots()
        self._covered: dict[Path, frozenset[tuple[str, ...]]] = {}
        for root in self._cone_roots:
            self._repository_roots.require_root(root)

    def is_transient(self, path: Path) -> bool:
        """True when *path* resolves under a transient location: the OS temp
        directory, or one of the workspace's own scratch directories. An
        executable there is an output the run itself started from something
        it (or a prior in-cone-covered step) generated, not an input -- and
        its path changes from run to run, so treating it as an input would
        make the fingerprint unable to ever match again."""
        key = _path_key(path)
        return any(_is_within(key, root) for root in self._transient_keys)

    def classify(self, path: Path) -> tuple[str, str]:
        """(bucket, key) for one observed path."""
        key = _path_key(path)
        if any(_is_within(key, environment) for environment in self._environment_keys):
            return _BUCKET_COVERED, ""
        if not _is_within(key, self._workspace_key):
            raise SuiteInputsError(
                f"Observed path {path} lies outside the workspace {self._workspace}. The runner "
                f"plugin records only workspace paths (and the interpreter's own environment, "
                f"which is ignored here), so this record is malformed."
            )
        for root, root_key in zip(self._cone_roots, self._cone_keys, strict=True):
            if _is_within(key, root_key):
                if self._covers(root, path.parts[len(root.parts) :]):
                    return _BUCKET_COVERED, ""
                return _BUCKET_IN_CONE_IGNORED, str(path)
        return _BUCKET_FOREIGN, self._foreign_key(path)

    def _foreign_key(self, path: Path) -> str:
        """``<repo>/<top-level-dir>`` when the owning repository's index covers
        *path* (its git state then pins everything under that subtree);
        otherwise the exact workspace-relative path, digested on its own."""
        workspace_relative = path.parts[len(self._workspace.parts) :]
        repository = self._repository_roots.owning(path, floor=self._workspace)
        if repository is None:
            return _join_key(workspace_relative)
        within_repository = path.parts[len(repository.parts) :]
        if not self._covers(repository, within_repository):
            return _join_key(workspace_relative)
        repository_relative = path.parts[len(self._workspace.parts) : len(repository.parts)]
        return _join_key((*repository_relative, *within_repository[:1]))

    def _covers(self, repository: Path, relative_parts: tuple[str, ...]) -> bool:
        if repository not in self._covered:
            covered: set[tuple[str, ...]] = set()
            for record in _index_records(repository, (_WHOLE_TREE_PATHSPEC,)):
                parts = tuple(os.path.normcase(part) for part in record.path.split("/"))
                covered.update(parts[:depth] for depth in range(len(parts) + 1))
            self._covered[repository] = frozenset(covered)
        return tuple(os.path.normcase(part) for part in relative_parts) in self._covered[repository]


def classify_observed(
    records: Mapping[str, object], cone_roots: tuple[str, ...], workspace: Path
) -> ObservedInputs:
    """Classify a run's MERGED observation record into observed components.

    *records* is the runner's merge of every worker's ``observed-<worker>.json``:
    ``{"opened": [...], "listed": [...], "dlopened": [...], "executables": [...]}``
    -- each a list of absolute path strings (validated here, so a record read
    back from JSON can be passed as it is).
    The runner plugin is a plain recorder that keeps every workspace path it
    sees; membership is decided here, once, on the merged set:

    - under the interpreter's own environment (the venv) -> dropped; the
      ``installed``/``interpreter`` components cover it;
    - inside a cone tree and covered by its index (a tracked file, or a
      directory holding one) -> dropped; the ``trees`` component covers it;
    - inside a cone tree, not covered (ignored or untracked) ->
      ``in_cone_ignored``, by absolute path;
    - outside every cone tree -> ``foreign``: ``<repo>/<top-level-dir>`` when
      the owning repository's index covers the path, otherwise the exact
      workspace-relative path (an ignored file, or a path in no repository),
      so a file no index tracks is still pinned by its own content;
    - a glob pattern recorded as a listing -> skipped; the directories the
      glob scanned carry their own listing records.
    - an executable resolved under a transient location (see
      :meth:`_Classifier.is_transient`) -> dropped, whether or not it lies
      inside the workspace at all; every other executable is kept exactly.

    Args:
        records: The merged observation record.
        cone_roots: Absolute package-root paths, as :func:`package_cone`
            returns them.
        workspace: The Datrix monorepo root.

    Returns:
        The classified :class:`ObservedInputs`.

    Raises:
        SuiteInputsError: if the record is malformed (unknown or missing kind,
            a non-list, a relative path, a path outside the workspace), or a
            cone root is not a git work-tree root.
    """
    path_records, executables = _validated_records(records)
    classifier = _Classifier(workspace, cone_roots)
    buckets: dict[str, set[str]] = {_BUCKET_IN_CONE_IGNORED: set(), _BUCKET_FOREIGN: set()}
    for kind, raw in path_records:
        if _is_unexpanded_glob(kind, raw):
            continue
        bucket, key = classifier.classify(Path(raw))
        if bucket != _BUCKET_COVERED:
            buckets[bucket].add(key)
    fingerprinted_executables = frozenset(
        raw for raw in executables if not classifier.is_transient(Path(raw))
    )
    return ObservedInputs(
        in_cone_ignored=frozenset(buckets[_BUCKET_IN_CONE_IGNORED]),
        foreign=frozenset(buckets[_BUCKET_FOREIGN]),
        executables=fingerprinted_executables,
    )


# ---------------------------------------------------------------------------
# Assembly and diff.
# ---------------------------------------------------------------------------


def fingerprint_of(algorithm: str, components: dict[str, object]) -> str:
    """blake2b over the canonical JSON of *algorithm* and *components*.

    The one assembly rule: :func:`compute_inputs` produces its fingerprint
    with it, and nothing else computes a fingerprint any other way.
    """
    canonical = json.dumps(
        {_INPUTS_ALGORITHM: algorithm, _INPUTS_COMPONENTS: components},
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.blake2b(canonical.encode("ascii")).hexdigest()


def _foreign_key_path(workspace_root: Path, key: str) -> Path:
    """The path a ``foreign`` key names, refusing any key that could leave the
    workspace (keys may come back from a recorded file)."""
    if key == _WORKSPACE_ROOT_KEY:
        return workspace_root
    parts = key.split("/")
    if (
        "\\" in key
        or PurePosixPath(key).is_absolute()
        or PureWindowsPath(key).anchor
        or any(part in _FORBIDDEN_KEY_PARTS for part in parts)
    ):
        raise SuiteInputsError(
            f"Foreign input key {key!r} is not a plain workspace-relative path. Expected "
            f"'<repo>/<dir>' or another '/'-separated relative path without '.', '..', or "
            f"a drive; refusing a key that could name a path outside {workspace_root}."
        )
    return workspace_root.joinpath(*parts)


def _workspace_member(workspace_root: Path, raw: str) -> Path:
    path = Path(raw)
    if not path.is_absolute() or not _is_within(_path_key(path), _path_key(workspace_root)):
        raise SuiteInputsError(
            f"In-cone ignored input {raw!r} is not an absolute path inside the workspace "
            f"{workspace_root}; in-cone inputs are always workspace paths, so the observed "
            f"set is malformed."
        )
    return path


def _absolute(raw: str) -> Path:
    path = Path(raw)
    if not path.is_absolute():
        raise SuiteInputsError(
            f"Executable {raw!r} is not an absolute path; the runner records resolved "
            f"executables, so the observed set is malformed."
        )
    return path


def _cone_tree_digests(
    package: str, cone_roots: tuple[str, ...], repository_roots: _RepositoryRoots
) -> dict[str, str]:
    roots = [Path(root) for root in cone_roots]
    names = [root.name for root in roots]
    if package not in names or len(set(names)) != len(names):
        raise SuiteInputsError(
            f"Cone {list(cone_roots)} does not name '{package}' exactly once among "
            f"distinct packages. A cone always contains its own package; pass the tuple "
            f"package_cone(workspace, '{package}') returns."
        )
    return {root.name: _tree_digest(root, repository_roots) for root in roots}


def compute_inputs(
    workspace: Path,
    package: str,
    observed: ObservedInputs,
    *,
    cone: tuple[str, ...] | None = None,
) -> dict[str, object]:
    """The ``inputs`` object of a stamped run: every component plus the
    fingerprint over all of them.

    Args:
        workspace: The Datrix monorepo root.
        package: The package the fingerprint is for.
        observed: The observed inputs -- freshly classified from a just-completed
            run (:func:`classify_observed`), or rebuilt from a prior run's own
            stamp (:meth:`ObservedInputs.from_recorded`) so the current state
            of exactly the paths it observed is digested again.
        cone: *package*'s cone as :func:`package_cone` / :func:`package_cones`
            return it. Derived here when omitted; pass it to avoid a second
            workspace scan when the caller already derived it.

    Returns:
        ``{"algorithm": ALGORITHM, "fingerprint": <hex>, "components": {...}}``.

    Raises:
        SuiteInputsError: if any component's state cannot be established, the
            cone does not contain *package*, or an observed key is malformed.
    """
    workspace_root = workspace.resolve()
    cone_roots = package_cone(workspace_root, package) if cone is None else cone
    repository_roots = _RepositoryRoots()
    components: dict[str, object] = {
        _COMPONENT_TREES: _cone_tree_digests(package, cone_roots, repository_roots),
        _COMPONENT_INSTALLED: _installed_digest(cone_roots, repository_roots),
        _COMPONENT_INTERPRETER: interpreter(),
        _COMPONENT_FOREIGN: {
            key: _digest_subtree(_foreign_key_path(workspace_root, key), repository_roots)
            for key in sorted(observed.foreign)
        },
        _COMPONENT_IN_CONE_IGNORED: {
            raw: digest_file(_workspace_member(workspace_root, raw)) for raw in sorted(observed.in_cone_ignored)
        },
        _COMPONENT_EXECUTABLES: {raw: digest_file(_absolute(raw)) for raw in sorted(observed.executables)},
    }
    logger.debug(
        "suite inputs for %s: %d trees, %d foreign, %d in-cone ignored, %d executables",
        package,
        len(cone_roots),
        len(observed.foreign),
        len(observed.in_cone_ignored),
        len(observed.executables),
    )
    return {
        _INPUTS_ALGORITHM: ALGORITHM,
        _INPUTS_FINGERPRINT: fingerprint_of(ALGORITHM, components),
        _INPUTS_COMPONENTS: components,
    }


@dataclass(frozen=True)
class _ParsedInputs:
    """A validated ``inputs`` object."""

    algorithm: str
    fingerprint: str
    trees: dict[str, str]
    installed: str
    interpreter: dict[str, str]
    foreign: dict[str, str]
    in_cone_ignored: dict[str, str]
    executables: dict[str, str]


def _require_object(value: object, where: str, expected_keys: frozenset[str]) -> dict[str, object]:
    if not isinstance(value, dict):
        raise SuiteInputsError(
            f"{where} is a {type(value).__name__}; expected an object with keys "
            f"{sorted(expected_keys)}."
        )
    keys = {key for key in value if isinstance(key, str)}
    if len(keys) != len(value) or keys != expected_keys:
        raise SuiteInputsError(
            f"{where} has keys {sorted(map(str, value))}; expected exactly {sorted(expected_keys)}."
        )
    return {str(key): item for key, item in value.items()}


def _require_text(value: object, where: str) -> str:
    if not isinstance(value, str) or not value:
        raise SuiteInputsError(f"{where} is {value!r}; expected a non-empty string.")
    return value


def _require_digest_map(value: object, where: str) -> dict[str, str]:
    if not isinstance(value, dict):
        raise SuiteInputsError(f"{where} is a {type(value).__name__}; expected an object of digests.")
    return {_require_text(key, f"a key of {where}"): _require_text(item, f"{where}[{key!r}]") for key, item in value.items()}


def _parse_inputs(raw: object, where: str) -> _ParsedInputs:
    top = _require_object(raw, where, _INPUTS_KEYS)
    components = _require_object(top[_INPUTS_COMPONENTS], f"{where}.components", _COMPONENT_KEYS)
    interpreter_fields = _require_object(
        components[_COMPONENT_INTERPRETER], f"{where}.components.interpreter", _INTERPRETER_KEYS
    )
    trees = _require_digest_map(components[_COMPONENT_TREES], f"{where}.components.trees")
    if not trees:
        raise SuiteInputsError(f"{where}.components.trees is empty; a cone always holds its own package.")
    return _ParsedInputs(
        algorithm=_require_text(top[_INPUTS_ALGORITHM], f"{where}.algorithm"),
        fingerprint=_require_text(top[_INPUTS_FINGERPRINT], f"{where}.fingerprint"),
        trees=trees,
        installed=_require_text(components[_COMPONENT_INSTALLED], f"{where}.components.installed"),
        interpreter={
            field: _require_text(value, f"{where}.components.interpreter.{field}")
            for field, value in interpreter_fields.items()
        },
        foreign=_require_digest_map(components[_COMPONENT_FOREIGN], f"{where}.components.foreign"),
        in_cone_ignored=_require_digest_map(
            components[_COMPONENT_IN_CONE_IGNORED], f"{where}.components.in_cone_ignored"
        ),
        executables=_require_digest_map(components[_COMPONENT_EXECUTABLES], f"{where}.components.executables"),
    )


def _recorded_algorithm(recorded: object) -> str:
    if not isinstance(recorded, dict) or _INPUTS_ALGORITHM not in recorded:
        raise SuiteInputsError(f"recorded inputs carry no '{_INPUTS_ALGORITHM}' field.")
    return _require_text(recorded[_INPUTS_ALGORITHM], "recorded inputs.algorithm")


class _IncomparableStamp(Exception):
    """A recorded stamp that cannot be compared component by component."""

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


def _comparable_stamp(recorded: object, algorithm: str) -> _ParsedInputs:
    """*recorded* parsed, when it was stamped under *algorithm* and is well formed.

    Raises:
        _IncomparableStamp: naming the one reason it cannot be compared -- a
            different (or absent) algorithm, or a malformed stamp.
    """
    try:
        if _recorded_algorithm(recorded) != algorithm:
            raise _IncomparableStamp(_REASON_ALGORITHM)
        return _parse_inputs(recorded, "recorded inputs")
    except SuiteInputsError as exc:
        raise _IncomparableStamp(_REASON_MALFORMED.format(detail=exc)) from exc


def incomparable_stamp_reasons(recorded: object) -> list[str]:
    """Why a recorded stamp cannot be compared at all, decided before anything
    is recomputed.

    Empty when *recorded* is a well-formed stamp under the current
    :data:`ALGORITHM`; otherwise the single reason :func:`diff_components`
    itself would give for it (``"algorithm version differs"``, or ``"recorded
    inputs are malformed: ..."``). A caller uses it to refuse a stamp without
    digesting the workspace, and still reports the reason in the same
    vocabulary as a component diff.

    Args:
        recorded: A prior run's stamped ``inputs`` object (as read from JSON).
    """
    try:
        _comparable_stamp(recorded, ALGORITHM)
    except _IncomparableStamp as exc:
        return [exc.reason]
    return []


def _diff_digest_map(recorded: dict[str, str], current: dict[str, str], subject: str) -> list[str]:
    reasons: list[str] = []
    for key in sorted(recorded.keys() | current.keys()):
        described = subject.format(key=key)
        if key not in recorded:
            reasons.append(f"{described} added")
        elif key not in current:
            reasons.append(f"{described} removed")
        elif recorded[key] != current[key]:
            reasons.append(f"{described} changed")
    return reasons


def diff_components(recorded: dict[str, object], current: dict[str, object]) -> list[str]:
    """Why *current* differs from *recorded*, one reason per differing component.

    Empty exactly when the two are interchangeable: same algorithm, every
    component equal, and the recorded fingerprint equal to the current one.
    A recorded stamp that is malformed, or whose fingerprint does not match its
    own components, yields a reason rather than an empty list -- the caller can
    treat "no reasons" as "carriable" without further checks.

    Args:
        recorded: A prior run's stamped ``inputs`` object (as read from JSON).
        current: :func:`compute_inputs`'s output for the same package, now.

    Returns:
        Reasons such as ``"datrix-common tree changed"``,
        ``"foreign tree datrix/examples changed"``, ``"ignored input <path>
        changed"``, ``"executable <path> removed"``, ``"installed distributions
        changed"``, ``"interpreter changed"``, ``"algorithm version differs"``.

    Raises:
        SuiteInputsError: if *current* is malformed (a caller defect -- it must
            come from :func:`compute_inputs`).
    """
    now = _parse_inputs(current, "current inputs")
    try:
        then = _comparable_stamp(recorded, now.algorithm)
    except _IncomparableStamp as exc:
        return [exc.reason]
    reasons = [
        *_diff_digest_map(then.trees, now.trees, _SUBJECT_TREE),
        *_diff_digest_map(then.foreign, now.foreign, _SUBJECT_FOREIGN),
        *_diff_digest_map(then.in_cone_ignored, now.in_cone_ignored, _SUBJECT_IGNORED),
        *_diff_digest_map(then.executables, now.executables, _SUBJECT_EXECUTABLE),
    ]
    if then.installed != now.installed:
        reasons.append(_REASON_INSTALLED)
    if then.interpreter != now.interpreter:
        reasons.append(_REASON_INTERPRETER)
    if not reasons and then.fingerprint != now.fingerprint:
        reasons.append(_REASON_INCONSISTENT)
    return reasons


# ---------------------------------------------------------------------------
# Self-test harness -- mirrors affected_set.py's _ok/_fail/_step +
# run_self_test_checks pattern. Every check builds real git repositories in
# a temporary directory; nothing is stubbed.
# ---------------------------------------------------------------------------

_GREEN = "\033[92m"
_RED = "\033[91m"
_CYAN = "\033[96m"
_RESET = "\033[0m"

_SELF_TEST_PREFIX = "suite-inputs-selftest-"
#: Every other self-test fixture lives under the OS temp directory (an
#: isolation convenience of ``tempfile.TemporaryDirectory()`` with no ``dir``
#: override). The transient-executable check needs a fixture root that is
#: genuinely OUTSIDE the OS temp directory -- matching every real workspace,
#: which never sits under it -- so it roots there instead: the workspace's own
#: scratch directory, itself never nested under the OS temp directory.
_SELF_TEST_OUTSIDE_TEMP_ROOT = _LIBRARY_DIR.parent.parent.parent / ".tmp"
#: Identity and line-ending settings passed on every self-test git call, so
#: the synthetic repositories never depend on the machine's git config.
_SELF_TEST_GIT_CONFIG = (
    "-c",
    "user.email=suite-inputs-selftest@example.invalid",
    "-c",
    "user.name=suite-inputs self-test",
    "-c",
    "core.autocrlf=false",
)
_OPEN_EVENT = "open"
_AUDITED_ACCESS_EVENTS = frozenset({_OPEN_EVENT, "os.listdir", "os.scandir"})
_PROCESS_LAUNCH_EVENT = "subprocess.Popen"
#: Subtrees digested in one computation by the launch-count check; enough that
#: per-subtree git calls (two each) could never fit the per-repository bound.
_SELF_TEST_SUBTREE_COUNT = 8
#: Git launches one repository costs a whole computation: the work-tree root
#: probe, one index read and one status read.
_GIT_LAUNCHES_PER_REPOSITORY = 3
_SELF_TEST_DIST_NAME = "suite-inputs-selftest-dist"
_SELF_TEST_METADATA = "Metadata-Version: 2.1\nName: {name}\nVersion: {version}\n"


def _ok(msg: str) -> None:
    print(f"{_GREEN}[OK]{_RESET} {msg}")


def _fail(msg: str) -> None:
    print(f"{_RED}[FAIL]{_RESET} {msg}")


def _step(msg: str) -> None:
    print(f"\n{_CYAN}=== {msg}{_RESET}")


def run_self_test_checks(checks: list[tuple[str, Callable[[], None]]]) -> bool:
    """Run every (name, check_fn) pair, printing [OK]/[FAIL] per check.

    Returns:
        True iff every check passed.
    """
    all_passed = True
    for name, fn in checks:
        try:
            fn()
        except (AssertionError, UsageError) as exc:
            _fail(f"{name}: {type(exc).__name__}: {exc}")
            all_passed = False
        else:
            _ok(name)
    return all_passed


class _AuditedAccess:
    """Paths this process opens or lists under one root while active, and how
    many child processes it launches.

    Backed by one real ``sys.addaudithook`` -- the same ``open`` /
    ``os.listdir`` / ``os.scandir`` events the suite runner's observation
    recorder uses, plus ``subprocess.Popen``. Audit hooks cannot be removed,
    so the hook is installed on first use and does nothing while no recorder
    is active.
    """

    _active: ClassVar[list[_AuditedAccess]] = []
    _hook_installed: ClassVar[bool] = False

    def __init__(self, root: Path) -> None:
        self._root = os.path.normcase(os.path.abspath(root))
        self.opened: set[str] = set()
        self.listed: set[str] = set()
        self.launches = 0

    def __enter__(self) -> _AuditedAccess:
        if not _AuditedAccess._hook_installed:
            sys.addaudithook(_AuditedAccess._hook)
            _AuditedAccess._hook_installed = True
        _AuditedAccess._active.append(self)
        return self

    def __exit__(self, *exc_info: object) -> None:
        _AuditedAccess._active.remove(self)

    @staticmethod
    def _hook(event: str, args: tuple[object, ...]) -> None:
        if not _AuditedAccess._active:
            return
        if event == _PROCESS_LAUNCH_EVENT:
            for recorder in _AuditedAccess._active:
                recorder.launches += 1
            return
        if event not in _AUDITED_ACCESS_EVENTS or not args:
            return
        raw = args[0]
        if not isinstance(raw, (str, bytes, os.PathLike)):
            return
        try:
            path = os.path.normcase(os.path.abspath(os.fsdecode(raw)))
        except ValueError:
            # A path the OS would reject (an embedded NUL) is not a read under
            # the root; the audited call itself will raise for it.
            return
        for recorder in _AuditedAccess._active:
            recorder._observe(event, path)

    def _observe(self, event: str, path: str) -> None:
        if path != self._root and not path.startswith(self._root + os.sep):
            return
        (self.opened if event == _OPEN_EVENT else self.listed).add(path)


def _normalized(path: Path) -> str:
    return os.path.normcase(os.path.abspath(path))


def _git(repo: Path, *args: str) -> str:
    result = subprocess.run(
        ["git", "-C", str(repo), *_SELF_TEST_GIT_CONFIG, *args],
        capture_output=True,
        check=False,
    )
    assert result.returncode == 0, (
        f"self-test git {' '.join(args)} failed in {repo}: "
        f"{result.stderr.decode('utf-8', errors='replace')}"
    )
    return result.stdout.decode("utf-8", errors="replace")


def _write(path: Path, text: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


def _init_repository(directory: Path) -> Path:
    directory.mkdir(parents=True, exist_ok=True)
    _git(directory, "init", "-q")
    return directory


def _commit_all(repo: Path, message: str) -> None:
    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "-m", message)


def _small_repository(root: Path) -> Path:
    repo = _init_repository(root / "repo")
    _write(repo / "a.txt", "alpha")
    _write(repo / "sub" / "b.txt", "beta")
    _commit_all(repo, "initial")
    return repo


def _check_clean_tree_reads_no_content() -> None:
    with tempfile.TemporaryDirectory(prefix=_SELF_TEST_PREFIX) as tmp:
        repo = _small_repository(Path(tmp).resolve())
        first = tree_digest(repo)
        with _AuditedAccess(repo) as access:
            second = tree_digest(repo)
        assert access.opened == set() and access.listed == set(), (
            f"a clean tree must be digested from its index alone; this process opened "
            f"{sorted(access.opened)} and listed {sorted(access.listed)}"
        )
        assert first == second, "an unchanged clean tree must digest identically"
        with _AuditedAccess(repo) as control:
            (repo / "a.txt").read_bytes()
        assert control.opened == {_normalized(repo / "a.txt")}, (
            f"positive control: the recorder must see an in-process read under the root; "
            f"saw {sorted(control.opened)}"
        )


def _check_one_modified_file_reads_exactly_that_file() -> None:
    with tempfile.TemporaryDirectory(prefix=_SELF_TEST_PREFIX) as tmp:
        repo = _small_repository(Path(tmp).resolve())
        before = tree_digest(repo)
        _write(repo / "a.txt", "alphb")
        with _AuditedAccess(repo) as access:
            after = tree_digest(repo)
        assert access.opened == {_normalized(repo / "a.txt")}, (
            f"exactly the modified file must be read; read {sorted(access.opened)}"
        )
        assert access.listed == set(), f"no directory may be listed; listed {sorted(access.listed)}"
        assert before != after, "a one-byte change to a tracked file must change the tree digest"


def _check_untracked_file_in_new_directory_is_digested() -> None:
    """A new directory's files are digested one by one (--untracked-files=all),
    so a later edit INSIDE the directory still moves the digest."""
    with tempfile.TemporaryDirectory(prefix=_SELF_TEST_PREFIX) as tmp:
        repo = _small_repository(Path(tmp).resolve())
        clean = tree_digest(repo)
        _write(repo / "newdir" / "deep" / "n.txt", "one")
        with_new_file = tree_digest(repo)
        _write(repo / "newdir" / "deep" / "n.txt", "two")
        edited = tree_digest(repo)
        assert len({clean, with_new_file, edited}) == 3, (
            "an untracked file in a new directory must be digested by content: adding it "
            "and editing it must each change the tree digest"
        )


def _check_ignored_file_is_not_part_of_the_tree_digest() -> None:
    """Ignored files are what the in_cone_ignored component exists for; the
    tree digest is the tracked state only."""
    with tempfile.TemporaryDirectory(prefix=_SELF_TEST_PREFIX) as tmp:
        repo = _small_repository(Path(tmp).resolve())
        _write(repo / ".gitignore", "build/\n")
        _commit_all(repo, "ignore build")
        before = tree_digest(repo)
        _write(repo / "build" / "artifact.bin", "generated")
        assert tree_digest(repo) == before, "an ignored file must not enter the tree digest"


def _check_staged_rename_appears_once_at_new_path() -> None:
    with tempfile.TemporaryDirectory(prefix=_SELF_TEST_PREFIX) as tmp:
        repo = _small_repository(Path(tmp).resolve())
        before = tree_digest(repo)
        _git(repo, "mv", "a.txt", "moved.txt")
        entries = _git_state_entries(repo, "", _RepositoryRoots())
        assert "a.txt" not in entries, f"a renamed file must not remain at its old path: {entries}"
        assert entries["moved.txt"].startswith(f"{_WORKTREE_ENTRY_PREFIX} "), (
            f"a renamed file must appear once, at its new path, with a content digest: {entries}"
        )
        assert sorted(entries) == ["moved.txt", "sub/b.txt"], sorted(entries)
        assert tree_digest(repo) != before, "a rename must change the tree digest"


def _check_deleted_file_drops_out() -> None:
    with tempfile.TemporaryDirectory(prefix=_SELF_TEST_PREFIX) as tmp:
        repo = _small_repository(Path(tmp).resolve())
        (repo / "sub" / "b.txt").unlink()
        entries = _git_state_entries(repo, "", _RepositoryRoots())
        assert sorted(entries) == ["a.txt"], f"a deleted file must drop out: {entries}"


def _check_assume_unchanged_file_is_read_from_worktree() -> None:
    """git status hides edits to an assume-unchanged file; the digest must
    not."""
    with tempfile.TemporaryDirectory(prefix=_SELF_TEST_PREFIX) as tmp:
        repo = _small_repository(Path(tmp).resolve())
        before = tree_digest(repo)
        _git(repo, "update-index", "--assume-unchanged", "a.txt")
        _write(repo / "a.txt", "alphb")
        assert _status_paths(repo, (_WHOLE_TREE_PATHSPEC,)) == set(), (
            "precondition: git status must not report an assume-unchanged edit"
        )
        with _AuditedAccess(repo) as access:
            after = tree_digest(repo)
        assert after != before, "an edit to an assume-unchanged file must change the tree digest"
        assert access.opened == {_normalized(repo / "a.txt")}, sorted(access.opened)


def _check_runner_output_dir_is_not_an_input() -> None:
    """Even in a repository that does not ignore it, the runner's own output
    directory never enters the digest -- the stamp itself is written there."""
    with tempfile.TemporaryDirectory(prefix=_SELF_TEST_PREFIX) as tmp:
        repo = _small_repository(Path(tmp).resolve())
        before = tree_digest(repo)
        _write(repo / _RUNNER_OUTPUT_DIRNAME / "test-results-20260101-000000" / "index.json", "{}")
        assert tree_digest(repo) == before, "the runner output directory must not be an input"


def _check_non_repository_tree_raises() -> None:
    with tempfile.TemporaryDirectory(prefix=_SELF_TEST_PREFIX) as tmp:
        plain = Path(tmp).resolve() / "plain"
        _write(plain / "a.txt", "alpha")
        assert _raises_suite_inputs_error(lambda: tree_digest(plain)), (
            "a tree that is not a git work-tree root must raise"
        )


def _check_foreign_subtree_scope_is_literal() -> None:
    """A subtree whose name contains wildcard characters digests exactly that
    subtree: ``weird[1]`` must not be matched as the pattern that selects the
    sibling file ``weird1``."""
    with tempfile.TemporaryDirectory(prefix=_SELF_TEST_PREFIX) as tmp:
        repo = _small_repository(Path(tmp).resolve())
        literal_dir = repo / "weird[1]"
        _write(literal_dir / "inside.txt", "in")
        sibling_file = _write(repo / "weird1", "sibling")
        _commit_all(repo, "wildcard names")
        before = digest_subtree(literal_dir)
        _flip_last_byte(sibling_file)
        assert digest_subtree(literal_dir) == before, (
            "a change in the sibling weird1 must not move the digest of weird[1]"
        )
        _flip_last_byte(literal_dir / "inside.txt")
        assert digest_subtree(literal_dir) != before, "a change inside weird[1] must move its digest"


def _check_scoped_state_matches_git_literal_pathspec() -> None:
    """A subtree's entries are one whole-tree read of its repository filtered
    here, never a git call per subtree; for every scope shape the filter must
    select exactly what git's own literal pathspec selects -- a partial name,
    a case variant, a wildcard name, a file, a tracked, an untracked and an
    ignored directory, and a path that does not exist."""
    with tempfile.TemporaryDirectory(prefix=_SELF_TEST_PREFIX) as tmp:
        repo = _small_repository(Path(tmp).resolve())
        _write(repo / ".gitignore", "build/\n")
        _write(repo / "tests" / "unit" / "a.py", "a")
        _write(repo / "tests" / "b.py", "b")
        _write(repo / "tes", "partial-name sibling")
        _write(repo / "weird[1]" / "inside.txt", "in")
        _write(repo / "weird1", "sibling")
        _commit_all(repo, "scope shapes")
        _write(repo / "tests" / "b.py", "b edited")
        _write(repo / "tests" / "new" / "c.py", "untracked")
        _write(repo / "build" / "out.bin", "ignored")
        _write(repo / _RUNNER_OUTPUT_DIRNAME / "index.json", "{}")
        state = _RepositoryRoots().state(repo)
        scopes = (
            "", "tests", "tes", "Tests", "tests/unit", "tests/unit/a.py", "tests/new",
            "weird[1]", "build", "sub/b.txt", "absent",
        )
        for scope in scopes:
            included = f"{_LITERAL_PATHSPEC_MAGIC}{scope}" if scope else _WHOLE_TREE_PATHSPEC
            pathspec = (included, _RUNNER_OUTPUT_EXCLUDE)
            filtered_records = {record for record in state.records if _within_scope(record.path, scope)}
            git_records = set(_index_records(repo, pathspec))
            assert filtered_records == git_records, (
                f"scope {scope!r}: the filtered index selects {sorted(r.path for r in filtered_records)}, "
                f"git's literal pathspec selects {sorted(r.path for r in git_records)}"
            )
            filtered_status = {path for path in state.status_paths if _within_scope(path, scope)}
            git_status = _status_paths(repo, pathspec)
            assert filtered_status == git_status, (
                f"scope {scope!r}: the filtered status selects {sorted(filtered_status)}, "
                f"git's literal pathspec selects {sorted(git_status)}"
            )
        assert "tests/b.py" in state.status_paths and "tests/new/c.py" in state.status_paths, (
            f"non-vacuity: the whole-tree status must name the edited and the untracked file; "
            f"it named {sorted(state.status_paths)}"
        )


def _check_subtree_digests_read_each_repository_once() -> None:
    """Digesting many subtrees of one repository in one computation launches
    a fixed number of git processes, not two per subtree: a suite that walks a
    sibling package observes thousands of paths in it, and a stamp paying two
    process launches for each once took over ten minutes to compute."""
    with tempfile.TemporaryDirectory(prefix=_SELF_TEST_PREFIX) as tmp:
        repo = _small_repository(Path(tmp).resolve())
        subtrees = [repo / f"d{index}" for index in range(_SELF_TEST_SUBTREE_COUNT)]
        for index, subtree in enumerate(subtrees):
            _write(subtree / "f.txt", str(index))
        _commit_all(repo, "many subtrees")
        roots = _RepositoryRoots()
        with _AuditedAccess(repo) as access:
            digests = {_digest_subtree(subtree, roots) for subtree in subtrees}
        assert len(digests) == _SELF_TEST_SUBTREE_COUNT, (
            f"each subtree must digest to its own git state; got {len(digests)} distinct digests"
        )
        assert all(digest.startswith(f"{_KIND_GIT_STATE}:") for digest in digests), sorted(digests)
        assert 0 < access.launches <= _GIT_LAUNCHES_PER_REPOSITORY, (
            f"digesting {_SELF_TEST_SUBTREE_COUNT} subtrees of one repository launched "
            f"{access.launches} processes; expected at most {_GIT_LAUNCHES_PER_REPOSITORY} "
            f"(root probe, index read, status read)"
        )


def _check_vanished_input_is_distinct_from_empty() -> None:
    with tempfile.TemporaryDirectory(prefix=_SELF_TEST_PREFIX) as tmp:
        root = Path(tmp).resolve()
        empty = _write(root / "empty.txt", "")
        missing = root / "missing.txt"
        listing = digest_file(root)
        assert len({digest_file(empty), digest_file(missing), listing}) == 3, (
            "an empty file, a missing file and a directory must digest differently"
        )
        _write(root / "another.txt", "x")
        assert digest_file(root) != listing, "a new entry must change a directory's listing digest"


def _check_invalid_name_observed_input_is_absent_not_an_error() -> None:
    """A recorded path whose name the operating system itself rejects (e.g.
    the pseudo-filename ``<unknown>`` an ``open`` audit event names for a
    library's failed open attempt -- Windows raises ERROR_INVALID_NAME,
    winerror 123, for it) digests as ``absent``, exactly like a path that is
    simply missing, and never raises: a name no filesystem could ever hold
    can never hold content. A genuinely unreadable path -- opening a
    directory as if it were a file, which raises a permission-style OSError
    that is neither ERROR_INVALID_NAME nor EINVAL on either platform -- must
    still raise, fail closed."""
    with tempfile.TemporaryDirectory(prefix=_SELF_TEST_PREFIX) as tmp:
        workspace = Path(tmp).resolve()
        pkg_dir = workspace / "pkg"
        pkg_dir.mkdir()
        invalid_name_path = pkg_dir / "<unknown>"
        missing_path = pkg_dir / "definitely-missing.txt"
        assert digest_file(invalid_name_path) == _ABSENT, digest_file(invalid_name_path)
        assert digest_file(invalid_name_path) == digest_file(missing_path)

        assert _raises_suite_inputs_error(lambda: _content_hex(pkg_dir)), (
            "opening a directory as a file must still raise, not be swallowed as absent"
        )


def _build_scanned_workspace(root: Path) -> None:
    """A synthetic monorepo mixing every edge signal affected_set scans."""
    affected_set._make_pkg(root, "datrix-common", conftest_imports=["datrix_cli"])
    affected_set._make_pkg(root, "datrix-language", imports=["datrix_common"])
    affected_set._make_pkg(root, "datrix-codegen-common", type_checking_imports=["datrix_common"])
    affected_set._make_pkg(
        root, "datrix-cli", imports=["datrix_codegen_common"], deferred_imports=["datrix_language"]
    )
    affected_set._make_pkg(
        root, "datrix-codegen-python", deps=["datrix-codegen-common"], test_imports=["datrix_cli"]
    )
    affected_set._make_node_pkg(root, "datrix-client")
    affected_set._write_cross_ecosystem_config(root, {"datrix-client": ["datrix-language"]})


def _check_package_cone_is_the_dual_of_the_reverse_closure() -> None:
    """package_cone(P) names exactly the packages Q whose reverse closure
    (compute_affected_closures, same scan) contains P."""
    with tempfile.TemporaryDirectory(prefix=_SELF_TEST_PREFIX) as tmp:
        root = Path(tmp).resolve()
        _build_scanned_workspace(root)
        graphs = affected_set.build_workspace_graphs(root)
        closures = affected_set.compute_affected_closures(
            graphs.source_graph, graphs.test_graph, graphs.deferred_graph
        )
        cones = package_cones(root)
        for package in graphs.packages:
            cone = package_cone(root, package)
            assert cone == cones[package], (package, cone, cones[package])
            expected = {other for other, closure in closures.items() if package in closure}
            assert {Path(member).name for member in cone} == expected, (package, cone, expected)
            assert all(Path(member) == graphs.packages[Path(member).name] for member in cone), cone
        assert {Path(member).name for member in cones["datrix-common"]} == {
            "datrix-common",
            "datrix-cli",
            "datrix-codegen-common",
        }, cones["datrix-common"]


def _check_node_consumer_cone_includes_cross_ecosystem_dependency() -> None:
    with tempfile.TemporaryDirectory(prefix=_SELF_TEST_PREFIX) as tmp:
        root = Path(tmp).resolve()
        _build_scanned_workspace(root)
        names = {Path(member).name for member in package_cone(root, "datrix-client")}
        assert names == {"datrix-client", "datrix-language", "datrix-common"}, names


def _check_unknown_package_raises() -> None:
    with tempfile.TemporaryDirectory(prefix=_SELF_TEST_PREFIX) as tmp:
        root = Path(tmp).resolve()
        affected_set._make_pkg(root, "datrix-solo")
        try:
            package_cone(root, "datrix-missing")
        except SuiteInputsError as exc:
            message = str(exc)
        else:
            raise AssertionError("an unknown package must raise SuiteInputsError")
        assert "datrix-missing" in message and "datrix-solo" in message, (
            f"the error must name the unknown package and the valid ones: {message}"
        )


@dataclass(frozen=True)
class _FingerprintWorkspace:
    """A synthetic workspace with one input of every observed kind."""

    workspace: Path
    package_dir: Path
    ignored_input: Path
    foreign_file: Path
    foreign_ignored_file: Path
    unowned_file: Path
    executable: Path
    records: dict[str, list[str]]


def _build_fingerprint_workspace(root: Path) -> _FingerprintWorkspace:
    """One observed input per component, none overlapping another: a change
    to any one of them moves exactly one component."""
    workspace = root / "workspace"
    workspace.mkdir()
    package_dir = affected_set._make_pkg(workspace, "datrix-solo")
    _write(package_dir / ".gitignore", "build/\n")
    ignored_input = _write(package_dir / "build" / "cache.txt", "v1")
    _init_repository(package_dir)
    _commit_all(package_dir, "initial")
    showcase = workspace / "datrix"
    affected_set._write_cross_ecosystem_config(workspace, {})
    _write(showcase / ".gitignore", ".cache/\n")
    foreign_file = _write(showcase / "examples" / "one" / "system.dtrx", "service a {}\n")
    foreign_ignored_file = _write(showcase / "examples" / "one" / ".cache" / "x.bin", "c1")
    _init_repository(showcase)
    _commit_all(showcase, "initial")
    unowned_file = _write(workspace / "notes" / "draft.md", "draft")
    executable = _write(root / "bin" / "tool.bin", "v1")
    records: dict[str, list[str]] = {
        _RECORD_OPENED: [
            str(package_dir / "src" / "datrix_solo" / "__init__.py"),
            str(ignored_input),
            str(foreign_file),
            str(foreign_ignored_file),
            str(unowned_file),
        ],
        _RECORD_LISTED: [str(package_dir / "src" / "datrix_solo")],
        _RECORD_DLOPENED: [],
        _RECORD_EXECUTABLES: [str(executable)],
    }
    return _FingerprintWorkspace(
        workspace=workspace,
        package_dir=package_dir,
        ignored_input=ignored_input,
        foreign_file=foreign_file,
        foreign_ignored_file=foreign_ignored_file,
        unowned_file=unowned_file,
        executable=executable,
        records=records,
    )


def _check_classify_observed_buckets() -> None:
    """Every classification rule on one record: tracked in-cone file and
    directory dropped; ignored and untracked in-cone files kept by path;
    a covered foreign file coarsened to <repo>/<top-level-dir>; an ignored
    foreign file and a file in no repository kept exactly; a listed repository
    root and the listed workspace root kept; the interpreter's own
    environment dropped; an unexpanded glob pattern skipped."""
    _SELF_TEST_OUTSIDE_TEMP_ROOT.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(
        prefix=_SELF_TEST_PREFIX, dir=str(_SELF_TEST_OUTSIDE_TEMP_ROOT)
    ) as tmp:
        # Rooted outside the OS temp directory (unlike every other fixture
        # here): fixture.executable must be a real, kept input, and a
        # location under the OS temp directory is now transient by
        # definition (see is_transient), like every real workspace.
        fixture = _build_fingerprint_workspace(Path(tmp).resolve())
        untracked_input = _write(fixture.package_dir / "notes.txt", "untracked")
        showcase = fixture.workspace / "datrix"
        records = {kind: list(paths) for kind, paths in fixture.records.items()}
        records[_RECORD_OPENED] += [str(untracked_input), str(Path(sys.prefix).resolve() / "pyvenv.cfg")]
        records[_RECORD_LISTED] += [
            str(fixture.workspace),
            str(showcase),
            str(showcase / "examples" / "*" / "system.dtrx"),
        ]
        cone = package_cone(fixture.workspace, "datrix-solo")
        observed = classify_observed(records, cone, fixture.workspace)
        assert observed.in_cone_ignored == frozenset(
            {str(fixture.ignored_input), str(untracked_input)}
        ), sorted(observed.in_cone_ignored)
        assert observed.foreign == frozenset(
            {
                "datrix/examples",
                "datrix/examples/one/.cache/x.bin",
                "notes/draft.md",
                "datrix",
                _WORKSPACE_ROOT_KEY,
            }
        ), sorted(observed.foreign)
        assert observed.executables == frozenset({str(fixture.executable)}), observed.executables


def _raises_suite_inputs_error(action: Callable[[], object]) -> bool:
    try:
        action()
    except SuiteInputsError:
        return True
    return False


def _check_classify_observed_rejects_malformed_records() -> None:
    with tempfile.TemporaryDirectory(prefix=_SELF_TEST_PREFIX) as tmp:
        root = Path(tmp).resolve()
        fixture = _build_fingerprint_workspace(root)
        cone = package_cone(fixture.workspace, "datrix-solo")
        valid: dict[str, object] = {kind: list(paths) for kind, paths in fixture.records.items()}
        malformed_records: list[dict[str, object]] = [
            {kind: paths for kind, paths in valid.items() if kind != _RECORD_DLOPENED},
            {**valid, "environment": []},
            {**valid, _RECORD_OPENED: ["relative/path.txt"]},
            {**valid, _RECORD_OPENED: [str(root / "elsewhere.txt")]},
            {**valid, _RECORD_LISTED: str(fixture.workspace)},
        ]
        assert not _raises_suite_inputs_error(lambda: classify_observed(valid, cone, fixture.workspace))
        for malformed in malformed_records:
            assert _raises_suite_inputs_error(
                lambda record=malformed: classify_observed(record, cone, fixture.workspace)
            ), f"a malformed observed record must raise: {malformed}"


def _check_transient_executable_is_not_a_fingerprint_input() -> None:
    """An executable resolved under the OS temp directory or under one of the
    workspace's own scratch directories is an output the run itself started,
    never a fingerprint input: classify_observed drops it, and a later change
    to its content never moves the fingerprint. A real executable elsewhere
    is kept exactly, and a change to it still moves the fingerprint."""
    _SELF_TEST_OUTSIDE_TEMP_ROOT.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(
        prefix=_SELF_TEST_PREFIX, dir=str(_SELF_TEST_OUTSIDE_TEMP_ROOT)
    ) as tmp:
        root = Path(tmp).resolve()
        assert not root.is_relative_to(Path(tempfile.gettempdir()).resolve()), (
            "precondition: this fixture must live outside the OS temp directory, like every "
            "real workspace does"
        )
        fixture = _build_fingerprint_workspace(root)
        cone = package_cone(fixture.workspace, "datrix-solo")
        with tempfile.TemporaryDirectory(prefix=_SELF_TEST_PREFIX) as scratch:
            temp_executable = _write(Path(scratch).resolve() / "mvnw.cmd", "v1")
            workspace_scratch_executable = _write(
                fixture.workspace / ".tmp" / "generated" / "javac.exe", "v1"
            )
            records = {kind: list(paths) for kind, paths in fixture.records.items()}
            records[_RECORD_EXECUTABLES] = [
                str(fixture.executable),
                str(temp_executable),
                str(workspace_scratch_executable),
            ]
            observed = classify_observed(records, cone, fixture.workspace)
            assert observed.executables == frozenset({str(fixture.executable)}), sorted(
                observed.executables
            )

            recorded = compute_inputs(fixture.workspace, "datrix-solo", observed, cone=cone)
            _flip_last_byte(temp_executable)
            _flip_last_byte(workspace_scratch_executable)
            unchanged = compute_inputs(fixture.workspace, "datrix-solo", observed, cone=cone)
            assert diff_components(recorded, unchanged) == [], (
                "a byte change to a transient executable must not move the fingerprint: "
                f"{diff_components(recorded, unchanged)}"
            )

            _flip_last_byte(fixture.executable)
            moved = compute_inputs(fixture.workspace, "datrix-solo", observed, cone=cone)
            _expect_single_reason(unchanged, moved, f"executable {fixture.executable} changed")


def _one_byte_changed(text: str) -> str:
    return text[:-1] + chr(ord(text[-1]) ^ 1)


def _flip_last_byte(path: Path) -> None:
    """A one-byte, same-size change to *path*'s content."""
    data = path.read_bytes()
    path.write_bytes(data[:-1] + bytes([data[-1] ^ 1]))


def _expect_single_reason(recorded: dict[str, object], current: dict[str, object], reason: str) -> None:
    assert current[_INPUTS_FINGERPRINT] != recorded[_INPUTS_FINGERPRINT], (
        f"the fingerprint must move for: {reason}"
    )
    reasons = diff_components(recorded, current)
    assert reasons == [reason], f"expected exactly [{reason!r}], got {reasons}"


def _write_selftest_distribution(site: Path, version: str) -> None:
    dist_info = site / f"{_SELF_TEST_DIST_NAME.replace('-', '_')}-1.0.dist-info"
    _write(dist_info / "METADATA", _SELF_TEST_METADATA.format(name=_SELF_TEST_DIST_NAME, version=version))


def _check_each_component_moves_the_fingerprint_and_is_named() -> None:
    """A one-byte change in each of the seven components -- a cone tree file,
    an in-cone ignored file, a foreign file, an executable, the installed
    set, the interpreter string, the algorithm constant -- moves the
    fingerprint and is named by diff_components (and only it)."""
    _SELF_TEST_OUTSIDE_TEMP_ROOT.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(
        prefix=_SELF_TEST_PREFIX, dir=str(_SELF_TEST_OUTSIDE_TEMP_ROOT)
    ) as tmp:
        # Rooted outside the OS temp directory: fixture.executable must be a
        # real, kept input whose content change moves the fingerprint, like
        # every real workspace's executables (see is_transient).
        root = Path(tmp).resolve()
        fixture = _build_fingerprint_workspace(root)
        cone = package_cone(fixture.workspace, "datrix-solo")
        observed = classify_observed(fixture.records, cone, fixture.workspace)
        recorded = compute_inputs(fixture.workspace, "datrix-solo", observed, cone=cone)
        again = compute_inputs(fixture.workspace, "datrix-solo", observed)
        assert again == recorded, "identical inputs must produce an identical stamp"
        assert diff_components(recorded, again) == [], diff_components(recorded, again)

        filesystem_changes = (
            (fixture.package_dir / "src" / "datrix_solo" / "__init__.py", "datrix-solo tree changed"),
            (fixture.ignored_input, f"ignored input {fixture.ignored_input} changed"),
            (fixture.foreign_file, "foreign tree datrix/examples changed"),
            (fixture.foreign_ignored_file, "foreign tree datrix/examples/one/.cache/x.bin changed"),
            (fixture.unowned_file, "foreign tree notes/draft.md changed"),
            (fixture.executable, f"executable {fixture.executable} changed"),
        )
        for path, reason in filesystem_changes:
            _flip_last_byte(path)
            current = compute_inputs(fixture.workspace, "datrix-solo", observed, cone=cone)
            _expect_single_reason(recorded, current, reason)
            recorded = current

        site = root / "site"
        _write_selftest_distribution(site, "1.0")
        sys.path.insert(0, str(site))
        try:
            recorded = compute_inputs(fixture.workspace, "datrix-solo", observed, cone=cone)
            _write_selftest_distribution(site, "1.1")
            current = compute_inputs(fixture.workspace, "datrix-solo", observed, cone=cone)
            _expect_single_reason(recorded, current, _REASON_INSTALLED)
        finally:
            sys.path.remove(str(site))
        recorded = compute_inputs(fixture.workspace, "datrix-solo", observed, cone=cone)

        components = recorded[_INPUTS_COMPONENTS]
        assert isinstance(components, dict)
        assert components[_COMPONENT_INTERPRETER] == {"version": sys.version, "platform": sys.platform}
        assert recorded[_INPUTS_FINGERPRINT] == fingerprint_of(ALGORITHM, components), (
            "compute_inputs must assemble its fingerprint with fingerprint_of"
        )
        other_interpreter = copy.deepcopy(components)
        other_interpreter[_COMPONENT_INTERPRETER] = {
            "version": _one_byte_changed(sys.version),
            "platform": sys.platform,
        }
        _expect_single_reason(
            recorded,
            {
                _INPUTS_ALGORITHM: ALGORITHM,
                _INPUTS_FINGERPRINT: fingerprint_of(ALGORITHM, other_interpreter),
                _INPUTS_COMPONENTS: other_interpreter,
            },
            _REASON_INTERPRETER,
        )
        other_algorithm = _one_byte_changed(ALGORITHM)
        assert fingerprint_of(other_algorithm, components) != recorded[_INPUTS_FINGERPRINT]
        _expect_single_reason(
            {**recorded, _INPUTS_ALGORITHM: other_algorithm, _INPUTS_FINGERPRINT: fingerprint_of(other_algorithm, components)},
            recorded,
            _REASON_ALGORITHM,
        )

        rebuilt = ObservedInputs.from_recorded(recorded)
        assert rebuilt == observed, (rebuilt, observed)
        replay = compute_inputs(fixture.workspace, "datrix-solo", rebuilt, cone=cone)
        assert replay[_INPUTS_FINGERPRINT] == recorded[_INPUTS_FINGERPRINT], (
            "observed inputs rebuilt from a stamp must reproduce its fingerprint"
        )


def _check_compute_inputs_reads_no_cone_content_when_clean() -> None:
    """Given the cone, a clean cone tree is fingerprinted from its index
    alone; one modified tracked file is the only file read."""
    with tempfile.TemporaryDirectory(prefix=_SELF_TEST_PREFIX) as tmp:
        fixture = _build_fingerprint_workspace(Path(tmp).resolve())
        cone = package_cone(fixture.workspace, "datrix-solo")
        nothing_observed = ObservedInputs(frozenset(), frozenset(), frozenset())
        with _AuditedAccess(fixture.package_dir) as clean_access:
            clean = compute_inputs(fixture.workspace, "datrix-solo", nothing_observed, cone=cone)
        assert clean_access.opened == set() and clean_access.listed == set(), (
            f"a clean cone must not be read: opened {sorted(clean_access.opened)}, "
            f"listed {sorted(clean_access.listed)}"
        )
        source = fixture.package_dir / "src" / "datrix_solo" / "__init__.py"
        _flip_last_byte(source)
        with _AuditedAccess(fixture.package_dir) as dirty_access:
            dirty = compute_inputs(fixture.workspace, "datrix-solo", nothing_observed, cone=cone)
        assert dirty_access.opened == {_normalized(source)}, sorted(dirty_access.opened)
        assert diff_components(clean, dirty) == ["datrix-solo tree changed"], diff_components(clean, dirty)


def _check_diff_is_complete_and_fails_closed() -> None:
    """Every difference -- a cone member added or removed, a tampered
    fingerprint, a malformed stamp -- yields a reason; only a stamp identical
    in every respect yields none."""
    components: dict[str, object] = {
        _COMPONENT_TREES: {"datrix-a": "git-state:1", "datrix-b": "git-state:2"},
        _COMPONENT_INSTALLED: "installed:3",
        _COMPONENT_INTERPRETER: {"version": "3.14", "platform": "win32"},
        _COMPONENT_FOREIGN: {"datrix/examples": "git-state:4"},
        _COMPONENT_IN_CONE_IGNORED: {},
        _COMPONENT_EXECUTABLES: {},
    }

    def stamp(parts: dict[str, object]) -> dict[str, object]:
        return {
            _INPUTS_ALGORITHM: ALGORITHM,
            _INPUTS_FINGERPRINT: fingerprint_of(ALGORITHM, parts),
            _INPUTS_COMPONENTS: parts,
        }

    current = stamp(components)
    assert diff_components(copy.deepcopy(current), current) == []
    fewer = copy.deepcopy(components)
    fewer[_COMPONENT_TREES] = {"datrix-a": "git-state:1"}
    assert diff_components(stamp(fewer), current) == ["datrix-b tree added"], diff_components(stamp(fewer), current)
    assert diff_components(current, stamp(fewer)) == ["datrix-b tree removed"]
    tampered = {**copy.deepcopy(current), _INPUTS_FINGERPRINT: "0" * len(str(current[_INPUTS_FINGERPRINT]))}
    assert diff_components(tampered, current) == [_REASON_INCONSISTENT], diff_components(tampered, current)
    malformed_stamps: list[dict[str, object]] = [
        {_INPUTS_ALGORITHM: ALGORITHM},
        {_INPUTS_FINGERPRINT: "x", _INPUTS_COMPONENTS: components},
        {**copy.deepcopy(current), _INPUTS_COMPONENTS: {**components, "extra": {}}},
        {**copy.deepcopy(current), _INPUTS_COMPONENTS: {**components, _COMPONENT_TREES: {}}},
    ]
    for malformed in malformed_stamps:
        reasons = diff_components(malformed, current)
        assert len(reasons) == 1 and reasons[0].startswith("recorded inputs are malformed"), reasons
        assert incomparable_stamp_reasons(malformed) == reasons, (
            "the pre-compute stamp check must refuse a malformed stamp with diff_components' own reason: "
            f"{incomparable_stamp_reasons(malformed)} vs {reasons}"
        )
    assert incomparable_stamp_reasons(current) == [], incomparable_stamp_reasons(current)
    other_algorithm = {**copy.deepcopy(current), _INPUTS_ALGORITHM: _one_byte_changed(ALGORITHM)}
    assert incomparable_stamp_reasons(other_algorithm) == [_REASON_ALGORITHM] == diff_components(
        other_algorithm, current
    ), incomparable_stamp_reasons(other_algorithm)
    assert _raises_suite_inputs_error(lambda: ObservedInputs.from_recorded({_INPUTS_ALGORITHM: ALGORITHM})), (
        "rebuilding observed inputs from a malformed stamp must raise"
    )


def _check_observed_keys_cannot_leave_the_workspace() -> None:
    with tempfile.TemporaryDirectory(prefix=_SELF_TEST_PREFIX) as tmp:
        root = Path(tmp).resolve()
        fixture = _build_fingerprint_workspace(root)
        cone = package_cone(fixture.workspace, "datrix-solo")
        escaping = (
            ObservedInputs(frozenset(), frozenset({"../outside"}), frozenset()),
            ObservedInputs(frozenset(), frozenset({str(root / "outside")}), frozenset()),
            ObservedInputs(frozenset({str(root / "outside.txt")}), frozenset(), frozenset()),
        )
        for observed in escaping:
            assert _raises_suite_inputs_error(
                lambda inputs=observed: compute_inputs(fixture.workspace, "datrix-solo", inputs, cone=cone)
            ), f"an observed key outside the workspace must raise: {observed}"


def _check_installed_digest_drops_only_editable_framework_installs() -> None:
    """An editable datrix-* install is its source tree (component 1) and is
    left out; the same name installed any other way stays in the set."""
    with tempfile.TemporaryDirectory(prefix=_SELF_TEST_PREFIX) as tmp:
        site = Path(tmp).resolve() / "site"
        editable = site / "datrix_selftest_editable-1.0.dist-info"
        wheel = site / "datrix_selftest_wheel-1.0.dist-info"
        _write(editable / "METADATA", _SELF_TEST_METADATA.format(name="datrix-selftest-editable", version="1.0"))
        _write(editable / _DIRECT_URL_FILE, json.dumps({"url": "file:///x", "dir_info": {"editable": True}}))
        _write(wheel / "METADATA", _SELF_TEST_METADATA.format(name="datrix-selftest-wheel", version="1.0"))
        baseline = installed_digest(())
        sys.path.insert(0, str(site))
        try:
            with_both = installed_digest(())
            _write(editable / "METADATA", _SELF_TEST_METADATA.format(name="datrix-selftest-editable", version="1.1"))
            editable_bumped = installed_digest(())
            _write(wheel / "METADATA", _SELF_TEST_METADATA.format(name="datrix-selftest-wheel", version="1.1"))
            wheel_bumped = installed_digest(())
        finally:
            sys.path.remove(str(site))
        assert with_both != baseline, "a non-editable datrix-* distribution must enter the installed set"
        assert editable_bumped == with_both, "an editable datrix-* install must not enter the installed set"
        assert wheel_bumped != editable_bumped, "a non-editable datrix-* version change must move the digest"


def _check_rejected_git_entry_is_no_repository() -> None:
    """A ``.git`` entry git rejects -- an empty directory at the workspace root
    -- makes no repository. A foreign file under it is a path in no repository:
    keyed exactly, content-digested, never sent to ``git ls-files`` in a
    directory git refuses; and a one-byte change to it moves the fingerprint."""
    with tempfile.TemporaryDirectory(prefix=_SELF_TEST_PREFIX) as tmp:
        fixture = _build_fingerprint_workspace(Path(tmp).resolve())
        (fixture.workspace / _GIT_DIRNAME).mkdir()
        loose = _write(fixture.workspace / "loose" / "input.txt", "loose")
        assert not _RepositoryRoots().is_root(fixture.workspace), (
            "precondition: git must not confirm a directory whose .git is empty as a work-tree root"
        )
        records = {kind: list(paths) for kind, paths in fixture.records.items()}
        records[_RECORD_OPENED].append(str(loose))
        records[_RECORD_LISTED].append(str(fixture.workspace))
        cone = package_cone(fixture.workspace, "datrix-solo")
        observed = classify_observed(records, cone, fixture.workspace)
        assert {"loose/input.txt", "notes/draft.md", _WORKSPACE_ROOT_KEY} <= observed.foreign, sorted(
            observed.foreign
        )
        recorded = compute_inputs(fixture.workspace, "datrix-solo", observed, cone=cone)
        components = recorded[_INPUTS_COMPONENTS]
        assert isinstance(components, dict)
        foreign = components[_COMPONENT_FOREIGN]
        assert isinstance(foreign, dict)
        assert foreign["loose/input.txt"] == digest_file(loose), foreign
        assert str(foreign["loose/input.txt"]).startswith(f"{_KIND_FILE}:"), foreign
        _flip_last_byte(loose)
        current = compute_inputs(fixture.workspace, "datrix-solo", observed, cone=cone)
        _expect_single_reason(recorded, current, "foreign tree loose/input.txt changed")


def _build_node_consumer_workspace(root: Path) -> tuple[Path, Path]:
    """A Node package consuming a Python package across ecosystems, both real
    git repositories; ``node_modules`` and ``package-lock.json`` are ignored.
    Returns (workspace, node package directory)."""
    workspace = root / "workspace"
    python_package = affected_set._make_pkg(workspace, "datrix-language")
    _init_repository(python_package)
    _commit_all(python_package, "initial")
    client = affected_set._make_node_pkg(workspace, "datrix-client")
    _write(client / ".gitignore", f"{_NODE_MODULES_DIRNAME}/\n{_NODE_LOCKFILE_NAME}\n")
    _write(client / _NODE_MODULES_DIRNAME / _NODE_HIDDEN_LOCKFILE_NAME, '{"lockfileVersion": 3}\n')
    _write(client / _NODE_LOCKFILE_NAME, '{"lockfileVersion": 3}\n')
    _init_repository(client)
    _commit_all(client, "initial")
    affected_set._write_cross_ecosystem_config(workspace, {"datrix-client": ["datrix-language"]})
    return workspace, client


def _check_node_dependency_state_is_an_installed_input() -> None:
    """A Node cone package's installed dependency state is part of the
    ``installed`` component: a one-byte change to npm's hidden lockfile moves
    the fingerprint and diff_components names it; a removed hidden lockfile
    digests as absent and moves it again; an untracked package-lock.json is
    covered the same way; a tracked one belongs to the package's tree only."""
    with tempfile.TemporaryDirectory(prefix=_SELF_TEST_PREFIX) as tmp:
        workspace, client = _build_node_consumer_workspace(Path(tmp).resolve())
        hidden_lockfile = client / _NODE_MODULES_DIRNAME / _NODE_HIDDEN_LOCKFILE_NAME
        lockfile = client / _NODE_LOCKFILE_NAME
        cone = package_cone(workspace, "datrix-client")
        nothing_observed = ObservedInputs(frozenset(), frozenset(), frozenset())

        def stamp() -> dict[str, object]:
            return compute_inputs(workspace, "datrix-client", nothing_observed, cone=cone)

        recorded = stamp()
        components = recorded[_INPUTS_COMPONENTS]
        assert isinstance(components, dict)
        assert components[_COMPONENT_INSTALLED] == installed_digest(cone), components
        assert components[_COMPONENT_INSTALLED] != installed_digest(()), (
            "a Node cone package's installed dependency state must enter the installed component"
        )
        _flip_last_byte(hidden_lockfile)
        current = stamp()
        _expect_single_reason(recorded, current, _REASON_INSTALLED)
        hidden_lockfile.unlink()
        removed = stamp()
        _expect_single_reason(current, removed, _REASON_INSTALLED)
        _flip_last_byte(lockfile)
        untracked_changed = stamp()
        _expect_single_reason(removed, untracked_changed, _REASON_INSTALLED)

        _write(client / ".gitignore", f"{_NODE_MODULES_DIRNAME}/\n")
        _commit_all(client, "track the lockfile")
        tracked = stamp()
        _flip_last_byte(lockfile)
        _expect_single_reason(tracked, stamp(), "datrix-client tree changed")


def _check_carry_window_is_twenty_four_hours() -> None:
    assert CARRY_WINDOW_SECONDS == 24 * 60 * 60, CARRY_WINDOW_SECONDS


_SELF_TEST_CHECKS: list[tuple[str, Callable[[], None]]] = [
    ("clean_tree_reads_no_content", _check_clean_tree_reads_no_content),
    ("one_modified_file_reads_exactly_that_file", _check_one_modified_file_reads_exactly_that_file),
    ("untracked_file_in_new_directory_is_digested", _check_untracked_file_in_new_directory_is_digested),
    ("ignored_file_is_not_part_of_the_tree_digest", _check_ignored_file_is_not_part_of_the_tree_digest),
    ("staged_rename_appears_once_at_new_path", _check_staged_rename_appears_once_at_new_path),
    ("deleted_file_drops_out", _check_deleted_file_drops_out),
    ("assume_unchanged_file_is_read_from_worktree", _check_assume_unchanged_file_is_read_from_worktree),
    ("runner_output_dir_is_not_an_input", _check_runner_output_dir_is_not_an_input),
    ("non_repository_tree_raises", _check_non_repository_tree_raises),
    ("foreign_subtree_scope_is_literal", _check_foreign_subtree_scope_is_literal),
    ("scoped_state_matches_git_literal_pathspec", _check_scoped_state_matches_git_literal_pathspec),
    ("subtree_digests_read_each_repository_once", _check_subtree_digests_read_each_repository_once),
    ("vanished_input_is_distinct_from_empty", _check_vanished_input_is_distinct_from_empty),
    (
        "invalid_name_observed_input_is_absent_not_an_error",
        _check_invalid_name_observed_input_is_absent_not_an_error,
    ),
    ("package_cone_is_the_dual_of_the_reverse_closure", _check_package_cone_is_the_dual_of_the_reverse_closure),
    (
        "node_consumer_cone_includes_cross_ecosystem_dependency",
        _check_node_consumer_cone_includes_cross_ecosystem_dependency,
    ),
    ("unknown_package_raises", _check_unknown_package_raises),
    ("classify_observed_buckets", _check_classify_observed_buckets),
    ("classify_observed_rejects_malformed_records", _check_classify_observed_rejects_malformed_records),
    (
        "transient_executable_is_not_a_fingerprint_input",
        _check_transient_executable_is_not_a_fingerprint_input,
    ),
    (
        "each_component_moves_the_fingerprint_and_is_named",
        _check_each_component_moves_the_fingerprint_and_is_named,
    ),
    (
        "compute_inputs_reads_no_cone_content_when_clean",
        _check_compute_inputs_reads_no_cone_content_when_clean,
    ),
    ("diff_is_complete_and_fails_closed", _check_diff_is_complete_and_fails_closed),
    ("observed_keys_cannot_leave_the_workspace", _check_observed_keys_cannot_leave_the_workspace),
    (
        "installed_digest_drops_only_editable_framework_installs",
        _check_installed_digest_drops_only_editable_framework_installs,
    ),
    ("rejected_git_entry_is_no_repository", _check_rejected_git_entry_is_no_repository),
    ("node_dependency_state_is_an_installed_input", _check_node_dependency_state_is_an_installed_input),
    ("carry_window_is_twenty_four_hours", _check_carry_window_is_twenty_four_hours),
]


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Suite-input fingerprint derivation. A library for the suite runner and the "
            "concurrent gate; its command line only runs the self-test."
        )
    )
    parser.add_argument("--self-test", action="store_true", help="Run the self-test suite and exit.")
    args = parser.parse_args()
    if not args.self_test:
        parser.error("nothing to do: this module is a library; pass --self-test to run its self-test.")
    return args


def main() -> int:
    """Entry point: run the self-test suite."""
    _parse_args()
    _step("Self-test: suite-input fingerprint derivation")
    return _EXIT_OK if run_self_test_checks(_SELF_TEST_CHECKS) else _EXIT_SELFCHECK_FAILED


if __name__ == "__main__":
    sys.exit(main())
