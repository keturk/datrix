"""Pytest plugin recording what a suite run touched, deselected, and spent.

Loaded only through ``-p test.runner_plugin`` -- it is never
registered as a ``pytest11`` entry point -- so its cost is paid solely by the
shared test runner's own invocations, never by an ad hoc ``pytest`` run.

The runner supplies three environment variables. A session missing any of them,
or given one that does not name what it must, stops with a usage error naming
the variable:

``DATRIX_RUN_DIR``
    The run's result directory. The record files are written here.
``DATRIX_WORKSPACE_ROOT``
    The monorepo root. Only paths beneath it are recorded.
``DATRIX_SUITE_CONE``
    The suite's package trees, joined with ``os.pathsep``. Validated, never used
    to filter: the recorder keeps every workspace path it sees. Which of those
    lie inside the suite's own trees, are tracked by git, or are foreign is
    decided once, by the runner, over the merged records of every worker.

At ``pytest_sessionfinish`` a session writes, each file atomically, into
``DATRIX_RUN_DIR``:

``observed-<worker>.json``
    Every executable the session started and every workspace path it opened,
    listed, or loaded as a shared library, outside transient locations. Paths
    and resolved executable paths only -- never file contents, command-line
    arguments, or environment values.
``deselected-<worker>.json``
    How many collected items this session deselected, so the runner can tell
    whether a later phase has anything to run without collecting again, and the
    same count per test file (``deselected_files``), so workers that disagree
    on the total can be compared file by file to name where their trees differ.
``timings-<worker>.json``
    The call-phase duration of every test and the setup duration of every
    session-, package-, and module-scoped fixture. Test report durations fold
    fixture setup into whichever test first used the fixture; these do not.

``<worker>`` is ``PYTEST_XDIST_WORKER`` inside an xdist worker and ``main`` in a
session that does not distribute tests. The xdist controller neither collects
nor runs a test, so it writes no deselected or timing record: a count of zero,
or a copy of the reports its workers forwarded, would be a fact the controller
did not produce. It writes two records instead:

``observed-controller.json``
    What the controller itself touched -- it does load conftests and start the
    workers.
``workers-controller.json``
    The id of every worker that went down during the session, cleanly or not.
    pytest-xdist does not propagate a worker's exit status to the controller's,
    so a worker whose session wrote no record -- it crashed, or it refused to
    write records it could not trust -- leaves a run that still exits green.
    This list is what lets the runner require every worker's records and treat
    a missing one as an incomplete run.

A record is never overwritten and never written incomplete. If a record file
for the same worker already exists in the run directory, or the recorder met
an audited operation it could not interpret, the session writes no record and
exits with ``ExitCode.INTERNAL_ERROR``, naming the cause.

What is observed is what Python's audit hooks report: file opens (including
the reads ``shutil`` performs through ``CopyFile2`` on Windows), directory
listings, globs and walks, shared-library loads, and process starts through
``subprocess``, ``os.system``, ``os.spawn*``, ``os.posix_spawn*`` and
``os.startfile``. Two things Python raises no audit event for are not seen: a
file a native extension opens by itself, and a process a spawned process starts
in turn. A bytecode cache read is recorded as the source file it caches, since
importing a module whose cache is fresh never opens the source -- in a
``__pycache__`` directory and under ``sys.pycache_prefix`` alike, for CPython's
and pytest's cache names both. Nothing else under ``sys.pycache_prefix`` is
recorded: it holds only derived bytecode.
"""

from __future__ import annotations

import functools
import json
import logging
import os
import re
import sys
import tempfile
import threading
import time
from collections.abc import Callable, Generator, Iterable, Iterator, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path, PurePath, PureWindowsPath
from typing import TYPE_CHECKING

import pytest

if sys.platform == "win32":
    import _winapi

if TYPE_CHECKING:
    from xdist.workermanage import WorkerController

logger = logging.getLogger(__name__)

_IS_WINDOWS = sys.platform == "win32"
_OS_OPEN_ACCEPTS_DIR_FD = os.open in os.supports_dir_fd

_ENV_RUN_DIR = "DATRIX_RUN_DIR"
_ENV_SUITE_CONE = "DATRIX_SUITE_CONE"
_ENV_WORKSPACE_ROOT = "DATRIX_WORKSPACE_ROOT"
_ENV_XDIST_WORKER = "PYTEST_XDIST_WORKER"

#: Name under which pytest-xdist registers its distributed-session plugin; it is
#: registered only in the controller of a distributing run.
_XDIST_CONTROLLER_PLUGIN = "dsession"

#: Name under which each session's recorder is registered on its plugin manager.
RECORDER_PLUGIN_NAME = "datrix-runner-recorder"

_RECORD_SCHEMA = 1
_STANDALONE_WORKER_ID = "main"
_CONTROLLER_WORKER_ID = "controller"
_WORKER_ID_PATTERN = re.compile(r"[A-Za-z0-9_-]+")
_OBSERVED_KIND = "observed"
_DESELECTED_KIND = "deselected"
_TIMINGS_KIND = "timings"
_WORKERS_KIND = "workers"
#: The key under which pytest-xdist hands each worker its id; the worker exports
#: the same value as ``PYTEST_XDIST_WORKER``, so it names that worker's records.
_XDIST_WORKER_ID_INPUT = "workerid"

_OPENED = "opened"
_LISTED = "listed"
_DLOPENED = "dlopened"
_EXECUTABLES = "executables"
_BUCKETS = (_EXECUTABLES, _OPENED, _LISTED, _DLOPENED)

_CALL_PHASE = "call"
_TIMED_FIXTURE_SCOPES = frozenset({"session", "package", "module"})

