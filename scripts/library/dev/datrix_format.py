#!/usr/bin/env python3
"""Format Datrix .dtrx files with the lossless formatter from datrix-language."""

from __future__ import annotations

import argparse
import difflib
import os
import signal
import sys
from dataclasses import dataclass
from pathlib import Path

_library_dir = Path(__file__).resolve().parent.parent
if _library_dir.exists() and str(_library_dir) not in sys.path:
    sys.path.insert(0, str(_library_dir))

from shared.venv import get_datrix_root  # noqa: E402

from datrix_common.errors.base import DatrixError  # noqa: E402
from datrix_common.fileops.io import (  # noqa: E402
    read_text_utf8_exact,
    replace_text_utf8_atomic,
)
from datrix_language.formatting.formatter import FormatOptions, format_dtrx_source  # noqa: E402
from datrix_language.formatting.verification import verify_lossless  # noqa: E402
from datrix_language.parser.tree_sitter_datrix.parser import TreeSitterParser  # noqa: E402

# Only valid .dtrx files: the formatter refuses a file it cannot parse, and
# `.dtrx.false` fixtures are intentionally invalid.
_DTRX_SUFFIX = ".dtrx"
_SKIP_DIRS = frozenset(
    {
        ".git",
        ".venv",
        "venv",
        "node_modules",
        "__pycache__",
        "build",
        "dist",
        ".tox",
        ".mypy_cache",
        ".pytest_cache",
        ".ruff_cache",
        "htmlcov",
        ".generated",
    }
)


@dataclass(frozen=True)
class FormatResult:
    path: Path
    changed: bool
    original: str = ""
    formatted: str = ""
    error: str | None = None


def _sigint_handler(_signum: int, _frame: object) -> None:
    sys.exit(130)


def _is_dtrx_file(path: Path) -> bool:
    return path.suffix == _DTRX_SUFFIX


def _discover_dtrx_files(path: Path) -> list[Path]:
    path = path.resolve()
    if path.is_file():
        return [path] if _is_dtrx_file(path) else []
    if not path.is_dir():
        return []

    found: list[Path] = []
    for dir_path, dirnames, filenames in os.walk(path, followlinks=False):
        dirnames[:] = [
            d for d in dirnames
            if d not in _SKIP_DIRS and not d.endswith(".egg-info")
        ]
        for filename in filenames:
            candidate = Path(dir_path) / filename
            if _is_dtrx_file(candidate):
                found.append(candidate.resolve())
    return sorted(found)


def _unified_diff(path: Path, original: str, formatted: str) -> str:
    return "".join(
        difflib.unified_diff(
            original.splitlines(keepends=True),
            formatted.splitlines(keepends=True),
            fromfile=str(path),
            tofile=f"{path} (formatted)",
        )
    )


class DatrixFormatter:
    def __init__(self, *, indent_size: int, check: bool, diff: bool, debug: bool) -> None:
        self.options = FormatOptions(indent_size=indent_size)
        self.parser = TreeSitterParser()
        self.check = check
        self.diff = diff
        self.debug = debug
        self.files_seen = 0
        self.files_changed = 0
        self.errors = 0

    def _debug(self, message: str) -> None:
        if self.debug:
            print(f"[DEBUG] {message}", file=sys.stderr, flush=True)

    def plan_file(self, path: Path) -> FormatResult:
        self.files_seen += 1
        self._debug(f"Formatting {path}")
        try:
            original = read_text_utf8_exact(path)
        except (OSError, UnicodeDecodeError) as exc:
            self.errors += 1
            return FormatResult(path, changed=False, error=f"Cannot read file: {exc}")

        try:
            formatted = format_dtrx_source(original, self.options, self.parser)
            verify_lossless(original, formatted, self.parser, file_path=path)
        except DatrixError as exc:
            self.errors += 1
            return FormatResult(path, changed=False, error=exc.message)

        if formatted == original:
            return FormatResult(path, changed=False, original=original, formatted=formatted)

        self.files_changed += 1
        return FormatResult(path, changed=True, original=original, formatted=formatted)

    def emit_or_write(self, result: FormatResult) -> FormatResult:
        if not result.changed:
            return result
        if self.diff:
            print(_unified_diff(result.path, result.original, result.formatted), end="")
        elif self.check:
            print(f"NEEDS-FORMAT {result.path}")
        else:
            try:
                replace_text_utf8_atomic(
                    result.path, result.formatted, expected_current=result.original
                )
            except (OSError, DatrixError) as exc:
                self.errors += 1
                self.files_changed -= 1
                return FormatResult(result.path, changed=False, error=f"Cannot write file: {exc}")
            print(f"FORMATTED {result.path}")
        return result

    def report(self) -> int:
        print()
        print("Datrix formatter summary")
        print("------------------------")
        print(f"Files scanned:         {self.files_seen}")
        print(f"Files needing format:  {self.files_changed}")
        print(f"Errors:                {self.errors}")
        print("Guarantee:             whitespace only; tokens and comments verified identical")
        if self.errors:
            return 1
        if (self.check or self.diff) and self.files_changed:
            return 1
        return 0


def main() -> int:
    signal.signal(signal.SIGINT, _sigint_handler)
    parser = argparse.ArgumentParser(description="Format Datrix .dtrx files losslessly")
    parser.add_argument("paths", nargs="*", help="Files or directories to format")
    parser.add_argument("--indent-size", type=int, default=4, choices=range(1, 9))
    parser.add_argument("--check", action="store_true", help="Report files that would change")
    parser.add_argument("--diff", action="store_true", help="Show diffs without writing files")
    parser.add_argument("--debug", action="store_true", help="Enable debug logging")
    args = parser.parse_args()

    if args.paths:
        input_paths = [Path(path) for path in args.paths]
    else:
        try:
            datrix_root = get_datrix_root()
        except FileNotFoundError:
            print("ERROR: Could not find Datrix root directory.", file=sys.stderr)
            return 1
        input_paths = sorted(
            d for d in datrix_root.iterdir()
            if d.is_dir() and d.name.startswith("datrix")
        )

    all_files: list[Path] = []
    print("Discovering .dtrx files...", flush=True)
    for path in input_paths:
        if not path.exists():
            print(f"WARN  Path does not exist: {path}")
            continue
        found = _discover_dtrx_files(path)
        if found:
            print(f"  {path}: {len(found)} file(s)", flush=True)
        all_files.extend(found)

    unique_files = sorted(set(all_files))
    if not unique_files:
        print("No .dtrx files found.")
        return 0

    print(f"Found {len(unique_files)} .dtrx file(s).")
    print()

    formatter = DatrixFormatter(
        indent_size=args.indent_size,
        check=args.check,
        diff=args.diff,
        debug=args.debug,
    )
    planned_results = [formatter.plan_file(file_path) for file_path in unique_files]
    for result in planned_results:
        if result.error is not None:
            print(f"ERROR {result.path}: {result.error}")

    if formatter.errors:
        if not args.check and not args.diff:
            print("\nNo files were written because one or more files failed verification.")
        return formatter.report()

    for result in planned_results:
        write_result = formatter.emit_or_write(result)
        if write_result.error is not None:
            print(f"ERROR {write_result.path}: {write_result.error}")
    return formatter.report()


if __name__ == "__main__":
    sys.exit(main())
