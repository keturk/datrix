"""Questions the index answers, each as structured results plus a compact text rendering.

References are resolved by name through each file's imports, not by type inference. A
module-level function or class is followed through every ``import`` that can reach it,
re-exports included, so its uses are exact up to aliasing tricks. A method or attribute
is matched by name on every ``.name`` access, because the receiver's type is unknown
without running a type checker; those results say so.
"""

from __future__ import annotations

import json
import re
import sqlite3
from dataclasses import dataclass, field
from pathlib import PurePosixPath

from datrix_scripts.code_index.extract import (
    REF_ATTR,
    REF_ATTR_CALL,
    REF_CALL,
    REF_NAME,
    SYMBOL_ATTRIBUTE,
    SYMBOL_CLASS,
    SYMBOL_FUNCTION,
    SYMBOL_METHOD,
    SYMBOL_VARIABLE,
)
from datrix_scripts.code_index.store import (
    FTS_MARKER,
    FTS_SYMBOL,
    META_LAST_REFRESH,
    SUMMARIES_ALIAS,
    identifier_words,
    read_meta,
)

SYMBOL_KINDS = (SYMBOL_CLASS, SYMBOL_FUNCTION, SYMBOL_METHOD, SYMBOL_VARIABLE, SYMBOL_ATTRIBUTE)
REF_IMPORT = "import"

DEFAULT_SYMBOL_LIMIT = 30
DEFAULT_REFERENCE_FILE_LIMIT = 100
DEFAULT_SEARCH_LIMIT = 25
DEFAULT_CANONICAL_LIMIT = 15
SUGGESTION_LIMIT = 10

# Marker kinds shown by default. Test-rule markers outnumber every other kind together
# and describe expected test behaviour, not implementations, so they are opt-in.
TEST_RULE_KIND = "test-rule"

# Words that carry no meaning in a code search and would match nearly every docstring.
_STOPWORDS = frozenset(
    "a an and are as at be by for from how in is it of on or that the this to what where which who why with"
    .split()
)
_WORD = re.compile(r"[A-Za-z0-9]+")

# Kind order for listing definitions: types first, then callables, then data.
_KIND_ORDER = f"CASE s.kind WHEN '{SYMBOL_CLASS}' THEN 0 WHEN '{SYMBOL_FUNCTION}' THEN 1 " \
              f"WHEN '{SYMBOL_METHOD}' THEN 2 WHEN '{SYMBOL_VARIABLE}' THEN 3 ELSE 4 END"
# Production code before tests.
_TESTS_LAST = "CASE WHEN f.path LIKE '%/tests/%' THEN 1 ELSE 0 END"

_SYMBOL_COLUMNS = "f.path, s.line, s.end_line, s.kind, f.module, s.qualname, s.signature, s.doc"


class QueryError(ValueError):
    """The query cannot be answered as asked; the message says what to pass instead."""


@dataclass(frozen=True)
class SymbolHit:
    path: str
    line: int
    end_line: int
    kind: str
    module: str
    qualname: str
    signature: str
    doc: str

    @property
    def name(self) -> str:
        return self.qualname.rsplit(".", 1)[-1]

    @property
    def is_top_level(self) -> bool:
        return "." not in self.qualname

    @property
    def dotted(self) -> str:
        return f"{self.module}.{self.qualname}"

    def render(self) -> str:
        doc = f"\n    {self.doc}" if self.doc else ""
        return f"{self.path}:{self.line}  {self.signature}  [{self.dotted}]{doc}"


@dataclass(frozen=True)
class SymbolResult:
    query: str
    hits: list[SymbolHit]
    # Near misses offered when nothing matched exactly.
    suggestions: list[str] = field(default_factory=list)

    def render(self) -> str:
        if self.hits:
            return "\n".join(hit.render() for hit in self.hits)
        tail = f" Similar names: {', '.join(self.suggestions)}." if self.suggestions else ""
        return f"No definition named '{self.query}' in the index.{tail}"


@dataclass(frozen=True)
class ReferenceSite:
    line: int
    kind: str


