#!/usr/bin/env python3
"""Dump the logic map SQLite database to a readable Markdown report.

Reads .logic-map/markers.db and writes a grouped Markdown file for human review.
The report includes all markers grouped by topic, with rules, anti-patterns,
and cross-references.

Usage:
    python scripts/library/dev/logic_map_report.py
    python scripts/library/dev/logic_map_report.py --output docs/logic-map.md

    Or use the PowerShell wrapper:
        .\\scripts\\dev\\logic-map-report.ps1
        .\\scripts\\dev\\logic-map-report.ps1 -Output docs\\logic-map.md
"""

from __future__ import annotations

import argparse
import io
import sqlite3
import sys
from datetime import datetime
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

# Kind display order and labels
_KIND_ORDER = ["canonical", "boundary", "pattern", "invariant"]
_KIND_LABELS = {
    "canonical": "Canonical Implementation",
    "boundary": "System Boundary",
    "pattern": "Approved Pattern",
    "invariant": "Invariant",
}


def _load_markers(db_path: Path) -> list[dict[str, object]]:
    """Load all markers with their rules, anti-patterns, and cross-refs.

    Args:
        db_path: Path to the SQLite database.

    Returns:
        List of marker dicts with nested lists for rules, anti_patterns, see_refs.
    """
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    try:
        markers = []
        for row in conn.execute("SELECT * FROM markers ORDER BY topic, kind"):
            marker_id = row["id"]
            marker: dict[str, object] = dict(row)
            marker["rules"] = [
                r["text"] for r in conn.execute(
                    "SELECT text FROM rules WHERE marker_id = ? ORDER BY id", (marker_id,)
                )
            ]
            marker["anti_patterns"] = [
                r["text"] for r in conn.execute(
                    "SELECT text FROM anti_patterns WHERE marker_id = ? ORDER BY id", (marker_id,)
                )
            ]
            marker["see_refs"] = [
                r["target_topic"] for r in conn.execute(
                    "SELECT target_topic FROM see_refs WHERE from_marker = ? ORDER BY id", (marker_id,)
                )
            ]
            markers.append(marker)
        return markers
    finally:
        conn.close()