#: Directory names that hold only derived or scratch data wherever they appear.
_TRANSIENT_DIR_NAMES = frozenset(
    {"__pycache__", ".pytest_cache", ".test_results", "htmlcov"}
)
#: Scratch directories directly under the workspace root.
_TRANSIENT_WORKSPACE_DIRS = (
    ".tmp",
    ".test-output",
    ".scripts",
    ".generated",
    ".agent_output",
)
_COVERAGE_REPORT_NAMES = frozenset({"coverage.xml"})
_COVERAGE_DATA_PREFIX = ".coverage"

_BYTECODE_SUFFIX = ".pyc"
_BYTECODE_CACHE_DIR = "__pycache__"
_SOURCE_SUFFIX = ".py"
#: ``sys.pycache_prefix`` is normally fixed for the life of a process; a few
#: slots cover a session that changes it.
_PYCACHE_PREFIX_CACHE_SIZE = 8

_NUL = "\0"
_GLOB_MAGIC_CHARACTERS = frozenset("*?[")
_WHITESPACE_RUN = re.compile(r"[ \t]+")

#: CreateProcess appends this to a module name that carries no extension.
_WINDOWS_DEFAULT_EXECUTABLE_SUFFIX = ".exe"
#: The C runtime's spawn functions try these, in order, for a name with no extension.
_WINDOWS_SPAWN_SUFFIXES = (".com", ".exe", ".bat", ".cmd")
_WINDOWS_SYSTEM_ROOT_VARIABLES = ("SystemRoot", "windir")
_WINDOWS_SHELL_VARIABLE = "ComSpec"
_WINDOWS_SHELL_NAME = "cmd.exe"
_WINDOWS_SYSTEM_DIRECTORY = "System32"
_WINDOWS_LEGACY_SYSTEM_DIRECTORY = "System"
#: When set, CreateProcess leaves the working directory out of its search.
_WINDOWS_NO_CURRENT_DIRECTORY_VARIABLE = "NoDefaultCurrentDirectoryInExePath"
_POSIX_SHELL = "/bin/sh"
#: Loader search-path variables through which a bare library name can reach the workspace.
_POSIX_LIBRARY_PATH_VARIABLES = ("LD_LIBRARY_PATH", "DYLD_LIBRARY_PATH")
_PATH_VARIABLE = "PATH"

#: Windows refuses an atomic replace with ``PermissionError`` while another
#: process -- typically a virus scanner or search indexer -- briefly holds the
#: freshly written file open. Bounded, so a real permission fault still surfaces.
_TEMPORARY_RECORD_SUFFIX = ".tmp"
_REPLACE_RETRY_ATTEMPTS = 5
_REPLACE_RETRY_INITIAL_DELAY_SECONDS = 0.02
_REPLACE_RETRY_BACKOFF = 2.0


@dataclass(frozen=True, slots=True)
class _Observation:
    """One fact an audited operation established: a path or an executable."""

    bucket: str
    path: str


_Handler = Callable[[tuple[object, ...]], tuple[_Observation, ...]]


# ---------------------------------------------------------------------------
# Argument normalization
# ---------------------------------------------------------------------------


def _argument_text(raw: object) -> tuple[str, ...]:
    """The filesystem path an audited argument names, as text.

    Empty for a file descriptor, ``None``, or any object no filesystem call
    accepts as a path: the audited call itself rejects such an argument, or --
    for a descriptor -- already had its path audited when it was opened.
    """
    if isinstance(raw, str):
        return (raw,)
    if isinstance(raw, bytes):
        return (os.fsdecode(raw),)
    if not isinstance(raw, os.PathLike):
        return ()
    try:
        value = os.fspath(raw)
    except Exception:
        # The audited call converts this same argument the same way before it
        # touches the filesystem, so it fails identically and touched nothing.
        return ()
    return (os.fsdecode(value),)


def _resolve(texts: Iterable[str], base: str | None = None) -> tuple[str, ...]:
    """Absolute, symlink-free forms of *texts*, relative ones taken from *base*
    (the working directory when *base* is ``None``)."""
    resolved: list[str] = []
    for text in texts:
        if _NUL in text:
            # Every filesystem call rejects a path with an embedded NUL before
            # touching anything; realpath does not reject it on every platform.
            continue
        resolved.append(
            os.path.realpath(os.path.join(base, text) if base is not None else text)
        )
    return tuple(resolved)


@functools.lru_cache(maxsize=_PYCACHE_PREFIX_CACHE_SIZE)
def _resolved_pycache_prefix(prefix: str) -> str:
    """The case-normalized, symlink-free form of a ``sys.pycache_prefix`` value."""
    return os.path.normcase(os.path.realpath(prefix))


def _pycache_prefix_source_directory(cache_directory: str) -> str | None:
    """The source directory a directory under ``sys.pycache_prefix`` mirrors,
    or None when *cache_directory* is not under the prefix (or none is set).

    CPython and pytest's assertion rewriter both mirror a source directory
    under the prefix as ``<prefix>/<source path without its anchor>``, so the
    source directory is the remainder re-anchored. On Windows the mirror drops
    the source's drive; the candidate takes the cache's own drive, and a
    source on another drive whose path coincides is then recorded as an extra
    input -- more than was read, never less.
    """
    prefix = sys.pycache_prefix
    if prefix is None:
        return None
    prefix_key = _resolved_pycache_prefix(prefix)
    directory_key = os.path.normcase(cache_directory)
    if directory_key == prefix_key:
        remainder = ""
    elif directory_key.startswith(_directory_prefix(prefix_key)):
        remainder = cache_directory[len(_directory_prefix(prefix_key)) :]
    else:
        return None
    anchor = os.path.splitdrive(cache_directory)[0] + os.sep
    return os.path.join(anchor, remainder)


