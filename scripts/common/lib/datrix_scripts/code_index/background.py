"""Keep module summaries current without anyone running ``-Summarize``.

A summary is keyed by its module's content hash, so every edit leaves the module without one,
and ``search`` and ``outline`` lose the model-written description of exactly the code being
worked on. Nothing used to re-run the summarizer. Now, when a query's refresh finds changed
files and modules are waiting for a summary, the query starts a detached
``datrix_scripts.dev.code_index --summarize`` run and answers at once; the run summarizes everything pending
on the local model servers and exits.

ONE RUN AT A TIME
    Every summarize run -- background or ``code-index.ps1 -Summarize`` -- holds
    ``<index dir>/summarize.lock`` (``datrix_scripts.detached_run``). A query does not start a run
    while the lock is held, and a run that finds it held exits at once. A live run refreshes the lock
    as it makes progress (every 25 summaries, minutes apart at worst: a request is capped at five
    minutes), so a lock older than ``LOCK_STALE_SECONDS`` belongs to a run that is gone.

The background run's output goes to ``<index dir>/summarize.log``, replaced by each run.
"""

from __future__ import annotations

import sys
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

from datrix_scripts.code_index.session import IndexSession
from datrix_scripts.code_index.sources import index_dir
from datrix_scripts.code_index.summaries import pending
from datrix_scripts.detached_run import Launcher, LockBusy, Touch, held_lock, launch_detached, lock_is_fresh

#: The module a background run executes, with ``--summarize``: the one behind ``code-index.ps1``.
SUMMARIZE_MODULE = "datrix_scripts.dev.code_index"
LOCK_NAME = "summarize.lock"
LOG_NAME = "summarize.log"
# A live run touches its lock at least this often. Older than this, nothing is refreshing it.
LOCK_STALE_SECONDS = 20 * 60


class SummarizeBusy(LockBusy):
    """Another summarize run holds the lock."""


def _lock_path(workspace: Path) -> Path:
    return index_dir(workspace) / LOCK_NAME


@contextmanager
def summarize_lock(workspace: Path) -> Iterator[Touch]:
    """Hold the summarize lock for the duration; raise SummarizeBusy when another run holds it.

    Yields a function the run calls as it makes progress to keep the lock fresh.
    """
    with held_lock(_lock_path(workspace), LOCK_STALE_SECONDS, SummarizeBusy) as touch:
        yield touch


def start_background_summaries(session: IndexSession, launch: Launcher = launch_detached) -> bool:
    """Start a background summarize run when modules await a summary and none is running.

    Returns True when a run was started.
    """
    if lock_is_fresh(_lock_path(session.workspace), LOCK_STALE_SECONDS):
        return False
    if not pending(session.conn, session.config):
        return False
    command = [sys.executable, "-m", SUMMARIZE_MODULE, "--summarize", "--limit=0"]
    launch(command, index_dir(session.workspace) / LOG_NAME)
    return True
