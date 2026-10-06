"""Bring the index up to date with the working tree, parsing only what changed.

A file whose size and modification time match the index is skipped without being read.
Otherwise it is hashed, and parsed again only when its content changed. The whole
refresh is one write transaction, so a query never sees a half-refreshed index and two
processes refreshing at once take turns rather than both writing.
"""

from __future__ import annotations

import hashlib
import json
import os
import sqlite3
import tempfile
import time
from concurrent.futures import ProcessPoolExecutor
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from datrix_scripts.code_index.extract import FileFacts, extract_file, extract_job
from datrix_scripts.code_index.sources import (
    LOGIC_MAP_DB,
    CodeIndexConfig,
    CodeIndexError,
    SourceFile,
    is_package_init,
    list_sources,
    module_name,
)
from datrix_scripts.code_index.store import META_LAST_REFRESH, delete_file, write_file, write_meta
from datrix_scripts.logic_map import Marker, build_database

# Below this many files to parse, starting worker processes costs more than it saves.
PARALLEL_THRESHOLD = 200
MAX_WORKERS = 8
EXTRACT_CHUNK_SIZE = 16


@dataclass(frozen=True)
class RefreshReport:
    total: int
    parsed: int
    removed: int
    parse_errors: int
    markers_rewritten: bool
    seconds: float

    def line(self) -> str:
        markers = "; logic map rewritten" if self.markers_rewritten else ""
        return (
            f"Index refreshed in {self.seconds:.1f}s: {self.total} files, {self.parsed} parsed, "
            f"{self.removed} removed, {self.parse_errors} with syntax errors{markers}."
        )


@dataclass(frozen=True)
class _Known:
    file_id: int
    size: int
    mtime_ns: int
    sha256: str
    has_markers: bool


@dataclass(frozen=True)
class _Job:
    source: SourceFile
    module: str
    sha256: str
    data: bytes


@dataclass(frozen=True)
class _Plan:
    jobs: list[_Job]
    touched: list[tuple[int, SourceFile]]
    vanished: list[str]


def _known_files(conn: sqlite3.Connection) -> dict[str, _Known]:
    rows = conn.execute(
        "SELECT f.path, f.id, f.size, f.mtime_ns, f.sha256, "
        "EXISTS (SELECT 1 FROM markers m WHERE m.file_id = f.id) FROM files f"
    ).fetchall()
    return {row[0]: _Known(row[1], row[2], row[3], row[4], bool(row[5])) for row in rows}


def _plan(sources: dict[str, SourceFile], known: dict[str, _Known], config: CodeIndexConfig) -> _Plan:
    """Split the tree into files to parse, files only touched, and files gone since listing."""
    plan = _Plan([], [], [])
    for rel_path, source in sources.items():
        row = known.get(rel_path)
        if row and row.size == source.size and row.mtime_ns == source.mtime_ns:
            continue
        try:
            data = source.abs_path.read_bytes()
        except FileNotFoundError:
            plan.vanished.append(rel_path)
            continue
        sha256 = hashlib.sha256(data).hexdigest()
        if row and row.sha256 == sha256:
            plan.touched.append((row.file_id, source))
            continue
        plan.jobs.append(_Job(source, module_name(rel_path, config), sha256, data))
    return plan


def _extract_all(jobs: list[_Job]) -> list[FileFacts]:
    args = [(job.data, job.source.rel_path, job.module, is_package_init(job.source.rel_path)) for job in jobs]
    if len(args) < PARALLEL_THRESHOLD:
        return [extract_file(*arg) for arg in args]
    workers = min(MAX_WORKERS, os.cpu_count() or 1)
    with ProcessPoolExecutor(max_workers=workers) as pool:
        return list(pool.map(extract_job, args, chunksize=EXTRACT_CHUNK_SIZE))


def indexed_markers(conn: sqlite3.Connection) -> list[Marker]:
    """Every marker in the index, in file and line order."""
    rows = conn.execute(
        "SELECT m.payload FROM markers m JOIN files f ON f.id = m.file_id ORDER BY f.path, m.line"
    ).fetchall()
    markers: list[Marker] = []
    for (payload,) in rows:
        fields = json.loads(payload)
        fields["dimensions"] = [tuple(pair) for pair in fields["dimensions"]]
        markers.append(Marker(**fields))
    return markers


def rewrite_logic_map(conn: sqlite3.Connection, workspace: Path) -> None:
    """Rewrite ``.logic-map/markers.db`` from the index, replacing the old file atomically."""
    target = workspace / LOGIC_MAP_DB
    target.parent.mkdir(parents=True, exist_ok=True)
    handle, temp_name = tempfile.mkstemp(dir=target.parent, prefix="markers-", suffix=".db.tmp")
    os.close(handle)
    temp_path = Path(temp_name)
    try:
        build_database(temp_path, indexed_markers(conn))
        os.replace(temp_path, target)
    except PermissionError as exc:
        raise CodeIndexError(
            f"Cannot replace {target}: {exc}. Another process holds it open; close it and query again."
        ) from exc
    finally:
        temp_path.unlink(missing_ok=True)


def _apply(conn: sqlite3.Connection, plan: _Plan, known: dict[str, _Known], gone: set[str]) -> bool:
    """Write the plan into the open transaction; return whether the marker set changed."""
    markers_changed = any(known[path].has_markers for path in gone)
    for path in gone:
        delete_file(conn, known[path].file_id)
    for file_id, source in plan.touched:
        conn.execute("UPDATE files SET size = ?, mtime_ns = ? WHERE id = ?", (source.size, source.mtime_ns, file_id))
    for job, facts in zip(plan.jobs, _extract_all(plan.jobs)):
        previous = known.get(job.source.rel_path)
        markers_changed |= bool(facts.markers) or bool(previous and previous.has_markers)
        write_file(conn, job.source, job.module, job.sha256, facts)
    write_meta(conn, META_LAST_REFRESH, datetime.now(UTC).isoformat(timespec="seconds"))
    return markers_changed


def refresh_index(conn: sqlite3.Connection, workspace: Path, config: CodeIndexConfig) -> RefreshReport:
    """Update the index to match the working tree; rewrite the logic map if its markers changed."""
    started = time.perf_counter()
    conn.execute("BEGIN IMMEDIATE")
    try:
        sources = list_sources(workspace, config)
        known = _known_files(conn)
        plan = _plan(sources, known, config)
        gone = (known.keys() - sources.keys()) | {path for path in plan.vanished if path in known}
        markers_changed = _apply(conn, plan, known, gone)
        conn.execute("COMMIT")
    except BaseException:
        conn.execute("ROLLBACK")
        raise
    rewrite = markers_changed or not (workspace / LOGIC_MAP_DB).exists()
    if rewrite:
        rewrite_logic_map(conn, workspace)
    parse_errors = conn.execute("SELECT COUNT(*) FROM files WHERE parse_error != ''").fetchone()[0]
    return RefreshReport(
        total=len(sources) - len(plan.vanished), parsed=len(plan.jobs), removed=len(gone),
        parse_errors=int(parse_errors), markers_rewritten=rewrite, seconds=time.perf_counter() - started,
    )
