#!/usr/bin/env python3
"""Aggregate a GREEN/RED test gate verdict across Datrix packages.

For each requested project (or all testable packages with --all), finds the
newest test-results run, reads its structured results, and reports a
per-project GREEN/RED verdict plus an overall verdict. Reuses the discovery
and index parsing from ``test/status_tests.py`` (find_latest_log_file,
parse_pytest_summary, get_datrix_projects).

Usage:
  python scripts/library/test/gate_verdict.py --projects datrix-common,datrix-language
  python scripts/library/test/gate_verdict.py --all
  .\\scripts\\test\\gate-verdict.ps1 -Projects datrix-common,datrix-language
  .\\scripts\\test\\gate-verdict.ps1 -All

Exit codes: 0 = overall GREEN, 1 = overall RED, 2 = usage error.
"""

from __future__ import annotations

import argparse
import io
import json
import logging
import sys
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

# Configure UTF-8 encoding for stdout/stderr on Windows
if sys.platform == "win32" and __name__ == "__main__":
    if hasattr(sys.stdout, "buffer"):
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    if hasattr(sys.stderr, "buffer"):
        sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

# Add library directory to sys.path to import from shared and sibling modules
_LIBRARY_DIR = Path(__file__).resolve().parent.parent
if _LIBRARY_DIR.exists() and str(_LIBRARY_DIR) not in sys.path:
    sys.path.insert(0, str(_LIBRARY_DIR))

from shared.venv import get_datrix_root  # noqa: E402
from test.status_tests import (  # noqa: E402
    find_latest_log_file,
    get_datrix_projects,
    parse_pytest_summary,
    parse_timestamp_from_log_file,
)

logger = logging.getLogger(__name__)

_SCHEMA_VERSION = 1
_OUTPUT_FILENAME = "gate-verdict.json"
_OUTPUT_SUBDIRS = ("test",)
_INDEX_JSON_NAME = "index.json"
_FAILING_CAP = 50
_GREEN = "GREEN"
_RED = "RED"
_REASON_NO_RESULTS = "NO_RESULTS"
_STATUS_PASSED = "PASSED"
_EXIT_GREEN = 0
_EXIT_RED = 1
_EXIT_USAGE = 2


class UsageError(Exception):
    """Invalid usage or missing input; the script exits with code 2."""


@dataclass(frozen=True)
class ProjectVerdict:
    """Gate verdict for one project's newest test-results run."""

    project: str
    run_dir: str | None
    result: str | None
    counts: dict[str, int] | None
    verdict: str
    reason: str | None
    failing: list[dict[str, str]]
    failing_total: int
    age_minutes: float | None

    def to_json(self) -> dict[str, object]:
        """Serialize for the output payload."""
        return {
            "project": self.project,
            "run_dir": self.run_dir,
            "result": self.result,
            "counts": self.counts,
            "verdict": self.verdict,
            "reason": self.reason,
            "failing": self.failing,
            "failing_total": self.failing_total,
            "age_minutes": self.age_minutes,
        }


def _no_results_verdict(project: str) -> ProjectVerdict:
    """Verdict row for a project with no test results at all."""
    return ProjectVerdict(
        project=project,
        run_dir=None,
        result=None,
        counts=None,
        verdict=_RED,
        reason=_REASON_NO_RESULTS,
        failing=[],
        failing_total=0,
        age_minutes=None,
    )


def _entry_str(entry: dict[str, object], key: str) -> str:
    """String value of an entry key; '' when the schema variant lacks it."""
    if key in entry and isinstance(entry[key], str):
        return str(entry[key])
    return ""


