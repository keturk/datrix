#!/usr/bin/env python3
"""Aggregate a GREEN/RED test gate verdict across Datrix packages.

For each requested project (or all testable packages with --all), finds the
newest test-results run, reads its structured results, and reports a
per-project GREEN/RED verdict plus an overall verdict. Reuses the discovery
and index parsing from ``test/status_tests.py`` (find_latest_log_file,
parse_pytest_summary, get_datrix_projects).

A caller that decided NOT to run a package because its recorded green full
run still matches its suite-input fingerprint (the concurrent affected gate)
passes it through ``evaluate_projects(carried=...)``; its row is CARRIED --
green for the overall verdict, but always rendered and serialized as its own
verdict, naming the run, its age and the fingerprint that stood in.

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

#: 2: rows carry ``carried`` and ``fingerprint``, and ``verdict`` may be CARRIED.
_SCHEMA_VERSION = 2
_OUTPUT_FILENAME = "gate-verdict.json"
_OUTPUT_SUBDIRS = ("test",)
_INDEX_JSON_NAME = "index.json"
_FAILING_CAP = 50
_GREEN = "GREEN"
_RED = "RED"
#: A package whose recorded green full run stood in for a fresh one: counts as
#: green for OVERALL, but is never rendered or serialized as GREEN.
_CARRIED = "CARRIED"
_REASON_NO_RESULTS = "NO_RESULTS"
_REASON_CARRY_REJECTED = "CARRY_REJECTED"
_STATUS_PASSED = "PASSED"
_SELECTION_KEY = "selection"
_SELECTION_KIND_KEY = "kind"
_SELECTION_FULL = "full"
_INPUTS_KEY = "inputs"
_FINGERPRINT_KEY = "fingerprint"
_RESULT_KEY = "result"
_COUNTS_KEY = "counts"
_ZERO_COUNT_KEYS = ("failed", "error")
_FINGERPRINT_DISPLAY_CHARS = 16
_EXIT_GREEN = 0
_EXIT_RED = 1
_EXIT_USAGE = 2


class UsageError(Exception):
    """Invalid usage or missing input; the script exits with code 2."""


@dataclass(frozen=True)
class ProjectVerdict:
    """Gate verdict for one project's judged test-results run.

    ``carried`` is True only on a CARRIED row: the run it names was not
    launched by the caller -- it is a recorded green full run whose suite-input
    ``fingerprint`` (the one computed now, equal to the one it recorded) still
    holds, standing in for a fresh run.
    """

    project: str
    run_dir: str | None
    result: str | None
    counts: dict[str, int] | None
    verdict: str
    reason: str | None
    failing: list[dict[str, str]]
    failing_total: int
    age_minutes: float | None
    carried: bool = False
    fingerprint: str | None = None

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
            "carried": self.carried,
            "fingerprint": self.fingerprint,
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


_FULL_LOG_NAME = "full.log"
_REASON_PINNED_RUN_HAS_NO_RESULTS = "PINNED_RUN_HAS_NO_RESULTS"


def _results_file_in(run_dir: Path) -> Path | None:
    """The structured index of ONE named run, else its log, else None.

    The same discovery order ``find_latest_log_file`` applies to the newest
    run, applied to a run the caller has already chosen.
    """
    for name in (_INDEX_JSON_NAME, _FULL_LOG_NAME):
        candidate = run_dir / name
        if candidate.is_file():
            return candidate
    return None


def _pinned_run_missing_verdict(project: str, run_dir: Path) -> ProjectVerdict:
    """RED for a run the caller pinned that carries no results file.

    A pinned run that cannot be read is never allowed to fall through to the
    newest-run lookup: that lookup is exactly the path that let an unrelated,
    later run stand in for the one being judged.
    """
    return ProjectVerdict(
        project=project,
        run_dir=str(run_dir),
        result=None,
        counts=None,
        verdict=_RED,
        reason=_REASON_PINNED_RUN_HAS_NO_RESULTS,
        failing=[],
        failing_total=0,
        age_minutes=_age_minutes(run_dir.name),
    )


def _evaluate_project(
    workspace: Path, project: str, pinned_run: str | None = None
) -> ProjectVerdict:
    """Evaluate one project's test-results run.

    Without ``pinned_run`` this is the project's NEWEST run -- the right
    question for a status report. With it, it is exactly the named
    ``test-results-*`` directory and nothing else. A scheduler that launched
    the run must judge THAT run: between its child exiting and the verdict
    being aggregated, a targeted run from another session (or the same one)
    can land a newer directory, and the newest-run lookup would then report
    that unrelated result -- a GREEN targeted subset standing in for a RED
    whole suite. That false green was observed; pinning is what forbids it.
    """
    test_results_dir = workspace / project / ".test_results"
    if not test_results_dir.is_dir():
        return _no_results_verdict(project)
    if pinned_run is not None:
        pinned_dir = test_results_dir / pinned_run
        latest = _results_file_in(pinned_dir)
        if latest is None:
            return _pinned_run_missing_verdict(project, pinned_dir)
    else:
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


def _read_index_object(index_path: Path) -> dict[str, object]:
    """The parsed ``index.json`` object of one run.

    Raises:
        ValueError: if it cannot be read, is not JSON, or is not an object.
    """
    try:
        raw = json.loads(index_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"{index_path} is unreadable ({exc})") from exc
    if not isinstance(raw, dict):
        raise ValueError(f"{index_path} is not a JSON object")
    return {str(key): value for key, value in raw.items()}


def _is_zero_count(counts: object, key: str) -> bool:
    if not isinstance(counts, dict) or key not in counts:
        return False
    value = counts[key]
    return isinstance(value, int) and not isinstance(value, bool) and value == 0


def _carry_claim_problems(index: dict[str, object], fingerprint: str) -> list[str]:
    """Why the named run cannot stand in for a fresh one; empty when it can.

    A carry is judged here on the run's own record, never on the caller's
    word: the run must be a FULL run (a targeted run can never stand in for
    one), recorded green with zero failures and errors, and stamped with
    exactly the fingerprint the caller computed now.
    """
    problems: list[str] = []
    selection = index[_SELECTION_KEY] if _SELECTION_KEY in index else None
    is_full = (
        isinstance(selection, dict)
        and _SELECTION_KIND_KEY in selection
        and selection[_SELECTION_KIND_KEY] == _SELECTION_FULL
    )
    if not is_full:
        problems.append(f"run is not a full run (selection={selection!r})")
    result = index[_RESULT_KEY] if _RESULT_KEY in index else None
    if result != _STATUS_PASSED:
        problems.append(f"run result is {result!r}, not {_STATUS_PASSED}")
    counts = index[_COUNTS_KEY] if _COUNTS_KEY in index else None
    for key in _ZERO_COUNT_KEYS:
        if not _is_zero_count(counts, key):
            problems.append(f"run counts.{key} is not 0")
    inputs = index[_INPUTS_KEY] if _INPUTS_KEY in index else None
    recorded = inputs[_FINGERPRINT_KEY] if isinstance(inputs, dict) and _FINGERPRINT_KEY in inputs else None
    if recorded != fingerprint:
        problems.append("run's recorded suite-input fingerprint does not equal the one computed now")
    return problems


def _carry_rejected_verdict(project: str, run_dir: Path, fingerprint: str, problems: list[str]) -> ProjectVerdict:
    """RED for a carry claim the named run does not support."""
    return ProjectVerdict(
        project=project,
        run_dir=str(run_dir),
        result=None,
        counts=None,
        verdict=_RED,
        reason=f"{_REASON_CARRY_REJECTED}: {'; '.join(problems)}",
        failing=[],
        failing_total=0,
        age_minutes=_age_minutes(run_dir.name),
        carried=False,
        fingerprint=fingerprint,
    )


def _carried_verdict(workspace: Path, project: str, run_dir_name: str, fingerprint: str) -> ProjectVerdict:
    """Verdict row for a package whose green full run stands in for a fresh one.

    Reads exactly the named run -- the same pinned-run discipline as
    ``_evaluate_project`` -- so a CARRIED row reports the real counts of the
    run it stands in for, its directory, its age, and the fingerprint that
    matched. The claim itself is re-checked against that run's own
    ``index.json`` (a full run, green, stamped with *fingerprint*); a claim
    the record does not support is RED, never CARRIED and never a
    fall-through to another run.

    Args:
        workspace: Monorepo root.
        project: The package name.
        run_dir_name: The ``test-results-*`` directory the carry decision judged.
        fingerprint: The fingerprint computed now that matched this run's
            recorded one.
    """
    run_dir = workspace / project / ".test_results" / run_dir_name
    index_path = run_dir / _INDEX_JSON_NAME
    try:
        index = _read_index_object(index_path)
    except ValueError as exc:
        return _carry_rejected_verdict(project, run_dir, fingerprint, [str(exc)])
    problems = _carry_claim_problems(index, fingerprint)
    if problems:
        return _carry_rejected_verdict(project, run_dir, fingerprint, problems)
    parsed = parse_pytest_summary(index_path)
    failing, failing_total = _collect_failing(index_path, parsed.total_failed + parsed.total_errors)
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
        verdict=_CARRIED,
        reason=None,
        failing=failing,
        failing_total=failing_total,
        age_minutes=_age_minutes(run_dir.name),
        carried=True,
        fingerprint=fingerprint,
    )


def _carried_line(row: ProjectVerdict, passed: int) -> str:
    run_name = Path(row.run_dir).name if row.run_dir is not None else "?"
    age = f"{row.age_minutes:.1f}m" if row.age_minutes is not None else "unknown"
    fingerprint = row.fingerprint[:_FINGERPRINT_DISPLAY_CHARS] if row.fingerprint is not None else "?"
    return f"{row.project}: {_CARRIED} {passed} passed (run {run_name}, age {age}, fingerprint {fingerprint})"


def _format_project_line(row: ProjectVerdict) -> str:
    """One console line per project."""
    if row.counts is None and row.reason is not None:
        return f"{row.project}: {_RED} {row.reason}"
    counts = row.counts if row.counts is not None else {}
    passed = counts["passed"] if "passed" in counts else 0
    if row.verdict == _CARRIED:
        return _carried_line(row, passed)
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


def _validate_carried(
    projects: Sequence[str],
    forced: Mapping[str, str],
    pinned: Mapping[str, str],
    carried: Mapping[str, str],
) -> None:
    """Reject a ``carried`` map that contradicts the rest of the request."""
    not_evaluated = sorted(set(carried) - set(projects))
    also_forced = sorted(set(carried) & set(forced))
    unpinned = sorted(set(carried) - set(pinned))
    if not_evaluated or also_forced or unpinned:
        raise UsageError(
            f"Inconsistent carry request: carried but not evaluated {not_evaluated}, "
            f"carried and forced RED {also_forced}, carried without a pinned run {unpinned}. "
            f"A carried package must be one of the evaluated projects, must not be forced "
            f"RED, and must be pinned (pinned_runs) to the run whose fingerprint it matched."
        )


def evaluate_projects(
    workspace: Path,
    projects: Sequence[str],
    *,
    forced_red: Mapping[str, str] | None = None,
    pinned_runs: Mapping[str, str] | None = None,
    carried: Mapping[str, str] | None = None,
) -> GateVerdictResult:
    """Evaluate each project's run and return the aggregate verdict.

    A project is judged on its NEWEST run unless ``pinned_runs`` names the
    ``test-results-*`` directory to judge instead (see ``_evaluate_project``
    for why a scheduler must pin). ``forced_red`` wins over both. A project
    in ``carried`` is judged as a CARRIED row on its pinned run: CARRIED counts
    as green for the overall verdict but stays a distinct verdict string in
    every rendered line and serialized row.

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
        pinned_runs: Optional package -> ``test-results-*`` directory name
            map. A package listed here is judged on exactly that run; a pinned
            run with no results file is RED, never a fall-through to the
            newest run.
        carried: Optional package -> fingerprint map. A package listed here
            was not run: its pinned run (it MUST also be in ``pinned_runs``)
            is a recorded green full run whose suite-input fingerprint equals
            the one the caller computed now. The row is CARRIED only when
            that run's own ``index.json`` confirms all of it; otherwise it is
            RED with reason ``CARRY_REJECTED``.

    Returns:
        The aggregate result: per-project rows, the overall verdict, the
        serializable payload, the formatted per-project report lines, and
        the process exit code.

    Raises:
        UsageError: if ``carried`` names a project that is not evaluated, is
            also forced RED, or has no pinned run.
    """
    forced = forced_red or {}
    pinned = pinned_runs or {}
    carried_map = carried or {}
    _validate_carried(projects, forced, pinned, carried_map)

    def _row_for(project: str) -> ProjectVerdict:
        if project in forced:
            return _forced_red_verdict(project, forced[project])
        if project in carried_map:
            return _carried_verdict(workspace, project, pinned[project], carried_map[project])
        return _evaluate_project(workspace, project, pinned[project] if project in pinned else None)

    rows = [_row_for(project) for project in projects]
    overall = _GREEN if all(row.verdict in (_GREEN, _CARRIED) for row in rows) else _RED
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
