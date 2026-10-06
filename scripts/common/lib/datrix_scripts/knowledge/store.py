"""The knowledge base file: curated chunks cut from the docs, and learned answers, in one SQLite database.

The database is a per-machine cache and is never the source of truth. Curated chunks are cut from
committed docs, and every learned answer is also kept as a committed text file
(``knowledge.learned_files``), so a machine can rebuild the whole database from the repositories and a
second machine converges on the same content. Nothing here reads a document or contacts a model.
"""

from __future__ import annotations

import hashlib
import os
import re
import sqlite3
from collections.abc import Iterator, Sequence
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path

from datrix_scripts.venv import get_datrix_root

KB_DIR_NAME = ".knowledge"
KB_FILE_NAME = "knowledge.db"
KB_VARIABLE = "DATRIX_KNOWLEDGE_DB"

# Bumping this drops and recreates the tables on next open: the database is derived data.
SCHEMA_VERSION = 1
BUSY_TIMEOUT_S = 30.0
HASH_BLOCK_BYTES = 1 << 20

KIND_CURATED = "curated"
KIND_LEARNED = "learned"

# bm25 column weights, in the column order of entries_fts: a title or a question that matches
# is worth more than a word somewhere in the body.
WEIGHT_TOPIC = 4.0
WEIGHT_BODY = 1.0
WEIGHT_QUESTION = 3.0

_SCHEMA = """
CREATE TABLE docs (
    path TEXT PRIMARY KEY,
    sha256 TEXT NOT NULL
);
CREATE TABLE entries (
    id INTEGER PRIMARY KEY,
    kind TEXT NOT NULL,
    entry_key TEXT NOT NULL,
    topic TEXT NOT NULL,
    body TEXT NOT NULL,
    source_path TEXT NOT NULL,
    line_start INTEGER NOT NULL,
    line_end INTEGER NOT NULL,
    question TEXT NOT NULL,
    model TEXT NOT NULL,
    created_at TEXT NOT NULL
);
CREATE UNIQUE INDEX entries_learned_key ON entries (entry_key) WHERE kind = 'learned';
CREATE INDEX entries_source ON entries (source_path);
CREATE TABLE sources (
    entry_id INTEGER NOT NULL REFERENCES entries (id) ON DELETE CASCADE,
    path TEXT NOT NULL,
    sha256 TEXT NOT NULL,
    PRIMARY KEY (entry_id, path)
);
CREATE VIRTUAL TABLE entries_fts USING fts5 (topic, body, question, tokenize = 'porter unicode61');
"""

_DROP = (
    "DROP TABLE IF EXISTS entries_fts",
    "DROP TABLE IF EXISTS sources",
    "DROP TABLE IF EXISTS entries",
    "DROP TABLE IF EXISTS docs",
)


class KnowledgeError(RuntimeError):
    """The knowledge base or its text copy cannot be used as asked; the message says what to do."""


@dataclass(frozen=True)
class Chunk:
    """A contiguous run of one document's lines, under the heading path that introduces it."""

    topic: str
    body: str
    line_start: int
    line_end: int


@dataclass(frozen=True)
class LearnedEntry:
    """An answer gathered by a local model, with the files whose content it was drawn from."""

    key: str
    question: str
    answer: str
    model: str
    created_at: str
    sources: dict[str, str]


@dataclass(frozen=True)
class Entry:
    id: int
    kind: str
    entry_key: str
    topic: str
    body: str
    source_path: str
    line_start: int
    line_end: int
    question: str
    model: str
    created_at: str


@dataclass(frozen=True)
class Hit:
    entry: Entry
    rank: float


_WORD = re.compile(r"[A-Za-z0-9]+")
_CAMEL_BOUNDARY = re.compile(r"(?<=[a-z0-9])(?=[A-Z])")


def split_words(text: str) -> list[str]:
    """Lower-case words of ``text``, with camelCase and snake_case identifiers split apart."""
    return [part.lower() for token in _WORD.findall(text) for part in _CAMEL_BOUNDARY.split(token) if part]


