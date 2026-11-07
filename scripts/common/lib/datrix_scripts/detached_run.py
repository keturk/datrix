"""Start a run that outlives the process which noticed the work, and let only one such run work at a time.

A hook or an MCP query that finds work pending cannot wait for it (a module summary pass, a model
load take minutes) and cannot do it on a thread (the process exits, and takes the thread with it). It
starts a detached run of a script module and answers at once.

ONE RUN AT A TIME
    A run holds a lock file, created exclusively and holding the run's process id. The process that
    would start a run does not while the lock is held (``lock_is_fresh``), and a run that finds it
    held exits at once (``held_lock`` raises ``LockBusy``).

    A run that is killed never releases its lock, so a lock is STALE -- and taken over -- when the
    process named in it is gone, or when it has not been refreshed for the lock's stale limit. A live
    run refreshes it (the function ``held_lock`` yields) as it makes progress, which is what lets
    the limit be short.
"""

from __future__ import annotations

import os
import subprocess
import sys
import time
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from pathlib import Path

from datrix_scripts.paths import script_env

Launcher = Callable[[list[str], Path], None]
Touch = Callable[[], None]


class LockBusy(RuntimeError):
    """Another run holds the lock."""


def process_is_alive(pid: int) -> bool:
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


def lock_is_fresh(lock: Path, stale_seconds: float) -> bool:
    """True when a live run holds ``lock``: its process exists and it was refreshed within ``stale_seconds``."""
    try:
        if time.time() - lock.stat().st_mtime >= stale_seconds:
            return False
        text = lock.read_text(encoding="ascii").strip()
    except FileNotFoundError:
        return False
    # A lock just created and not yet written to names no process: the age alone decides.
    return not text.isdigit() or process_is_alive(int(text))


@contextmanager
def held_lock(lock: Path, stale_seconds: float, busy: Callable[[str], LockBusy] = LockBusy) -> Iterator[Touch]:
    """Hold ``lock`` for the duration; raise ``busy`` (a ``LockBusy`` type) when another run holds it.

    Yields a function the run calls as it makes progress to keep the lock fresh.
    """
    lock.parent.mkdir(parents=True, exist_ok=True)
    if lock.exists() and not lock_is_fresh(lock, stale_seconds):
        lock.unlink(missing_ok=True)
    try:
        descriptor = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    except FileExistsError as exc:
        raise busy(f"A run already holds {lock}; this one exits.") from exc
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
    log.parent.mkdir(parents=True, exist_ok=True)
    with log.open("w", encoding="utf-8") as output:
        common = {
            "stdin": subprocess.DEVNULL,
            "stdout": output,
            "stderr": subprocess.STDOUT,
            "close_fds": True,
            "env": script_env(),
        }
        if sys.platform != "win32":
            subprocess.Popen(command, start_new_session=True, **common)
            return
        detached = subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP
        try:
            subprocess.Popen(command, creationflags=detached | subprocess.CREATE_BREAKAWAY_FROM_JOB, **common)
        except OSError:
            subprocess.Popen(command, creationflags=detached, **common)