@dataclass(frozen=True)
class ReferenceResult:
    target: str
    definitions: list[SymbolHit]
    sites: dict[str, list[ReferenceSite]]
    resolution: str
    file_limit: int

    def render(self) -> str:
        lines = [f"References to {self.target}: {self.resolution}"]
        lines.extend(f"  defined at {d.path}:{d.line}  [{d.dotted}]" for d in self.definitions)
        total = sum(len(s) for s in self.sites.values())
        lines.append(f"{total} sites in {len(self.sites)} files.")
        for path in list(self.sites)[: self.file_limit]:
            joined = ", ".join(f"{s.line} {s.kind}" for s in self.sites[path])
            lines.append(f"{path}: {joined}")
        if len(self.sites) > self.file_limit:
            lines.append(f"... {len(self.sites) - self.file_limit} more files (raise the limit to see them).")
        return "\n".join(lines)


@dataclass(frozen=True)
class OutlineResult:
    path: str
    module: str
    line_count: int
    module_doc: str
    summary: str
    parse_error: str
    symbols: list[SymbolHit]

    def render(self) -> str:
        lines = [f"{self.path}  [{self.module}]  {self.line_count} lines"]
        if self.parse_error:
            lines.append(f"Not parsed: {self.parse_error}")
        if self.module_doc:
            lines.append(f"Doc: {self.module_doc}")
        if self.summary:
            lines.append(f"Summary: {self.summary}")
        for symbol in self.symbols:
            indent = "  " * symbol.qualname.count(".")
            span = f"{symbol.line}-{symbol.end_line}" if symbol.end_line > symbol.line else f"{symbol.line}"
            doc = f"  -- {symbol.doc}" if symbol.doc else ""
            lines.append(f"{indent}L{span} {symbol.signature}{doc}")
        return "\n".join(lines)


@dataclass(frozen=True)
class SearchHit:
    kind: str
    path: str
    line: int
    ref: str
    detail: str

    def render(self) -> str:
        detail = f"  -- {self.detail}" if self.detail else ""
        return f"{self.path}:{self.line}  {self.kind} {self.ref}{detail}"


@dataclass(frozen=True)
class SearchResult:
    query: str
    hits: list[SearchHit]

    def render(self) -> str:
        if not self.hits:
            return f"Nothing in the index matches '{self.query}'."
        return "\n".join(hit.render() for hit in self.hits)


@dataclass(frozen=True)
class MarkerHit:
    kind: str
    topic: str
    path: str
    line: int
    symbol: str
    summary: str
    rules: list[str]
    anti_patterns: list[str]
    see_refs: list[str]

    def render(self) -> str:
        symbol = f"  [{self.symbol}]" if self.symbol else ""
        lines = [f"@{self.kind}({self.topic})  {self.path}:{self.line}{symbol}", f"  {self.summary}"]
        lines.extend(f"  rule: {rule}" for rule in self.rules)
        lines.extend(f"  anti-pattern: {anti}" for anti in self.anti_patterns)
        if self.see_refs:
            lines.append(f"  see: {', '.join(self.see_refs)}")
        return "\n".join(lines)


@dataclass(frozen=True)
class CanonicalResult:
    query: str
    hits: list[MarkerHit]
    kinds: tuple[str, ...]

    def render(self) -> str:
        if not self.hits:
            return (
                f"No {'/'.join(self.kinds)} marker matches '{self.query}'. No marker means no declared "
                f"canonical implementation, not that none exists: search the code (search, find_symbol) too."
            )
        return "\n".join(hit.render() for hit in self.hits)


def _symbol_hits(rows: list[tuple[object, ...]]) -> list[SymbolHit]:
    return [SymbolHit(str(r[0]), int(str(r[1])), int(str(r[2])), str(r[3]), str(r[4]), str(r[5]), str(r[6]),
                      str(r[7])) for r in rows]


def _kind_clause(kind: str | None) -> tuple[str, list[object]]:
    if kind is None:
        return "", []
    if kind not in SYMBOL_KINDS:
        raise QueryError(f"Unknown symbol kind '{kind}'. Valid kinds: {', '.join(SYMBOL_KINDS)}.")
    return " AND s.kind = ?", [kind]


