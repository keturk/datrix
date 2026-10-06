"""The index's SQLite databases: the schema, and writing one file's facts.

Two files: ``index.db`` holds everything derived from source by parsing, and is dropped
and rebuilt whenever its schema changes. ``summaries.db`` holds model-written module
summaries keyed by content hash; they cost minutes of model time each, so they live
apart and survive any rebuild of the index.
"""

from __future__ import annotations

import json
import re
import sqlite3
from dataclasses import asdict
from pathlib import Path

from datrix_scripts.code_index.extract import FileFacts
from datrix_scripts.code_index.sources import INDEX_DB_NAME, SUMMARIES_DB_NAME, CodeIndexError, SourceFile

# Bump whenever the index schema or what extraction records changes; an index built by
# another version is dropped and rebuilt from source on the next refresh.
INDEX_SCHEMA_VERSION = "5"
META_SCHEMA_VERSION = "schema_version"
META_LAST_REFRESH = "last_refresh"

SUMMARIES_ALIAS = "summaries"

# A second process refreshing at the same time waits for the first; a first build of the
# whole workspace takes about a minute.
BUSY_TIMEOUT_MS = 600000

# Kinds of full-text rows: one per symbol, one per module, one per logic-map marker.
FTS_SYMBOL = "symbol"
FTS_MODULE = "module"
FTS_MARKER = "marker"

# A file's full-text rows occupy the rowid block ``file_id << FTS_ROWID_BITS`` onwards:
# the module row first, then one row per symbol and marker. An FTS5 table can filter
# cheaply only by rowid, so this is what lets a file's rows be replaced without scanning
# the whole table (filtering on an UNINDEXED column is a full scan per file).
FTS_ROWID_BITS = 20
MAX_FTS_ROWS_PER_FILE = 1 << FTS_ROWID_BITS

_INDEX_SCHEMA = """
CREATE TABLE IF NOT EXISTS meta (key TEXT PRIMARY KEY, value TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS files (
    id INTEGER PRIMARY KEY,
    path TEXT NOT NULL UNIQUE,
    repo TEXT NOT NULL,
    module TEXT NOT NULL,
    sha256 TEXT NOT NULL,
    size INTEGER NOT NULL,
    mtime_ns INTEGER NOT NULL,
    line_count INTEGER NOT NULL,
    module_doc TEXT NOT NULL,
    parse_error TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS files_module ON files(module);
CREATE TABLE IF NOT EXISTS symbols (
    id INTEGER PRIMARY KEY,
    file_id INTEGER NOT NULL REFERENCES files(id) ON DELETE CASCADE,
    name TEXT NOT NULL,
    qualname TEXT NOT NULL,
    kind TEXT NOT NULL,
    line INTEGER NOT NULL,
    end_line INTEGER NOT NULL,
    signature TEXT NOT NULL,
    doc TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS symbols_name ON symbols(name);
CREATE INDEX IF NOT EXISTS symbols_file ON symbols(file_id);
CREATE TABLE IF NOT EXISTS imports (
    file_id INTEGER NOT NULL REFERENCES files(id) ON DELETE CASCADE,
    module TEXT NOT NULL,
    name TEXT NOT NULL,
    alias TEXT NOT NULL,
    line INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS imports_target ON imports(module, name);
CREATE INDEX IF NOT EXISTS imports_file ON imports(file_id);
CREATE TABLE IF NOT EXISTS refs (
    file_id INTEGER NOT NULL REFERENCES files(id) ON DELETE CASCADE,
    name TEXT NOT NULL,
    kind TEXT NOT NULL,
    lines TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS refs_name ON refs(name);
CREATE INDEX IF NOT EXISTS refs_file ON refs(file_id);
CREATE TABLE IF NOT EXISTS markers (
    id INTEGER PRIMARY KEY,
    file_id INTEGER NOT NULL REFERENCES files(id) ON DELETE CASCADE,
    kind TEXT NOT NULL,
    topic TEXT NOT NULL,
    line INTEGER NOT NULL,
    payload TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS markers_topic ON markers(topic);
CREATE INDEX IF NOT EXISTS markers_file ON markers(file_id);
CREATE VIRTUAL TABLE IF NOT EXISTS fts USING fts5(
    name, body, file_id UNINDEXED, line UNINDEXED, kind UNINDEXED, ref UNINDEXED,
    tokenize = 'porter unicode61'
);
"""

