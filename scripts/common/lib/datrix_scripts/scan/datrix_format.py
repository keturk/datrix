"""Format Datrix .dtrx files with the lossless formatter from datrix-language.

The module behind ``scan/datrix-format.ps1`` (and its ``.sh`` twin). Discovers ``.dtrx`` files under
the given paths (every Datrix repository with ``--all``; never both, and neither prints the usage
and exits 1) and normalizes their whitespace over the parse tree. Every token and comment is
verified identical before anything is written; writes are atomic, and nothing is written if any
file fails parsing or verification. ``--check`` and ``--diff`` write nothing and exit 1 when a file
needs formatting.

Usage:
    python -m datrix_scripts.scan.datrix_format --all [--check] [--diff] [--indent-size=4] [--dbg]
    python -m datrix_scripts.scan.datrix_format --path=<path> [--path=...] [--check] [--diff] [--dbg]
"""

from __future__ import annotations

import argparse
import contextlib
import difflib
import io
import logging
import os
import sys
import tempfile
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Final

from datrix_common.errors.base import DatrixError
from datrix_common.fileops.io import (
    read_text_utf8_exact,
    replace_text_utf8_atomic,
)
from datrix_language.formatting.formatter import FormatOptions, format_dtrx_source
from datrix_language.formatting.verification import verify_lossless
from datrix_language.parser.tree_sitter_datrix.parser import TreeSitterParser

from datrix_scripts.gate_harness import WRAPPER_DEBUG_FLAG, install_sigint_handler, write_files
from datrix_scripts.paths import WORKSPACE_DIR
from datrix_scripts.scan.selection import (
    BOTH_SELECTED,
    SelectionRefused,
    every_repository,
    expect_refusal,
    require_selection,
    wrapper_usage,
)
from datrix_scripts.test.wrappers import SCAN_SCRIPTS_DIR, module_main, run_self_test

MODULE: Final = "datrix_scripts.scan.datrix_format"
WRAPPER: Final = "datrix-format"
DEFAULT_INDENT_SIZE: Final = 4
_INDENT_SIZES: Final = range(1, 9)

_USAGE: Final = wrapper_usage(
    WRAPPER,
    [
        "-All [-Check] [-Diff] [-IndentSize 4] [-Dbg]",
        "<path> [path2 ...] [-Check] [-Diff] [-IndentSize 4] [-Dbg]",
    ],
    get_help=False,
)

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


def _discover(input_paths: Sequence[Path]) -> list[Path]:
    """Every ``.dtrx`` file under *input_paths*, once each, sorted; each path's count printed."""
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
    return sorted(set(all_files))


def _apply(formatter: DatrixFormatter, planned_results: Sequence[FormatResult]) -> int:
    """Write (or report) every planned change, unless any file failed planning; the report's exit code."""
    for result in planned_results:
        if result.error is not None:
            print(f"ERROR {result.path}: {result.error}")

    if formatter.errors:
        if not formatter.check and not formatter.diff:
            print("\nNo files were written because one or more files failed verification.")
        return formatter.report()

    for result in planned_results:
        write_result = formatter.emit_or_write(result)
        if write_result.error is not None:
            print(f"ERROR {write_result.path}: {write_result.error}")
    return formatter.report()


def format_paths(input_paths: Sequence[Path], *, indent_size: int, check: bool, diff: bool, debug: bool) -> int:
    """Format (or with *check* / *diff* only report) every ``.dtrx`` under *input_paths*; the exit code."""
    unique_files = _discover(input_paths)
    if not unique_files:
        print("No .dtrx files found.")
        return 0

    print(f"Found {len(unique_files)} .dtrx file(s).")
    print()

    formatter = DatrixFormatter(indent_size=indent_size, check=check, diff=diff, debug=debug)
    return _apply(formatter, [formatter.plan_file(file_path) for file_path in unique_files])


def build_parser() -> argparse.ArgumentParser:
    """The options of ``scan/datrix-format.ps1``: one per wrapper parameter, spelled exactly."""
    parser = argparse.ArgumentParser(
        prog=WRAPPER, description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter, allow_abbrev=False
    )
    parser.add_argument("--path", action="append", default=[], help="A file or directory to format (repeatable).")
    parser.add_argument("--all", action="store_true", help="Format every Datrix repository.")
    parser.add_argument("--check", action="store_true", help="Report files that would change.")
    parser.add_argument("--diff", action="store_true", help="Show diffs without writing files.")
    parser.add_argument("--indent-size", type=int, default=DEFAULT_INDENT_SIZE, choices=_INDENT_SIZES,
                        help=f"Spaces per indentation level (default: {DEFAULT_INDENT_SIZE}).")
    parser.add_argument(WRAPPER_DEBUG_FLAG, dest="debug", action="store_true", help="Enable debug logging.")
    parser.add_argument("--self-test", action="store_true",
                        help="Run only the self-test: a planted badly indented model is reported and left "
                             "unwritten under --check, the selection rules hold, and the wrapper seam holds.")
    return parser


def format_targets(args: argparse.Namespace, workspace: Path) -> list[Path]:
    """The paths named, or every repository with ``--all``.

    Raises:
        SelectionRefused: neither or both were given.
    """
    require_selection(args.path, args.all, _USAGE)
    return every_repository(workspace) if args.all else [Path(path) for path in args.path]


def _check_a_badly_indented_model_is_reported_not_written() -> None:
    source = "module planted.common {\nabstract entity BaseEntity {\n        UUID id : primaryKey, server = uuid();\n}\n}\n"
    with tempfile.TemporaryDirectory() as tmp:
        planted = write_files(Path(tmp), {"planted.dtrx": source})[0]
        with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
            code = format_paths([Path(tmp)], indent_size=DEFAULT_INDENT_SIZE, check=True, diff=False, debug=False)
        assert code == 1, f"a model needing format must exit 1 under --check, got {code}"
        assert planted.read_text(encoding="utf-8") == source, "--check must leave the file unwritten"


def _check_nothing_selected_prints_the_usage() -> None:
    expect_refusal(lambda: format_targets(build_parser().parse_args([]), WORKSPACE_DIR), 1, _USAGE)


def _check_paths_with_all_are_refused() -> None:
    args = build_parser().parse_args(["--all", "--path=x"])
    expect_refusal(lambda: format_targets(args, WORKSPACE_DIR), 1, BOTH_SELECTED)


def _run(args: argparse.Namespace) -> int:
    """The formatter reports by printing. The parser logs its builtin loading at INFO, which is noise in
    its report, so the root logger stays at WARNING unless ``--dbg`` asks for DEBUG."""
    install_sigint_handler()
    if not args.debug:
        logging.getLogger().setLevel(logging.WARNING)
    if args.self_test:
        checks = [
            _check_a_badly_indented_model_is_reported_not_written,
            _check_nothing_selected_prints_the_usage,
            _check_paths_with_all_are_refused,
        ]
        return run_self_test(checks, wrapper=WRAPPER, module=MODULE, parser=build_parser(), folder=SCAN_SCRIPTS_DIR)
    try:
        input_paths = format_targets(args, WORKSPACE_DIR)
    except SelectionRefused as refused:
        return refused.report()
    return format_paths(input_paths, indent_size=args.indent_size, check=args.check, diff=args.diff, debug=args.debug)


def main(argv: Sequence[str] | None = None) -> int:
    """Entry point."""
    return module_main(build_parser(), _run, argv)


if __name__ == "__main__":
    sys.exit(main())