def find_symbol(conn: sqlite3.Connection, name: str, kind: str | None = None,
                limit: int = DEFAULT_SYMBOL_LIMIT) -> SymbolResult:
    """Definitions of ``name``: a bare name, a glob (``*Resolver``), ``Class.method``, or a dotted path."""
    query = name.strip()
    if not query:
        raise QueryError("Pass a symbol name: a bare name, a glob such as '*Resolver', 'Class.method', "
                         "or a dotted path such as 'datrix_common.utils.text.to_snake_case'.")
    kind_sql, kind_args = _kind_clause(kind)
    last = query.rsplit(".", 1)[-1]
    if "*" in query or "?" in query:
        where, args = "s.name GLOB ?", [last]
    elif "." in query:
        where = "s.name = ? AND (f.module || '.' || s.qualname = ? OR s.qualname = ? " \
                "OR f.module || '.' || s.qualname LIKE ? ESCAPE '\\')"
        args = [last, query, query, "%." + query.replace("_", "\\_")]
    else:
        where, args = "s.name = ?", [query]
    rows = conn.execute(
        f"SELECT {_SYMBOL_COLUMNS} FROM symbols s JOIN files f ON f.id = s.file_id "
        f"WHERE {where}{kind_sql} ORDER BY {_KIND_ORDER}, {_TESTS_LAST}, f.path, s.line LIMIT ?",
        [*args, *kind_args, limit],
    ).fetchall()
    hits = _symbol_hits(rows)
    suggestions: list[str] = []
    if not hits:
        suggestions = [str(r[0]) for r in conn.execute(
            "SELECT DISTINCT name FROM symbols WHERE name LIKE ? ORDER BY length(name) LIMIT ?",
            (f"%{last}%", SUGGESTION_LIMIT),
        ).fetchall()]
    return SymbolResult(query, hits, suggestions)


def _add_sites(sites: dict[str, list[ReferenceSite]], rows: list[tuple[object, ...]]) -> None:
    """Merge ``(path, comma-separated lines, kind)`` rows into ``sites``."""
    for path, lines, kind in rows:
        bucket = sites.setdefault(str(path), [])
        bucket.extend(ReferenceSite(int(line), str(kind)) for line in str(lines).split(",") if line)


def _exporting_modules(conn: sqlite3.Connection, module: str, name: str) -> set[str]:
    """Every module ``name`` can be imported from: its own, and each module that imports it."""
    exporters = {module}
    frontier = [module]
    while frontier:
        current = frontier.pop()
        for (importer,) in conn.execute(
            "SELECT DISTINCT f.module FROM imports i JOIN files f ON f.id = i.file_id "
            "WHERE i.module = ? AND i.name = ?", (current, name),
        ).fetchall():
            if importer not in exporters:
                exporters.add(str(importer))
                frontier.append(str(importer))
    return exporters


def _placeholders(values: set[str]) -> str:
    return ",".join("?" * len(values))


def _resolved_sites(conn: sqlite3.Connection, definition: SymbolHit) -> dict[str, list[ReferenceSite]]:
    """Uses of a module-level definition, followed through every import that can reach it."""
    name = definition.name
    exporters = sorted(_exporting_modules(conn, definition.module, name))
    marks = _placeholders(set(exporters))
    sites: dict[str, list[ReferenceSite]] = {}
    # ``from exporter import name [as alias]``: the alias's bare uses in that file.
    importers = conn.execute(
        f"SELECT i.file_id, f.path, i.line, i.alias FROM imports i JOIN files f ON f.id = i.file_id "
        f"WHERE i.name = ? AND i.module IN ({marks})", [name, *exporters],
    ).fetchall()
    for file_id, path, line, alias in importers:
        sites.setdefault(str(path), []).append(ReferenceSite(int(line), REF_IMPORT))
        _add_sites(sites, conn.execute(
            "SELECT ?, lines, kind FROM refs WHERE file_id = ? AND name = ? AND kind IN (?, ?)",
            (path, file_id, alias or name, REF_NAME, REF_CALL),
        ).fetchall())
    # ``import exporter`` / ``from package import exporter``: ``exporter.name`` in that file.
    module_importers = conn.execute(
        f"SELECT DISTINCT i.file_id FROM imports i WHERE (i.name = '' AND i.module IN ({marks})) "
        f"OR (i.name != '' AND i.module || '.' || i.name IN ({marks}))", [*exporters, *exporters],
    ).fetchall()
    for (file_id,) in module_importers:
        _add_sites(sites, conn.execute(
            "SELECT f.path, r.lines, r.kind FROM refs r JOIN files f ON f.id = r.file_id "
            "WHERE r.file_id = ? AND r.name = ? AND r.kind IN (?, ?)", (file_id, name, REF_ATTR, REF_ATTR_CALL),
        ).fetchall())
    # The defining file itself uses the name bare.
    _add_sites(sites, conn.execute(
        "SELECT f.path, r.lines, r.kind FROM refs r JOIN files f ON f.id = r.file_id "
        "WHERE f.path = ? AND r.name = ? AND r.kind IN (?, ?)", (definition.path, name, REF_NAME, REF_CALL),
    ).fetchall())
    return sites


