"""Semantic linter for Datrix .dtrx files.

The module behind ``scan/datrix-linter.ps1`` (and its ``.sh`` twin). Discovers system.dtrx entry
points under the given paths (each a directory, scanned recursively, or a direct path to a
system.dtrx file), runs the full Datrix semantic analysis pipeline on each one, and reports all
diagnostics (errors and warnings) with codes, severities, messages, and source locations.

Exit codes:
  0  No issues found
  1  One or more errors found (or warnings in --strict mode); or no path and no --all (the
     usage), or both

Usage::

    python -m datrix_scripts.scan.datrix_linter --path=examples/01-foundation
    python -m datrix_scripts.scan.datrix_linter --all
    python -m datrix_scripts.scan.datrix_linter --path=examples/01-foundation --strict
    python -m datrix_scripts.scan.datrix_linter --path=examples/01-foundation --resolve-configs --profile=production
"""

from __future__ import annotations

import argparse
import contextlib
import io
import logging
import os
import sys
import tempfile
from collections.abc import Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Final

if TYPE_CHECKING:
    # Imported for annotations only -- the runtime imports stay function-local
    # inside _get_parser()/_get_analyzer() so `--help` and path discovery do not
    # pay the tree-sitter/semantic-analyzer import cost.
    from datrix_common.datrix_model.containers import Application
    from datrix_language.parser.tree_sitter_datrix.parser import TreeSitterParser
    from datrix_semantic.analyzer import SemanticAnalyzer

from datrix_scripts.gate_harness import WRAPPER_DEBUG_FLAG, install_sigint_handler, write_files
from datrix_scripts.paths import WORKSPACE_DIR
from datrix_scripts.scan.selection import (
    BOTH_SELECTED,
    SelectionRefused,
    expect_refusal,
    require_selection,
    wrapper_usage,
)
from datrix_scripts.test.wrappers import SCAN_SCRIPTS_DIR, module_main, run_self_test

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

MODULE: Final = "datrix_scripts.scan.datrix_linter"
WRAPPER: Final = "datrix-linter"
DEFAULT_PROFILE: Final = "development"

_USAGE: Final = wrapper_usage(WRAPPER, ["-All [-Strict] [-Dbg]", "<path> [path2 ...] [-Strict] [-Dbg]"])

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
# Path helpers
# ---------------------------------------------------------------------------

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
        profile: str = DEFAULT_PROFILE,
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
        self._parser: TreeSitterParser | None = None
        self._analyzer: SemanticAnalyzer | None = None

    def _dbg(self, message: str) -> None:
        if self.debug:
            print(f"[DEBUG] {message}", file=sys.stderr, flush=True)

    def _get_parser(self) -> TreeSitterParser:
        if self._parser is None:
            from datrix_language.parser.tree_sitter_datrix.parser import TreeSitterParser
            from datrix_language.registration import register_all
            self._dbg("Initialising TreeSitterParser + registering stdlib parser...")
            register_all()
            self._parser = TreeSitterParser()
            self._dbg("Parser ready.")
        return self._parser

    def _get_analyzer(self) -> SemanticAnalyzer:
        if self._analyzer is None:
            from datrix_semantic.analyzer import SemanticAnalyzer
            self._analyzer = SemanticAnalyzer()
            self._dbg("SemanticAnalyzer ready.")
        return self._analyzer

    def _resolve_service_configs(self, app: Application, project_root: Path) -> list[str]:
        """Resolve service/shared config profiles before semantic validation."""
        from datrix_common.config_resolution import (
            ConfigResolutionError,
            resolve_service_configs,
        )

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
            parser = self._get_parser()
            app = parser.parse_loaded_file(content, entry_point)
            # Every .dcfg (config resolution, and the strings files semantic
            # analysis loads) is read through the application's source, as the
            # generation pipeline's attach_config_documents stage provides.
            from datrix_language.parser.dcfg_documents import disk_config_documents

            app.config_documents = disk_config_documents()
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
        from datrix_semantic.result import Severity

        skipped_codes = {"SVC007"} if not self.resolve_configs else set()
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

