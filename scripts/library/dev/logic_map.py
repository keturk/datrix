"""Logic-map markers: their comment syntax, their parser, and the markers.db writer.

Python source carries specially formatted comment markers (@canonical, @pattern,
@boundary, @invariant, @test-rule) declaring canonical implementations, approved
patterns, system boundaries, invariants and conformance rules. The code index
(``code_index``) extracts them with ``parse_markers`` on every refresh and rewrites
``.logic-map/markers.db`` with ``build_database`` whenever they changed, so that database
is exactly as fresh as the index. Agents query markers through the index's
``find_canonical`` (MCP tool, or ``code-index.ps1 -Canonical``).

The marker syntax is shown on ``parse_markers``: a marker-shaped line in this module
docstring would itself be read as a marker.
"""

from __future__ import annotations

import io
import re
import sqlite3
import tokenize
from dataclasses import dataclass, field
from pathlib import Path

# ---------------------------------------------------------------------------
# Marker kinds
# ---------------------------------------------------------------------------

MARKER_KINDS = frozenset({"canonical", "pattern", "boundary", "invariant", "test-rule"})

# ---------------------------------------------------------------------------
# Regex patterns
# ---------------------------------------------------------------------------

# Matches:  # @canonical(topic/subtopic): summary text
_MARKER_RE = re.compile(
    r"^#\s*@(" + "|".join(MARKER_KINDS) + r")"  # kind
    r"\(([^)]+)\)"                                # (topic)
    r":\s*(.+)$"                                  # : summary
)

# Matches sub-directives inside a marker block
_RULE_RE = re.compile(r"^#\s*@rule:\s*(.+)$")
_ANTI_PATTERN_RE = re.compile(r"^#\s*@anti-pattern:\s*(.+)$")
_SEE_RE = re.compile(r"^#\s*@see:\s*(.+)$")

# @test-rule sub-directives.
# @dim: key=value  (repeatable; open vocabulary — e.g. language=typescript, provider=aws, variant=msk-serverless)
_DIM_RE = re.compile(r"^#\s*@dim:\s*([A-Za-z0-9_.+-]+)\s*=\s*(.+)$")
# @behavior: target-specific expected outcome
_BEHAVIOR_RE = re.compile(r"^#\s*@behavior:\s*(.+)$")
# @differs: free-text note on how this rule diverges from other targets
_DIFFERS_RE = re.compile(r"^#\s*@differs:\s*(.+)$")

# Matches a plain comment continuation line (not a new marker or sub-directive)
_CONTINUATION_RE = re.compile(r"^#\s?(.*)$")

# Matches a def or class line immediately following the marker block
_SYMBOL_RE = re.compile(r"^(?:def|class|async\s+def)\s+(\w+)")

# Tokens whose text is string-literal content. Named, not imported, because the f-string
# and t-string middle tokens exist only on the Python versions that tokenize them.
_STRING_TOKEN_NAMES = frozenset({"STRING", "FSTRING_MIDDLE", "TSTRING_MIDDLE"})

# Tokens that carry no statement content: skipped when finding the module docstring.
_LAYOUT_TOKEN_NAMES = frozenset({"ENCODING", "COMMENT", "NL", "INDENT", "DEDENT"})

# Tokens that end the first statement, confirming a lone leading string is the docstring.
_STATEMENT_END_TOKEN_NAMES = frozenset({"NEWLINE", "ENDMARKER"})

# Directories to skip during file discovery
_SKIP_DIRS = frozenset({
    "node_modules", ".git", "__pycache__", ".venv", "venv",
    "build", "dist", ".tox", ".mypy_cache", ".pytest_cache",
    ".eggs", ".ruff_cache",
})


# ---------------------------------------------------------------------------
# Data model
# ---------------------------------------------------------------------------

@dataclass
class Marker:
    """A single extracted marker."""

    kind: str
    topic: str
    summary: str
    description: str
    file: str          # relative to datrix root
    line: int          # 1-based line of the @marker comment
    symbol: str        # function/class name if detectable
    signature: str     # full def/class line if detectable
    rules: list[str] = field(default_factory=list)
    anti_patterns: list[str] = field(default_factory=list)
    see_refs: list[str] = field(default_factory=list)
    behavior: str = ""                                              # test-rule: target-specific expected outcome
    dimensions: list[tuple[str, str]] = field(default_factory=list)  # test-rule: (key, value) pairs
    differs: list[str] = field(default_factory=list)               # test-rule: divergence notes


# ---------------------------------------------------------------------------
# Parser
# ---------------------------------------------------------------------------

