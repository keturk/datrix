#!/usr/bin/env python3
"""Conservative formatter for Datrix .dtrx files."""

from __future__ import annotations

import argparse
import difflib
import os
import re
import signal
import sys
from dataclasses import dataclass
from pathlib import Path

_library_dir = Path(__file__).resolve().parent.parent
if _library_dir.exists() and str(_library_dir) not in sys.path:
    sys.path.insert(0, str(_library_dir))

from shared.venv import get_datrix_root  # noqa: E402

_DTRX_SUFFIXES = (".dtrx", ".dtrx.false")
_LINE_RE = re.compile(r"(.*?)(\r\n|\n|\r)?$")
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
    return path.name.endswith(_DTRX_SUFFIXES)


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


def _split_line(line: str) -> tuple[str, str]:
    match = _LINE_RE.fullmatch(line)
    if match is None:
        return line, ""
    return match.group(1), match.group(2) or ""


def _code_portion(text: str) -> str:
    result: list[str] = []
    quote: str | None = None
    escaped = False
    i = 0
    while i < len(text):
        char = text[i]
        next_char = text[i + 1] if i + 1 < len(text) else ""
        if quote is None and char == "/" and next_char == "/":
            break
        if quote is None and char in {"'", '"'}:
            quote = char
            result.append(" ")
        elif quote is not None:
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == quote:
                quote = None
            result.append(" ")
        else:
            result.append(char)
        i += 1
    return "".join(result)


def _leading_closing_braces(code: str) -> int:
    count = 0
    for char in code.lstrip():
        if char == "}":
            count += 1
        elif char.isspace():
            continue
        else:
            break
    return count


def _format_source(source: str, *, indent_size: int) -> str:
    lines = source.splitlines(keepends=True)
    if not lines:
        return source

    indent_level = 0
    formatted_lines: list[str] = []
    unit = " " * indent_size
    default_newline = "\r\n" if "\r\n" in source else "\n"

    for line in lines:
        body, newline = _split_line(line)
        stripped_body = body.lstrip(" \t")
        if stripped_body == "":
            if formatted_lines and formatted_lines[-1].strip() == "":
                continue
            formatted_lines.append(newline or default_newline)
            continue

        code = _code_portion(stripped_body)
        line_indent = max(indent_level - _leading_closing_braces(code), 0)
        formatted_lines.append(f"{unit * line_indent}{stripped_body}{newline}")

        indent_level = max(indent_level + code.count("{") - code.count("}"), 0)

    return _ensure_blank_line_after_standalone_closing_brace(
        formatted_lines,
        default_newline=default_newline,
    )


def _ensure_blank_line_after_standalone_closing_brace(
    lines: list[str],
    *,
    default_newline: str,
) -> str:
    output: list[str] = []
    for index, line in enumerate(lines):
        output.append(line)
        body, newline = _split_line(line)
        if body.strip() != "}":
            continue
        next_line = lines[index + 1] if index + 1 < len(lines) else ""
        next_body, _ = _split_line(next_line)
        if next_line and next_body.strip() != "":
            output.append(newline or default_newline)
    return "".join(output)


def _nonblank_payload(source: str) -> list[str]:
    payload: list[str] = []
    for line in source.splitlines():
        stripped = line.lstrip(" \t")
        if stripped:
            payload.append(stripped)
    return payload


def _assert_safe_format(original: str, formatted: str) -> None:
    if _nonblank_payload(original) != _nonblank_payload(formatted):
        raise ValueError("formatter changed nonblank source content")


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
        self.indent_size = indent_size
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
            original = path.read_text(encoding="utf-8-sig")
        except Exception as exc:
            self.errors += 1
            return FormatResult(path, changed=False, error=f"Cannot read file: {exc}")

        try:
            formatted = _format_source(original, indent_size=self.indent_size)
            _assert_safe_format(original, formatted)
        except Exception as exc:
            self.errors += 1
            return FormatResult(path, changed=False, error=str(exc))

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
                result.path.write_text(result.formatted, encoding="utf-8")
            except Exception as exc:
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
        print("Guarantee:             indentation and blank lines only")
        if self.errors:
            return 1
        if (self.check or self.diff) and self.files_changed:
            return 1
        return 0


def main() -> int:
    signal.signal(signal.SIGINT, _sigint_handler)
    parser = argparse.ArgumentParser(description="Format Datrix .dtrx indentation safely")
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
            print("\nNo files were written because one or more files failed safety validation.")
        return formatter.report()

    for result in planned_results:
        write_result = formatter.emit_or_write(result)
        if write_result.error is not None:
            print(f"ERROR {write_result.path}: {write_result.error}")
    return formatter.report()


if __name__ == "__main__":
    sys.exit(main())