def _input_path(resolved: str) -> str:
    """The file a read of *resolved* depends on.

    A bytecode cache read stands for its source: importing a module whose cache
    is fresh never opens the source, so recording the cache (a transient file)
    and dropping it would lose the source as an input. Every name in a cache
    location is a cache of ``<module>.py`` -- CPython's own
    ``<module>.<tag>[.opt-N].pyc`` and pytest's assertion-rewrite
    ``<module>.<tag>-pytest-<version>.pyc`` alike -- whether the cache location
    is a ``__pycache__`` directory beside the source or the mirror of the
    source's directory under ``sys.pycache_prefix``; so a cache is always
    recorded as its (possibly absent) source, never as itself. A ``.pyc``
    outside any cache location is a sourceless module and is itself the input.
    """
    if not os.path.normcase(resolved).endswith(_BYTECODE_SUFFIX):
        return resolved
    head, name = os.path.split(resolved)
    source_directory = _pycache_prefix_source_directory(head)
    if source_directory is None:
        if os.path.normcase(os.path.basename(head)) != _BYTECODE_CACHE_DIR:
            return resolved
        source_directory = os.path.dirname(head)
    source_name = name.partition(".")[0] + _SOURCE_SUFFIX
    return os.path.realpath(os.path.join(source_directory, source_name))


def _path_observations(
    bucket: str, resolved: Iterable[str]
) -> tuple[_Observation, ...]:
    return tuple(_Observation(bucket, _input_path(path)) for path in resolved)


def _executable_observations(resolved: Iterable[str]) -> tuple[_Observation, ...]:
    return tuple(_Observation(_EXECUTABLES, path) for path in resolved)


def _static_glob_prefix(pattern: str) -> str:
    """The leading components of *pattern* that contain no wildcard -- the
    directory a glob starts from, or the whole path when nothing is a wildcard
    (a literal pattern is an existence check on that path)."""
    static: list[str] = []
    for part in PurePath(pattern).parts:
        if _GLOB_MAGIC_CHARACTERS.intersection(part):
            break
        static.append(part)
    return os.path.join(*static) if static else os.curdir


def _environment_value(environment: Mapping[str, str], name: str) -> str:
    """*name*'s value, or the empty string when it is unset -- an unset search
    path contributes no directory, exactly as the loader treats it."""
    return environment[name] if name in environment else ""


def _first_existing(candidates: Iterable[str], *, executable: bool) -> tuple[str, ...]:
    """The resolved first candidate that is a file (and executable, on POSIX)."""
    for candidate in candidates:
        if not os.path.isfile(candidate):
            continue
        if executable and not os.access(candidate, os.X_OK):
            continue
        return _resolve((candidate,))
    return ()


# ---------------------------------------------------------------------------
# Path events
# ---------------------------------------------------------------------------


def _observe_open(args: tuple[object, ...]) -> tuple[_Observation, ...]:
    """``open``: ``(path, mode, flags)``.

    ``mode`` is ``None`` only for ``os.open``. Where ``os.open`` accepts
    ``dir_fd``, its audit event does not carry that descriptor, so a relative
    name there may be relative to a directory other than the working directory;
    such a name is kept only when it exists under the working directory.
    """
    texts = _argument_text(args[0])
    if args[1] is None and _OS_OPEN_ACCEPTS_DIR_FD:
        texts = tuple(
            text for text in texts if os.path.isabs(text) or os.path.lexists(text)
        )
    return _path_observations(_OPENED, _resolve(texts))


def _observe_listing(args: tuple[object, ...]) -> tuple[_Observation, ...]:
    """``os.listdir`` / ``os.scandir``: ``(path,)``; ``None`` means the working directory."""
    texts = (os.curdir,) if args[0] is None else _argument_text(args[0])
    return _path_observations(_LISTED, _resolve(texts))


def _observe_walk_root(args: tuple[object, ...]) -> tuple[_Observation, ...]:
    """``os.walk`` / ``pathlib.Path.walk``: the root is the first argument."""
    return _path_observations(_LISTED, _resolve(_argument_text(args[0])))


def _observe_fwalk(args: tuple[object, ...]) -> tuple[_Observation, ...]:
    """``os.fwalk``: ``(top, topdown, onerror, follow_symlinks, dir_fd)``.

    A relative ``top`` under a ``dir_fd`` names a directory relative to that
    descriptor, whose own path was audited when it was opened.
    """
    texts = _argument_text(args[0])
    if args[4] is not None:
        texts = tuple(text for text in texts if os.path.isabs(text))
    return _path_observations(_LISTED, _resolve(texts))


def _observe_glob(args: tuple[object, ...]) -> tuple[_Observation, ...]:
    """``glob.glob/2``: ``(pathname, recursive, root_dir, dir_fd)``."""
    prefixes = tuple(_static_glob_prefix(text) for text in _argument_text(args[0]))
    roots = _argument_text(args[2]) if args[2] is not None else ()
    if roots:
        prefixes = tuple(
            os.path.join(root, prefix) for root in roots for prefix in prefixes
        )
    if args[3] is not None:
        prefixes = tuple(prefix for prefix in prefixes if os.path.isabs(prefix))
    return _path_observations(_LISTED, _resolve(prefixes))


def _observe_path_glob(args: tuple[object, ...]) -> tuple[_Observation, ...]:
    """``pathlib.Path.glob`` / ``pathlib.Path.rglob``: ``(self, pattern)``."""
    prefixes = tuple(_static_glob_prefix(text) for text in _argument_text(args[1]))
    joined = (
        os.path.join(base, prefix)
        for base in _argument_text(args[0])
        for prefix in prefixes
    )
    return _path_observations(_LISTED, _resolve(joined))


