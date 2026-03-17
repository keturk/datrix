#!/usr/bin/env python3
"""
Syntax Checker for Datrix .dtrx Files

This script validates the syntax of .dtrx files using the tree-sitter parser.
It can check a single file, all files in a directory, or all files in current directory.

Requirements:
- tree-sitter Python package: pip install tree-sitter>=0.23.0
- tree-sitter CLI: npm install -g tree-sitter-cli
- C compiler: MSVC (Windows), GCC/Clang (Linux/macOS)
"""

import argparse
import os
import signal
import sys
from pathlib import Path


def _sigint_handler(_signum: int, _frame: object) -> None:
    """Handle Ctrl-C: exit with 130 (standard SIGINT exit code)."""
    sys.exit(130)

# Add library directory to sys.path to import from shared
library_dir = Path(__file__).parent.parent
if library_dir.exists() and str(library_dir) not in sys.path:
    sys.path.insert(0, str(library_dir))

from shared.venv import get_datrix_root

# Try to import datrix-language parser
try:
    # Add datrix-common and datrix-language to path
    datrix_root = get_datrix_root()
    datrix_common_src = datrix_root / "datrix-common" / "src"
    if datrix_common_src.exists() and str(datrix_common_src) not in sys.path:
        sys.path.insert(0, str(datrix_common_src))
    datrix_language_src = datrix_root / "datrix-language" / "src"
    if datrix_language_src.exists() and str(datrix_language_src) not in sys.path:
        sys.path.insert(0, str(datrix_language_src))

    from datrix_common import DATRIX_FILE_EXTENSION
    from datrix_common.errors import ParseError
    from datrix_language.parser import TreeSitterParser
    from datrix_language.parser.contextual_keywords import validate_contextual_keywords
except ImportError as e:
    print(f"Error: Could not import Datrix parser: {e}", file=sys.stderr)
    print("Make sure datrix-language is installed and the parser is available:", file=sys.stderr)
    print("  pip install -e datrix-language", file=sys.stderr)
    print("  pip install tree-sitter>=0.23.0", file=sys.stderr)
    sys.exit(1)


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

            # Only do tree-sitter parse + error check, skip full AST transform
            tree = parser.parse_tree(source, file_path=file_path)
            if tree.root_node.has_error:
                # Use parser's error reporting to get a nice message
                parser._raise_parse_error(tree.root_node, source, file_path)

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


def main():
    """Main entry point."""
    signal.signal(signal.SIGINT, _sigint_handler)

    parser = argparse.ArgumentParser(
        description="Check syntax of .dtrx files",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "paths",
        nargs="*",
        type=str,
        help="File or directory paths to check (default: all datrix repositories)",
    )
    parser.add_argument("--debug", action="store_true", help="Enable debug output")

    args = parser.parse_args()

    checker = SyntaxChecker(debug=args.debug)

    if args.paths:
        paths_to_check = [Path(p) for p in args.paths]
    else:
        # Fallback for direct invocation (without the PowerShell wrapper).
        # The wrapper uses DatrixPaths.psm1 as the single source of truth
        # and passes paths as arguments.
        try:
            datrix_root = get_datrix_root()
            paths_to_check = sorted(
                d for d in datrix_root.iterdir()
                if d.is_dir() and d.name.startswith("datrix")
            )
        except FileNotFoundError:
            print("ERROR: Could not find Datrix root directory", file=sys.stderr)
            return 1

    print("Discovering .dtrx files...", flush=True)
    all_files = []
    for path in paths_to_check:
        path_obj = Path(path)
        if not path_obj.exists():
            print(f"Warning: Path does not exist: {path_obj}", file=sys.stderr)
            continue
        found = checker.find_datrix_files(path_obj)
        if found:
            print(f"  {path_obj.name}: {len(found)} files", flush=True)
        all_files.extend(found)

    if not all_files:
        print("No .dtrx files found to check.")
        return 0

    print(f"Found {len(all_files)} .dtrx files total.\n", flush=True)

    success = checker.check_files(all_files)
    checker.report()

    return 0 if success else 1


if __name__ == "__main__":
    sys.exit(main())