def searchable(text: str) -> str:
    """``text`` plus the parts of its camelCase identifiers: the tokenizer keeps ``crossTenant`` as one
    token, so a search for "cross tenant" would otherwise miss it."""
    parts = [part.lower() for token in _WORD.findall(text)
             for pieces in [_CAMEL_BOUNDARY.split(token)] if len(pieces) > 1 for part in pieces]
    return f"{text}\n{' '.join(parts)}" if parts else text


def knowledge_db_path() -> Path:
    override = os.environ.get(KB_VARIABLE, "")
    if override:
        return Path(override)
    return get_datrix_root() / KB_DIR_NAME / KB_FILE_NAME


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(HASH_BLOCK_BYTES), b""):
            digest.update(block)
    return digest.hexdigest()


_ENTRY_COLUMNS = (
    "e.id, e.kind, e.entry_key, e.topic, e.body, e.source_path, e.line_start, e.line_end, "
    "e.question, e.model, e.created_at"
)


def _entry(row: sqlite3.Row) -> Entry:
    return Entry(row["id"], row["kind"], row["entry_key"], row["topic"], row["body"], row["source_path"],
                 row["line_start"], row["line_end"], row["question"], row["model"], row["created_at"])


class KnowledgeBase:
    """One SQLite file. Every operation opens its own short-lived connection, so two agents on one
    machine never hold a lock between calls."""

    def __init__(self, path: Path) -> None:
        self.path = path
        self._ensure_schema()

    @contextmanager
    def _connect(self) -> Iterator[sqlite3.Connection]:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(self.path, timeout=BUSY_TIMEOUT_S)
        conn.row_factory = sqlite3.Row
        try:
            conn.execute("PRAGMA foreign_keys = ON")
            conn.execute("PRAGMA journal_mode = WAL")
            yield conn
            conn.commit()
        except BaseException:
            conn.rollback()
            raise
        finally:
            conn.close()

    def _ensure_schema(self) -> None:
        with self._connect() as conn:
            version = conn.execute("PRAGMA user_version").fetchone()[0]
            if version == SCHEMA_VERSION:
                return
            for statement in _DROP:
                conn.execute(statement)
            conn.executescript(_SCHEMA)
            conn.execute(f"PRAGMA user_version = {SCHEMA_VERSION}")

    def clear(self) -> None:
        """Drop everything; the next sync rebuilds it from the docs and the learned text files."""
        with self._connect() as conn:
            for statement in _DROP:
                conn.execute(statement)
            conn.executescript(_SCHEMA)

    # ---- curated chunks -------------------------------------------------------------------

    def curated_docs(self) -> dict[str, str]:
        with self._connect() as conn:
            return {row["path"]: row["sha256"] for row in conn.execute("SELECT path, sha256 FROM docs")}

    def replace_curated_doc(self, path: str, sha256: str, chunks: Sequence[Chunk]) -> None:
        with self._connect() as conn:
            self._delete_curated(conn, path)
            conn.execute("INSERT INTO docs (path, sha256) VALUES (?, ?)", (path, sha256))
            for chunk in chunks:
                self._insert(conn, KIND_CURATED, "", chunk.topic, chunk.body, path, chunk.line_start,
                             chunk.line_end, "", "", "")

    def remove_curated_doc(self, path: str) -> None:
        with self._connect() as conn:
            self._delete_curated(conn, path)

    @staticmethod
    def _delete_curated(conn: sqlite3.Connection, path: str) -> None:
        ids = [row["id"] for row in conn.execute(
            "SELECT id FROM entries WHERE kind = ? AND source_path = ?", (KIND_CURATED, path))]
        for entry_id in ids:
            conn.execute("DELETE FROM entries_fts WHERE rowid = ?", (entry_id,))
            conn.execute("DELETE FROM entries WHERE id = ?", (entry_id,))
        conn.execute("DELETE FROM docs WHERE path = ?", (path,))

    # ---- learned answers ------------------------------------------------------------------

    def upsert_learned(self, entry: LearnedEntry) -> None:
        with self._connect() as conn:
            self._delete_learned(conn, entry.key)
            entry_id = self._insert(conn, KIND_LEARNED, entry.key, entry.question, entry.answer, "", 0, 0,
                                    entry.question, entry.model, entry.created_at)
            conn.executemany("INSERT INTO sources (entry_id, path, sha256) VALUES (?, ?, ?)",
                             [(entry_id, path, sha) for path, sha in sorted(entry.sources.items())])

    def remove_learned(self, key: str) -> None:
        with self._connect() as conn:
            self._delete_learned(conn, key)

    @staticmethod
    def _delete_learned(conn: sqlite3.Connection, key: str) -> None:
        row = conn.execute("SELECT id FROM entries WHERE kind = ? AND entry_key = ?",
                           (KIND_LEARNED, key)).fetchone()
        if row is None:
            return
        conn.execute("DELETE FROM entries_fts WHERE rowid = ?", (row["id"],))
        conn.execute("DELETE FROM entries WHERE id = ?", (row["id"],))

    def learned(self) -> dict[str, LearnedEntry]:
        """Every learned answer, by key."""
        with self._connect() as conn:
            rows = conn.execute(f"SELECT {_ENTRY_COLUMNS} FROM entries e WHERE e.kind = ?",
                                (KIND_LEARNED,)).fetchall()
            found: dict[str, LearnedEntry] = {}
            for row in rows:
                entry = _entry(row)
                sources = {source["path"]: source["sha256"] for source in conn.execute(
                    "SELECT path, sha256 FROM sources WHERE entry_id = ?", (entry.id,))}
                found[entry.entry_key] = LearnedEntry(entry.entry_key, entry.question, entry.body, entry.model,
                                                      entry.created_at, sources)
            return found

    def sources_of(self, entry_id: int) -> dict[str, str]:
        with self._connect() as conn:
            return {row["path"]: row["sha256"] for row in conn.execute(
                "SELECT path, sha256 FROM sources WHERE entry_id = ?", (entry_id,))}

    # ---- queries --------------------------------------------------------------------------

    def search(self, match: str, limit: int) -> list[Hit]:
        """The entries matching an FTS5 expression, best first."""
        with self._connect() as conn:
            rows = conn.execute(
                f"SELECT {_ENTRY_COLUMNS}, bm25(entries_fts, ?, ?, ?) AS rank FROM entries_fts "
                "JOIN entries e ON e.id = entries_fts.rowid WHERE entries_fts MATCH ? ORDER BY rank LIMIT ?",
                (WEIGHT_TOPIC, WEIGHT_BODY, WEIGHT_QUESTION, match, limit)).fetchall()
            return [Hit(_entry(row), row["rank"]) for row in rows]

    def counts(self) -> dict[str, int]:
        with self._connect() as conn:
            return {
                "docs": conn.execute("SELECT COUNT(*) FROM docs").fetchone()[0],
                KIND_CURATED: conn.execute("SELECT COUNT(*) FROM entries WHERE kind = ?",
                                           (KIND_CURATED,)).fetchone()[0],
                KIND_LEARNED: conn.execute("SELECT COUNT(*) FROM entries WHERE kind = ?",
                                           (KIND_LEARNED,)).fetchone()[0],
            }

    @staticmethod
    def _insert(conn: sqlite3.Connection, kind: str, key: str, topic: str, body: str, source_path: str,
                line_start: int, line_end: int, question: str, model: str, created_at: str) -> int:
        cursor = conn.execute(
            "INSERT INTO entries (kind, entry_key, topic, body, source_path, line_start, line_end, question, "
            "model, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (kind, key, topic, body, source_path, line_start, line_end, question, model, created_at))
        entry_id = cursor.lastrowid
        if entry_id is None:
            raise KnowledgeError(f"SQLite returned no row id inserting into {KB_FILE_NAME}; delete {KB_DIR_NAME}.")
        conn.execute("INSERT INTO entries_fts (rowid, topic, body, question) VALUES (?, ?, ?, ?)",
                     (entry_id, searchable(topic), searchable(body), searchable(question)))
        return entry_id
