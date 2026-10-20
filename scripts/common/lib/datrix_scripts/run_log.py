"""Run-log file naming and exclusive claiming, for the scripts that run in Python.

Two runs that start in the same second compute the same timestamped log name, so a name is a label
and the claim is what makes it unique: ``claim_run_log_file`` creates each candidate with
``O_CREAT | O_EXCL`` -- an atomic create-or-fail -- so of two runs racing on one candidate exactly
one creates it and the other moves to the next candidate. The path it returns is owned by that run
alone.

This is the Python twin of ``common/DatrixRunLog.psm1`` (``ConvertTo-DatrixRunLogSegment``,
``Get-DatrixRunLogBaseName``, ``New-DatrixRunLogFile``): both compose the same names and claim the
same way, and ``test/run-log-exclusivity-gate.ps1`` holds both to that, name for name.
"""

from __future__ import annotations

import os
import re
from collections.abc import Sequence
from datetime import datetime
from pathlib import Path
from typing import Final

#: How many candidate names ``claim_run_log_file`` tries before failing (base name, then base-2 ...
#: base-N); far above any plausible number of same-second runs writing into one directory.
MAX_CLAIM_ATTEMPTS: Final = 1000
#: Second granularity, leading in the name, so sorting a results directory by name stays chronological.
TIMESTAMP_FORMAT: Final = "%Y%m%d-%H%M%S"
LOG_EXTENSION: Final = ".log"
#: What a caller-supplied label may contribute to a file name: every run of other characters (path
#: separators, drive colons, "..", spaces, wildcards) collapses to one dash, so a label taken from a
#: command line can never steer the log out of its directory.
_SEGMENT_SEPARATORS: Final = re.compile(r"[^A-Za-z0-9]+")
_DASH: Final = "-"
#: Create-or-fail: never relax to a mode that opens an existing file, which is how two runs end up
#: truncating and interleaving one log.
_CLAIM_FLAGS: Final = os.O_CREAT | os.O_EXCL | os.O_WRONLY


def run_log_segment(value: str) -> str:
    """*value* reduced to the characters a run-log name may carry ("" when nothing survives)."""
    return _SEGMENT_SEPARATORS.sub(_DASH, value).strip(_DASH)


def run_log_base_name(prefix: str, segments: Sequence[str] = (), *, timestamp: datetime | None = None) -> str:
    """``<prefix>-<timestamp>[-<segment>...]``, the preferred extension-less name of a run log.

    The segments say which run a log belongs to; they are not what makes it unique
    (``claim_run_log_file`` is). A segment that reduces to nothing is dropped. *timestamp* defaults
    to now; a fixed one makes the name deterministic.
    """
    moment = timestamp if timestamp is not None else datetime.now()
    parts = [run_log_segment(prefix), moment.strftime(TIMESTAMP_FORMAT)]
    parts.extend(clean for clean in (run_log_segment(segment) for segment in segments) if clean)
    return _DASH.join(parts)


def _candidate(directory: Path, base_name: str, attempt: int, extension: str) -> Path:
    suffix = "" if attempt == 1 else f"{_DASH}{attempt}"
    return directory / f"{base_name}{suffix}{extension}"


def claim_run_log_file(directory: Path, base_name: str, extension: str = LOG_EXTENSION) -> Path:
    """Create, and return the path of, an empty run-log file no other run owns.

    Tries ``<base_name><extension>``, then ``<base_name>-2<extension>`` ... up to
    ``MAX_CLAIM_ATTEMPTS``. *directory* is created when missing.

    Raises:
        OSError: the directory cannot be created or written (any failure other than the name
            being taken is raised as it is, never retried).
        RuntimeError: every candidate name is taken.
    """
    directory.mkdir(parents=True, exist_ok=True)
    for attempt in range(1, MAX_CLAIM_ATTEMPTS + 1):
        candidate = _candidate(directory, base_name, attempt, extension)
        try:
            descriptor = os.open(candidate, _CLAIM_FLAGS)
        except FileExistsError:
            continue
        os.close(descriptor)
        return candidate
    last = _candidate(directory, base_name, MAX_CLAIM_ATTEMPTS, extension)
    raise RuntimeError(
        f"Could not claim a private run-log file under '{directory}': the names '{base_name}{extension}' "
        f"through '{last.name}' are all taken. Expected at least one free name. This run cannot proceed, "
        "because sharing a log file with another run truncates that run's log and interleaves both runs' "
        f"output into one file. Fix: delete stale logs from '{directory}' and re-run."
    )
