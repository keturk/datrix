"""Syntax Checker for Datrix .dtrx Files

The module behind ``scan/syntax-checker.ps1`` (and its ``.sh`` twin). Validates the syntax of
``.dtrx`` files with the tree-sitter parser (a parse with no ERROR or MISSING node, plus the
contextual-keyword check): one file, every file under a directory, or -- with no ``--path`` --
every Datrix repository. ``.dtrx.false`` files (intentionally invalid fixtures) are skipped.
Exit codes: 0 every file is valid (or none was found), 1 a file has a syntax error.

Requirements:
- datrix-language and its tree-sitter dependency, both installed with the shared venv
- tree-sitter CLI: npm install -g tree-sitter-cli
- C compiler: MSVC (Windows), GCC/Clang (Linux/macOS)

Usage:
    python -m datrix_scripts.scan.syntax_checker [--path=<file or directory>] [--dbg]
"""

from __future__ import annotations

import argparse
import contextlib
import io
import os
import sys
import tempfile
from collections.abc import Sequence
from pathlib import Path
from typing import Final

from datrix_scripts.gate_harness import (
    EXIT_PASS,
    EXIT_VIOLATION,
    WRAPPER_DEBUG_FLAG,
    install_sigint_handler,
    write_files,
)
from datrix_scripts.paths import WORKSPACE_DIR
from datrix_scripts.scan.selection import every_repository
from datrix_scripts.test.wrappers import SCAN_SCRIPTS_DIR, module_main, run_self_test
from datrix_scripts.venv import PACKAGE_DEPENDENCIES, missing_declared_tool

try:
    from datrix_common.constants import DATRIX_FILE_EXTENSION
    from datrix_common.errors.parse import ParseError
    from datrix_language.parser.contextual_keywords import validate_contextual_keywords
    from datrix_language.parser.tree_sitter_datrix.parser import TreeSitterParser
except ImportError as exc:
    raise SystemExit(
        f"{missing_declared_tool('datrix-language (with datrix-common and tree-sitter)', PACKAGE_DEPENDENCIES)} "
        f"The import failed with: {exc}"
    ) from exc


