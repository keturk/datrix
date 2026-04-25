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

from shared.venv import get_datrix_root

# ---------------------------------------------------------------------------
# Marker kinds
# ---------------------------------------------------------------------------

MARKER_KINDS = frozenset({"canonical", "pattern", "boundary", "invariant"})

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


# ---------------------------------------------------------------------------
# Parser
# ---------------------------------------------------------------------------

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
        line = lines[i]
        stripped = line.strip()
        m = _MARKER_RE.match(stripped)
        if not m:
            i += 1
            continue

        kind = m.group(1)
        topic = m.group(2).strip()
        summary = m.group(3).strip()
        marker_line = i + 1  # 1-based

        # Collect the block: rules, anti-patterns, see refs, description lines
        description_parts: list[str] = []
        rules: list[str] = []
        anti_patterns: list[str] = []
        see_refs: list[str] = []
        i += 1
        while i < total:
            bline = lines[i].strip()

            # Stop if we hit a non-comment line or a new marker
            if not bline.startswith("#"):
                break
            if _MARKER_RE.match(bline):
                break

            rule_m = _RULE_RE.match(bline)
            if rule_m:
                rules.append(rule_m.group(1).strip())
                i += 1
                continue

            ap_m = _ANTI_PATTERN_RE.match(bline)
            if ap_m:
                anti_patterns.append(ap_m.group(1).strip())
                i += 1
                continue

            see_m = _SEE_RE.match(bline)
            if see_m:
                see_refs.append(see_m.group(1).strip())
                i += 1
                continue

            cont_m = _CONTINUATION_RE.match(bline)
            if cont_m:
                desc_text = cont_m.group(1)
                description_parts.append(desc_text)
                i += 1
                continue

            # Unrecognized comment line — treat as description
            description_parts.append(bline.lstrip("# "))
            i += 1

        # Try to detect the symbol (def/class) on the next non-blank line
        symbol = ""
        signature = ""
        j = i
        while j < total and not lines[j].strip():
            j += 1
        if j < total:
            sym_m = _SYMBOL_RE.match(lines[j].strip())
            if sym_m:
                symbol = sym_m.group(1)
                signature = lines[j].strip()

        description = "\n".join(description_parts).strip()

        markers.append(Marker(
            kind=kind,
            topic=topic,
            summary=summary,
            description=description,
            file=relative_path,
            line=marker_line,
            symbol=symbol,
            signature=signature,
            rules=rules,
            anti_patterns=anti_patterns,
            see_refs=see_refs,
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
    signature     TEXT
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

CREATE INDEX IF NOT EXISTS idx_markers_topic ON markers(topic);
CREATE INDEX IF NOT EXISTS idx_markers_kind ON markers(kind);
CREATE INDEX IF NOT EXISTS idx_markers_file ON markers(file);
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
        cur.execute("DROP TABLE IF EXISTS see_refs")
        cur.execute("DROP TABLE IF EXISTS anti_patterns")
        cur.execute("DROP TABLE IF EXISTS rules")
        cur.execute("DROP TABLE IF EXISTS markers")
        cur.executescript(_SCHEMA)

        for marker in markers:
            cur.execute(
                "INSERT INTO markers (kind, topic, summary, description, file, line, symbol, signature) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    marker.kind,
                    marker.topic,
                    marker.summary,
                    marker.description,
                    marker.file,
                    marker.line,
                    marker.symbol,
                    marker.signature,
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
