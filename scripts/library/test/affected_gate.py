#!/usr/bin/env python3
"""Concurrent affected-set test gate for Datrix packages.

Derives the affected set of a changed-package request (changed packages
union their transitive reverse-dependency closure, via the affected_set
module), schedules `test.ps1 <pkg>` child processes longest-first under a
PYTEST_XDIST_AUTO_NUM_WORKERS budget so that concurrently running children
never oversubscribe the machine, and aggregates one final verdict by
reusing gate_verdict's own per-project evaluation and formatting -- never
reimplementing index.json parsing here.

Usage:
  python scripts/library/test/affected_gate.py --projects datrix-common
  python scripts/library/test/affected_gate.py --all --max-concurrent 4
  .\\scripts\\test\\affected-gate.ps1 -Projects datrix-common
  .\\scripts\\test\\affected-gate.ps1 -All -MaxConcurrent 4

Exit codes: 0 = overall GREEN, 1 = overall RED, 2 = usage error.
"""

from __future__ import annotations

import argparse
import heapq
import io
import json
import logging
import os
import re
import subprocess
import sys
import tempfile
import time
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

if sys.platform == "win32" and __name__ == "__main__":
    if hasattr(sys.stdout, "buffer"):
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    if hasattr(sys.stderr, "buffer"):
        sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

_LIBRARY_DIR = Path(__file__).resolve().parent.parent
if _LIBRARY_DIR.exists() and str(_LIBRARY_DIR) not in sys.path:
    sys.path.insert(0, str(_LIBRARY_DIR))

from shared.venv import get_datrix_root  # noqa: E402
from test import affected_set  # noqa: E402
from test import gate_verdict  # noqa: E402

logger = logging.getLogger(__name__)

_DEFAULT_MAX_CONCURRENT = 4
_POLL_INTERVAL_SECONDS = 2.0
_OUTPUT_FILENAME = "affected-gate.json"
_OUTPUT_SUBDIRS = ("test",)
_RUN_DIR_PATTERN = re.compile(r"^test-results-\d{8}-\d{6}$")
_INCOMPLETE_MARKER = "INCOMPLETE"
_REASON_CHILD_PRODUCED_NO_RUN = "CHILD_PRODUCED_NO_RUN"
_VERDICT_RED = "RED"
_EXIT_GREEN = 0
_EXIT_RED = 1
_EXIT_USAGE = 2


class UsageError(Exception):
    """Invalid usage or unschedulable request; the script exits with code 2."""


# ---------------------------------------------------------------------------
# Affected-set derivation (delegates entirely to affected_set -- no
# reimplementation of graph/closure logic here).
# ---------------------------------------------------------------------------


def compute_affected_set(workspace: Path, changed: list[str]) -> list[str]:
    """The changed packages union their transitive reverse-dependency
    closure, via affected_set's own closure derivation.

    Args:
        workspace: The Datrix monorepo root.
        changed: The caller's explicitly-named changed packages.

    Returns:
        Sorted, deduplicated list of package names to test.
    """
    packages = affected_set.discover_packages(workspace)
    import_names = {name: affected_set.discover_import_name(d) for name, d in packages.items()}
    source_graph, test_graph, deferred_graph = affected_set.build_source_test_and_deferred_graphs(
        packages, import_names, include_root_conftest=True
    )
    closures = affected_set.compute_affected_closures(source_graph, test_graph, deferred_graph)
    affected: set[str] = set(changed)
    for name in changed:
        affected |= closures.get(name, set())
    return sorted(affected)


# ---------------------------------------------------------------------------
# Scheduling: longest-first ordering + worker budget.
# ---------------------------------------------------------------------------