def _name_sites(conn: sqlite3.Connection, name: str, kinds: tuple[str, ...]) -> dict[str, list[ReferenceSite]]:
    sites: dict[str, list[ReferenceSite]] = {}
    _add_sites(sites, conn.execute(
        f"SELECT f.path, r.lines, r.kind FROM refs r JOIN files f ON f.id = r.file_id "
        f"WHERE r.name = ? AND r.kind IN ({','.join('?' * len(kinds))})", (name, *kinds),
    ).fetchall())
    return sites


def _ordered(sites: dict[str, list[ReferenceSite]]) -> dict[str, list[ReferenceSite]]:
    """Files with production code first, then tests; sites in line order, each once."""
    def rank(path: str) -> tuple[int, str]:
        return (1 if "/tests/" in path else 0, path)
    return {
        path: sorted(set(sites[path]), key=lambda s: (s.line, s.kind))
        for path in sorted(sites, key=rank)
    }


def find_references(conn: sqlite3.Connection, target: str,
                    file_limit: int = DEFAULT_REFERENCE_FILE_LIMIT) -> ReferenceResult:
    """Where ``target`` (a bare name, ``Class.method``, or a dotted path) is used."""
    if "*" in target or "?" in target:
        raise QueryError(f"'{target}' is a pattern; references are found for one name. Find the definition "
                         f"with find_symbol first, then pass its dotted path.")
    definitions = find_symbol(conn, target, limit=DEFAULT_SYMBOL_LIMIT).hits
    name = target.strip().rsplit(".", 1)[-1]
    if len(definitions) == 1 and definitions[0].is_top_level:
        return ReferenceResult(target, definitions, _ordered(_resolved_sites(conn, definitions[0])),
                               "resolved through imports (aliases and re-exports followed).", file_limit)
    if len(definitions) == 1:
        sites = _name_sites(conn, name, (REF_ATTR, REF_ATTR_CALL))
        return ReferenceResult(target, definitions, _ordered(sites),
                               f"every '.{name}' access -- receiver types are not checked, so other "
                               f"classes' members named '{name}' are included.", file_limit)
    everything = (REF_NAME, REF_CALL, REF_ATTR, REF_ATTR_CALL)
    if definitions:
        resolution = (f"{len(definitions)} definitions share this name, so every use of the name is listed; "
                      f"pass a dotted path from the list to resolve one.")
    else:
        resolution = "no definition in the index (builtin, third-party, or dynamic); every use of the name."
    return ReferenceResult(target, definitions, _ordered(_name_sites(conn, name, everything)), resolution,
                           file_limit)


def _resolve_file(conn: sqlite3.Connection, path_or_module: str) -> tuple[object, ...]:
    wanted = path_or_module.strip().replace("\\", "/")
    columns = "id, path, module, line_count, module_doc, parse_error, sha256"
    row = conn.execute(f"SELECT {columns} FROM files WHERE path = ? OR module = ? ORDER BY path = ? DESC LIMIT 1",
                       (wanted, wanted, wanted)).fetchone()
    if row:
        return tuple(row)
    suffix = "/" + str(PurePosixPath(wanted)).lstrip("/")
    matches = conn.execute(f"SELECT {columns} FROM files WHERE '/' || path LIKE ? ESCAPE '\\' LIMIT ?",
                           ("%" + suffix.replace("_", "\\_"), SUGGESTION_LIMIT + 1)).fetchall()
    if len(matches) == 1:
        return tuple(matches[0])
    if not matches:
        raise QueryError(f"No indexed file matches '{path_or_module}'. Pass a workspace-relative path "
                         f"(datrix-common/src/...), a unique path suffix, or a dotted module name.")
    candidates = ", ".join(str(m[1]) for m in matches[:SUGGESTION_LIMIT])
    raise QueryError(f"'{path_or_module}' matches several files: {candidates}. Pass more of the path.")