def _observe_start_file(args: tuple[object, ...]) -> tuple[_Observation, ...]:
    """``os.startfile``: ``(path, operation)``; ``os.startfile/2`` adds
    ``(arguments, cwd, show_cmd)``. The file handed to the shell is an input."""
    working_directories = (
        _argument_text(args[3]) if len(args) > 3 and args[3] is not None else ()
    )
    base = working_directories[0] if working_directories else None
    return _path_observations(_OPENED, _resolve(_argument_text(args[0]), base))


def _observe_copy_file2(args: tuple[object, ...]) -> tuple[_Observation, ...]:
    """``_winapi.CopyFile2``: ``(src, dst, flags)``. ``shutil.copy2`` and
    ``copytree`` read their sources through it without an ``open`` event."""
    return _path_observations(_OPENED, _resolve(_argument_text(args[0])))


def _observe_dll_directory(args: tuple[object, ...]) -> tuple[_Observation, ...]:
    """``os.add_dll_directory``: ``(path,)``. A library later loaded by bare
    name may come from this directory, so the directory is an input."""
    return _path_observations(_LISTED, _resolve(_argument_text(args[0])))


def _search_path_entries(value: str) -> Iterator[str]:
    return (entry for entry in value.split(os.pathsep) if entry)


def _library_search_directories() -> Iterator[str]:
    for variable in _POSIX_LIBRARY_PATH_VARIABLES:
        yield from _search_path_entries(_environment_value(os.environ, variable))


def _observe_dlopen(args: tuple[object, ...]) -> tuple[_Observation, ...]:
    """``ctypes.dlopen``: ``(name,)``.

    A name with a directory component is a path. A bare name is found by the
    platform loader: on Windows (ctypes loads with the default DLL directories)
    that is the interpreter's directory, the system directory, and directories
    added with ``os.add_dll_directory`` -- recorded through their own event; on
    POSIX, the part of the search that can reach the workspace is the library
    search-path variable.
    """
    texts = _argument_text(args[0])
    if not texts:
        return ()
    name = texts[0]
    if os.path.dirname(name):
        return _path_observations(_DLOPENED, _resolve(texts))
    if _IS_WINDOWS:
        return ()
    candidates = (
        os.path.join(directory, name) for directory in _library_search_directories()
    )
    return _path_observations(_DLOPENED, _first_existing(candidates, executable=False))


# ---------------------------------------------------------------------------
# Process events
# ---------------------------------------------------------------------------


def _windows_system_root() -> str:
    for variable in _WINDOWS_SYSTEM_ROOT_VARIABLES:
        if os.environ.get(variable):
            return os.environ[variable]
    raise OSError(
        f"Neither {' nor '.join(_WINDOWS_SYSTEM_ROOT_VARIABLES)} is set, so the Windows "
        f"system directories CreateProcess searches cannot be located and the started "
        f"executable cannot be identified. Run the suite with the standard Windows "
        f"environment."
    )


def _windows_search_directories() -> Iterator[str]:
    """CreateProcess's search order for a module name without a directory: the
    directory of the running image, the working directory (unless
    ``NoDefaultCurrentDirectoryInExePath`` is set), the system directories, and
    the parent's ``PATH``."""
    yield os.path.dirname(_winapi.GetModuleFileName(0))
    if _WINDOWS_NO_CURRENT_DIRECTORY_VARIABLE not in os.environ:
        yield os.getcwd()
    system_root = _windows_system_root()
    yield os.path.join(system_root, _WINDOWS_SYSTEM_DIRECTORY)
    yield os.path.join(system_root, _WINDOWS_LEGACY_SYSTEM_DIRECTORY)
    yield system_root
    path_value = _environment_value(os.environ, _PATH_VARIABLE)
    yield from (entry.strip('"') for entry in _search_path_entries(path_value))


def _windows_module_candidates(name: str) -> Iterator[str]:
    """Files CreateProcess tries for module *name* taken from a command line."""
    has_suffix = bool(PureWindowsPath(name).suffix)
    file_name = name if has_suffix else name + _WINDOWS_DEFAULT_EXECUTABLE_SUFFIX
    if os.path.dirname(file_name):
        yield os.path.join(os.getcwd(), file_name)
        return
    for directory in _windows_search_directories():
        yield os.path.join(directory, file_name)


def _windows_module_names(command_line: str) -> tuple[str, ...]:
    """The module names CreateProcess tries for *command_line*: a quoted
    leading token, or else each prefix ending at a whitespace run, shortest
    first (an unquoted path containing spaces is ambiguous, and tried in turn)."""
    stripped = command_line.lstrip(" \t")
    if stripped.startswith('"'):
        closing = stripped.find('"', 1)
        return (stripped[1:closing] if closing > 0 else stripped[1:],)
    ends = [match.start() for match in _WHITESPACE_RUN.finditer(stripped)]
    return tuple(stripped[:end] for end in (*ends, len(stripped)) if end > 0)


def _windows_created_process(
    executable: object, command_line: object
) -> tuple[str, ...]:
    """The file CreateProcess starts for ``(lpApplicationName, lpCommandLine)``.

    An explicit application name is completed against the working directory
    only -- no search and no default extension. Otherwise the module name comes
    from the command line and is searched for; the child's ``cwd`` and ``env``
    play no part in either (the parent's ``PATH`` is the one searched).
    """
    if executable is not None:
        return _first_existing(_argument_text(executable), executable=False)
    if not isinstance(command_line, str):
        raise TypeError(
            f"a Windows process-start event carried a command line of type "
            f"{type(command_line).__name__}; expected str, so the started executable "
            f"cannot be identified"
        )
    for name in _windows_module_names(command_line):
        found = _first_existing(_windows_module_candidates(name), executable=False)
        if found:
            return found
    return ()


