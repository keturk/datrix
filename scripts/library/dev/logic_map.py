#!/usr/bin/env python3
"""Extract logic markers from Python source into a SQLite database.

Scans Python files for specially formatted comment markers (@canonical, @pattern,
@boundary, @invariant) and stores them in a queryable SQLite database.
This enables AI agents to look up canonical implementations, approved patterns,
system boundaries, and invariants before writing code.

Marker syntax::

    # @canonical(topic/subtopic): One-line summary
    # Extended description lines.
    # @rule: A constraint that must hold
    # @anti-pattern: What NOT to do
    # @see: related-topic/subtopic

Supported marker kinds: canonical, pattern, boundary, invariant.

Usage:
    python scripts/library/dev/logic_map.py --all
    python scripts/library/dev/logic_map.py datrix-common --src
    python scripts/library/dev/logic_map.py datrix-common datrix-language --tests

    Or use the PowerShell wrapper:
        .\\scripts\\dev\\logic-map.ps1 -All
        .\\scripts\\dev\\logic-map.ps1 datrix-common -Src
"""

from __future__ import annotations

import argparse
import io
import re
import sqlite3
import sys
from dataclasses import dataclass, field
from pathlib import Path

if sys.platform == "win32" and __name__ == "__main__":
    if hasattr(sys.stdout, "buffer"):
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    if hasattr(sys.stderr, "buffer"):
        sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

_library_dir = Path(__file__).resolve().parent.parent
if _library_dir.exists() and str(_library_dir) not in sys.path:
    sys.path.insert(0, str(_library_dir))

from shared.venv import get_datrix_root  # noqa: E402

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


def _apply_directive(bline: str, parts: _BlockParts) -> None:
    """Route a single comment line to the matching block bucket.

    Specific directives are matched before the generic continuation fallback so a
    ``# @dim: ...`` line is never swallowed as description text.

    Args:
        bline: Stripped comment line.
        parts: Accumulator mutated in place.
    """
    rule_m = _RULE_RE.match(bline)
    if rule_m:
        parts.rules.append(rule_m.group(1).strip())
        return

    ap_m = _ANTI_PATTERN_RE.match(bline)
    if ap_m:
        parts.anti_patterns.append(ap_m.group(1).strip())
        return

    behavior_m = _BEHAVIOR_RE.match(bline)
    if behavior_m:
        parts.behavior_parts.append(behavior_m.group(1).strip())
        return

    differs_m = _DIFFERS_RE.match(bline)
    if differs_m:
        parts.differs.append(differs_m.group(1).strip())
        return

    see_m = _SEE_RE.match(bline)
    if see_m:
        parts.see_refs.append(see_m.group(1).strip())
        return

    dim_m = _DIM_RE.match(bline)
    if dim_m:
        parts.dimensions.append((dim_m.group(1).strip(), dim_m.group(2).strip()))
        return

    cont_m = _CONTINUATION_RE.match(bline)
    if cont_m:
        parts.description_parts.append(cont_m.group(1))
        return

    # Unrecognized comment line — treat as description
    parts.description_parts.append(bline.lstrip("# "))


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


def parse_markers(lines: list[str], relative_path: str) -> list[Marker]:
    """Parse all markers from the lines of a single file.

    Args:
        lines: File content split into lines (no trailing newlines).
        relative_path: Path relative to datrix root for storage.

    Returns:
        List of Marker objects found in the file.
    """
    markers: list[Marker] = []
    i = 0
    total = len(lines)

    while i < total:
        m = _MARKER_RE.match(lines[i].strip())
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


# ---------------------------------------------------------------------------
# Reporting
# ---------------------------------------------------------------------------