@dataclass
class _BlockParts:
    """Accumulator for one marker's comment block (sub-directives + description)."""

    description_parts: list[str] = field(default_factory=list)
    rules: list[str] = field(default_factory=list)
    anti_patterns: list[str] = field(default_factory=list)
    see_refs: list[str] = field(default_factory=list)
    behavior_parts: list[str] = field(default_factory=list)
    dimensions: list[tuple[str, str]] = field(default_factory=list)
    differs: list[str] = field(default_factory=list)
    next_index: int = 0
    # The free-text directive list a plain continuation line extends: a ``@rule:``,
    # ``@anti-pattern:``, ``@behavior:`` or ``@differs:`` wraps onto the lines after it
    # until the next directive. None before any such directive (plain lines are then
    # description) and after ``@see:``/``@dim:``, whose values are single tokens.
    wrapping: list[str] | None = None


def _apply_directive(bline: str, parts: _BlockParts) -> None:
    """Route a single comment line to the matching block bucket.

    Specific directives are matched before the generic continuation fallback so a
    ``# @dim: ...`` line is never swallowed as description text. A plain line after a
    free-text directive continues that directive's text.

    Args:
        bline: Stripped comment line.
        parts: Accumulator mutated in place.
    """
    wrapping_directives = (
        (_RULE_RE, parts.rules),
        (_ANTI_PATTERN_RE, parts.anti_patterns),
        (_BEHAVIOR_RE, parts.behavior_parts),
        (_DIFFERS_RE, parts.differs),
    )
    for pattern, bucket in wrapping_directives:
        match = pattern.match(bline)
        if match:
            bucket.append(match.group(1).strip())
            parts.wrapping = bucket
            return

    see_m = _SEE_RE.match(bline)
    if see_m:
        parts.see_refs.append(see_m.group(1).strip())
        parts.wrapping = None
        return

    dim_m = _DIM_RE.match(bline)
    if dim_m:
        parts.dimensions.append((dim_m.group(1).strip(), dim_m.group(2).strip()))
        parts.wrapping = None
        return

    cont_m = _CONTINUATION_RE.match(bline)
    text = cont_m.group(1) if cont_m else bline.lstrip("# ")
    if parts.wrapping is not None and text.strip():
        parts.wrapping[-1] = f"{parts.wrapping[-1]} {text.strip()}"
        return
    parts.description_parts.append(text)


def _collect_block(lines: list[str], start: int, total: int) -> _BlockParts:
    """Collect the comment block beginning at ``start`` (line after the @marker).

    Args:
        lines: All file lines.
        start: Index of the first line after the marker line.
        total: Number of lines.

    Returns:
        Accumulated parts; ``next_index`` is the first line not consumed.
    """
    parts = _BlockParts()
    i = start
    while i < total:
        bline = lines[i].strip()
        if not bline.startswith("#") or _MARKER_RE.match(bline):
            break
        _apply_directive(bline, parts)
        i += 1
    parts.next_index = i
    return parts


def _detect_symbol(lines: list[str], start: int, total: int) -> tuple[str, str]:
    """Detect a def/class symbol on the first non-blank line at/after ``start``.

    Args:
        lines: All file lines.
        start: Index to begin scanning from.
        total: Number of lines.

    Returns:
        ``(symbol, signature)``, or ``("", "")`` if none is found.
    """
    j = start
    while j < total and not lines[j].strip():
        j += 1
    if j < total:
        sym_m = _SYMBOL_RE.match(lines[j].strip())
        if sym_m:
            return sym_m.group(1), lines[j].strip()
    return "", ""


def _string_literal_lines(lines: list[str]) -> frozenset[int]:
    """The 0-based indexes of the lines inside a string literal other than the module docstring.

    A marker is a comment or a line of the module docstring (where a module-level marker
    sits with the prose it summarises). A ``# @canonical(...)`` line in any other string --
    a function docstring showing the syntax, a test fixture -- is an example, not a
    marker. A file that stops tokenizing (an unterminated string or bracket) yields the
    literals found before that point and its remaining lines are read as source, so a
    file with a syntax error keeps its markers.

    Args:
        lines: File content split into lines (no trailing newlines).

    Returns:
        Indexes of every line such a string-literal token covers.
    """
    covered: set[int] = set()
    significant = 0
    first_string: range | None = None  # held back until we know whether it is the docstring
    tokens = tokenize.generate_tokens(io.StringIO("\n".join(lines) + "\n").readline)
    try:
        for token in tokens:
            name = tokenize.tok_name[token.type]
            if name in _LAYOUT_TOKEN_NAMES:
                continue
            significant += 1
            span = range(token.start[0] - 1, token.end[0])
            if significant == 1 and name == "STRING":
                first_string = span
                continue
            if first_string is not None and significant == 2 and name in _STATEMENT_END_TOKEN_NAMES:
                first_string = None  # a lone string statement first in the file: the docstring
                continue
            if first_string is not None:
                covered.update(first_string)  # the first string was part of a longer statement
                first_string = None
            if name in _STRING_TOKEN_NAMES:
                covered.update(span)
    except (tokenize.TokenError, SyntaxError):
        return frozenset(covered)
    return frozenset(covered)