class SyntaxChecker:
    """Checks syntax of .dtrx files."""

    def __init__(self, debug: bool = False):
        """Initialize syntax checker.

        Args:
            debug: Enable debug output
        """
        self.errors: list[tuple[Path, str, int, int]] = []  # (file, message, line, column)
        self.files_checked = 0
        self.files_with_errors = 0
        self.debug = debug
        self._parser: TreeSitterParser | None = None

    def _get_parser(self) -> TreeSitterParser:
        """Get cached parser instance."""
        if self._parser is None:
            print("Initializing parser...", flush=True)
            self._parser = TreeSitterParser()
            print("Parser initialized.", flush=True)
        return self._parser

    def _debug(self, message: str):
        """Print debug message if debug mode is enabled."""
        if self.debug:
            print(f"[DEBUG] {message}", file=sys.stderr)

    # Directories to skip during file discovery
    _SKIP_DIRS = frozenset({
        "node_modules", ".git", "__pycache__", ".venv", "venv",
        "build", "dist", ".tox", ".mypy_cache", ".pytest_cache",
        ".eggs", ".ruff_cache",
    })

    def find_datrix_files(self, path: Path) -> list[Path]:
        """
        Recursively find all .dtrx files in a directory.
        Excludes .dtrx.false files (intentionally invalid fixtures).
        Does not follow symlinks to avoid infinite loops.
        Skips node_modules, .git, __pycache__, and other non-source directories.

        Args:
            path: Directory or file path

        Returns:
            List of .dtrx file paths (excluding .dtrx.false)
        """
        datrix_files = []

        if path.is_file():
            if path.suffix == DATRIX_FILE_EXTENSION and not path.name.endswith(".false"):
                datrix_files.append(path)
        elif path.is_dir():
            for dir_path, dirnames, filenames in os.walk(path, followlinks=False):
                # Prune irrelevant directories in-place to prevent traversal
                dirnames[:] = [
                    d for d in dirnames
                    if d not in self._SKIP_DIRS and not d.endswith(".egg-info")
                ]
                for name in filenames:
                    if name.endswith(DATRIX_FILE_EXTENSION) and not name.endswith(".false"):
                        datrix_files.append(Path(dir_path) / name)
        else:
            print(f"Warning: Path does not exist or is not a file/directory: {path}", file=sys.stderr)

        return sorted(datrix_files)

    def check_file(self, file_path: Path) -> bool:
        """
        Check syntax of a single .dtrx file.

        Uses tree-sitter parse only (no AST transformation) for speed.

        Args:
            file_path: Path to the .dtrx file

        Returns:
            True if file has no syntax errors, False otherwise
        """
        try:
            self._debug(f"Checking syntax of {file_path}...")

            if not file_path.exists():
                self.errors.append((file_path, f"File not found: {file_path}", 0, 0))
                self.files_with_errors += 1
                return False

            if file_path.suffix != DATRIX_FILE_EXTENSION:
                self.errors.append(
                    (
                        file_path,
                        f"File must have {DATRIX_FILE_EXTENSION} extension: {file_path}",
                        0,
                        0,
                    )
                )
                self.files_with_errors += 1
                return False

            parser = self._get_parser()
            source = file_path.read_text(encoding="utf-8")

            if not source.strip():
                self.errors.append((file_path, "Empty source file", 1, 1))
                self.files_with_errors += 1
                return False

            # Only do tree-sitter parse + error check, skip full AST transform. The grammar
            # also parses config and seed documents cleanly, so the check is the model
            # parser's own: a .dtrx model with no ERROR or MISSING node.
            tree = parser.parse_tree(source, file_path=file_path)
            parser.require_clean_tree(tree, source, file_path)

            # Lightweight semantic check: validate contextual keywords
            source_bytes = source.encode("utf-8")
            keyword_errors = validate_contextual_keywords(tree.root_node, source_bytes)
            if keyword_errors:
                for line, col, msg in keyword_errors:
                    self.errors.append((file_path, msg, line, col))
                self.files_with_errors += 1
                return False

            self._debug(f"Checked {file_path}, errors: 0")
            return True
        except ParseError as e:
            msg = e.message if hasattr(e, "message") else str(e)
            line = e.line if e.line is not None else 0
            col = e.column if e.column is not None else 0
            self.errors.append((file_path, msg, line, col))
            self._debug(f"Checked {file_path}, errors: 1")
            self.files_with_errors += 1
            return False
        except Exception as e:
            self._debug(f"Exception checking {file_path}: {e}")
            self.errors.append((file_path, f"Unexpected error: {str(e)}", 0, 0))
            self.files_with_errors += 1
            return False

    def check_files(self, file_paths: list[Path]) -> bool:
        """
        Check syntax of multiple .dtrx files.

        Args:
            file_paths: List of paths to .dtrx files

        Returns:
            True if all files have no syntax errors, False otherwise
        """
        self.errors.clear()
        self.files_checked = 0
        self.files_with_errors = 0

        total = len(file_paths)
        print(f"Checking {total} files...", flush=True)
        for i, file_path in enumerate(file_paths, 1):
            self.files_checked += 1
            ok = self.check_file(file_path)
            if not ok:
                print(f"  [{i}/{total}] {file_path} ERROR", flush=True)

        return self.files_with_errors == 0

    def get_source_line(self, file_path: Path, line_number: int) -> str:
        """
        Get a specific line from a source file.

        Args:
            file_path: Path to the file
            line_number: 1-based line number

        Returns:
            The line content or empty string if not found
        """
        try:
            with open(file_path, encoding="utf-8") as f:
                lines = f.readlines()
                if 1 <= line_number <= len(lines):
                    return lines[line_number - 1].rstrip("\n\r")
        except Exception:
            pass
        return ""

    def format_error_context(
        self, file_path: Path, line: int, column: int, message: str
    ) -> list[str]:
        """
        Format error with source context showing the problematic line and marker.

        Args:
            file_path: Path to the file
            line: 1-based line number
            column: 1-based column number
            message: Error message

        Returns:
            List of formatted lines for output
        """
        output = []

        if line > 0:
            if not isinstance(file_path, Path):
                file_path = Path(file_path)

            source_line = self.get_source_line(file_path, line)

            if source_line:
                display_line = source_line.expandtabs(4)

                if column > 0:
                    prefix = (
                        source_line[: column - 1] if column <= len(source_line) + 1 else source_line
                    )
                    display_column = len(prefix.expandtabs(4))
                else:
                    display_column = 0

                line_prefix = f"  {line} | "
                output.append(f"{line_prefix}{display_line}")

                pointer_padding = " " * len(line_prefix) + " " * display_column
                output.append(f"{pointer_padding}^ {message}")
            else:
                if column > 0:
                    output.append(f"  Line {line}, Column {column}: {message}")
                else:
                    output.append(f"  Line {line}: {message}")
        else:
            output.append(f"  {message}")

        return output

    def report(self):
        """Print report of syntax errors."""
        if not self.errors:
            print(f"\n[OK] All {self.files_checked} file(s) have valid syntax!")
            return

        print(f"\n[ERROR] Found syntax errors in {self.files_with_errors} of {self.files_checked} file(s):\n")

        errors_by_file = {}
        for file_path, msg, line, col in self.errors:
            if file_path not in errors_by_file:
                errors_by_file[file_path] = []
            errors_by_file[file_path].append((msg, line, col))

        for file_path, file_errors in sorted(errors_by_file.items()):
            print(f"{file_path}:")
            for msg, line, col in file_errors:
                context_lines = self.format_error_context(file_path, line, col, msg)
                for context_line in context_lines:
                    print(context_line)
            print()