def print_summary(markers: list[Marker], db_path: Path, scan_pairs: list[tuple[str, Path]]) -> None:
    """Print a summary of the extraction to stdout.

    Args:
        markers: All extracted markers.
        db_path: Path to the generated database.
        scan_pairs: The (project, directory) pairs that were scanned.
    """
    by_kind: dict[str, int] = {}
    for m in markers:
        by_kind[m.kind] = by_kind.get(m.kind, 0) + 1

    unique_projects = sorted({name for name, _ in scan_pairs})
    total_rules = sum(len(m.rules) for m in markers)
    total_anti_patterns = sum(len(m.anti_patterns) for m in markers)
    total_dimensions = sum(len(m.dimensions) for m in markers)
    unique_topics = sorted({m.topic for m in markers})

    print()
    print("=" * 60)
    print("LOGIC MAP SUMMARY")
    print("=" * 60)
    print(f"  Database:        {db_path}")
    print(f"  Projects:        {', '.join(unique_projects)}")
    print(f"  Total markers:   {len(markers)}")
    for kind in sorted(by_kind):
        print(f"    {kind}: {by_kind[kind]}")
    print(f"  Rules:           {total_rules}")
    print(f"  Anti-patterns:   {total_anti_patterns}")
    print(f"  Dimensions:      {total_dimensions}")
    print(f"  Unique topics:   {len(unique_topics)}")
    if unique_topics:
        for topic in unique_topics:
            print(f"    - {topic}")
    print()


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> int:
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Extract logic markers from Python source into a SQLite database.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument(
        "projects",
        nargs="*",
        help="Project names (e.g. datrix-common datrix-language)",
    )
    parser.add_argument(
        "--all", "-a",
        action="store_true",
        dest="scan_all",
        help="Scan every datrix* project under the monorepo root",
    )
    parser.add_argument(
        "--src",
        action="store_true",
        help="Scan only each project's src/ tree (combine with --tests to scan both)",
    )
    parser.add_argument(
        "--tests",
        action="store_true",
        help="Scan only each project's tests/ tree (combine with --src to scan both)",
    )
    parser.add_argument(
        "--debug", "-d",
        action="store_true",
        help="Enable debug output",
    )
    args = parser.parse_args()

    if not args.projects and not args.scan_all:
        parser.print_help()
        print("\nProvide project names or use --all.", file=sys.stderr)
        return 1

    # Resolve scope flags
    if args.src and not args.tests:
        include_src, include_tests = True, False
    elif args.tests and not args.src:
        include_src, include_tests = False, True
    else:
        include_src, include_tests = True, True

    try:
        datrix_root = get_datrix_root()
    except FileNotFoundError:
        print("ERROR: Could not find Datrix root directory", file=sys.stderr)
        return 1

    try:
        scan_pairs = resolve_scan_paths(
            datrix_root,
            args.projects,
            args.scan_all,
            include_src=include_src,
            include_tests=include_tests,
        )
    except FileNotFoundError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1

    if not scan_pairs:
        print("No src/ or tests/ directories found to scan.")
        return 0

    # Scan all files and extract markers
    all_markers: list[Marker] = []
    seen_dirs: set[Path] = set()
    files_scanned = 0

    for _project_name, directory in scan_pairs:
        resolved = directory.resolve()
        if resolved in seen_dirs:
            continue
        seen_dirs.add(resolved)
        if not resolved.is_dir():
            continue

        py_files = iter_python_files(resolved)
        for py_file in py_files:
            files_scanned += 1
            try:
                text = py_file.read_text(encoding="utf-8-sig", errors="replace")
            except OSError as exc:
                print(f"Warning: could not read {py_file}: {exc}", file=sys.stderr)
                continue

            try:
                rel = str(py_file.resolve().relative_to(datrix_root.resolve())).replace("\\", "/")
            except ValueError:
                rel = str(py_file.resolve()).replace("\\", "/")

            file_lines = text.splitlines()
            file_markers = parse_markers(file_lines, rel)

            if args.debug and file_markers:
                print(f"  [DEBUG] {rel}: {len(file_markers)} marker(s)", file=sys.stderr)

            all_markers.extend(file_markers)

    print(f"Scanned {files_scanned} file(s) across {len(seen_dirs)} director(ies).", flush=True)

    # Build database
    db_path = datrix_root / ".logic-map" / "markers.db"
    build_database(db_path, all_markers)

    print_summary(all_markers, db_path, scan_pairs)

    if not all_markers:
        print("[OK] No markers found. Database created (empty).")
    else:
        print(f"[OK] Logic map built: {db_path}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