def parse_markers(lines: list[str], relative_path: str) -> list[Marker]:
    """Parse all markers from the lines of a single file.

    Marker syntax::

        # @canonical(topic/subtopic): One-line summary
        # Extended description lines.
        # @rule: A constraint that must hold, which may wrap
        # onto the following comment lines
        # @anti-pattern: What NOT to do
        # @see: related-topic/subtopic

    Args:
        lines: File content split into lines (no trailing newlines).
        relative_path: Path relative to datrix root for storage.

    Returns:
        List of Marker objects found in the file: in comments and in the module
        docstring, never in any other string literal.
    """
    if not any(_MARKER_RE.match(line.strip()) for line in lines):
        return []
    in_string = _string_literal_lines(lines)
    markers: list[Marker] = []
    i = 0
    total = len(lines)

    while i < total:
        m = None if i in in_string else _MARKER_RE.match(lines[i].strip())
        if not m:
            i += 1
            continue

        kind = m.group(1)
        topic = m.group(2).strip()
        summary = m.group(3).strip()
        marker_line = i + 1  # 1-based

        block = _collect_block(lines, i + 1, total)
        i = block.next_index
        symbol, signature = _detect_symbol(lines, i, total)

        markers.append(Marker(
            kind=kind,
            topic=topic,
            summary=summary,
            description="\n".join(block.description_parts).strip(),
            file=relative_path,
            line=marker_line,
            symbol=symbol,
            signature=signature,
            rules=block.rules,
            anti_patterns=block.anti_patterns,
            see_refs=block.see_refs,
            behavior=" ".join(block.behavior_parts).strip(),
            dimensions=block.dimensions,
            differs=block.differs,
        ))

    return markers


# ---------------------------------------------------------------------------
# File discovery
# ---------------------------------------------------------------------------

def iter_python_files(scan_dir: Path) -> list[Path]:
    """Recursively find all .py files under scan_dir, skipping irrelevant directories.

    Args:
        scan_dir: Root directory to scan.

    Returns:
        Sorted list of .py file paths.
    """
    if not scan_dir.is_dir():
        return []
    import os
    out: list[Path] = []
    for dir_path, dirnames, filenames in os.walk(scan_dir, followlinks=False):
        dirnames[:] = [d for d in dirnames if d not in _SKIP_DIRS and not d.endswith(".egg-info")]
        for name in filenames:
            if name.endswith(".py"):
                out.append(Path(dir_path) / name)
    return sorted(out)


def resolve_scan_paths(
    datrix_root: Path,
    project_names: list[str],
    scan_all: bool,
    *,
    include_src: bool = True,
    include_tests: bool = True,
) -> list[tuple[str, Path]]:
    """Return (project_name, directory) pairs for src / tests.

    Args:
        datrix_root: Workspace root containing datrix-* projects.
        project_names: Explicit project names to scan.
        scan_all: If True, scan every datrix* project.
        include_src: Include src/ trees.
        include_tests: Include tests/ trees.

    Returns:
        List of (project_name, directory) pairs.

    Raises:
        FileNotFoundError: If a requested project does not exist.
    """
    if scan_all:
        pairs: list[tuple[str, Path]] = []
        for d in sorted(datrix_root.iterdir()):
            if not d.is_dir() or not d.name.startswith("datrix"):
                continue
            if include_src and (d / "src").is_dir():
                pairs.append((d.name, d / "src"))
            if include_tests:
                tests_dir = d / "tests"
                if tests_dir.is_dir():
                    pairs.append((d.name, tests_dir))
        return pairs

    pairs = []
    for name in project_names:
        clean = name.rstrip("/\\")
        project_dir = datrix_root / clean
        if not project_dir.is_dir():
            available = sorted(
                d.name for d in datrix_root.iterdir() if d.is_dir() and d.name.startswith("datrix")
            )
            raise FileNotFoundError(
                f"Project '{clean}' not found. Available: {available}"
            )
        if include_src:
            src_dir = project_dir / "src"
            if src_dir.is_dir():
                pairs.append((clean, src_dir))
        if include_tests:
            tests_dir = project_dir / "tests"
            if tests_dir.is_dir():
                pairs.append((clean, tests_dir))
    return pairs


