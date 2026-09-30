"""Module summaries written by a local model, for search by concept rather than by name.

The only part of the index that leaves the machine: each module's outline and source are
sent to a model server found by ``shared.local_llm`` (plain HTTP on the local network, as
every local-model script does), and only when ``summarize`` is called explicitly -- never
by a query. Summaries are keyed by the module's content hash in ``summaries.db``, so an
unchanged module is never sent twice and a rebuilt index keeps every summary.
"""

from __future__ import annotations

import hashlib
import re
import sqlite3
from collections.abc import Callable
from concurrent.futures import Future, ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from shared.local_llm import ChatRequest, LocalLlmPool, LocalLlmReply

from code_index.queries import outline
from code_index.sources import CodeIndexConfig
from code_index.store import SUMMARIES_ALIAS, write_module_fts

# A module this short is fully described by its docstring and outline.
MIN_SUMMARY_LINES = 30
MAX_SOURCE_CHARS = 24000
MAX_OUTLINE_CHARS = 6000
MAX_SUMMARY_CHARS = 800
SUMMARY_MAX_TOKENS = 400
SUMMARY_TEMPERATURE = 0.2
DEFAULT_SUMMARY_WORKERS = 4
DEFAULT_SUMMARY_LIMIT = 200

_WHITESPACE = re.compile(r"\s+")

SUMMARY_SYSTEM_PROMPT = (
    "You write the search-index entry for one Python module of Datrix, a multi-language, "
    "multi-platform code generator. In 2 to 4 plain sentences, say what the module is responsible "
    "for, name its main public classes and functions, and name the domain concepts it handles, in "
    "the words a developer would search for. No preamble, no markdown, no bullet points."
)


@dataclass(frozen=True)
class SummaryCandidate:
    path: str
    module: str
    sha256: str


@dataclass(frozen=True)
class SummaryRun:
    summarized: int
    changed_on_disk: int
    pending_after: int

    def line(self) -> str:
        changed = f"; {self.changed_on_disk} changed on disk since the refresh" if self.changed_on_disk else ""
        return f"Summarized {self.summarized} modules{changed}; {self.pending_after} still without a summary."


def summarizable(conn: sqlite3.Connection, config: CodeIndexConfig) -> list[SummaryCandidate]:
    """Every indexed module the configuration says to summarize, long enough to need it."""
    rows = conn.execute(
        "SELECT path, module, sha256 FROM files WHERE parse_error = '' AND line_count >= ? ORDER BY path",
        (MIN_SUMMARY_LINES,),
    ).fetchall()
    return [SummaryCandidate(str(p), str(m), str(s)) for p, m, s in rows if config.is_summarized(str(p))]


def pending(conn: sqlite3.Connection, config: CodeIndexConfig) -> list[SummaryCandidate]:
    """Summarizable modules with no summary for their current content."""
    done = {str(r[0]) for r in conn.execute(f"SELECT sha256 FROM {SUMMARIES_ALIAS}.summaries")}
    return [candidate for candidate in summarizable(conn, config) if candidate.sha256 not in done]


def _clip(text: str, limit: int) -> tuple[str, bool]:
    return (text, False) if len(text) <= limit else (text[:limit], True)


def summary_request(conn: sqlite3.Connection, workspace: Path, candidate: SummaryCandidate) -> ChatRequest | None:
    """The request for one module, or None when the file changed since the index read it."""
    data = (workspace / candidate.path).read_bytes()
    if hashlib.sha256(data).hexdigest() != candidate.sha256:
        return None
    source, truncated = _clip(data.decode("utf-8-sig", errors="replace"), MAX_SOURCE_CHARS)
    outline_text, _ = _clip(outline(conn, candidate.path).render(), MAX_OUTLINE_CHARS)
    user = (
        f"Module: {candidate.module}\nFile: {candidate.path}\n\nOutline:\n{outline_text}\n\n"
        f"Source{' (truncated)' if truncated else ''}:\n{source}"
    )
    return ChatRequest(system=SUMMARY_SYSTEM_PROMPT, user=user, temperature=SUMMARY_TEMPERATURE,
                       max_tokens=SUMMARY_MAX_TOKENS)


def _store(conn: sqlite3.Connection, candidate: SummaryCandidate, text: str, model: str) -> None:
    summary, _ = _clip(_WHITESPACE.sub(" ", text).strip(), MAX_SUMMARY_CHARS)
    conn.execute("BEGIN IMMEDIATE")
    try:
        conn.execute(
            f"INSERT INTO {SUMMARIES_ALIAS}.summaries (sha256, summary, model, created_at) VALUES (?, ?, ?, ?) "
            f"ON CONFLICT(sha256) DO UPDATE SET summary = excluded.summary, model = excluded.model, "
            f"created_at = excluded.created_at",
            (candidate.sha256, summary, model, datetime.now(UTC).isoformat(timespec="seconds")),
        )
        for (file_id,) in conn.execute("SELECT id FROM files WHERE sha256 = ?", (candidate.sha256,)).fetchall():
            write_module_fts(conn, int(file_id))
        conn.execute("COMMIT")
    except BaseException:
        conn.execute("ROLLBACK")
        raise


def summarize(
    conn: sqlite3.Connection,
    workspace: Path,
    config: CodeIndexConfig,
    pool: LocalLlmPool,
    *,
    limit: int = DEFAULT_SUMMARY_LIMIT,
    workers: int = DEFAULT_SUMMARY_WORKERS,
    report: Callable[[str], None],
) -> SummaryRun:
    """Summarize up to ``limit`` pending modules (0 = all), storing each as it arrives.

    Raises LocalLlmUnavailable when no model server can answer; every summary stored
    before that stays stored.
    """
    todo = pending(conn, config)
    if limit:
        todo = todo[:limit]
    requests: list[tuple[SummaryCandidate, ChatRequest]] = []
    changed = 0
    for candidate in todo:
        request = summary_request(conn, workspace, candidate)
        if request is None:
            changed += 1
        else:
            requests.append((candidate, request))
    report(f"Summarizing {len(requests)} modules with {workers} parallel requests...")
    done = 0
    executor = ThreadPoolExecutor(max_workers=workers)
    try:
        futures: dict[Future[LocalLlmReply], SummaryCandidate] = {
            executor.submit(pool.chat, request): candidate for candidate, request in requests
        }
        for future in as_completed(futures):
            reply = future.result()
            _store(conn, futures[future], reply.text, reply.host.model)
            done += 1
            if done % 25 == 0:
                report(f"  {done}/{len(requests)} summarized")
    finally:
        executor.shutdown(wait=True, cancel_futures=True)
    return SummaryRun(done, changed, len(pending(conn, config)))
