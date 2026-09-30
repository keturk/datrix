"""Open the index for this workspace and bring it up to date: the start of every use."""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from pathlib import Path

from shared.venv import get_datrix_root

from code_index.refresh import RefreshReport, refresh_index
from code_index.sources import CodeIndexConfig, index_dir, load_config
from code_index.store import open_index


@dataclass
class IndexSession:
    conn: sqlite3.Connection
    workspace: Path
    config: CodeIndexConfig

    def refresh(self) -> RefreshReport:
        return refresh_index(self.conn, self.workspace, self.config)

    def close(self) -> None:
        self.conn.close()


def open_session(workspace: Path | None = None) -> IndexSession:
    """Open (creating if needed) the index of ``workspace`` (default: this checkout's workspace)."""
    root = workspace or get_datrix_root()
    return IndexSession(open_index(index_dir(root)), root, load_config())