MODULE: Final = "datrix_scripts.scan.syntax_checker"
WRAPPER: Final = "syntax-checker"

_PLANTED_MODEL: Final = """module planted.common {
    abstract entity BaseEntity {
        UUID id : primaryKey, server = uuid();
    }
}
"""


def check_paths(paths_to_check: Sequence[Path], debug: bool) -> int:
    """Check every ``.dtrx`` file under *paths_to_check* and print the report: 0 all valid, else 1."""
    checker = SyntaxChecker(debug=debug)
    print("Discovering .dtrx files...", flush=True)
    all_files: list[Path] = []
    for path in paths_to_check:
        if not path.exists():
            print(f"Warning: Path does not exist: {path}", file=sys.stderr)
            continue
        found = checker.find_datrix_files(path)
        if found:
            print(f"  {path.name}: {len(found)} files", flush=True)
        all_files.extend(found)

    if not all_files:
        print("No .dtrx files found to check.")
        return EXIT_PASS

    print(f"Found {len(all_files)} .dtrx files total.\n", flush=True)

    success = checker.check_files(all_files)
    checker.report()
    return EXIT_PASS if success else EXIT_VIOLATION


def selected_paths(path: str | None, workspace: Path) -> list[Path]:
    """The one ``--path`` given, else every Datrix repository under *workspace*."""
    if path:
        return [Path(path)]
    return every_repository(workspace)


def build_parser() -> argparse.ArgumentParser:
    """The options of ``scan/syntax-checker.ps1``: one per wrapper parameter, spelled exactly."""
    parser = argparse.ArgumentParser(
        prog=WRAPPER, description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter, allow_abbrev=False
    )
    parser.add_argument("--path", help="File or directory to check (default: all datrix repositories).")
    parser.add_argument(WRAPPER_DEBUG_FLAG, dest="debug", action="store_true",
                        help="Print each file checked and log at DEBUG level.")
    parser.add_argument("--self-test", action="store_true",
                        help="Run only the self-test: a planted valid model passes, a planted broken one fails, "
                             "a .dtrx.false fixture is skipped.")
    return parser


def _quiet_check(paths: Sequence[Path]) -> int:
    with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
        return check_paths(paths, debug=False)


def _check_a_valid_model_passes() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        write_files(Path(tmp), {"valid.dtrx": _PLANTED_MODEL, "fixture.dtrx.false": "module {{{\n"})
        assert _quiet_check([Path(tmp)]) == EXIT_PASS, "a valid model (beside a skipped .dtrx.false) must exit 0"


def _check_a_broken_model_fails() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        write_files(Path(tmp), {"valid.dtrx": _PLANTED_MODEL, "broken.dtrx": "module planted.broken {\n entity {\n"})
        assert _quiet_check([Path(tmp)]) == EXIT_VIOLATION, "a model with a syntax error must exit 1"


def _check_no_path_selects_every_repository() -> None:
    repos = selected_paths(None, WORKSPACE_DIR)
    assert repos and all(repo.parent == WORKSPACE_DIR for repo in repos), (
        f"no --path must select the Datrix repositories under {WORKSPACE_DIR}, got {repos}"
    )
    assert selected_paths("one.dtrx", WORKSPACE_DIR) == [Path("one.dtrx")], "--path must select exactly that path"


def _run(args: argparse.Namespace) -> int:
    install_sigint_handler()
    if args.self_test:
        checks = [_check_a_valid_model_passes, _check_a_broken_model_fails, _check_no_path_selects_every_repository]
        return run_self_test(checks, wrapper=WRAPPER, module=MODULE, parser=build_parser(), folder=SCAN_SCRIPTS_DIR)
    return check_paths(selected_paths(args.path, WORKSPACE_DIR), args.debug)


def main(argv: Sequence[str] | None = None) -> int:
    """Entry point."""
    return module_main(build_parser(), _run, argv)


if __name__ == "__main__":
    sys.exit(main())
