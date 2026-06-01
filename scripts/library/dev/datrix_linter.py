#!/usr/bin/env python3
"""Semantic linter for Datrix .dtrx files.

Discovers system.dtrx entry points under the given paths, runs the full
Datrix semantic analysis pipeline on each one, and reports all diagnostics
(errors and warnings) with codes, severities, messages, and source locations.

Exit codes:
  0  No issues found
  1  One or more errors found (or warnings in --strict mode)

Usage::

    python datrix_linter.py examples/01-foundation
    python datrix_linter.py --all
    python datrix_linter.py examples/01-foundation --strict
    python datrix_linter.py examples/01-foundation --debug
"""

from __future__ import annotations

import argparse
import io
import os
import signal
import sys
from dataclasses import dataclass, field
from pathlib import Path

# ── UTF-8 stdout/stderr on Windows ──────────────────────────────────────────
if sys.platform == "win32" and __name__ == "__main__":
    if hasattr(sys.stdout, "buffer"):
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    if hasattr(sys.stderr, "buffer"):
        sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

# ── sys.path bootstrap ───────────────────────────────────────────────────────
_library_dir = Path(__file__).resolve().parent.parent
if _library_dir.exists() and str(_library_dir) not in sys.path:
    sys.path.insert(0, str(_library_dir))

from shared.venv import get_datrix_root  # noqa: E402

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

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

_DTRX_SUFFIX = ".dtrx"
_ENTRY_POINT_NAME = "system.dtrx"


# ---------------------------------------------------------------------------
# Signal handler
# ---------------------------------------------------------------------------

def _sigint_handler(_signum: int, _frame: object) -> None:
    """Exit cleanly on Ctrl-C."""
    sys.exit(130)


# ---------------------------------------------------------------------------
# Path helpers
# ---------------------------------------------------------------------------

def _add_src_packages_to_path(datrix_root: Path) -> None:
    """Add datrix-common and datrix-language src directories to sys.path."""
    for pkg in ("datrix-common", "datrix-language"):
        src = datrix_root / pkg / "src"
        if src.exists() and str(src) not in sys.path:
            sys.path.insert(0, str(src))


def _discover_entry_points(path: Path) -> list[Path]:
    """Recursively find system.dtrx entry point files under *path*.

    If *path* is itself a ``system.dtrx`` file it is returned directly.
    Directories containing ``system.dtrx`` are treated as project roots.
    Skips hidden/generated/build directories.

    Args:
        path: File or directory to scan.

    Returns:
        Sorted list of absolute ``system.dtrx`` paths.
    """
    found: list[Path] = []
    path = path.resolve()

    if path.is_file():
        if path.name == _ENTRY_POINT_NAME:
            found.append(path)
        elif path.suffix == _DTRX_SUFFIX:
            # Accept a non-system.dtrx file too — will be linted without include resolution
            found.append(path)
        return found

    if not path.is_dir():
        return found

    for dir_path, dirnames, filenames in os.walk(path, followlinks=False):
        dirnames[:] = [
            d for d in dirnames
            if d not in _SKIP_DIRS and not d.endswith(".egg-info")
        ]
        for name in filenames:
            if name == _ENTRY_POINT_NAME:
                found.append(Path(dir_path) / name)

    return sorted(found)


# ---------------------------------------------------------------------------
# Diagnostic model helpers
# ---------------------------------------------------------------------------

@dataclass
class FileLintResult:
    """Collected lint results for a single project (system.dtrx)."""

    entry_point: Path
    parse_error: str | None = None
    error_count: int = 0
    warning_count: int = 0
    diagnostic_lines: list[str] = field(default_factory=list)

    @property
    def has_issues(self) -> bool:
        return self.parse_error is not None or self.error_count > 0 or self.warning_count > 0


# ---------------------------------------------------------------------------
# Core linting
# ---------------------------------------------------------------------------