def _posix_program_candidates(
    name: str, base: str, search_path: Sequence[str]
) -> Iterator[str]:
    """Files ``execve`` tries for *name*: the name itself when it contains a
    slash, else each search-path entry in order -- relative ones (including an
    empty entry) taken from *base*, the directory the child starts in."""
    if "/" in name:
        yield os.path.join(base, name)
        return
    for directory in search_path:
        yield os.path.join(base, directory, name)


def _posix_search_path(environment: object) -> list[str]:
    if environment is not None and not isinstance(environment, Mapping):
        raise TypeError(
            f"a process-start event carried an environment of type "
            f"{type(environment).__name__}; expected a mapping or None, so the "
            f"executable search path cannot be determined"
        )
    return os.get_exec_path(environment)


def _posix_started_program(
    program: object, cwd: object, environment: object
) -> tuple[str, ...]:
    names = _argument_text(program)
    if not names:
        raise TypeError(
            f"a process-start event named its program with a {type(program).__name__}; "
            f"expected a path, so the started executable cannot be identified"
        )
    child_directories = _argument_text(cwd) if cwd is not None else ()
    base = child_directories[0] if child_directories else os.getcwd()
    candidates = _posix_program_candidates(
        names[0], base, _posix_search_path(environment)
    )
    return _first_existing(candidates, executable=True)


def _observe_popen(args: tuple[object, ...]) -> tuple[_Observation, ...]:
    """``subprocess.Popen``: ``(executable, args, cwd, env)``.

    On Windows ``args`` is already the command-line string and ``executable``
    is ``None`` unless the caller passed one (or ``shell=True`` chose the
    shell). On POSIX ``executable`` is always set: the caller's, or ``args[0]``.
    """
    executable, command, cwd, environment = args[0], args[1], args[2], args[3]
    if _IS_WINDOWS:
        return _executable_observations(_windows_created_process(executable, command))
    return _executable_observations(
        _posix_started_program(executable, cwd, environment)
    )


def _observe_system(args: tuple[object, ...]) -> tuple[_Observation, ...]:
    """``os.system``: ``(command,)``. The process started is the shell."""
    if not _IS_WINDOWS:
        return _executable_observations(
            _first_existing((_POSIX_SHELL,), executable=True)
        )
    shell = os.environ.get(_WINDOWS_SHELL_VARIABLE)
    if shell:
        return _executable_observations(_first_existing((shell,), executable=False))
    return _executable_observations(
        _first_existing(
            _windows_module_candidates(_WINDOWS_SHELL_NAME), executable=False
        )
    )


def _observe_spawn(args: tuple[object, ...]) -> tuple[_Observation, ...]:
    """``os.spawn*`` on Windows: ``(mode, path, args, env)``. The C runtime
    uses the path as given and tries its extensions when it has none."""
    texts = _argument_text(args[1])
    if not texts:
        raise TypeError(
            f"an os.spawn event named its program with a {type(args[1]).__name__}; "
            f"expected a path, so the started executable cannot be identified"
        )
    path = texts[0]
    if PureWindowsPath(path).suffix:
        candidates: tuple[str, ...] = (path,)
    else:
        candidates = tuple(path + suffix for suffix in _WINDOWS_SPAWN_SUFFIXES)
    return _executable_observations(_first_existing(candidates, executable=False))


def _observe_posix_spawn(args: tuple[object, ...]) -> tuple[_Observation, ...]:
    """``os.posix_spawn`` / ``os.posix_spawnp``: ``(path, argv, env)``. Both
    raise this event; a bare name only starts anything through the ``p``
    variant, which searches the calling process's ``PATH``."""
    return _executable_observations(_posix_started_program(args[0], None, None))


_EVENT_HANDLERS: dict[str, _Handler] = {
    "open": _observe_open,
    "os.listdir": _observe_listing,
    "os.scandir": _observe_listing,
    "os.walk": _observe_walk_root,
    "pathlib.Path.walk": _observe_walk_root,
    "os.fwalk": _observe_fwalk,
    "glob.glob/2": _observe_glob,
    "pathlib.Path.glob": _observe_path_glob,
    "pathlib.Path.rglob": _observe_path_glob,
    "os.startfile": _observe_start_file,
    "os.startfile/2": _observe_start_file,
    "_winapi.CopyFile2": _observe_copy_file2,
    "os.add_dll_directory": _observe_dll_directory,
    "ctypes.dlopen": _observe_dlopen,
    "subprocess.Popen": _observe_popen,
    "os.system": _observe_system,
    "os.spawn": _observe_spawn,
    "os.posix_spawn": _observe_posix_spawn,
}


# ---------------------------------------------------------------------------
# Scope: which resolved paths a session keeps
# ---------------------------------------------------------------------------


def _directory_prefix(normalized: str) -> str:
    return normalized if normalized.endswith(os.sep) else normalized + os.sep


def transient_roots(workspace_root: Path) -> tuple[Path, ...]:
    """Resolved transient locations no fingerprint may name as an input: the
    OS temp directory and the workspace's own scratch directories (``.tmp``,
    ``.test-output``, ``.scripts``, ``.generated``, ``.agent_output``).

    Something under one of these is an output the run itself produced and
    started -- a generated toolchain, a scratch build -- never an input, and
    its own path is unstable from run to run (pytest's per-run temp
    subdirectory included). This is the single definition of that set:
    :meth:`_PathScope.for_workspace` consults it for its own exclusion zones,
    and so does every consumer outside this module, so neither can drift from
    the other.
    """
    zones = [workspace_root / name for name in _TRANSIENT_WORKSPACE_DIRS]
    zones.append(Path(tempfile.gettempdir()))
    return tuple(Path(os.path.realpath(zone)) for zone in zones)


