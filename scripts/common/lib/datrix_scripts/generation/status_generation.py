"""Report generation status from the latest ``generate-results-*.log`` file.

The module behind ``generation/status-generation.ps1`` (and its ``.sh`` twin). Finds the latest
timestamped log under the results directory (default ``<workspace>/.generated/.results``; a
relative ``--results-dir`` is taken from the workspace root) and lists which projects succeeded
and failed, from its ``[N/M] <project>: Success|Failed`` lines.

Exit codes: 0 = no project failed, 1 = a project failed, or no results directory or log.

Usage:
    python -m datrix_scripts.generation.status_generation [--results-dir=<dir>]
"""

from __future__ import annotations

import argparse
import contextlib
import io
import re
import sys
import tempfile
from collections.abc import Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Final

from datrix_scripts.logging_utils import ColorCodes, colorize
from datrix_scripts.paths import WORKSPACE_DIR
from datrix_scripts.test.wrappers import GENERATION_SCRIPTS_DIR, module_main, run_self_test

MODULE: Final = "datrix_scripts.generation.status_generation"
WRAPPER: Final = "status-generation"
DEFAULT_RESULTS_DIR: Final = Path(".generated") / ".results"
LOG_GLOB: Final = "generate-results-*.log"
STATUS_LINE: Final = re.compile(r"^\s*\[(\d+)/(\d+)\]\s+([^:]+):\s+(Success|Failed)\s*$")
TIMESTAMP_LINE: Final = re.compile(r"^Timestamp:\s+(.+)$")
SUCCESS: Final = "Success"
RULE: Final = "=" * 80
EXIT_OK: Final = 0
EXIT_FAILED: Final = 1


@dataclass
class GenerationStatus:
    """What one results log says."""

    log_path: Path
    timestamp: str | None = None
    succeeded: list[str] = field(default_factory=list)
    failed: list[str] = field(default_factory=list)
    total_expected: int | None = None


class ResultsNotFound(Exception):
    """No results directory, or no log in it."""


def results_dir(value: str, workspace: Path) -> Path:
    """The results directory *value* names (empty: the default under *workspace*)."""
    if not value.strip():
        return workspace / DEFAULT_RESULTS_DIR
    path = Path(value)
    return path if path.is_absolute() else (workspace / path).resolve()


def latest_log(directory: Path) -> Path:
    """The newest ``generate-results-*.log`` (names sort chronologically: ``generate-results-YYYYMMDD-HHMMSS``)."""
    if not directory.is_dir():
        raise ResultsNotFound(f"Results directory not found: {directory}")
    logs = sorted((path for path in directory.glob(LOG_GLOB) if path.is_file()), key=lambda path: path.name)
    if not logs:
        raise ResultsNotFound(f"No {LOG_GLOB} files found in {directory}")
    return logs[-1]


def parse_log(log: Path) -> GenerationStatus:
    status = GenerationStatus(log_path=log)
    for line in log.read_text(encoding="utf-8", errors="replace").splitlines():
        timestamp = TIMESTAMP_LINE.match(line)
        if status.timestamp is None and timestamp:
            status.timestamp = timestamp.group(1).strip()
        match = STATUS_LINE.match(line)
        if match:
            status.total_expected = int(match.group(2))
            (status.succeeded if match.group(4) == SUCCESS else status.failed).append(match.group(3).strip())
    return status


def _section(title: str, names: Sequence[str], marker: str, color: str) -> None:
    if not names:
        return
    print(colorize(f"{title} ({len(names)})", color))
    for name in names:
        print(colorize(f" {marker} {name}", color))
    print()


def print_report(status: GenerationStatus) -> None:
    print(RULE)
    print(colorize("GENERATION STATUS REPORT", ColorCodes.CYAN))
    print(RULE)
    print()
    print(f"Log file: {status.log_path}")
    if status.timestamp:
        print(colorize(f"Timestamp: {status.timestamp}", ColorCodes.GRAY))
    if status.total_expected is not None:
        print(f"Projects in log: {len(status.succeeded) + len(status.failed)} / {status.total_expected}")
    print()
    _section("SUCCEEDED", status.succeeded, "[OK]", ColorCodes.GREEN)
    _section("FAILED", status.failed, "[X]", ColorCodes.RED)
    print(RULE)
    print(colorize("SUMMARY", ColorCodes.CYAN))
    print(RULE)
    print(f"Succeeded: {len(status.succeeded)}")
    print(f"Failed: {len(status.failed)}")
    if status.total_expected is not None:
        pending = status.total_expected - len(status.succeeded) - len(status.failed)
        if pending > 0:
            print(f"Pending: {pending} (run may still be in progress)")
    print(RULE)


def report(directory: Path) -> int:
    try:
        status = parse_log(latest_log(directory))
    except ResultsNotFound as exc:
        print(f"ERROR: {exc}. Pass -ResultsDir with the directory generate.ps1 wrote its logs to.", file=sys.stderr)
        return EXIT_FAILED
    print_report(status)
    return EXIT_FAILED if status.failed else EXIT_OK


def build_parser() -> argparse.ArgumentParser:
    """The options of ``generation/status-generation.ps1``: one per wrapper parameter, spelled exactly."""
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter, allow_abbrev=False
    )
    parser.add_argument("--results-dir", default="",
                        help="Results directory, relative to the workspace root or absolute (default: .generated/.results).")
    parser.add_argument("--self-test", action="store_true",
                        help="Run only the self-test: the latest planted log is read, and a failure exits 1.")
    parser.set_defaults(debug=False)
    return parser


_PLANTED_LOG: Final = "Timestamp: 2026-01-01 10:00:00\n[1/3] shop: Success\n[2/3] billing: Failed\n"


def _check_the_latest_log_is_reported() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        directory = Path(tmp)
        (directory / "generate-results-20260101-090000.log").write_text("[1/1] old: Success\n", encoding="utf-8")
        (directory / "generate-results-20260101-100000.log").write_text(_PLANTED_LOG, encoding="utf-8")
        with contextlib.redirect_stdout(io.StringIO()) as printed:
            code = report(directory)
    text = printed.getvalue()
    assert code == EXIT_FAILED, f"a failed project exited {code}"
    assert " [X] billing" in text and " [OK] shop" in text and "old" not in text, text
    assert "Pending: 1 (run may still be in progress)" in text, text


def _check_missing_results_exit_1() -> None:
    with tempfile.TemporaryDirectory() as tmp, contextlib.redirect_stderr(io.StringIO()) as errors:
        assert report(Path(tmp) / "no-such") == EXIT_FAILED
        assert report(Path(tmp)) == EXIT_FAILED
    assert "Results directory not found" in errors.getvalue() and "No generate-results" in errors.getvalue()
    assert results_dir("", Path("ws")) == Path("ws") / DEFAULT_RESULTS_DIR


def _run(args: argparse.Namespace) -> int:
    if args.self_test:
        checks = [_check_the_latest_log_is_reported, _check_missing_results_exit_1]
        return run_self_test(checks, wrapper=WRAPPER, module=MODULE, parser=build_parser(),
                             folder=GENERATION_SCRIPTS_DIR)
    return report(results_dir(args.results_dir, WORKSPACE_DIR))


def main(argv: Sequence[str] | None = None) -> int:
    """Entry point."""
    return module_main(build_parser(), _run, argv)


if __name__ == "__main__":
    sys.exit(main())