class DatrixLinter:
    """Lint .dtrx entry points using the Datrix semantic analysis pipeline."""

    def __init__(
        self,
        *,
        strict: bool = False,
        debug: bool = False,
        resolve_configs: bool = False,
        profile: str = "development",
    ) -> None:
        self.strict = strict
        self.debug = debug
        self.resolve_configs = resolve_configs
        self.profile = profile
        self.projects_seen = 0
        self.projects_clean = 0
        self.total_errors = 0
        self.total_warnings = 0
        self.total_parse_errors = 0
        self._parser: object = None   # TreeSitterParser (lazy)
        self._analyzer: object = None  # SemanticAnalyzer (lazy)

    def _dbg(self, message: str) -> None:
        if self.debug:
            print(f"[DEBUG] {message}", file=sys.stderr, flush=True)

    def _get_parser(self) -> "TreeSitterParser":  # type: ignore[name-defined]
        if self._parser is None:
            from datrix_language.parser import TreeSitterParser
            from datrix_language.registration import register_all
            self._dbg("Initialising TreeSitterParser + registering stdlib parser...")
            register_all()
            self._parser = TreeSitterParser()
            self._dbg("Parser ready.")
        return self._parser  # type: ignore[return-value]

    def _get_analyzer(self) -> "SemanticAnalyzer":  # type: ignore[name-defined]
        if self._analyzer is None:
            from datrix_common.semantic import SemanticAnalyzer
            self._analyzer = SemanticAnalyzer()
            self._dbg("SemanticAnalyzer ready.")
        return self._analyzer  # type: ignore[return-value]

    def _resolve_service_configs(self, app: object, project_root: Path) -> list[str]:
        """Resolve service/shared config profiles before semantic validation."""
        from datrix_common.config_resolution import ConfigResolutionError, resolve_service_configs

        try:
            resolve_service_configs(app, project_root, self.profile)
            return []
        except ConfigResolutionError as exc:
            return list(exc.errors)
        except Exception as exc:
            # Some resolver failures bubble up as non-ConfigResolutionError exceptions.
            return [str(exc)]

    def lint_file(self, entry_point: Path) -> FileLintResult:
        """Parse and semantically analyse a single system.dtrx entry point.

        Args:
            entry_point: Path to the system.dtrx file.

        Returns:
            FileLintResult with all diagnostics.
        """
        self.projects_seen += 1
        result = FileLintResult(entry_point=entry_point)

        self._dbg(f"Linting {entry_point}")

        # ── Parse ────────────────────────────────────────────────────────────
        try:
            content = entry_point.read_text(encoding="utf-8-sig")
        except Exception as exc:
            result.parse_error = f"Cannot read file: {exc}"
            self.total_parse_errors += 1
            print(f"ERROR {entry_point}: {result.parse_error}")
            return result

        if not content.strip():
            result.parse_error = "File is empty"
            self.total_parse_errors += 1
            print(f"ERROR {entry_point}: {result.parse_error}")
            return result

        try:
            from datrix_common.errors import ParseError as _ParseError
            parser = self._get_parser()
            app = parser.parse_loaded_file(content, entry_point)
            self._dbg(f"Parsed OK: {entry_point}")
        except Exception as exc:
            msg = str(exc)
            result.parse_error = msg
            self.total_parse_errors += 1
            print(f"ERROR {entry_point}: Parse error: {msg}")
            return result

        # Optional config resolution. Disabled by default to keep linter focused on .dtrx.
        if self.resolve_configs:
            config_errors = self._resolve_service_configs(app, entry_point.parent)
            for err in config_errors:
                self.total_errors += 1
                result.error_count += 1
                line_str = f"ERROR {entry_point} [CFG001] {err.replace(chr(10), ' ')}"
                result.diagnostic_lines.append(line_str)
                print(line_str)

        # ── Semantic analysis ─────────────────────────────────────────────────
        try:
            analyzer = self._get_analyzer()
            analysis = analyzer.analyze(app)
        except Exception as exc:
            result.parse_error = f"Semantic analysis failed: {exc}"
            self.total_parse_errors += 1
            print(f"ERROR {entry_point}: {result.parse_error}")
            return result

        # ── Report diagnostics ────────────────────────────────────────────────
        from datrix_common.semantic.result import Severity

        skipped_codes = {"SVC006", "SVC007"} if not self.resolve_configs else set()
        for diag in analysis.diagnostics:
            if diag.code in skipped_codes:
                continue
            loc = diag.location
            if loc is not None and loc.file_path is not None:
                file_str = str(loc.file_path)
            else:
                file_str = str(entry_point)

            line = loc.line if loc is not None else None
            col = loc.column if loc is not None else None

            location_str = file_str
            if line is not None:
                location_str += f":{line}"
                if col is not None:
                    location_str += f":{col}"

            tag = f"[{diag.code}]"
            msg = diag.message.replace("\n", " ")

            if diag.severity == Severity.ERROR:
                line_str = f"ERROR {location_str} {tag} {msg}"
                result.error_count += 1
                self.total_errors += 1
            else:
                line_str = f"WARN  {location_str} {tag} {msg}"
                result.warning_count += 1
                self.total_warnings += 1

            result.diagnostic_lines.append(line_str)
            print(line_str)

        if not result.has_issues:
            self.projects_clean += 1
            self._dbg(f"Clean: {entry_point}")

        return result

    def report(self) -> int:
        """Print summary and return exit code.

        Returns:
            0 if no errors (and no warnings in strict mode), 1 otherwise.
        """
        print()
        print("Datrix linter summary")
        print("---------------------")
        print(f"Projects scanned:     {self.projects_seen}")
        print(f"Projects clean:       {self.projects_clean}")
        print(f"Parse errors:         {self.total_parse_errors}")
        print(f"Semantic errors:      {self.total_errors}")
        print(f"Warnings:             {self.total_warnings}")
        if self.strict:
            print("Mode:                 strict (warnings treated as errors)")

        if self.total_parse_errors > 0 or self.total_errors > 0:
            return 1
        if self.strict and self.total_warnings > 0:
            return 1
        return 0


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