@dataclass(frozen=True)
class _PathScope:
    """The workspace root and the transient locations beneath it.

    An excluded location is honoured only when it lies strictly inside the
    workspace: anything outside is already out of scope, and a location that
    contains the workspace (a workspace under the temp directory) cannot
    exclude the whole of it.
    """

    root_key: str
    root_prefix: str
    excluded_prefixes: tuple[str, ...]

    @classmethod
    def for_workspace(cls, root: Path) -> _PathScope:
        root_key = os.path.normcase(str(root))
        root_prefix = _directory_prefix(root_key)
        zones = list(transient_roots(root))
        environment_zones = [sys.prefix, sys.exec_prefix, sys.base_prefix, sys.base_exec_prefix]
        # Only bytecode caches live under the prefix, and a cache read is
        # recorded as its source before this scope is consulted; what remains
        # there (a cache being written, an interpreter's temporary file) is
        # derived data, never an input.
        if sys.pycache_prefix is not None:
            environment_zones.append(sys.pycache_prefix)
        zones.extend(Path(os.path.realpath(zone)) for zone in environment_zones)
        prefixes = {_directory_prefix(os.path.normcase(str(zone))) for zone in zones}
        inside = tuple(
            sorted(
                p for p in prefixes if p.startswith(root_prefix) and p != root_prefix
            )
        )
        return cls(root_key=root_key, root_prefix=root_prefix, excluded_prefixes=inside)

    def admits(self, path: str) -> bool:
        key = os.path.normcase(path)
        if key != self.root_key and not key.startswith(self.root_prefix):
            return False
        directory_key = _directory_prefix(key)
        if any(directory_key.startswith(prefix) for prefix in self.excluded_prefixes):
            return False
        relative_parts = [
            part for part in key[len(self.root_prefix) :].split(os.sep) if part
        ]
        if any(part in _TRANSIENT_DIR_NAMES for part in relative_parts):
            return False
        name = relative_parts[-1] if relative_parts else ""
        return name not in _COVERAGE_REPORT_NAMES and not name.startswith(
            _COVERAGE_DATA_PREFIX
        )


# ---------------------------------------------------------------------------
# The process-wide audit hook
# ---------------------------------------------------------------------------

_active_recorders: tuple[_SessionRecorder, ...] = ()
_activation_lock = threading.Lock()
_audit_hook_installed = False


def _dispatch(
    recorders: Sequence[_SessionRecorder], event: str, args: tuple[object, ...]
) -> None:
    """Interpret *event* once and offer what it established to each recorder.

    An operation the recorder cannot interpret is never allowed to fail the
    audited call -- that would change the test's outcome -- and never silently
    dropped: it becomes a fault that fails each recording session and
    suppresses its records.
    """
    try:
        observations = _EVENT_HANDLERS[event](args)
    except Exception as fault:
        for recorder in recorders:
            recorder.record_fault(event, fault)
        return
    for recorder in recorders:
        recorder.record(observations)


def _audit_hook(event: str, args: tuple[object, ...]) -> None:
    """The single audit hook this module installs for the life of the process.

    Audit hooks cannot be removed, so outside a recording session this costs
    one tuple truth test per audited event.
    """
    recorders = _active_recorders
    if recorders and event in _EVENT_HANDLERS:
        _dispatch(recorders, event, args)


def _activate(recorder: _SessionRecorder) -> None:
    global _active_recorders, _audit_hook_installed
    with _activation_lock:
        if not _audit_hook_installed:
            sys.addaudithook(_audit_hook)
            _audit_hook_installed = True
        if recorder not in _active_recorders:
            _active_recorders = (*_active_recorders, recorder)


def _deactivate(recorder: _SessionRecorder) -> None:
    global _active_recorders
    with _activation_lock:
        _active_recorders = tuple(
            active for active in _active_recorders if active is not recorder
        )


# ---------------------------------------------------------------------------
# Configuration from the environment
# ---------------------------------------------------------------------------


def _usage_error(name: str, problem: str) -> pytest.UsageError:
    return pytest.UsageError(
        f"test.runner_plugin is loaded (-p) but {name} {problem}. "
        f"The runner must set {_ENV_RUN_DIR} (the run's existing result directory), "
        f"{_ENV_WORKSPACE_ROOT} (the existing workspace root) and {_ENV_SUITE_CONE} "
        f"(the suite's package directories under the workspace root, joined with "
        f"{os.pathsep!r}), each as absolute paths, before starting pytest with this "
        f"plugin; or drop '-p test.runner_plugin' from an ad hoc run."
    )


def _required_value(name: str) -> str:
    value = os.environ.get(name)
    if value is None or not value.strip():
        raise _usage_error(name, "is not set")
    return value


def _existing_directory(name: str, raw: str) -> Path:
    candidate = Path(raw)
    if not candidate.is_absolute():
        raise _usage_error(name, f"is not an absolute path ({raw!r})")
    if not candidate.is_dir():
        raise _usage_error(name, f"does not name an existing directory ({raw!r})")
    return candidate.resolve()


def _validated_cone(workspace_root: Path) -> tuple[Path, ...]:
    entries = [
        entry for entry in _required_value(_ENV_SUITE_CONE).split(os.pathsep) if entry
    ]
    if not entries:
        raise _usage_error(_ENV_SUITE_CONE, "lists no package directory")
    cone = tuple(_existing_directory(_ENV_SUITE_CONE, entry) for entry in entries)
    outside = [str(tree) for tree in cone if not tree.is_relative_to(workspace_root)]
    if outside:
        raise _usage_error(
            _ENV_SUITE_CONE,
            f"lists directories outside {_ENV_WORKSPACE_ROOT}: {outside}",
        )
    return cone