def outline(conn: sqlite3.Connection, path_or_module: str) -> OutlineResult:
    """A file's definitions with signatures and first docstring lines, in source order."""
    file_id, path, module, line_count, module_doc, parse_error, sha256 = _resolve_file(conn, path_or_module)
    rows = conn.execute(
        f"SELECT {_SYMBOL_COLUMNS} FROM symbols s JOIN files f ON f.id = s.file_id WHERE s.file_id = ? "
        f"ORDER BY s.line", (file_id,),
    ).fetchall()
    summary_row = conn.execute(f"SELECT summary FROM {SUMMARIES_ALIAS}.summaries WHERE sha256 = ?",
                               (sha256,)).fetchone()
    return OutlineResult(str(path), str(module), int(str(line_count)), str(module_doc),
                         str(summary_row[0]) if summary_row else "", str(parse_error), _symbol_hits(rows))


def fts_expression(text: str) -> str:
    """An FTS5 query matching any meaningful word of ``text`` (identifiers split into words)."""
    words = {w.lower() for w in _WORD.findall(identifier_words(text.replace(".", " ")))} - _STOPWORDS
    if not words:
        raise QueryError(f"'{text}' has no searchable words. Describe the code in words or name an identifier.")
    return " OR ".join(f'"{w}"' for w in sorted(words))


def search(conn: sqlite3.Connection, text: str, limit: int = DEFAULT_SEARCH_LIMIT) -> SearchResult:
    """Ranked full-text search over names, signatures, docstrings, module summaries and markers."""
    rows = conn.execute(
        "SELECT fts.kind, f.path, fts.line, fts.ref, fts.body FROM fts JOIN files f ON f.id = fts.file_id "
        "WHERE fts MATCH ? ORDER BY bm25(fts, 4.0, 1.0) LIMIT ?", (fts_expression(text), limit),
    ).fetchall()
    hits = []
    for kind, path, line, ref, body in rows:
        detail_lines = [ln for ln in str(body).splitlines() if ln.strip()]
        detail = detail_lines[-1] if kind == FTS_SYMBOL and len(detail_lines) > 1 else (
            detail_lines[0] if detail_lines else "")
        hits.append(SearchHit(str(kind), str(path), int(str(line)), str(ref), detail[:200]))
    return SearchResult(text, hits)


def topic_matches(topic: str, text: str) -> bool:
    """Whether ``text`` names ``topic`` or a whole segment of it.

    ``snake`` matches ``text/to-snake``; ``case`` does not match ``api-test-cases``. Text
    containing ``/`` is a topic path and matches anywhere inside the topic.
    """
    wanted = text.strip().lower()
    if "/" in wanted:
        return wanted in topic.lower()
    return re.search(rf"(^|[/\-_.]){re.escape(wanted)}($|[/\-_.])", topic.lower()) is not None


def _marker_hits(conn: sqlite3.Connection, where: str, args: list[object], limit: int | None) -> list[MarkerHit]:
    limit_sql = " LIMIT ?" if limit is not None else ""
    rows = conn.execute(
        f"SELECT m.payload FROM markers m JOIN files f ON f.id = m.file_id WHERE {where} "
        f"ORDER BY m.topic, f.path, m.line{limit_sql}", [*args, *([limit] if limit is not None else [])],
    ).fetchall()
    hits = []
    for (payload,) in rows:
        m = json.loads(payload)
        hits.append(MarkerHit(m["kind"], m["topic"], m["file"], m["line"], m["symbol"], m["summary"],
                              m["rules"], m["anti_patterns"], m["see_refs"]))
    return hits