_SUMMARIES_SCHEMA = f"""
CREATE TABLE IF NOT EXISTS {SUMMARIES_ALIAS}.summaries (
    sha256 TEXT PRIMARY KEY,
    summary TEXT NOT NULL,
    model TEXT NOT NULL,
    created_at TEXT NOT NULL
);
"""

_INDEX_TABLES = ("fts", "markers", "refs", "imports", "symbols", "files", "meta")

_CAMEL_BOUNDARY = re.compile(r"(?<=[a-z0-9])(?=[A-Z])|(?<=[A-Z])(?=[A-Z][a-z])")


def identifier_words(name: str) -> str:
    """``build_database`` / ``BuildDatabase`` -> ``build database``, for full-text matching."""
    return " ".join(part.lower() for chunk in name.split("_") for part in _CAMEL_BOUNDARY.split(chunk) if part)


def open_index(directory: Path) -> sqlite3.Connection:
    """Open (creating if needed) the index and attach the summaries database.

    The connection is in autocommit mode; callers group writes with ``BEGIN IMMEDIATE``.
    """
    directory.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(directory / INDEX_DB_NAME, timeout=BUSY_TIMEOUT_MS / 1000, isolation_level=None)
    conn.execute(f"PRAGMA busy_timeout = {BUSY_TIMEOUT_MS}")
    conn.execute("PRAGMA journal_mode = WAL")
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute(f"ATTACH DATABASE ? AS {SUMMARIES_ALIAS}", (str(directory / SUMMARIES_DB_NAME),))
    conn.execute(f"PRAGMA {SUMMARIES_ALIAS}.journal_mode = WAL")
    conn.execute(_SUMMARIES_SCHEMA)
    _ensure_index_schema(conn)
    return conn


def _ensure_index_schema(conn: sqlite3.Connection) -> None:
    conn.execute("BEGIN IMMEDIATE")
    try:
        if read_meta(conn, META_SCHEMA_VERSION) != INDEX_SCHEMA_VERSION:
            for table in _INDEX_TABLES:
                conn.execute(f"DROP TABLE IF EXISTS main.{table}")
            # One statement at a time: executescript would commit the open transaction
            # first, and a crash between the drops and the creates would leave no schema.
            for statement in _INDEX_SCHEMA.split(";"):
                if statement.strip():
                    conn.execute(statement)
            write_meta(conn, META_SCHEMA_VERSION, INDEX_SCHEMA_VERSION)
        conn.execute("COMMIT")
    except BaseException:
        conn.execute("ROLLBACK")
        raise


def read_meta(conn: sqlite3.Connection, key: str) -> str | None:
    exists = conn.execute("SELECT 1 FROM main.sqlite_master WHERE type = 'table' AND name = 'meta'").fetchone()
    if not exists:
        return None
    row = conn.execute("SELECT value FROM meta WHERE key = ?", (key,)).fetchone()
    return str(row[0]) if row else None


def write_meta(conn: sqlite3.Connection, key: str, value: str) -> None:
    conn.execute("INSERT INTO meta (key, value) VALUES (?, ?) ON CONFLICT(key) DO UPDATE SET value = excluded.value",
                 (key, value))


def _fts_rowid(file_id: int, row: int) -> int:
    return (file_id << FTS_ROWID_BITS) + row


def delete_file(conn: sqlite3.Connection, file_id: int) -> None:
    conn.execute("DELETE FROM fts WHERE rowid BETWEEN ? AND ?",
                 (_fts_rowid(file_id, 0), _fts_rowid(file_id, MAX_FTS_ROWS_PER_FILE - 1)))
    conn.execute("DELETE FROM files WHERE id = ?", (file_id,))


def summary_for(conn: sqlite3.Connection, sha256: str) -> str:
    row = conn.execute(f"SELECT summary FROM {SUMMARIES_ALIAS}.summaries WHERE sha256 = ?", (sha256,)).fetchone()
    return str(row[0]) if row else ""