def _validated_xdist_worker() -> str:
    """This process's xdist worker id, or the empty string outside an xdist worker.

    pytest-xdist sets the variable in each worker before building its config.
    The id becomes part of a file name, so anything but a plain token is refused.
    """
    worker = os.environ.get(_ENV_XDIST_WORKER)
    if not worker:
        return ""
    if not _WORKER_ID_PATTERN.fullmatch(worker):
        raise pytest.UsageError(
            f"{_ENV_XDIST_WORKER}={worker!r} cannot name a record file: a worker id must "
            f"match {_WORKER_ID_PATTERN.pattern} (pytest-xdist uses gw0, gw1, ...). Unset "
            f"it, or let pytest-xdist set it."
        )
    return worker


@dataclass(frozen=True)
class _Settings:
    run_dir: Path
    workspace_root: Path
    xdist_worker: str


def _read_settings() -> _Settings:
    """The runner's environment, validated. The suite cone is checked for shape
    and containment but not kept: this recorder never filters by it."""
    run_dir = _existing_directory(_ENV_RUN_DIR, _required_value(_ENV_RUN_DIR))
    workspace_root = _existing_directory(
        _ENV_WORKSPACE_ROOT, _required_value(_ENV_WORKSPACE_ROOT)
    )
    _validated_cone(workspace_root)
    return _Settings(
        run_dir=run_dir,
        workspace_root=workspace_root,
        xdist_worker=_validated_xdist_worker(),
    )


# ---------------------------------------------------------------------------
# Writing records
# ---------------------------------------------------------------------------


def _replace_with_retry(temporary: str, target: Path) -> None:
    delay = _REPLACE_RETRY_INITIAL_DELAY_SECONDS
    for attempt in range(1, _REPLACE_RETRY_ATTEMPTS + 1):
        try:
            os.replace(temporary, target)
            return
        except PermissionError:
            if attempt == _REPLACE_RETRY_ATTEMPTS:
                raise
            logger.debug(
                "record replace refused, retrying: attempt=%d target=%s",
                attempt,
                target,
            )
            time.sleep(delay)
            delay *= _REPLACE_RETRY_BACKOFF


def _stage_json(directory: Path, name: str, payload: Mapping[str, object]) -> str:
    """Write *payload* to a new temporary file in *directory* and return its
    path. The temporary name starts with a dot, so no record glob matches it."""
    handle, temporary = tempfile.mkstemp(
        dir=directory, prefix=f".{name}.", suffix=_TEMPORARY_RECORD_SUFFIX
    )
    try:
        with os.fdopen(handle, "w", encoding="utf-8") as stream:
            # One compact dumps call: the C encoder serves it, where an indented
            # or streamed dump falls back to the pure-Python one -- a timing
            # record holds an entry per test, so that difference is per worker.
            stream.write(json.dumps(payload, sort_keys=True))
    except BaseException:
        Path(temporary).unlink(missing_ok=True)
        raise
    return temporary


def _publish_json_records(
    directory: Path, records: Mapping[str, Mapping[str, object]]
) -> None:
    """Write each record through a temporary file and one replace, so no
    reader ever sees a partial record.

    Every record is staged before any is moved into place: on Windows a file
    scanner briefly holds each freshly closed file, and a replace issued
    straight after the close waits for it; staging all first gives it that
    time while the next record is written.
    """
    staged: list[tuple[str, Path]] = []
    try:
        for name, payload in records.items():
            staged.append((_stage_json(directory, name, payload), directory / name))
        for temporary, target in staged:
            _replace_with_retry(temporary, target)
    except BaseException:
        for temporary, _ in staged:
            Path(temporary).unlink(missing_ok=True)
        raise


@dataclass(frozen=True)
class _Role:
    """What a session is in a (possibly distributed) run, and so what it can attest."""

    worker_id: str
    collects_and_runs: bool


def _session_role(config: pytest.Config, xdist_worker: str) -> _Role:
    """Decided at session end: pytest-xdist registers its controller plugin
    during configuration, after this plugin has started recording."""
    if config.pluginmanager.has_plugin(_XDIST_CONTROLLER_PLUGIN):
        return _Role(worker_id=_CONTROLLER_WORKER_ID, collects_and_runs=False)
    if xdist_worker:
        return _Role(worker_id=xdist_worker, collects_and_runs=True)
    return _Role(worker_id=_STANDALONE_WORKER_ID, collects_and_runs=True)


def _record_file(kind: str, worker_id: str) -> str:
    return f"{kind}-{worker_id}.json"


# ---------------------------------------------------------------------------
# The per-session recorder
# ---------------------------------------------------------------------------


