"""Append-only logs with a size cap: one line per append, never more than two files on disk.

Every persistent JSONL log the scripts and hooks keep (search usage, local-model usage, the
stop-gate judge's verdicts, the guards' audit trails) is written through ``append_line``.
When an append would take the log past its cap, the log is first renamed to
``<name>.1`` -- replacing the previous ``.1`` -- and a fresh log is started. So a log costs
at most twice its cap on disk, and a reader that wants history reads ``read_lines``: the
rotated file, then the current one.

Several processes append to the same log at once (parallel subagents, each running hooks).
Only one may rotate: rotation is claimed by creating ``<name>.rotating`` exclusively. A claim
older than ``STALE_CLAIM_SECONDS`` was left by a process that died mid-rotation and is
broken. A process that loses the race simply appends to whichever file is current.

Standard library only: the Claude Code hooks import it under the system interpreter.
"""

from __future__ import annotations

import os
import time
from pathlib import Path

DEFAULT_MAX_BYTES = 5 * 1024 * 1024
ROTATED_SUFFIX = ".1"
CLAIM_SUFFIX = ".rotating"
STALE_CLAIM_SECONDS = 60


def rotated_path(log: Path) -> Path:
    return log.with_name(log.name + ROTATED_SUFFIX)


def _claim(claim: Path) -> bool:
    try:
        os.close(os.open(claim, os.O_CREAT | os.O_EXCL | os.O_WRONLY))
        return True
    except FileExistsError:
        try:
            if time.time() - claim.stat().st_mtime > STALE_CLAIM_SECONDS:
                claim.unlink(missing_ok=True)
        except OSError:
            return False
        return False


def _rotate_if_full(log: Path, incoming: int, max_bytes: int) -> None:
    try:
        if log.stat().st_size + incoming <= max_bytes:
            return
    except FileNotFoundError:
        return
    claim = log.with_name(log.name + CLAIM_SUFFIX)
    if not _claim(claim):
        return
    try:
        # Checked again under the claim: another process may have rotated in between.
        if log.exists() and log.stat().st_size + incoming > max_bytes:
            os.replace(log, rotated_path(log))
    finally:
        claim.unlink(missing_ok=True)


def append_line(log: Path, line: str, max_bytes: int = DEFAULT_MAX_BYTES) -> None:
    """Append ``line`` (a newline is added) to ``log``, rotating first when the cap would be
    passed. Raises OSError when the log cannot be written; callers that must never fail on a
    lost log line catch it."""
    if max_bytes <= 0:
        raise ValueError(f"max_bytes must be positive; got {max_bytes}. Pass the log's size cap in bytes.")
    data = (line + "\n").encode("utf-8")
    log.parent.mkdir(parents=True, exist_ok=True)
    _rotate_if_full(log, len(data), max_bytes)
    with log.open("ab") as handle:
        handle.write(data)


def read_lines(log: Path) -> list[str]:
    """Every line still on disk, oldest first: the rotated file, then the current log."""
    lines: list[str] = []
    for path in (rotated_path(log), log):
        if path.exists():
            lines.extend(path.read_text(encoding="utf-8", errors="replace").splitlines())
    return lines