def write_module_fts(conn: sqlite3.Connection, file_id: int) -> None:
    """(Re)write the module's own full-text row: its name, docstring and summary."""
    path, module, sha256, module_doc = conn.execute(
        "SELECT path, module, sha256, module_doc FROM files WHERE id = ?", (file_id,)
    ).fetchone()
    rowid = _fts_rowid(file_id, 0)
    conn.execute("DELETE FROM fts WHERE rowid = ?", (rowid,))
    name = f"{module} {identifier_words(module.replace('.', '_'))} {path}"
    body = f"{module_doc}\n{summary_for(conn, sha256)}".strip()
    conn.execute("INSERT INTO fts (rowid, name, body, file_id, line, kind, ref) VALUES (?, ?, ?, ?, 1, ?, ?)",
                 (rowid, name, body, file_id, FTS_MODULE, module))


def write_file(conn: sqlite3.Connection, source: SourceFile, module: str, sha256: str, facts: FileFacts) -> int:
    """Replace everything recorded about ``source`` with ``facts``; return its file id."""
    existing = conn.execute("SELECT id FROM files WHERE path = ?", (source.rel_path,)).fetchone()
    if existing:
        delete_file(conn, int(existing[0]))
    cursor = conn.execute(
        "INSERT INTO files (path, repo, module, sha256, size, mtime_ns, line_count, module_doc, parse_error) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (source.rel_path, source.repo, module, sha256, source.size, source.mtime_ns, facts.line_count,
         facts.module_doc, facts.parse_error),
    )
    file_id = int(cursor.lastrowid or 0)
    conn.executemany(
        "INSERT INTO symbols (file_id, name, qualname, kind, line, end_line, signature, doc) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        [(file_id, s.name, s.qualname, s.kind, s.line, s.end_line, s.signature, s.doc) for s in facts.symbols],
    )
    conn.executemany(
        "INSERT INTO imports (file_id, module, name, alias, line) VALUES (?, ?, ?, ?, ?)",
        [(file_id, i.module, i.name, i.alias, i.line) for i in facts.imports],
    )
    conn.executemany(
        "INSERT INTO refs (file_id, name, kind, lines) VALUES (?, ?, ?, ?)",
        [(file_id, r.name, r.kind, ",".join(map(str, r.lines))) for r in facts.refs],
    )
    conn.executemany(
        "INSERT INTO markers (file_id, kind, topic, line, payload) VALUES (?, ?, ?, ?, ?)",
        [(file_id, m.kind, m.topic, m.line, json.dumps(asdict(m))) for m in facts.markers],
    )
    _write_symbol_and_marker_fts(conn, file_id, facts)
    write_module_fts(conn, file_id)
    return file_id


def _write_symbol_and_marker_fts(conn: sqlite3.Connection, file_id: int, facts: FileFacts) -> None:
    rows: list[tuple[str, str, int, int, str, str]] = [
        (f"{s.name} {identifier_words(s.name)}", f"{s.signature}\n{s.doc}", file_id, s.line, FTS_SYMBOL, s.qualname)
        for s in facts.symbols
    ]
    rows.extend(
        (
            f"{m.topic} {m.topic.replace('/', ' ').replace('-', ' ')}",
            "\n".join([m.summary, m.description, *m.rules, *m.anti_patterns]),
            file_id, m.line, FTS_MARKER, m.topic,
        )
        for m in facts.markers
    )
    if len(rows) >= MAX_FTS_ROWS_PER_FILE:
        raise CodeIndexError(
            f"File id {file_id} has {len(rows)} definitions and markers; the full-text index holds at most "
            f"{MAX_FTS_ROWS_PER_FILE - 1} per file. Raise FTS_ROWID_BITS and INDEX_SCHEMA_VERSION together."
        )
    conn.executemany(
        "INSERT INTO fts (rowid, name, body, file_id, line, kind, ref) VALUES (?, ?, ?, ?, ?, ?, ?)",
        [(_fts_rowid(file_id, number), *row) for number, row in enumerate(rows, start=1)],
    )
