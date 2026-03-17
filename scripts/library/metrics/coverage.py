#!/usr/bin/env python3
"""
Run pytest with coverage on a Datrix project and display coverage details.

Runs the test suite with pytest-cov and outputs a coverage report. Optionally
fails (exit 1) if total coverage is below a threshold (--fail-under).

Usage:
    python coverage.py --project-root D:\\datrix\\datrix-common
    python coverage.py --project-root D:\\datrix\\datrix-common --format html
    python coverage.py --project-root D:\\datrix\\datrix-common --fail-under 90 --verbose
"""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
from pathlib import Path

COVERAGE_FORMATS = ("term", "term-missing", "html", "xml")
DEFAULT_FORMAT = "term-missing"

# Pattern for the TOTAL line from coverage report: "TOTAL ... 6017  696  88%"
_COVERAGE_TOTAL_RE = re.compile(r"TOTAL\s+.*\s+(\d+(?:\.\d+)?)%\s*$")


def _check_pytest_cov() -> None:
    """Raise SystemExit(2) with message if pytest-cov is not installed."""
    try:
        import pytest_cov  # noqa: F401
    except ImportError:
        print(
            "Error: pytest-cov is not installed. Install with: pip install pytest-cov",
            file=sys.stderr,
        )
        sys.exit(2)


def _coverage_source(project_root: Path) -> str:
    """Return coverage source path (src or src/datrix) for the project."""
    if (project_root / "src" / "datrix").exists():
        return "src/datrix"
    return "src"


def _write_summary_file(
    summary_file: Path,
    project_root: Path,
    exit_code: int,
    fail_under: float | None,
) -> None:
    """Run coverage report, parse total percent, write one line to summary_file for the script."""
    try:
        rep = subprocess.run(
            [sys.executable, "-m", "coverage", "report"],
            capture_output=True,
            text=True,
            cwd=str(project_root),
            timeout=30,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired):
        summary_file.write_text("error 0 unknown\n")
        return

    total_pct: float | None = None
    if rep.stdout:
        for line in rep.stdout.strip().splitlines():
            m = _COVERAGE_TOTAL_RE.search(line.strip())
            if m:
                total_pct = float(m.group(1))
                break

    if total_pct is None:
        summary_file.write_text("error 0 unknown\n")
        return

    fail_under_val = fail_under if fail_under is not None else 0.0
    status = "fail" if exit_code != 0 else "pass"
    summary_file.write_text(f"{total_pct:.2f} {fail_under_val:.1f} {status}\n")


def main() -> int:
    """Run pytest with coverage for the given project. Return exit code (0, 1, or 2)."""
    parser = argparse.ArgumentParser(
        description="Run pytest with coverage for a Datrix project.",
    )
    parser.add_argument(
        "--project-root",
        type=Path,
        required=True,
        help="Path to the project root (containing src/ and tests/).",
    )
    parser.add_argument(
        "--format",
        choices=COVERAGE_FORMATS,
        default=DEFAULT_FORMAT,
        help=f"Coverage report format (default: {DEFAULT_FORMAT}).",
    )
    parser.add_argument(
        "--fail-under",
        type=float,
        default=None,
        metavar="N",
        help="Exit with code 1 if total coverage is below N percent.",
    )
    parser.add_argument("--verbose", action="store_true", help="Verbose pytest output (-v).")
    parser.add_argument(
        "--summary-file",
        type=Path,
        default=None,
        help="Write one-line coverage summary (percent fail_under status) for script summary.",
    )

    args = parser.parse_args()
    _check_pytest_cov()
    project_root = args.project_root.resolve()

    if not project_root.is_dir():
        print(
            f"Error: project root is not a directory: {project_root}",
            file=sys.stderr,
        )
        return 1

    src = project_root / "src"
    if not src.is_dir():
        print(
            f"Error: project has no src/ directory: {project_root}",
            file=sys.stderr,
        )
        return 1

    tests_dir = project_root / "tests"
    if not tests_dir.is_dir():
        print(
            f"Error: project has no tests/ directory: {project_root}",
            file=sys.stderr,
        )
        return 1

    coverage_source = _coverage_source(project_root)

    cmd: list[str] = [
        sys.executable,
        "-m",
        "pytest",
        "tests/",
        f"--cov={coverage_source}",
        f"--cov-report={args.format}",
    ]
    if args.fail_under is not None:
        cmd.append(f"--cov-fail-under={args.fail_under}")
    if args.verbose:
        cmd.append("-v")

    try:
        result = subprocess.run(
            cmd,
            cwd=str(project_root),
        )
    except FileNotFoundError as e:
        print(f"Error: could not run pytest: {e}", file=sys.stderr)
        return 2

    if args.summary_file is not None:
        _write_summary_file(
            args.summary_file.resolve(),
            project_root,
            result.returncode,
            args.fail_under,
        )

    return result.returncode


if __name__ == "__main__":
    sys.exit(main())