def _build_report(markers: list[dict[str, object]], db_path: Path) -> str:
    """Build the Markdown report string.

    Args:
        markers: List of marker dicts from _load_markers.
        db_path: Path to the database (for display).

    Returns:
        Complete Markdown report as a string.
    """
    lines: list[str] = []
    local_ts = datetime.now().astimezone().strftime("%Y-%m-%d %H:%M:%S %Z")

    # --- Summary ---
    kind_counts: dict[str, int] = {}
    for m in markers:
        kind = str(m["kind"])
        kind_counts[kind] = kind_counts.get(kind, 0) + 1
    total_rules = sum(len(m["rules"]) for m in markers)
    total_ap = sum(len(m["anti_patterns"]) for m in markers)
    total_refs = sum(len(m["see_refs"]) for m in markers)
    unique_files = sorted({str(m["file"]) for m in markers})

    lines.append("# Logic Map Report")
    lines.append("")
    lines.append(f"Generated: {local_ts}")
    lines.append(f"Database: `{db_path}`")
    lines.append("")
    lines.append("## Summary")
    lines.append("")
    lines.append(f"| Metric | Count |")
    lines.append(f"|--------|-------|")
    lines.append(f"| Total markers | {len(markers)} |")
    for kind in _KIND_ORDER:
        if kind in kind_counts:
            lines.append(f"| {_KIND_LABELS.get(kind, kind)} | {kind_counts[kind]} |")
    lines.append(f"| Rules | {total_rules} |")
    lines.append(f"| Anti-patterns | {total_ap} |")
    lines.append(f"| Cross-references | {total_refs} |")
    lines.append(f"| Files | {len(unique_files)} |")
    lines.append("")

    # --- Group by topic prefix ---
    groups: dict[str, list[dict[str, object]]] = {}
    for m in markers:
        topic = str(m["topic"])
        prefix = topic.split("/")[0] if "/" in topic else topic
        groups.setdefault(prefix, []).append(m)

    lines.append("---")
    lines.append("")

    # --- Table of Contents ---
    lines.append("## Table of Contents")
    lines.append("")
    for prefix in sorted(groups):
        anchor = prefix.lower().replace("/", "-").replace(" ", "-")
        count = len(groups[prefix])
        lines.append(f"- [{prefix}](#{anchor}) ({count})")
    lines.append("")
    lines.append("---")
    lines.append("")

    # --- Per-group sections ---
    for prefix in sorted(groups):
        lines.append(f"## {prefix}")
        lines.append("")

        for m in groups[prefix]:
            kind = str(m["kind"])
            topic = str(m["topic"])
            summary = str(m["summary"])
            kind_label = _KIND_LABELS.get(kind, kind)
            symbol = str(m["symbol"]) if m["symbol"] else ""
            signature = str(m["signature"]) if m["signature"] else ""
            file_path = str(m["file"])
            line_num = m["line"]

            lines.append(f"### `{topic}` ({kind_label})")
            lines.append("")
            lines.append(f"**{summary}**")
            lines.append("")
            lines.append(f"- File: `{file_path}:{line_num}`")
            if symbol:
                lines.append(f"- Symbol: `{symbol}`")
            if signature:
                lines.append(f"- Signature: `{signature}`")
            lines.append("")

            desc = str(m["description"]) if m["description"] else ""
            if desc:
                lines.append(desc)
                lines.append("")

            rules = m["rules"]
            if rules:
                lines.append("**Rules:**")
                for r in rules:
                    lines.append(f"- {r}")
                lines.append("")

            anti_patterns = m["anti_patterns"]
            if anti_patterns:
                lines.append("**Anti-patterns:**")
                for ap in anti_patterns:
                    lines.append(f"- {ap}")
                lines.append("")

            see_refs = m["see_refs"]
            if see_refs:
                lines.append("**See also:**")
                for ref in see_refs:
                    lines.append(f"- `{ref}`")
                lines.append("")

            lines.append("---")
            lines.append("")

    # --- Cross-reference graph ---
    all_refs = [(str(m["topic"]), ref) for m in markers for ref in m["see_refs"]]

    if all_refs:
        lines.append("## Cross-Reference Graph")
        lines.append("")
        lines.append("| From | To |")
        lines.append("|------|----|")
        for from_topic, to_topic in sorted(all_refs):
            lines.append(f"| `{from_topic}` | `{to_topic}` |")
        lines.append("")

    # --- File index ---
    lines.append("## File Index")
    lines.append("")
    lines.append("| File | Markers |")
    lines.append("|------|---------|")
    file_counts: dict[str, int] = {}
    for m in markers:
        f = str(m["file"])
        file_counts[f] = file_counts.get(f, 0) + 1
    for f in sorted(file_counts):
        lines.append(f"| `{f}` | {file_counts[f]} |")
    lines.append("")

    return "\n".join(lines)


def main() -> int:
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Dump the logic map database to a Markdown report.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument(
        "--output", "-o",
        type=Path,
        default=None,
        help="Output file path (default: ./logic-map-report.md)",
    )
    args = parser.parse_args()

    try:
        datrix_root = get_datrix_root()
    except FileNotFoundError:
        print("ERROR: Could not find Datrix root directory", file=sys.stderr)
        return 1

    db_path = datrix_root / ".logic-map" / "markers.db"
    if not db_path.exists():
        print(
            f"ERROR: Database not found at {db_path}\n"
            "Run logic-map.ps1 -All first to build the database.",
            file=sys.stderr,
        )
        return 1

    markers = _load_markers(db_path)
    if not markers:
        print("No markers in database. Nothing to report.")
        return 0

    report = _build_report(markers, db_path)

    out_path = args.output
    if out_path is None:
        out_path = Path.cwd() / "logic-map-report.md"
    elif out_path.is_dir():
        out_path = out_path / "logic-map-report.md"

    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(report, encoding="utf-8")
    print(f"Report written: {out_path} ({len(markers)} markers)", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