def main() -> int:
    signal.signal(signal.SIGINT, _sigint_handler)

    parser = argparse.ArgumentParser(
        description="Semantic linter for Datrix .dtrx files",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Each path may be a directory (recursively scanned for system.dtrx)\n"
            "or a direct path to a system.dtrx file.\n\n"
            "Examples:\n"
            "  datrix_linter.py examples/01-foundation\n"
            "  datrix_linter.py --all\n"
            "  datrix_linter.py datrix-projects/curvaero/curvaero-backend/system.dtrx --strict\n"
        ),
    )
    parser.add_argument(
        "paths",
        nargs="*",
        help="Paths to scan (file or directory)",
    )
    parser.add_argument(
        "--all",
        "-a",
        action="store_true",
        help="Scan all datrix* subdirectories in the monorepo root",
    )
    parser.add_argument(
        "--resolve-configs",
        action="store_true",
        help="Resolve service/shared .dcfg files before semantic checks (off by default)",
    )
    parser.add_argument(
        "--profile",
        default="development",
        help="Config profile used with --resolve-configs (default: development)",
    )
    parser.add_argument(
        "--strict",
        action="store_true",
        help="Treat warnings as errors (non-zero exit if any warnings found)",
    )
    parser.add_argument(
        "--debug",
        action="store_true",
        help="Enable debug logging",
    )

    args = parser.parse_args()

    if args.all and args.paths:
        print("ERROR: Specify either paths or --all, not both.", file=sys.stderr)
        return 1
    if not args.all and not args.paths:
        parser.print_help()
        print("\nProvide one or more paths, or use --all.", file=sys.stderr)
        return 1

    # ── Resolve datrix root and add packages to sys.path ──────────────────
    try:
        datrix_root = get_datrix_root()
    except FileNotFoundError:
        print("ERROR: Could not find Datrix root directory.", file=sys.stderr)
        return 1

    _add_src_packages_to_path(datrix_root)

    # ── Build input path list ─────────────────────────────────────────────
    if args.all:
        # Only scan directories that are Datrix source projects or contain examples
        input_paths = sorted(
            d for d in datrix_root.iterdir()
            if d.is_dir() and not d.name.startswith(".")
        )
    else:
        input_paths = [Path(p) for p in args.paths]

    # Discover entry points for semantic lint.
    print("Discovering system.dtrx entry points...", flush=True)
    discovered: list[Path] = []
    for p in input_paths:
        if not p.exists():
            print(f"WARN  Path does not exist: {p}")
            continue
        found = _discover_entry_points(p)
        if found:
            print(f"  {p}: {len(found)} project(s)", flush=True)
        discovered.extend(found)

    unique_files = sorted(set(discovered))
    if not unique_files:
        print("No system.dtrx entry points found.")
        return 0

    print(f"Found {len(unique_files)} project(s) to lint.", flush=True)
    print()

    # ── Run linter ────────────────────────────────────────────────────────
    linter = DatrixLinter(
        strict=args.strict,
        debug=args.debug,
        resolve_configs=args.resolve_configs,
        profile=args.profile,
    )

    for entry_point in unique_files:
        linter.lint_file(entry_point)

    return linter.report()


if __name__ == "__main__":
    sys.exit(main())

