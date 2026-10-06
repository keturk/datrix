"""Append one JSON record to a hook's log, within the log's size cap.

Every hook that keeps a persistent log (search usage, the stop-gate judge's verdicts, the
guards' audit trails) appends through ``append_record``, which writes through the shared
scripts package's ``datrix_scripts.capped_log``: when the log reaches its cap it is rotated to
``<name>.1``, so no hook log grows without bound.

The package is reached from this file's REAL path (``<workspace>/datrix/claude-config/.claude/
hooks/``, beside ``<workspace>/datrix/scripts/common/lib``), whichever way the hook was started.

Never raises: a hook -- above all a guard, which must still refuse after a failed write --
must not fail because a log line was lost. The loss is reported on stderr.
"""

import json
import os
import sys
from pathlib import Path
from typing import Final

#: The workspace root: this file is <workspace>/datrix/claude-config/.claude/hooks/_hook_log.py.
WORKSPACE: Final = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.realpath(__file__))))))
#: The directory holding the shared scripts package, for hooks that import ``datrix_scripts.*``.
SCRIPTS_LIB_DIR: Final = os.path.join(WORKSPACE, "datrix", "scripts", "common", "lib")


def add_scripts_lib_to_path() -> None:
    """Put the shared scripts package's directory first on ``sys.path`` (once)."""
    if SCRIPTS_LIB_DIR not in sys.path:
        sys.path.insert(0, SCRIPTS_LIB_DIR)


def append_record(log: str, record: dict[str, object], writer: str, max_bytes: int | None = None) -> None:
    """Append ``record`` to ``log`` as one JSON line; ``writer`` names the hook in any warning.

    ``max_bytes`` left unset takes ``datrix_scripts.capped_log.DEFAULT_MAX_BYTES`` -- the cap every
    log with no reason for its own shares, including logs a hook and a repo script both write.
    """
    add_scripts_lib_to_path()
    try:
        from datrix_scripts.capped_log import DEFAULT_MAX_BYTES, append_line
    except ImportError as exc:
        sys.stderr.write(f"{writer}: could not append to {log}: datrix_scripts.capped_log not importable "
                         f"from {SCRIPTS_LIB_DIR}: {exc}\n")
        return
    try:
        append_line(Path(log), json.dumps(record, ensure_ascii=False),
                    DEFAULT_MAX_BYTES if max_bytes is None else max_bytes)
    except (OSError, ValueError) as exc:
        sys.stderr.write(f"{writer}: could not append to {log}: {exc}\n")
