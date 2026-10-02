"""Append one JSON record to a hook's log, within the log's size cap.

Every hook that keeps a persistent log (search usage, the stop-gate judge's verdicts, the
guards' audit trails) appends through ``append_record``, which writes through the scripts
library's ``shared.capped_log``: when the log reaches its cap it is rotated to ``<name>.1``,
so no hook log grows without bound.

The library is reached from this file's REAL path (``<workspace>/datrix/claude-config/.claude/
hooks/``, beside ``<workspace>/datrix/scripts/library``), whichever way the hook was started.

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
#: The scripts library, for hooks that import ``shared.*`` or ``code_index.*``.
LIBRARY_DIR: Final = os.path.join(WORKSPACE, "datrix", "scripts", "library")


def append_record(log: str, record: dict[str, object], writer: str, max_bytes: int | None = None) -> None:
    """Append ``record`` to ``log`` as one JSON line; ``writer`` names the hook in any warning.

    ``max_bytes`` left unset takes ``shared.capped_log.DEFAULT_MAX_BYTES`` -- the cap every log
    with no reason for its own shares, including logs a hook and a library script both write.
    """
    if LIBRARY_DIR not in sys.path:
        sys.path.insert(0, LIBRARY_DIR)
    try:
        from shared.capped_log import DEFAULT_MAX_BYTES, append_line
    except ImportError as exc:
        sys.stderr.write(f"{writer}: could not append to {log}: shared.capped_log not importable from "
                         f"{LIBRARY_DIR}: {exc}\n")
        return
    try:
        append_line(Path(log), json.dumps(record, ensure_ascii=False),
                    DEFAULT_MAX_BYTES if max_bytes is None else max_bytes)
    except (OSError, ValueError) as exc:
        sys.stderr.write(f"{writer}: could not append to {log}: {exc}\n")