# ---------------------------------------------------------------------------
# SQLite database
# ---------------------------------------------------------------------------

_SCHEMA = """\
CREATE TABLE IF NOT EXISTS markers (
    id            INTEGER PRIMARY KEY,
    kind          TEXT NOT NULL,
    topic         TEXT NOT NULL,
    summary       TEXT NOT NULL,
    description   TEXT,
    file          TEXT NOT NULL,
    line          INTEGER NOT NULL,
    symbol        TEXT,
    signature     TEXT,
    behavior      TEXT
);

CREATE TABLE IF NOT EXISTS rules (
    id         INTEGER PRIMARY KEY,
    marker_id  INTEGER NOT NULL REFERENCES markers(id) ON DELETE CASCADE,
    text       TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS anti_patterns (
    id         INTEGER PRIMARY KEY,
    marker_id  INTEGER NOT NULL REFERENCES markers(id) ON DELETE CASCADE,
    text       TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS see_refs (
    id            INTEGER PRIMARY KEY,
    from_marker   INTEGER NOT NULL REFERENCES markers(id) ON DELETE CASCADE,
    target_topic  TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS dimensions (
    id         INTEGER PRIMARY KEY,
    marker_id  INTEGER NOT NULL REFERENCES markers(id) ON DELETE CASCADE,
    key        TEXT NOT NULL,
    value      TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS differs (
    id         INTEGER PRIMARY KEY,
    marker_id  INTEGER NOT NULL REFERENCES markers(id) ON DELETE CASCADE,
    text       TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_markers_topic ON markers(topic);
CREATE INDEX IF NOT EXISTS idx_markers_kind ON markers(kind);
CREATE INDEX IF NOT EXISTS idx_markers_file ON markers(file);
CREATE INDEX IF NOT EXISTS idx_dimensions_kv ON dimensions(key, value);
CREATE INDEX IF NOT EXISTS idx_dimensions_marker ON dimensions(marker_id);
"""


def build_database(db_path: Path, markers: list[Marker]) -> None:
    """Create (or recreate) the SQLite database from extracted markers.

    The database is rebuilt from scratch on each invocation — all existing data
    is dropped and replaced.

    Args:
        db_path: Path to the .db file.
        markers: All extracted markers to insert.
    """
    db_path.parent.mkdir(parents=True, exist_ok=True)

    conn = sqlite3.connect(str(db_path))
    try:
        cur = conn.cursor()
        # Drop existing tables for a clean rebuild
        cur.execute("DROP TABLE IF EXISTS dependencies")  # legacy table, removed
        cur.execute("DROP TABLE IF EXISTS differs")
        cur.execute("DROP TABLE IF EXISTS dimensions")
        cur.execute("DROP TABLE IF EXISTS see_refs")
        cur.execute("DROP TABLE IF EXISTS anti_patterns")
        cur.execute("DROP TABLE IF EXISTS rules")
        cur.execute("DROP TABLE IF EXISTS markers")
        cur.executescript(_SCHEMA)

        for marker in markers:
            cur.execute(
                "INSERT INTO markers (kind, topic, summary, description, file, line, symbol, signature, behavior) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    marker.kind,
                    marker.topic,
                    marker.summary,
                    marker.description,
                    marker.file,
                    marker.line,
                    marker.symbol,
                    marker.signature,
                    marker.behavior,
                ),
            )
            marker_id = cur.lastrowid

            for rule_text in marker.rules:
                cur.execute(
                    "INSERT INTO rules (marker_id, text) VALUES (?, ?)",
                    (marker_id, rule_text),
                )

            for ap_text in marker.anti_patterns:
                cur.execute(
                    "INSERT INTO anti_patterns (marker_id, text) VALUES (?, ?)",
                    (marker_id, ap_text),
                )

            for see_topic in marker.see_refs:
                cur.execute(
                    "INSERT INTO see_refs (from_marker, target_topic) VALUES (?, ?)",
                    (marker_id, see_topic),
                )

            for dim_key, dim_value in marker.dimensions:
                cur.execute(
                    "INSERT INTO dimensions (marker_id, key, value) VALUES (?, ?, ?)",
                    (marker_id, dim_key, dim_value),
                )

            for differs_text in marker.differs:
                cur.execute(
                    "INSERT INTO differs (marker_id, text) VALUES (?, ?)",
                    (marker_id, differs_text),
                )

        conn.commit()
    finally:
        conn.close()
