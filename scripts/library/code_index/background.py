"""Keep module summaries current without anyone running ``-Summarize``.

A summary is keyed by its module's content hash, so every edit leaves the module without one,
and ``search`` and ``outline`` lose the model-written description of exactly the code being
worked on. Nothing used to re-run the summarizer. Now, when a query's refresh finds changed
files and modules are waiting for a summary, the query starts a detached
``code_index_cli.py summarize`` run and answers at once; the run summarizes everything pending
on the local model servers and exits.

ONE RUN AT A TIME
    Every summarize run -- background or ``code-index.ps1 -Summarize`` -- holds
    ``<index dir>/summarize.lock``, created exclusively and holding the run's process id. A query
    does not start a run while the lock is held, and a run that finds it held exits at once.

    A run that is killed never releases its lock, so a lock is STALE -- and taken over -- when
    the process named in it is gone, or when it has not been refreshed for
    ``LOCK_STALE_SECONDS``. A live run refreshes it (``touch``) as it makes progress, which is
    what lets the age limit be short.

The background run's output goes to ``<index dir>/summarize.log``, replaced by each run.
"""

from __future__ import annotations

import os
import subprocess
import sys
import time
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from pathlib import Path

from code_index.session import IndexSession
from code_index.sources import index_dir
from code_index.summaries import pending

LOCK_NAME = "summarize.lock"
LOG_NAME = "summarize.log"
# A live run touches its lock at least this often (every 25 summaries, minutes apart at worst:
# a request is capped at five minutes). Older than this, nothing is refreshing it.
LOCK_STALE_SECONDS = 20 * 60

_CLI_SCRIPT = Path(__file__).resolve().parent.parent / "dev" / "code_index_cli.py"

Launcher = Callable[[list[str], Path], None]
Touch = Callable[[], None]


class SummarizeBusy(RuntimeError):
    """Another summarize run holds the lock."""


def _lock_path(workspace: Path) -> Path:
    return index_dir(workspace) / LOCK_NAME


def _process_is_alive(pid: int) -> bool:
    if sys.platform == "win32":
        # os.kill(pid, 0) is not a probe on Windows: any signal other than a console event
        # terminates the process. Ask the kernel for its exit code instead.
        import ctypes

        process_query_limited_information, still_active = 0x1000, 259
        kernel32 = ctypes.windll.kernel32  # type: ignore[attr-defined]
        handle = kernel32.OpenProcess(process_query_limited_information, False, pid)
        if not handle:
            return False
        try:
            code = ctypes.c_ulong()
            return bool(kernel32.GetExitCodeProcess(handle, ctypes.byref(code))) and code.value == still_active
        finally:
            kernel32.CloseHandle(handle)
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def _lock_is_fresh(lock: Path) -> bool:
    """True when a live run holds ``lock``: its process exists and it was refreshed recently."""
    try:
        if time.time() - lock.stat().st_mtime >= LOCK_STALE_SECONDS:
            return False
        text = lock.read_text(encoding="ascii").strip()
    except FileNotFoundError:
        return False
    # A lock just created and not yet written to names no process: the age alone decides.
    return not text.isdigit() or _process_is_alive(int(text))


@contextmanager
def summarize_lock(workspace: Path) -> Iterator[Touch]:
    """Hold the summarize lock for the duration; raise SummarizeBusy when another run holds it.

    Yields a function the run calls as it makes progress to keep the lock fresh.
    """
    lock = _lock_path(workspace)
    lock.parent.mkdir(parents=True, exist_ok=True)
    if lock.exists() and not _lock_is_fresh(lock):
        lock.unlink(missing_ok=True)
    try:
        descriptor = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    except FileExistsError as exc:
        raise SummarizeBusy(f"A summarize run already holds {lock}; this one exits.") from exc
    os.write(descriptor, f"{os.getpid()}\n".encode("ascii"))
    os.close(descriptor)
    try:
        yield lambda: os.utime(lock)
    finally:
        lock.unlink(missing_ok=True)


def launch_detached(command: list[str], log: Path) -> None:
    """Start ``command`` as a process that outlives this one, its output to ``log``.

    On Windows a process started by a tool call or an MCP server belongs to a job object that
    ends it with the parent; ``CREATE_BREAKAWAY_FROM_JOB`` leaves the job, and is dropped when
    the job does not allow it.
    """
    with log.open("w", encoding="utf-8") as output:
        common = {"stdin": subprocess.DEVNULL, "stdout": output, "stderr": subprocess.STDOUT, "close_fds": True}
        if sys.platform != "win32":
            subprocess.Popen(command, start_new_session=True, **common)
            return
        detached = subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP
        try:
            subprocess.Popen(command, creationflags=detached | subprocess.CREATE_BREAKAWAY_FROM_JOB, **common)
        except OSError:
            subprocess.Popen(command, creationflags=detached, **common)


def start_background_summaries(session: IndexSession, launch: Launcher = launch_detached) -> bool:
    """Start a background summarize run when modules await a summary and none is running.

    Returns True when a run was started.
    """
    if _lock_is_fresh(_lock_path(session.workspace)):
        return False
    if not pending(session.conn, session.config):
        return False
    command = [sys.executable, str(_CLI_SCRIPT), "summarize", "--limit", "0"]
    launch(command, index_dir(session.workspace) / LOG_NAME)
    return True