def _collect_failing(latest: Path, fallback_total: int) -> tuple[list[dict[str, str]], int]:
    """Failing test details (capped) plus the uncapped total.

    Reads the index.json failures/errors arrays when available. When the
    newest run only has a full.log (no structured index), the detail list is
    empty and the total comes from the parsed log counts.
    """
    if latest.name != _INDEX_JSON_NAME:
        return [], fallback_total
    try:
        raw = json.loads(latest.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        logger.warning("failing_list_unavailable path=%s error=%s", latest, exc)
        return [], fallback_total
    if not isinstance(raw, dict):
        logger.warning("failing_list_unavailable path=%s error=root is not an object", latest)
        return [], fallback_total

    failing: list[dict[str, str]] = []
    total = 0
    for key in ("failures", "errors"):
        if key not in raw or not isinstance(raw[key], list):
            continue
        for item in raw[key]:
            if not isinstance(item, dict):
                continue
            entry = {str(k): v for k, v in item.items()}
            total += 1
            if len(failing) >= _FAILING_CAP:
                continue
            failing.append(
                {
                    "test_id": _entry_str(entry, "test_id"),
                    "error_type": _entry_str(entry, "error_type"),
                    "source_location": _entry_str(entry, "source_location"),
                }
            )
    return failing, total


def _age_minutes(run_dir_name: str) -> float | None:
    """Minutes elapsed since the run directory's timestamp."""
    timestamp = parse_timestamp_from_log_file(run_dir_name)
    if timestamp is None:
        return None
    return round((datetime.now() - timestamp).total_seconds() / 60.0, 1)


def _evaluate_project(workspace: Path, project: str) -> ProjectVerdict:
    """Evaluate one project's newest test-results run."""
    test_results_dir = workspace / project / ".test_results"
    if not test_results_dir.is_dir():
        return _no_results_verdict(project)
    latest = find_latest_log_file(test_results_dir)
    if latest is None:
        return _no_results_verdict(project)

    parsed = parse_pytest_summary(latest)
    run_dir = latest.parent
    verdict = _GREEN if parsed.status == _STATUS_PASSED else _RED
    failing, failing_total = _collect_failing(
        latest, parsed.total_failed + parsed.total_errors
    )
    return ProjectVerdict(
        project=project,
        run_dir=str(run_dir),
        result=parsed.status,
        counts={
            "passed": parsed.total_passed,
            "failed": parsed.total_failed,
            "error": parsed.total_errors,
            "skipped": parsed.total_skipped,
        },
        verdict=verdict,
        reason=None if verdict == _GREEN else parsed.status,
        failing=failing,
        failing_total=failing_total,
        age_minutes=_age_minutes(run_dir.name),
    )


def _format_project_line(row: ProjectVerdict) -> str:
    """One console line per project."""
    if row.reason == _REASON_NO_RESULTS:
        return f"{row.project}: {_RED} {_REASON_NO_RESULTS}"
    counts = row.counts if row.counts is not None else {}
    passed = counts["passed"] if "passed" in counts else 0
    if row.verdict == _GREEN:
        return f"{row.project}: {_GREEN} {passed} passed"
    failed = counts["failed"] if "failed" in counts else 0
    errors = counts["error"] if "error" in counts else 0
    return (
        f"{row.project}: {_RED} {failed} failed, {errors} errors "
        f"({passed} passed, result={row.result})"
    )


@dataclass(frozen=True)
class GateVerdictResult:
    """Aggregate GREEN/RED verdict across a set of projects.

    Returned by ``evaluate_projects``, the public entry point other modules
    (e.g. a concurrent scheduler) use to reuse this module's own per-project
    evaluation and formatting instead of reimplementing ``index.json``
    parsing or verdict-line formatting.
    """

    rows: list[ProjectVerdict]
    overall: str
    payload: dict[str, object]
    report_lines: list[str]
    exit_code: int


def _forced_red_verdict(project: str, reason: str) -> ProjectVerdict:
    """Verdict row for a project reported RED by caller instruction, without
    consulting its newest run.

    Used by ``evaluate_projects``'s ``forced_red`` argument: a caller that
    knows a project's test run crashed before producing any results must not
    fall through to this module's own newest-run lookup, which would find
    whatever OLDER run is sitting on disk -- including a stale GREEN one.
    """
    return ProjectVerdict(
        project=project,
        run_dir=None,
        result=None,
        counts=None,
        verdict=_RED,
        reason=reason,
        failing=[],
        failing_total=0,
        age_minutes=None,
    )


def evaluate_projects(
    workspace: Path,
    projects: Sequence[str],
    *,
    forced_red: Mapping[str, str] | None = None,
) -> GateVerdictResult:
    """Evaluate each project's newest run and return the aggregate verdict.

    This is the module's public entry point for reuse by other tooling
    (e.g. a concurrent scheduler that must aggregate a final verdict without
    reimplementing ``index.json`` parsing or verdict-line formatting). The
    CLI (``_run``) also calls this function, so its own console output and
    exit codes stay driven by exactly one evaluation path.

    Args:
        workspace: Monorepo root containing the package directories.
        projects: Package names to evaluate, in report order.
        forced_red: Optional package -> reason map. A package listed here is
            reported RED with that reason WITHOUT consulting its newest run --
            used by callers that know a run crashed and must not be allowed to
            pass on a stale prior result.

    Returns:
        The aggregate result: per-project rows, the overall verdict, the
        serializable payload, the formatted per-project report lines, and
        the process exit code.
    """
    forced = forced_red or {}
    rows = [
        _forced_red_verdict(project, forced[project])
        if project in forced
        else _evaluate_project(workspace, project)
        for project in projects
    ]
    overall = _GREEN if all(row.verdict == _GREEN for row in rows) else _RED
    payload: dict[str, object] = {
        "schema_version": _SCHEMA_VERSION,
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "overall_verdict": overall,
        "projects": [row.to_json() for row in rows],
    }
    report_lines = [_format_project_line(row) for row in rows]
    exit_code = _EXIT_GREEN if overall == _GREEN else _EXIT_RED
    return GateVerdictResult(
        rows=rows,
        overall=overall,
        payload=payload,
        report_lines=report_lines,
        exit_code=exit_code,
    )


def _resolve_projects(args: argparse.Namespace, workspace: Path) -> list[str]:
    """Resolve and validate the requested project list."""
    testable = get_datrix_projects(workspace)
    if args.all:
        if args.projects:
            raise UsageError("Use either --projects or --all, not both.")
        if not testable:
            raise UsageError(
                f"No testable datrix-* packages found under {workspace} (a "
                f"package is testable when it carries a tests/ directory or a "
                f"package.json declaring a test script). Expected the Datrix "
                f"monorepo layout."
            )
        return testable
    if not args.projects:
        raise UsageError(
            "No projects specified. Pass --projects <a,b,c> or --all."
        )
    names: list[str] = []
    for chunk in args.projects:
        names.extend(name.strip() for name in chunk.split(",") if name.strip())
    names = list(dict.fromkeys(names))
    if not names:
        raise UsageError("The --projects list is empty. Pass --projects <a,b,c> or --all.")
    unknown = [name for name in names if name not in testable]
    if unknown:
        raise UsageError(
            f"Unknown or untestable project(s): {', '.join(unknown)}. "
            f"Valid testable packages: {', '.join(testable)}."
        )
    return names


def _resolve_output_path(raw_output: str | None, workspace: Path) -> Path:
    """Default to <workspace>/.tmp/test/gate-verdict.json unless overridden."""
    if raw_output:
        output_path = Path(raw_output).resolve()
    else:
        output_path = workspace.joinpath(".tmp", *_OUTPUT_SUBDIRS, _OUTPUT_FILENAME)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    return output_path


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Aggregate a GREEN/RED test gate verdict across Datrix packages."
    )
    parser.add_argument(
        "--projects",
        action="append",
        help="Project name(s); repeatable and/or comma-separated",
    )
    parser.add_argument(
        "--all",
        action="store_true",
        help="Check all testable datrix-* packages",
    )
    parser.add_argument(
        "--output",
        help="Output JSON path (default <workspace>/.tmp/test/gate-verdict.json)",
    )
    parser.add_argument("--debug", action="store_true", help="Enable debug logging")
    return parser.parse_args()


def _configure_logging(debug: bool) -> None:
    logging.basicConfig(
        level=logging.DEBUG if debug else logging.INFO,
        format="%(levelname)s %(name)s: %(message)s",
        stream=sys.stderr,
    )


def _run(args: argparse.Namespace) -> int:
    workspace = get_datrix_root()
    projects = _resolve_projects(args, workspace)
    output_path = _resolve_output_path(args.output, workspace)

    result = evaluate_projects(workspace, projects)

    output_path.write_text(
        json.dumps(result.payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )

    for line in result.report_lines:
        print(line)
    print(f"OVERALL: {result.overall}")
    print(f"Details: {output_path}")
    return result.exit_code


def main() -> int:
    """Entry point."""
    args = _parse_args()
    _configure_logging(args.debug)
    try:
        return _run(args)
    except UsageError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return _EXIT_USAGE


if __name__ == "__main__":
    sys.exit(main())