def find_canonical(conn: sqlite3.Connection, text: str, include_test_rules: bool = False,
                   limit: int = DEFAULT_CANONICAL_LIMIT) -> CanonicalResult:
    """Logic-map markers whose topic contains ``text``, then markers whose text matches it."""
    kinds = tuple(str(r[0]) for r in conn.execute("SELECT DISTINCT kind FROM markers ORDER BY kind").fetchall()
                  if include_test_rules or r[0] != TEST_RULE_KIND)
    if not kinds:
        return CanonicalResult(text, [], kinds)
    kind_marks = ",".join("?" * len(kinds))
    by_topic = [
        hit for hit in _marker_hits(conn, f"m.kind IN ({kind_marks}) AND m.topic LIKE ?",
                                    [*kinds, f"%{text.strip()}%"], None)
        if topic_matches(hit.topic, text)
    ][:limit]
    seen = {(h.path, h.line) for h in by_topic}
    by_text: list[MarkerHit] = []
    if len(by_topic) < limit:
        matched = conn.execute(
            "SELECT fts.file_id, fts.line FROM fts WHERE fts MATCH ? AND fts.kind = ? "
            "ORDER BY bm25(fts, 4.0, 1.0) LIMIT ?", (fts_expression(text), FTS_MARKER, limit * 4),
        ).fetchall()
        for file_id, line in matched:
            for hit in _marker_hits(conn, f"m.kind IN ({kind_marks}) AND m.file_id = ? AND m.line = ?",
                                    [*kinds, file_id, line], 1):
                if (hit.path, hit.line) not in seen and len(by_topic) + len(by_text) < limit:
                    seen.add((hit.path, hit.line))
                    by_text.append(hit)
    return CanonicalResult(text, by_topic + by_text, kinds)


def marker_topics(conn: sqlite3.Connection, kind: str) -> set[str]:
    """Every topic the index holds a marker of ``kind`` for."""
    return {str(r[0]) for r in conn.execute("SELECT DISTINCT topic FROM markers WHERE kind = ?", (kind,))}


def all_marker_topics(conn: sqlite3.Connection) -> set[str]:
    """Every topic the index holds a marker of any kind for: the targets an ``@see`` may name."""
    return {str(r[0]) for r in conn.execute("SELECT DISTINCT topic FROM markers")}


@dataclass(frozen=True)
class StatusResult:
    last_refresh: str
    files: int
    symbols: int
    markers: dict[str, int]
    summarizable: int
    summarized: int
    parse_errors: list[str]

    def render(self) -> str:
        marker_text = ", ".join(f"{kind} {count}" for kind, count in sorted(self.markers.items())) or "none"
        lines = [
            f"Last refresh: {self.last_refresh}",
            f"Files: {self.files}; definitions: {self.symbols}",
            f"Logic-map markers: {marker_text}",
            f"Module summaries: {self.summarized} of {self.summarizable} summarizable modules",
            f"Syntax errors: {len(self.parse_errors)}",
        ]
        lines.extend(f"  {entry}" for entry in self.parse_errors)
        return "\n".join(lines)


def status(conn: sqlite3.Connection, summarizable_paths: set[str]) -> StatusResult:
    """What the index holds and how complete its summaries are."""
    files = conn.execute("SELECT path, sha256 FROM files").fetchall()
    summarized_hashes = {str(r[0]) for r in conn.execute(f"SELECT sha256 FROM {SUMMARIES_ALIAS}.summaries")}
    summarized = sum(1 for path, sha in files if path in summarizable_paths and sha in summarized_hashes)
    markers = {str(k): int(n) for k, n in conn.execute("SELECT kind, COUNT(*) FROM markers GROUP BY kind")}
    errors = [f"{p}: {e}" for p, e in conn.execute(
        "SELECT path, parse_error FROM files WHERE parse_error != '' ORDER BY path")]
    return StatusResult(
        last_refresh=read_meta(conn, META_LAST_REFRESH) or "never",
        files=len(files),
        symbols=int(conn.execute("SELECT COUNT(*) FROM symbols").fetchone()[0]),
        markers=markers,
        summarizable=len(summarizable_paths),
        summarized=summarized,
        parse_errors=errors,
    )
