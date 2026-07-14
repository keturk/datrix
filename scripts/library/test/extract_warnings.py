#!/usr/bin/env python3
"""Extract and deduplicate pytest warnings from a test run's full.log.

Parses every ``warnings summary`` section emitted by pytest into a run
directory's ``full.log``, deduplicates repeated warnings by
(file, line, category, normalized message) with an occurrence count, and
writes ``warnings.json`` into the run directory.

Usage:
  python scripts/library/test/extract_warnings.py <run-dir | index.json | full.log>
  .\\scripts\\test\\extract-warnings.ps1 <path>

Exit codes: 0 = analysis completed (even with zero warnings),
2 = usage / input-not-found error.
"""

from __future__ import annotations

import argparse
import io
import json
import logging
import re
import sys
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

# Configure UTF-8 encoding for stdout/stderr on Windows
if sys.platform == "win32" and __name__ == "__main__":
    if hasattr(sys.stdout, "buffer"):
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    if hasattr(sys.stderr, "buffer"):
        sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

# Add library directory to sys.path to import from shared
_LIBRARY_DIR = Path(__file__).resolve().parent.parent
if _LIBRARY_DIR.exists() and str(_LIBRARY_DIR) not in sys.path:
    sys.path.insert(0, str(_LIBRARY_DIR))

logger = logging.getLogger(__name__)

_SCHEMA_VERSION = 1
_OUTPUT_FILENAME = "warnings.json"
_FULL_LOG_NAME = "full.log"
_INDEX_JSON_NAME = "index.json"
_EXIT_OK = 0
_EXIT_USAGE = 2

# Section header: "===== warnings summary =====" (pytest may append "(final)")
_WARNINGS_HEADER = re.compile(r"^=+\s+warnings summary(?:\s+\(final\))?\s+=+\s*$")
# Any other "="-run header line terminates the section
_SECTION_DIVIDER = re.compile(r"^=+")
# Documentation footer line that closes the warnings section
_DOCS_FOOTER_PREFIX = "-- Docs:"
# Warning entry line: "  <path>:<line>: <Category>: <message>"
_WARNING_ENTRY = re.compile(
    r"^\s+(?P<file>.+?):(?P<line>\d+): (?P<category>[A-Za-z_][A-Za-z0-9_]*): ?(?P<message>.*)$"
)
# Location line carrying an occurrence count: "tests/foo.py::test_bar: 12 warnings"
_LOCATION_COUNT = re.compile(r":\s*(\d+)\s+warnings?\s*$")


class UsageError(Exception):
    """Invalid usage or missing input; the script exits with code 2."""


@dataclass
class _ParsedWarning:
    """One warning entry parsed from a warnings-summary group."""

    file: str
    line: int
    category: str
    message: str
    trailing: list[str] = field(default_factory=list)


@dataclass
class WarningRecord:
    """A deduplicated warning with its raw occurrence count."""

    file: str
    line: int
    category: str
    message: str
    code_line: str
    count: int


def _resolve_full_log(raw_path: str) -> Path:
    """Resolve a run dir / index.json / full.log input to the run's full.log.

    Args:
        raw_path: User-supplied path.

    Returns:
        Path to the run directory's full.log.

    Raises:
        UsageError: If the path does not exist or does not lead to a full.log.
    """
    path = Path(raw_path).resolve()
    if path.is_dir():
        candidate = path / _FULL_LOG_NAME
        if not candidate.is_file():
            raise UsageError(
                f"No {_FULL_LOG_NAME} found in directory {path}. "
                f"Expected a test-results run directory containing {_FULL_LOG_NAME} "
                f"(e.g. <project>/.test_results/test-results-YYYYMMDD-HHMMSS). "
                f"Pass a run directory, an index.json path, or a full.log path."
            )
        return candidate
    if path.is_file():
        if path.name == _FULL_LOG_NAME:
            return path
        if path.name == _INDEX_JSON_NAME:
            sibling = path.parent / _FULL_LOG_NAME
            if not sibling.is_file():
                raise UsageError(
                    f"index.json given but no {_FULL_LOG_NAME} exists next to it in {path.parent}. "
                    f"Expected the run directory to contain {_FULL_LOG_NAME}; "
                    f"re-run the test suite to produce a complete run directory."
                )
            return sibling
        raise UsageError(
            f"Unsupported input file '{path.name}'. Expected a run directory, "
            f"an {_INDEX_JSON_NAME} path, or a {_FULL_LOG_NAME} path."
        )
    raise UsageError(
        f"Input path does not exist: {path}. Expected a test-results run directory, "
        f"an {_INDEX_JSON_NAME} path, or a {_FULL_LOG_NAME} path."
    )


def _extract_sections(lines: list[str]) -> list[list[str]]:
    """Collect the content lines of every pytest warnings-summary section.

    Args:
        lines: All lines of full.log.

    Returns:
        One list of content lines per warnings-summary section found.
    """
    sections: list[list[str]] = []
    in_section = False
    current: list[str] = []
    for line in lines:
        if _WARNINGS_HEADER.match(line):
            in_section = True
            current = []
            continue
        if not in_section:
            continue
        if line.startswith(_DOCS_FOOTER_PREFIX) or _SECTION_DIVIDER.match(line):
            sections.append(current)
            in_section = False
            continue
        current.append(line)
    if in_section:
        sections.append(current)
    return sections


def _split_groups(section_lines: list[str]) -> list[list[str]]:
    """Split a warnings-summary section into blank-line-separated groups."""
    groups: list[list[str]] = []
    current: list[str] = []
    for line in section_lines:
        if not line.strip():
            if current:
                groups.append(current)
                current = []
            continue
        current.append(line)
    if current:
        groups.append(current)
    return groups