# @canonical(testing/observed-suite-inputs): the recorder of what a suite run read, spawned,
# deselected and spent, written per worker into the runner's run directory, plus the xdist
# controller's list of the workers it ran, so a worker's missing records are detectable.
# @rule: records carry paths and resolved executable paths only -- never file contents,
#   command-line arguments or environment values.
# @rule: a record is complete or absent: an uninterpretable audited operation or an existing
#   record for the same worker fails the session and writes nothing.
# @anti-pattern: filtering by the suite cone inside the recorder -- classification happens
#   once over the merged records, where tracked-versus-ignored can be decided.
class _SessionRecorder:
    """One pytest session's records, registered as a plugin on its config."""

    def __init__(self, settings: _Settings) -> None:
        self._settings = settings
        self._scope = _PathScope.for_workspace(settings.workspace_root)
        self._lock = threading.Lock()
        self._observed: dict[str, set[str]] = {bucket: set() for bucket in _BUCKETS}
        self._faults: list[str] = []
        self._deselected = 0
        self._deselected_files: dict[str, int] = {}
        self._calls: list[dict[str, object]] = []
        self._fixtures: list[dict[str, object]] = []
        self._workers: set[str] = set()

    def start(self) -> None:
        _activate(self)

    def stop(self) -> None:
        _deactivate(self)

    def record(self, observations: Iterable[_Observation]) -> None:
        with self._lock:
            for observation in observations:
                if observation.bucket == _EXECUTABLES or self._scope.admits(
                    observation.path
                ):
                    self._observed[observation.bucket].add(observation.path)

    def record_fault(self, event: str, fault: Exception) -> None:
        with self._lock:
            self._faults.append(f"{event}: {type(fault).__name__}: {fault}")

    def pytest_deselected(self, items: Sequence[pytest.Item]) -> None:
        with self._lock:
            self._deselected += len(items)
            for item in items:
                test_file = item.nodeid.partition("::")[0]
                self._deselected_files[test_file] = self._deselected_files.get(test_file, 0) + 1

    @pytest.hookimpl(optionalhook=True)
    def pytest_testnodedown(
        self, node: WorkerController, error: object | None
    ) -> None:
        """pytest-xdist controller: a worker went down, cleanly or not.

        Optional, because the hook exists only where pytest-xdist is installed.
        A worker id that could not name a record file is a fault: the worker
        itself refused to start with it, so it wrote no record either.
        """
        worker_id = node.workerinput[_XDIST_WORKER_ID_INPUT]
        with self._lock:
            if isinstance(worker_id, str) and _WORKER_ID_PATTERN.fullmatch(worker_id):
                self._workers.add(worker_id)
                return
            self._faults.append(
                f"pytest_testnodedown: worker id {worker_id!r} cannot name a record "
                f"file (expected {_WORKER_ID_PATTERN.pattern})"
            )

    def pytest_runtest_logreport(self, report: pytest.TestReport) -> None:
        if report.when != _CALL_PHASE:
            return
        with self._lock:
            self._calls.append({"nodeid": report.nodeid, "seconds": report.duration})

    @pytest.hookimpl(hookwrapper=True)
    def pytest_fixture_setup(
        self, fixturedef: pytest.FixtureDef[object], request: pytest.FixtureRequest
    ) -> Generator[None, object, None]:
        """Time the setup of a session-, package- or module-scoped fixture.

        Dependencies are set up before this hook is called for the fixture
        that requests them, so the measured span is the fixture's own body.
        """
        if fixturedef.scope not in _TIMED_FIXTURE_SCOPES:
            yield
            return
        started = time.perf_counter()
        yield
        elapsed = time.perf_counter() - started
        with self._lock:
            self._fixtures.append(
                {
                    "fixture": f"{fixturedef.baseid}::{fixturedef.argname}",
                    "scope": fixturedef.scope,
                    "seconds": elapsed,
                }
            )

    @pytest.hookimpl(trylast=True)
    def pytest_sessionfinish(self, session: pytest.Session) -> None:
        """Stop recording and write this session's records, or fail the session."""
        self.stop()
        role = _session_role(session.config, self._settings.xdist_worker)
        records = self._records(role)
        with self._lock:
            problems = list(self._faults)
        run_dir = self._settings.run_dir
        problems.extend(
            f"{name} already exists in {run_dir}; a record is never overwritten"
            for name in records
            if (run_dir / name).exists()
        )
        if problems:
            self._fail(session, problems)
            return
        _publish_json_records(run_dir, records)
        logger.debug(
            "runner records written: worker=%s files=%s",
            role.worker_id,
            sorted(records),
        )

    def _records(self, role: _Role) -> dict[str, dict[str, object]]:
        header: dict[str, object] = {"schema": _RECORD_SCHEMA, "worker": role.worker_id}
        with self._lock:
            observed = {
                bucket: sorted(paths) for bucket, paths in self._observed.items()
            }
            records: dict[str, dict[str, object]] = {
                _record_file(_OBSERVED_KIND, role.worker_id): {**header, **observed}
            }
            if not role.collects_and_runs:
                records[_record_file(_WORKERS_KIND, role.worker_id)] = {
                    **header,
                    "workers": sorted(self._workers),
                }
            else:
                records[_record_file(_DESELECTED_KIND, role.worker_id)] = {
                    **header,
                    "deselected": self._deselected,
                    "deselected_files": dict(sorted(self._deselected_files.items())),
                }
                records[_record_file(_TIMINGS_KIND, role.worker_id)] = {
                    **header,
                    "calls": list(self._calls),
                    "fixtures": list(self._fixtures),
                }
        return records

    def _fail(self, session: pytest.Session, problems: Sequence[str]) -> None:
        message = (
            "test.runner_plugin wrote no record for this session, because "
            "its records could not be trusted:\n"
            + "\n".join(f"  - {problem}" for problem in problems)
            + "\nA fresh run directory per runner invocation, one worker id per session, and "
            "a recorder that understands every audited operation are all required; fix the "
            "cause above and re-run."
        )
        logger.error("%s", message)
        sys.stderr.write(message + "\n")
        session.exitstatus = pytest.ExitCode.INTERNAL_ERROR


# ---------------------------------------------------------------------------
# Plugin entry point
# ---------------------------------------------------------------------------


@pytest.hookimpl(tryfirst=True)
def pytest_load_initial_conftests(early_config: pytest.Config) -> None:
    """Validate the runner's environment and start recording before any
    conftest is imported, so what the initial conftests read is recorded too."""
    recorder = _SessionRecorder(_read_settings())
    early_config.pluginmanager.register(recorder, RECORDER_PLUGIN_NAME)
    early_config.add_cleanup(recorder.stop)
    recorder.start()