def _src_loc(package_dir: Path) -> int:
    """Total line count under package_dir/src -- the fallback duration
    proxy when no index.json exists yet for a package."""
    src_dir = package_dir / "src"
    if not src_dir.is_dir():
        return 0
    total = 0
    for py_file in src_dir.rglob("*.py"):
        try:
            with py_file.open("r", encoding="utf-8-sig") as handle:
                total += sum(1 for _ in handle)
        except OSError:
            continue
    return total


def _newest_completed_index(test_results_dir: Path) -> Path | None:
    """The newest test-results-* directory's index.json, skipping any
    run directory that has none yet."""
    if not test_results_dir.is_dir():
        return None
    candidates = [d for d in test_results_dir.iterdir() if d.is_dir() and _RUN_DIR_PATTERN.match(d.name)]
    for run_dir in sorted(candidates, key=lambda d: d.name, reverse=True):
        index_path = run_dir / "index.json"
        if index_path.is_file():
            return index_path
    return None


def predicted_duration_seconds(package_dir: Path) -> float:
    """Newest full-run wall-clock duration_seconds from index.json; falls
    back to package src/ line count (always available, monotone) when no
    run has ever completed for this package.

    Args:
        package_dir: Absolute path to one package directory.

    Returns:
        Predicted duration in seconds (never negative).
    """
    test_results_dir = package_dir / ".test_results"
    newest_index = _newest_completed_index(test_results_dir)
    if newest_index is not None:
        try:
            data = json.loads(newest_index.read_text(encoding="utf-8"))
            duration = data.get("duration_seconds")
            if isinstance(duration, (int, float)):
                return float(duration)
        except (OSError, json.JSONDecodeError):
            pass
    return float(_src_loc(package_dir))


def schedule_longest_first(packages: dict[str, Path]) -> list[str]:
    """Package names ordered by predicted duration, longest first -- bounds
    makespan near the slowest suite instead of leaving it for last."""
    return sorted(packages, key=lambda name: predicted_duration_seconds(packages[name]), reverse=True)