def _location_weight(line: str) -> int:
    """Occurrence weight of one location line (1, or N for ': N warnings')."""
    match = _LOCATION_COUNT.search(line)
    if match:
        return int(match.group(1))
    return 1


def _parse_group(group: list[str]) -> tuple[int, list[_ParsedWarning]]:
    """Parse one group: leading location lines, then warning entries.

    Args:
        group: Non-blank lines of one warnings-summary group.

    Returns:
        Tuple of (occurrence weight from the location lines, parsed entries).
    """
    weight = 0
    parsed: list[_ParsedWarning] = []
    for line in group:
        entry_match = _WARNING_ENTRY.match(line)
        if entry_match is not None:
            parsed.append(
                _ParsedWarning(
                    file=entry_match.group("file").replace("\\", "/"),
                    line=int(entry_match.group("line")),
                    category=entry_match.group("category"),
                    message=entry_match.group("message"),
                )
            )
            continue
        if line[:1].isspace():
            if parsed:
                parsed[-1].trailing.append(line.strip())
            else:
                logger.debug("stray indented line before any warning entry: %r", line)
            continue
        weight += _location_weight(line)
    if weight == 0:
        # A warning entry with no location lines above it still occurred once.
        weight = 1
    return weight, parsed


def _normalize_message(message: str) -> str:
    """Collapse whitespace for dedup-key purposes."""
    return re.sub(r"\s+", " ", message).strip()


def _merge_entry(
    records: dict[tuple[str, int, str, str], WarningRecord],
    parsed: _ParsedWarning,
    weight: int,
) -> None:
    """Merge one parsed warning entry into the deduplication map."""
    message = parsed.message
    code_line = ""
    if parsed.trailing:
        code_line = parsed.trailing[-1]
        extra = parsed.trailing[:-1]
        if extra:
            message = "\n".join([message, *extra])
    key = (parsed.file, parsed.line, parsed.category, _normalize_message(message))
    if key in records:
        records[key].count += weight
        return
    records[key] = WarningRecord(
        file=parsed.file,
        line=parsed.line,
        category=parsed.category,
        message=message,
        code_line=code_line,
        count=weight,
    )


def collect_warnings(full_log: Path) -> tuple[list[WarningRecord], int]:
    """Parse full.log and return deduplicated warnings plus the raw total.

    Args:
        full_log: Path to the run directory's full.log.

    Returns:
        Tuple of (records sorted by count desc then file/line/category,
        total raw warning occurrences).

    Raises:
        UsageError: If a warnings-summary section exists but none of its
            entries could be parsed (pytest output format drift).
    """
    text = full_log.read_text(encoding="utf-8", errors="replace")
    records: dict[tuple[str, int, str, str], WarningRecord] = {}
    total_raw = 0
    sections = _extract_sections(text.splitlines())
    for section in sections:
        for group in _split_groups(section):
            weight, entries = _parse_group(group)
            if not entries:
                continue
            total_raw += weight * len(entries)
            for parsed in entries:
                _merge_entry(records, parsed, weight)

    sections_have_content = any(any(line.strip() for line in s) for s in sections)
    if sections_have_content and not records:
        raise UsageError(
            f"A warnings summary section exists in {full_log} but no warning entries "
            f"could be parsed. Expected entries of the form "
            f"'<path>:<line>: <Category>: <message>' followed by an indented code line. "
            f"The pytest output format may have changed - update extract_warnings.py."
        )

    ordered = sorted(records.values(), key=lambda r: (-r.count, r.file, r.line, r.category))
    return ordered, total_raw


def _by_category(records: list[WarningRecord]) -> dict[str, int]:
    """Sum raw occurrence counts per warning category."""
    result: dict[str, int] = {}
    for record in records:
        if record.category in result:
            result[record.category] += record.count
        else:
            result[record.category] = record.count
    return dict(sorted(result.items()))


def _write_output(run_dir: Path, records: list[WarningRecord], total_raw: int) -> Path:
    """Write warnings.json into the run directory and return its path."""
    payload: dict[str, object] = {
        "schema_version": _SCHEMA_VERSION,
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "run_dir": str(run_dir),
        "total_raw": total_raw,
        "warnings": [
            {
                "file": record.file,
                "line": record.line,
                "category": record.category,
                "message": record.message,
                "code_line": record.code_line,
                "count": record.count,
            }
            for record in records
        ],
        "by_category": _by_category(records),
    }
    output_path = run_dir / _OUTPUT_FILENAME
    output_path.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    return output_path


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Extract and deduplicate pytest warnings from a test run's full.log."
    )
    parser.add_argument(
        "path",
        help="Run directory, index.json path, or full.log path of a test-results run",
    )
    parser.add_argument("--debug", action="store_true", help="Enable debug logging")
    return parser.parse_args()


def _configure_logging(debug: bool) -> None:
    logging.basicConfig(
        level=logging.DEBUG if debug else logging.INFO,
        format="%(levelname)s %(name)s: %(message)s",
        stream=sys.stderr,
    )


def _run(args: argparse.Namespace) -> int:
    full_log = _resolve_full_log(args.path)
    run_dir = full_log.parent
    records, total_raw = collect_warnings(full_log)
    output_path = _write_output(run_dir, records, total_raw)

    if records:
        file_count = len({record.file for record in records})
        print(f"{len(records)} unique warnings ({total_raw} raw) in {file_count} files")
    else:
        print("0 unique warnings (0 raw) - no warnings summary section in full.log")
    print(f"Details: {output_path}")
    return _EXIT_OK


def main() -> int:
    """Entry point."""
    args = _parse_args()
    _configure_logging(args.debug)
    try:
        return _run(args)
    except UsageError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return _EXIT_USAGE


if __name__ == "__main__":
    sys.exit(main())