def build_parser() -> argparse.ArgumentParser:
    """The options of ``scan/datrix-linter.ps1``: one per wrapper parameter, spelled exactly."""
    parser = argparse.ArgumentParser(
        prog=WRAPPER, description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter, allow_abbrev=False
    )
    parser.add_argument("--path", action="append", default=[],
                        help="A directory (scanned for system.dtrx) or a system.dtrx file (repeatable).")
    parser.add_argument("--all", action="store_true",
                        help="Scan every non-hidden directory in the workspace root.")
    parser.add_argument("--strict", action="store_true",
                        help="Treat warnings as errors (non-zero exit if any warnings found).")
    parser.add_argument(WRAPPER_DEBUG_FLAG, dest="debug", action="store_true", help="Enable debug logging.")
    parser.add_argument("--resolve-configs", action="store_true",
                        help="Resolve service/shared .dcfg files before semantic checks (off by default).")
    parser.add_argument("--profile", default=DEFAULT_PROFILE,
                        help=f"Config profile used with --resolve-configs (default: {DEFAULT_PROFILE}).")
    parser.add_argument("--self-test", action="store_true",
                        help="Run only the self-test: a planted broken system.dtrx fails the lint, the "
                             "selection rules hold, and the wrapper seam holds.")
    return parser


def lint_targets(args: argparse.Namespace, workspace: Path) -> list[Path]:
    """The paths named, or with ``--all`` every non-hidden directory in *workspace*.

    Raises:
        SelectionRefused: neither or both were given.
    """
    require_selection(args.path, args.all, _USAGE)
    if args.all:
        # Only scan directories that are Datrix source projects or contain examples
        return sorted(d for d in workspace.iterdir() if d.is_dir() and not d.name.startswith("."))
    return [Path(p) for p in args.path]


def _check_a_broken_system_fails_the_lint() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        write_files(Path(tmp), {"planted/system.dtrx": "system planted.broken {\n service {\n"})
        args = build_parser().parse_args([f"--path={tmp}"])
        with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
            code = lint_paths(lint_targets(args, WORKSPACE_DIR), args)
        assert code == 1, f"a system.dtrx that does not parse must exit 1, got {code}"


def _check_nothing_selected_prints_the_usage() -> None:
    expect_refusal(lambda: lint_targets(build_parser().parse_args([]), WORKSPACE_DIR), 1, _USAGE)


def _check_paths_with_all_are_refused() -> None:
    args = build_parser().parse_args(["--all", "--path=x"])
    expect_refusal(lambda: lint_targets(args, WORKSPACE_DIR), 1, BOTH_SELECTED)


def _run(args: argparse.Namespace) -> int:
    """The linter reports by printing. The parser and analyzer log their builtin loading at INFO, which is
    noise in its report, so the root logger stays at WARNING unless ``--dbg`` asks for DEBUG."""
    install_sigint_handler()
    if not args.debug:
        logging.getLogger().setLevel(logging.WARNING)
    if args.self_test:
        checks = [
            _check_a_broken_system_fails_the_lint,
            _check_nothing_selected_prints_the_usage,
            _check_paths_with_all_are_refused,
        ]
        return run_self_test(checks, wrapper=WRAPPER, module=MODULE, parser=build_parser(), folder=SCAN_SCRIPTS_DIR)
    try:
        input_paths = lint_targets(args, WORKSPACE_DIR)
    except SelectionRefused as refused:
        return refused.report()
    return lint_paths(input_paths, args)


def lint_paths(input_paths: Sequence[Path], args: argparse.Namespace) -> int:
    """Lint every system.dtrx entry point under *input_paths* with *args*' options; the report's exit code."""
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


def main(argv: Sequence[str] | None = None) -> int:
    """Entry point."""
    return module_main(build_parser(), _run, argv)


if __name__ == "__main__":
    sys.exit(main())

