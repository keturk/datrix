"""Extract and deduplicate pytest warnings from a test run's full.log, behind ``test/extract-warnings.ps1``.

Parses every ``warnings summary`` section emitted by pytest into a run
directory's ``full.log``, deduplicates repeated warnings by
(file, line, category, normalized message) with an occurrence count, and
writes ``warnings.json`` into the run directory.

Usage:
  .\\scripts\\test\\extract-warnings.ps1 <run-dir | index.json | full.log>
  scripts/test/extract-warnings.sh <path>     (or --path=<path>)

Exit codes: 0 = analysis completed (even with zero warnings),
2 = usage / input-not-found error; ``--self-test`` exits 0 when every check holds, else 1.
"""

from __future__ import annotations

import argparse
import json
import logging
import re
import sys
from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Final

from datrix_scripts.gate_harness import EXIT_USAGE, UsageError, configure_logging
from datrix_scripts.test.wrappers import ensure_utf8_stdio, run_self_test

logger = logging.getLogger(__name__)

MODULE: Final = "datrix_scripts.test.extract_warnings"
WRAPPER: Final = "extract-warnings"
_SCHEMA_VERSION = 1
_OUTPUT_FILENAME = "warnings.json"
_FULL_LOG_NAME = "full.log"
_INDEX_JSON_NAME = "index.json"
_EXIT_OK = 0

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


def build_parser() -> argparse.ArgumentParser:
    """The options ``test/extract-warnings.ps1`` passes (each wrapper parameter as ``--kebab-name``)."""
    parser = argparse.ArgumentParser(
        prog=WRAPPER,
        description="Extract and deduplicate pytest warnings from a test run's full.log.",
        allow_abbrev=False,
    )
    parser.add_argument("positional_path", nargs="?", default="", metavar="PATH",
                        help="as --path, for a caller of the .sh twin")
    parser.add_argument("--path", default="",
                        help="Run directory, index.json path, or full.log path of a test-results run")
    parser.add_argument("--dbg", action="store_true", help="Enable debug logging")
    parser.add_argument("--self-test", action="store_true", help="run this module's self-test")
    return parser


def _input_path(parser: argparse.ArgumentParser, args: argparse.Namespace) -> str:
    """The one path given, as --path or positionally; a usage error (exit 2) when none or both are given."""
    if args.path and args.positional_path:
        parser.error(f"the path was given twice ({args.path} and {args.positional_path}); give it once")
    path = args.path or args.positional_path
    if not path:
        parser.error("a path is required: a run directory, an index.json path, or a full.log path")
    return path


def _run(path: str) -> int:
    full_log = _resolve_full_log(path)
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


_SELF_TEST_LOG: Final = """\
============================= test session starts =============================
=============================== warnings summary ===============================
tests/test_a.py::test_one
tests/test_a.py::test_two
  src/pkg/mod.py:12: DeprecationWarning: old API
    legacy_call()

tests/test_b.py::test_three: 3 warnings
  src/pkg/mod.py:12: DeprecationWarning: old API
    legacy_call()

-- Docs: https://docs.pytest.org/en/stable/how-to/capture-warnings.html
======================== 3 passed, 5 warnings in 0.10s ========================
"""


def _check_warnings_are_deduplicated_and_weighted() -> None:
    with TemporaryDirectory() as raw:
        full_log = Path(raw) / _FULL_LOG_NAME
        full_log.write_text(_SELF_TEST_LOG, encoding="utf-8")
        records, total_raw = collect_warnings(full_log)
        assert total_raw == 5, f"read {total_raw} raw warnings, expected 5 (2 locations + 3 counted)"
        assert len(records) == 1, f"read {len(records)} unique warnings, expected 1"
        record = records[0]
        assert (record.file, record.line, record.category, record.count, record.code_line) == (
            "src/pkg/mod.py", 12, "DeprecationWarning", 5, "legacy_call()"
        ), f"read {record}"


def _check_inputs_resolve_to_full_log() -> None:
    with TemporaryDirectory() as raw:
        run_dir = Path(raw)
        full_log = run_dir / _FULL_LOG_NAME
        full_log.write_text("", encoding="utf-8")
        (run_dir / _INDEX_JSON_NAME).write_text("{}", encoding="utf-8")
        for given in (run_dir, full_log, run_dir / _INDEX_JSON_NAME):
            resolved = _resolve_full_log(str(given))
            assert resolved == full_log.resolve(), f"{given} resolved to {resolved}, expected {full_log}"
        unsupported = run_dir / "notes.txt"
        unsupported.write_text("", encoding="utf-8")
        for refused in (run_dir / "missing", unsupported):
            try:
                _resolve_full_log(str(refused))
            except UsageError:
                continue
            raise AssertionError(f"{refused} was accepted; expected a UsageError")


def _check_unparseable_section_fails_loud() -> None:
    with TemporaryDirectory() as raw:
        full_log = Path(raw) / _FULL_LOG_NAME
        full_log.write_text("===== warnings summary =====\nsomething unexpected\n  not an entry\n", encoding="utf-8")
        try:
            collect_warnings(full_log)
        except UsageError:
            return
        raise AssertionError("a warnings summary with no parseable entry was accepted; expected a UsageError")


def main(argv: Sequence[str] | None = None) -> int:
    """Parse *argv* (default: the process's), then run the self-test or extract the warnings of the given run."""
    ensure_utf8_stdio()
    parser = build_parser()
    args = parser.parse_args(argv)
    configure_logging(args.dbg)
    if args.self_test:
        checks = [
            _check_warnings_are_deduplicated_and_weighted,
            _check_inputs_resolve_to_full_log,
            _check_unparseable_section_fails_loud,
        ]
        return run_self_test(checks, wrapper=WRAPPER, module=MODULE, parser=parser)
    path = _input_path(parser, args)
    try:
        return _run(path)
    except UsageError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return EXIT_USAGE


if __name__ == "__main__":
    sys.exit(main())