def workers_per_child(max_concurrent: int, logical_cores: int | None = None) -> int:
    """floor(logical cores / max_concurrent), minimum 1.

    Args:
        max_concurrent: The number of concurrently-running package suites.
        logical_cores: Override for os.cpu_count() (used by tests).
    """
    cores = logical_cores if logical_cores is not None else (os.cpu_count() or 1)
    return max(1, cores // max_concurrent)


@dataclass(frozen=True)
class ScheduleEvent:
    """One package's simulated [start, end) interval under the
    longest-first, max_concurrent-slot policy."""

    package: str
    start: float
    end: float
    workers: int


def simulate_schedule(
    ordered_packages: list[str],
    predicted_durations: dict[str, float],
    max_concurrent: int,
    workers_per_child_count: int,
) -> list[ScheduleEvent]:
    """Deterministic discrete-event simulation of the longest-first,
    max_concurrent-slot policy -- used by the self-test to prove the worker
    budget is never exceeded, and usable to reason about predicted makespan
    before spawning any real process.

    Args:
        ordered_packages: Package names, already longest-first.
        predicted_durations: Package name -> predicted duration seconds.
        max_concurrent: Number of concurrent slots.
        workers_per_child_count: Workers assigned to each child.

    Raises:
        UsageError: if max_concurrent < 1.
    """
    if max_concurrent < 1:
        raise UsageError(f"-MaxConcurrent must be >= 1, got {max_concurrent}.")
    slot_free_at: list[float] = [0.0] * max_concurrent
    heapq.heapify(slot_free_at)
    events: list[ScheduleEvent] = []
    for package in ordered_packages:
        start = heapq.heappop(slot_free_at)
        duration = predicted_durations.get(package, 0.0)
        end = start + duration
        events.append(ScheduleEvent(package=package, start=start, end=end, workers=workers_per_child_count))
        heapq.heappush(slot_free_at, end)
    return events


def max_concurrent_workers(events: list[ScheduleEvent]) -> int:
    """Peak sum of `workers` across simultaneously-active events -- the
    quantity the worker-budget invariant bounds by logical core count."""
    boundaries = sorted({e.start for e in events} | {e.end for e in events})
    peak = 0
    for t in boundaries[:-1]:
        active = sum(e.workers for e in events if e.start <= t < e.end)
        peak = max(peak, active)
    return peak


# ---------------------------------------------------------------------------
# Same-package exclusivity + in-progress detection.
# ---------------------------------------------------------------------------


def _resolve_requested_packages(
    raw_projects: list[str] | None, use_all: bool, testable: dict[str, Path]
) -> list[str]:
    """Validate and return the caller's requested (changed) package names.

    Raises:
        UsageError: on --all with --projects both set, an empty selection,
            an unknown package name, or the SAME package named twice -- a
            duplicate is rejected outright, never silently deduped.
    """
    if use_all:
        if raw_projects:
            raise UsageError("Use either -Projects or -All, not both.")
        return sorted(testable)
    if not raw_projects:
        raise UsageError("No projects specified. Pass -Projects <a,b,c> or -All.")
    names: list[str] = []
    for chunk in raw_projects:
        names.extend(name.strip() for name in chunk.split(",") if name.strip())
    duplicates = sorted({name for name in names if names.count(name) > 1})
    if duplicates:
        raise UsageError(
            f"Package(s) named more than once in -Projects: {', '.join(duplicates)}. "
            f"Pass each changed package exactly once."
        )
    unknown = [name for name in names if name not in testable]
    if unknown:
        raise UsageError(
            f"Unknown package(s): {', '.join(unknown)}. "
            f"Valid packages: {', '.join(sorted(testable))}."
        )
    return names


def _newest_run_dir_any_state(test_results_dir: Path) -> str | None:
    """The name of the newest test-results-* directory, regardless of
    whether it yet contains an index.json -- unlike
    status_tests.find_latest_log_file, which only recognizes directories
    that already have a results file and would miss a run still mid-write.
    """
    if not test_results_dir.is_dir():
        return None
    candidates = [d.name for d in test_results_dir.iterdir() if d.is_dir() and _RUN_DIR_PATTERN.match(d.name)]
    return max(candidates) if candidates else None


def is_run_in_progress(test_results_dir: Path) -> bool:
    """True when the package's newest test-results-* directory has no
    index.json yet, or an INCOMPLETE one -- i.e. a run is currently writing
    to it. Starting a concurrent run against the same package while true
    would race that writer's run-directory claim.
    """
    newest_name = _newest_run_dir_any_state(test_results_dir)
    if newest_name is None:
        return False
    index_path = test_results_dir / newest_name / "index.json"
    if not index_path.is_file():
        return True
    try:
        data = json.loads(index_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return True
    return str(data.get("status", "")).upper() == _INCOMPLETE_MARKER


def _reject_in_progress_unless_forced(workspace: Path, affected: list[str], force: bool) -> None:
    """Raise UsageError naming any affected package whose newest run looks
    in-progress, unless force is set."""
    in_progress = [pkg for pkg in affected if is_run_in_progress(workspace / pkg / ".test_results")]
    if in_progress and not force:
        raise UsageError(
            f"Package(s) already have a run in progress (newest run dir has "
            f"no completed index.json): {', '.join(sorted(in_progress))}. "
            f"Wait for it to finish, or pass -Force to start anyway (a forced "
            f"concurrent run against an in-progress package may corrupt or "
            f"race that run's own run-directory claim)."
        )


# ---------------------------------------------------------------------------
# Child process launch + monitoring.
# ---------------------------------------------------------------------------


@dataclass
class RunningChild:
    """A test.ps1 child process currently executing for one package."""

    package: str
    process: subprocess.Popen[bytes]
    started_at: float


def _launch_child(workspace: Path, package: str, workers: int, dbg: bool) -> subprocess.Popen[bytes]:
    """Launch `test.ps1 <package>` as a child process with a capped xdist
    worker budget. The child's own stdout/stderr stream to this process's
    (never captured/suppressed), so a hang is visible while it runs."""
    env = os.environ.copy()
    env["PYTEST_XDIST_AUTO_NUM_WORKERS"] = str(workers)
    logger.info(
        "scheduling package=%s workers=%d PYTEST_XDIST_AUTO_NUM_WORKERS=%d",
        package, workers, workers,
    )
    test_ps1 = workspace / "datrix" / "scripts" / "test" / "test.ps1"
    args = ["powershell", "-File", str(test_ps1), package]
    if dbg:
        args.append("-Dbg")
    return subprocess.Popen(args, env=env)


def run_scheduled(
    workspace: Path,
    ordered_packages: list[str],
    max_concurrent: int,
    workers_per_child_count: int,
    dbg: bool,
) -> set[str]:
    """Launch `ordered_packages` (already longest-first) as `test.ps1`
    child processes, never more than max_concurrent live at once, and never
    two live children for the same package (each package appears at most
    once in `ordered_packages` by construction of the affected set).
    Blocks until every child has exited.

    Returns:
        Names of packages whose child exited without the package's newest
        test-results-* run directory advancing past its pre-launch
        baseline -- a hard crash before any index.json was even written.
        The caller must treat these as forced-RED rather than trusting
        gate_verdict's own newest-run lookup, which would otherwise
        silently report a STALE prior (possibly GREEN) run.
    """
    baseline = {pkg: _newest_run_dir_any_state(workspace / pkg / ".test_results") for pkg in ordered_packages}
    pending = list(ordered_packages)
    running: list[RunningChild] = []
    forced_red: set[str] = set()
    while pending or running:
        while pending and len(running) < max_concurrent:
            package = pending.pop(0)
            proc = _launch_child(workspace, package, workers_per_child_count, dbg)
            running.append(RunningChild(package=package, process=proc, started_at=time.monotonic()))
        finished = [child for child in running if child.process.poll() is not None]
        for child in finished:
            elapsed = time.monotonic() - child.started_at
            newest_after = _newest_run_dir_any_state(workspace / child.package / ".test_results")
            if newest_after == baseline[child.package]:
                forced_red.add(child.package)
                print(
                    f"{child.package}: child exited code={child.process.returncode} "
                    f"after {elapsed:.1f}s WITHOUT producing a new run directory "
                    f"-- forcing RED (never trusting a stale prior result)"
                )
            else:
                print(f"{child.package}: child exited code={child.process.returncode} after {elapsed:.1f}s")
            running.remove(child)
        if running:
            time.sleep(_POLL_INTERVAL_SECONDS)
    return forced_red


def run_mypy_for_changed(workspace: Path, changed: list[str], max_concurrent: int, dbg: bool) -> bool:
    """Run `mypy.ps1 <pkg>` for each CHANGED package (never the whole
    affected set) inside the same MaxConcurrent budget.

    Returns:
        True iff every changed package's mypy run exited 0.
    """
    mypy_ps1 = workspace / "datrix" / "scripts" / "test" / "mypy.ps1"
    pending = list(changed)
    running: list[subprocess.Popen[bytes]] = []
    running_names: list[str] = []
    all_ok = True
    while pending or running:
        while pending and len(running) < max_concurrent:
            package = pending.pop(0)
            args = ["powershell", "-File", str(mypy_ps1), package]
            if dbg:
                args.append("-Dbg")
            running.append(subprocess.Popen(args))
            running_names.append(package)
        still_running: list[subprocess.Popen[bytes]] = []
        still_names: list[str] = []
        for proc, name in zip(running, running_names):
            code = proc.poll()
            if code is None:
                still_running.append(proc)
                still_names.append(name)
                continue
            print(f"{name}: mypy exited code={code}")
            if code != 0:
                all_ok = False
        running, running_names = still_running, still_names
        if running:
            time.sleep(_POLL_INTERVAL_SECONDS)
    return all_ok


# ---------------------------------------------------------------------------
# Aggregation -- delegates entirely to gate_verdict's PUBLIC entry point.
# ---------------------------------------------------------------------------


def _aggregate_verdict(
    workspace: Path,
    affected: list[str],
    forced_red: dict[str, str],
    output_path: Path,
) -> int:
    """Aggregate the final verdict via ``gate_verdict.evaluate_projects``.

    Never reimplement index.json parsing or verdict formatting here, and
    never reach into ``gate_verdict``'s underscore-private names -- this
    task adds the public ``evaluate_projects`` entry point precisely so the
    coupling is a contract instead of an internal reach-through.

    `forced_red` maps a package to the reason its child process failed to
    produce a run directory newer than when it started. Those packages MUST
    NOT fall through to a newest-run lookup: it would find the STALE prior
    run and could report GREEN -- exactly the false-green this gate must
    never produce. Passing them as ``forced_red`` makes the override part of
    gate_verdict's own contract rather than a local patch-up.
    """
    result = gate_verdict.evaluate_projects(
        workspace,
        affected,
        forced_red=forced_red,
    )
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(result.payload, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    for line in result.report_lines:
        print(line)
    print(f"OVERALL: {result.overall}")
    print(f"Details: {output_path}")
    return result.exit_code


def _resolve_output_path(raw_output: str | None, workspace: Path) -> Path:
    if raw_output:
        output_path = Path(raw_output).resolve()
    else:
        output_path = workspace.joinpath(".tmp", *_OUTPUT_SUBDIRS, _OUTPUT_FILENAME)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    return output_path


# ---------------------------------------------------------------------------
# Self-test harness -- mirrors check-docs-conformance.py's pattern.
# ---------------------------------------------------------------------------

_GREEN_ANSI = "\033[92m"
_RED_ANSI = "\033[91m"
_CYAN_ANSI = "\033[96m"
_RESET_ANSI = "\033[0m"


def _ok(msg: str) -> None:
    print(f"{_GREEN_ANSI}[OK]{_RESET_ANSI} {msg}")


def _fail(msg: str) -> None:
    print(f"{_RED_ANSI}[FAIL]{_RESET_ANSI} {msg}")


def _step(msg: str) -> None:
    print(f"\n{_CYAN_ANSI}=== {msg}{_RESET_ANSI}")


def run_self_test_checks(checks: list[tuple[str, Callable[[], None]]]) -> bool:
    """Run every (name, check_fn) pair, printing [OK]/[FAIL] per check."""
    all_passed = True
    for name, fn in checks:
        try:
            fn()
        except AssertionError as e:
            _fail(f"{name}: {e}")
            all_passed = False
        else:
            _ok(name)
    return all_passed


def _configure_logging(debug: bool) -> None:
    logging.basicConfig(
        level=logging.DEBUG if debug else logging.INFO,
        format="%(levelname)s %(name)s: %(message)s",
        stream=sys.stderr,
    )


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run the affected set of Datrix package suites concurrently under a worker budget and return one verdict."
    )
    parser.add_argument("--projects", action="append", help="Changed package name(s); repeatable and/or comma-separated")
    parser.add_argument("--all", action="store_true", help="Treat every discovered package as changed")
    parser.add_argument(
        "--max-concurrent", type=int, default=None,
        help=f"Max concurrent package suites (default {_DEFAULT_MAX_CONCURRENT})",
    )
    parser.add_argument(
        "--workers-per-child", type=int, default=None,
        help="Override PYTEST_XDIST_AUTO_NUM_WORKERS per child (default floor(logical_cores / max_concurrent))",
    )
    parser.add_argument("--mypy", action="store_true", help="Also run mypy.ps1 for the changed packages, inside the same budget")
    parser.add_argument("--force", action="store_true", help="Start even if a requested package's newest run looks in-progress")
    parser.add_argument("--output", help="Output JSON path (default <workspace>/.tmp/test/affected-gate.json)")
    parser.add_argument(
        "--self-test", action="store_true",
        help=(
            "Run only the self-test suite and exit -- skips real scheduling. "
            "The same checks run automatically as step 1 of every normal invocation."
        ),
    )
    parser.add_argument("--debug", action="store_true", help="Enable debug logging")
    return parser.parse_args()


def _run(args: argparse.Namespace) -> int:
    workspace = get_datrix_root()
    testable = affected_set.discover_packages(workspace)
    changed = _resolve_requested_packages(args.projects, args.all, testable)
    affected = compute_affected_set(workspace, changed)

    _reject_in_progress_unless_forced(workspace, affected, args.force)

    max_concurrent = args.max_concurrent if args.max_concurrent else _DEFAULT_MAX_CONCURRENT
    if max_concurrent < 1:
        raise UsageError(f"-MaxConcurrent must be >= 1, got {max_concurrent}.")
    logical_cores = os.cpu_count() or 1
    workers = args.workers_per_child if args.workers_per_child else workers_per_child(max_concurrent, logical_cores)
    if workers < 1:
        raise UsageError(f"-WorkersPerChild must be >= 1, got {workers}.")

    package_dirs = {name: testable[name] for name in affected}
    ordered = schedule_longest_first(package_dirs)
    logger.info(
        "scheduling affected=%s max_concurrent=%d workers_per_child=%d logical_cores=%d",
        ordered, max_concurrent, workers, logical_cores,
    )

    forced_red_set = run_scheduled(workspace, ordered, max_concurrent, workers, args.debug)
    forced_red = {pkg: _REASON_CHILD_PRODUCED_NO_RUN for pkg in forced_red_set}

    mypy_ok = True
    if args.mypy:
        mypy_ok = run_mypy_for_changed(workspace, changed, max_concurrent, args.debug)
        if not mypy_ok:
            print("mypy: at least one changed package failed type-checking", file=sys.stderr)

    output_path = _resolve_output_path(args.output, workspace)
    exit_code = _aggregate_verdict(workspace, affected, forced_red, output_path)
    if args.mypy and not mypy_ok:
        return _EXIT_RED
    return exit_code


# ---------------------------------------------------------------------------
# Self-test checks (pure-function scheduling/validation/aggregation checks --
# none spawn a real test.ps1 subprocess; see Success Criterion 8's POSITIVE
# check for the real end-to-end proof).
# ---------------------------------------------------------------------------


def _check_budget_never_exceeds_cores_across_simulated_schedule() -> None:
    durations = {"pkg-a": 500.0, "pkg-b": 100.0, "pkg-c": 90.0, "pkg-d": 30.0, "pkg-e": 10.0}
    max_concurrent = 4
    logical_cores = 32
    per_child = workers_per_child(max_concurrent, logical_cores)
    events = simulate_schedule(list(durations), durations, max_concurrent, per_child)
    peak = max_concurrent_workers(events)
    assert peak <= logical_cores, f"peak worker demand {peak} exceeds {logical_cores} logical cores"
    assert per_child * max_concurrent <= logical_cores


def _make_package_with_duration(root: Path, name: str, duration_seconds: float) -> Path:
    pkg_dir = root / name
    run_dir = pkg_dir / ".test_results" / "test-results-20260729-120000"
    run_dir.mkdir(parents=True)
    (run_dir / "index.json").write_text(
        json.dumps({"duration_seconds": duration_seconds}), encoding="utf-8"
    )
    return pkg_dir


def _check_longest_first_ordering() -> None:
    with tempfile.TemporaryDirectory(prefix="affected-gate-selftest-") as tmp:
        root = Path(tmp)
        package_dirs = {
            "datrix-slow": _make_package_with_duration(root, "datrix-slow", 500.0),
            "datrix-fast": _make_package_with_duration(root, "datrix-fast", 10.0),
            "datrix-mid": _make_package_with_duration(root, "datrix-mid", 90.0),
        }
        ordered = schedule_longest_first(package_dirs)
        assert ordered == ["datrix-slow", "datrix-mid", "datrix-fast"], ordered


def _check_missing_index_falls_back_to_loc() -> None:
    with tempfile.TemporaryDirectory(prefix="affected-gate-selftest-") as tmp:
        root = Path(tmp)
        pkg_dir = root / "datrix-new"
        src_dir = pkg_dir / "src" / "datrix_new"
        src_dir.mkdir(parents=True)
        (src_dir / "module.py").write_text(
            "\n".join(f"line_{i} = {i}" for i in range(37)) + "\n", encoding="utf-8"
        )
        duration = predicted_duration_seconds(pkg_dir)
        assert duration == 37.0, f"expected LOC fallback of 37.0, got {duration}"


def _check_resolve_requested_packages_distinct_ok_and_duplicate_rejected() -> None:
    """Both halves of _resolve_requested_packages's dedup/validation contract:
    a legitimate list of DISTINCT packages resolves cleanly to the expected
    set, and naming the SAME package twice is rejected outright rather than
    silently deduped."""
    testable = {"datrix-common": Path("."), "datrix-language": Path(".")}
    resolved = _resolve_requested_packages(["datrix-common,datrix-language"], False, testable)
    assert resolved == ["datrix-common", "datrix-language"], resolved
    try:
        _resolve_requested_packages(["datrix-common,datrix-common"], False, testable)
    except UsageError:
        pass
    else:
        raise AssertionError("naming the same package twice must raise UsageError, not silently dedupe")


def _check_child_with_no_new_run_forces_red_never_stale_green() -> None:
    """The crux fail-loud property: a package with a STALE GREEN prior run,
    whose child produced no new run at all, must be forced RED in the
    aggregate -- gate_verdict's own newest-run lookup would otherwise
    report the stale GREEN, which is exactly the false-green this gate
    must avoid."""
    with tempfile.TemporaryDirectory(prefix="affected-gate-selftest-") as tmp:
        workspace = Path(tmp)
        stale_run = workspace / "datrix-crashed" / ".test_results" / "test-results-20260101-000000"
        stale_run.mkdir(parents=True)
        (stale_run / "index.json").write_text(
            json.dumps(
                {
                    "status": "PASSED",
                    "total_passed": 10,
                    "total_failed": 0,
                    "total_errors": 0,
                    "total_skipped": 0,
                }
            ),
            encoding="utf-8",
        )
        output_path = workspace / ".tmp" / "test" / "affected-gate.json"
        exit_code = _aggregate_verdict(
            workspace,
            ["datrix-crashed"],
            {"datrix-crashed": _REASON_CHILD_PRODUCED_NO_RUN},
            output_path,
        )
        assert exit_code == _EXIT_RED, f"forced_red package must make the overall verdict RED, got {exit_code}"
        payload = json.loads(output_path.read_text(encoding="utf-8"))
        row = payload["projects"][0]
        assert row["verdict"] == _VERDICT_RED, row
        assert row["reason"] == _REASON_CHILD_PRODUCED_NO_RUN, row


def _check_is_run_in_progress_missing_index_json() -> None:
    """A newest run directory that exists but has no index.json yet is a
    run still writing -- must be reported in-progress."""
    with tempfile.TemporaryDirectory(prefix="affected-gate-selftest-") as tmp:
        test_results_dir = Path(tmp) / "datrix-writing" / ".test_results"
        run_dir = test_results_dir / "test-results-20260730-090000"
        run_dir.mkdir(parents=True)
        assert is_run_in_progress(test_results_dir) is True, (
            "a newest run dir with no index.json must be reported in-progress"
        )


def _check_is_run_in_progress_incomplete_status() -> None:
    """A newest run directory whose index.json reports an INCOMPLETE status
    is also a run still writing -- must be reported in-progress."""
    with tempfile.TemporaryDirectory(prefix="affected-gate-selftest-") as tmp:
        test_results_dir = Path(tmp) / "datrix-writing" / ".test_results"
        run_dir = test_results_dir / "test-results-20260730-090000"
        run_dir.mkdir(parents=True)
        (run_dir / "index.json").write_text(
            json.dumps({"status": _INCOMPLETE_MARKER}), encoding="utf-8"
        )
        assert is_run_in_progress(test_results_dir) is True, (
            "a newest run dir with an INCOMPLETE index.json must be reported in-progress"
        )


def _check_is_run_in_progress_completed_index_is_not_in_progress() -> None:
    """Negative control: a newest run directory with a completed (non-
    INCOMPLETE) index.json must NOT be reported in-progress."""
    with tempfile.TemporaryDirectory(prefix="affected-gate-selftest-") as tmp:
        test_results_dir = Path(tmp) / "datrix-done" / ".test_results"
        run_dir = test_results_dir / "test-results-20260730-090000"
        run_dir.mkdir(parents=True)
        (run_dir / "index.json").write_text(
            json.dumps({"status": "PASSED"}), encoding="utf-8"
        )
        assert is_run_in_progress(test_results_dir) is False, (
            "a newest run dir with a completed index.json must NOT be reported in-progress"
        )


def _check_max_concurrent_one_is_sequential() -> None:
    durations = {"pkg-a": 50.0, "pkg-b": 30.0, "pkg-c": 10.0}
    events = simulate_schedule(list(durations), durations, 1, 8)
    ordered_events = sorted(events, key=lambda e: e.start)
    for earlier, later in zip(ordered_events, ordered_events[1:]):
        assert later.start >= earlier.end, (
            f"-MaxConcurrent 1 must run sequentially; {later.package} started "
            f"at {later.start} before {earlier.package} ended at {earlier.end}"
        )


_SELF_TEST_CHECKS: list[tuple[str, Callable[[], None]]] = [
    (
        "budget_never_exceeds_cores_across_simulated_schedule",
        _check_budget_never_exceeds_cores_across_simulated_schedule,
    ),
    ("longest_first_ordering", _check_longest_first_ordering),
    ("missing_index_falls_back_to_loc", _check_missing_index_falls_back_to_loc),
    (
        "resolve_requested_packages_distinct_ok_and_duplicate_rejected",
        _check_resolve_requested_packages_distinct_ok_and_duplicate_rejected,
    ),
    (
        "child_with_no_new_run_forces_red_never_stale_green",
        _check_child_with_no_new_run_forces_red_never_stale_green,
    ),
    ("is_run_in_progress_missing_index_json", _check_is_run_in_progress_missing_index_json),
    ("is_run_in_progress_incomplete_status", _check_is_run_in_progress_incomplete_status),
    (
        "is_run_in_progress_completed_index_is_not_in_progress",
        _check_is_run_in_progress_completed_index_is_not_in_progress,
    ),
    ("max_concurrent_one_is_sequential", _check_max_concurrent_one_is_sequential),
]


def main() -> int:
    """Entry point."""
    args = _parse_args()
    _configure_logging(args.debug)

    _step("Self-test: affected-gate scheduling edge cases")
    self_test_passed = run_self_test_checks(_SELF_TEST_CHECKS)
    if args.self_test:
        return _EXIT_GREEN if self_test_passed else _EXIT_RED
    if not self_test_passed:
        print(
            "\nError: self-test failed -- refusing to trust the scheduler for a real run.",
            file=sys.stderr,
        )
        return _EXIT_RED

    try:
        return _run(args)
    except UsageError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return _EXIT_USAGE


if __name__ == "__main__":
    sys.exit(main())
