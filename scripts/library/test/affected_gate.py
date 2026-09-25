#!/usr/bin/env python3
"""Concurrent affected-set test gate for Datrix packages.

Runs the affected set of a change: the changed packages plus the consumers
the caller named. The reverse-dependency closure (via the affected_set module)
is only the upper bound on who CAN observe the change, never the set that runs:
a package that imports a changed package without reaching the changed surface
is not affected. When the closure holds any package beyond the changed ones,
the caller must say which of them the change reaches (``--consumers``) or that
none does (``--no-consumers``); every closure member left out is printed and
recorded as excluded, so a narrowed run is visible, never silent. Schedules
`test.ps1 <pkg>` child processes longest-first, each with
a PYTEST_XDIST_AUTO_NUM_WORKERS allotment proportional to its share of the
predicted CPU work, admitting a child only while the running children's
allotments fit in the logical core count -- so they never oversubscribe the
machine, and the largest suite is not held to a fixed slot's share of it --
and aggregates one final verdict by
reusing gate_verdict's own per-project evaluation and formatting -- never
reimplementing index.json parsing here.

Before any child is launched, each affected package's newest FULL run is
checked for carry: when it is green, complete, younger than the carry window,
and its recorded suite-input fingerprint equals the fingerprint computed now
(suite_inputs), that run stands in as a CARRIED verdict and no child is
launched for the package. Every unknown runs the package instead, and the
reason is printed and recorded in affected-gate.json. After aggregation the
gate appends one completion row (what ran, what was carried, per-package wall
seconds, the overall verdict) to the workspace's full-suite audit log.

The shared venv's package install check runs ONCE per gate, before the carry
decision and before any child: every child is launched with
DATRIX_PACKAGES_ENSURED=1, so no ``test.ps1`` child repeats it. A failing check
fails the gate (RED, INSTALL_CHECK_FAILED) with no child launched.

Usage:
  python scripts/library/test/affected_gate.py --projects datrix-codegen-python
  python scripts/library/test/affected_gate.py --projects datrix-codegen-common --consumers datrix-codegen-python,datrix-cli
  python scripts/library/test/affected_gate.py --projects datrix-codegen-common --no-consumers
  python scripts/library/test/affected_gate.py --all --max-concurrent 4
  .\\scripts\\test\\affected-gate.ps1 -Projects datrix-codegen-common -Consumers datrix-codegen-python,datrix-cli
  .\\scripts\\test\\affected-gate.ps1 -All -MaxConcurrent 4

Exit codes: 0 = overall GREEN, 1 = overall RED, 2 = usage error.
"""

from __future__ import annotations

import argparse
import ast
import copy
import heapq
import io
import json
import logging
import math
import os
import re
import subprocess
import sys
import tempfile
import threading
import time
from collections.abc import Callable, Iterable, Iterator, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import datetime, timedelta
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
from test import suite_inputs  # noqa: E402
from test.status_tests import parse_timestamp_from_log_file  # noqa: E402

logger = logging.getLogger(__name__)

#: No child gets fewer xdist workers than this (one worker gives a suite none
#: of xdist's parallelism) unless the machine has fewer logical cores.
MIN_WORKERS_PER_CHILD = 2
_POLL_INTERVAL_SECONDS = 2.0
_OUTPUT_FILENAME = "affected-gate.json"
_OUTPUT_SUBDIRS = ("test",)
_RUN_DIR_PATTERN = re.compile(r"^test-results-\d{8}-\d{6}$")
#: The one line by which ``test.ps1`` attributes a run to itself: the absolute
#: ``index.json`` path it prints under its own ``[PASSED]``/``[FAILED]`` block.
#: The runner never guesses that path from the newest directory, and neither
#: does this gate -- see :func:`attributed_run_dir`.
_DETAILS_LINE_PATTERN = re.compile(r"^\s*Details:\s+(?P<index>.+?[\\/]index\.json)\s*$")
_INCOMPLETE_MARKER = "INCOMPLETE"
_REASON_CHILD_PRODUCED_NO_RUN = "CHILD_PRODUCED_NO_RUN"
_VERDICT_RED = "RED"
_VERDICT_GREEN = "GREEN"
_VERDICT_CARRIED = "CARRIED"
_EXIT_GREEN = 0
_EXIT_RED = 1
_EXIT_USAGE = 2

_TEST_RESULTS_DIRNAME = ".test_results"
_INDEX_JSON_NAME = "index.json"
_SCHEMA_VERSION_KEY = "schema_version"
#: The first index.json schema that records ``selection`` and ``inputs``.
_STAMPED_SCHEMA_VERSION = 2
_SELECTION_KEY = "selection"
_SELECTION_KIND_KEY = "kind"
_SELECTION_FULL = "full"
_SELECTION_TARGETED = "targeted"
_RESULT_KEY = "result"
_STATUS_KEY = "status"
_COUNTS_KEY = "counts"
_INPUTS_KEY = "inputs"
_FINGERPRINT_KEY = "fingerprint"
_RESULT_PASSED = "PASSED"
_DURATION_SECONDS_KEY = "duration_seconds"
_TEST_TIME_SECONDS_KEY = "test_time_seconds"
_ZERO_COUNT_KEYS = ("failed", "error")
_SECONDS_PER_HOUR = 3600

_REASON_NO_FULL_RUN = "no full run recorded"
_REASON_RUN_IS_RED = "newest full run is RED"
_REASON_RUN_IS_INCOMPLETE = "newest full run is INCOMPLETE"
_REASON_STAMP_TOO_OLD = f"stamp older than {suite_inputs.CARRY_WINDOW_SECONDS // _SECONDS_PER_HOUR}h"
_REASON_PREDATES_STAMPS = "run predates suite-input stamps"
_REASON_CARRY_DISABLED = "carry disabled (-NoCarry)"

#: The workspace-relative audit log the full-suite guard appends its decision
#: rows to; the gate appends its own completion row to the same file.
_AUDIT_LOG_RELPATH = (".tmp", "full-suite-audit.jsonl")
#: Distinguishes the gate's completion rows from the guard's decision rows.
_AUDIT_SOURCE = "affected-gate"
_OVERALL_ABORTED = "ABORTED"
_OVERALL_USAGE_ERROR = "USAGE_ERROR"
_OVERALL_SELF_TEST_FAILED = "SELF_TEST_FAILED"
_OVERALL_INSTALL_CHECK_FAILED = "INSTALL_CHECK_FAILED"
_WALL_SECONDS_DECIMALS = 1

#: The PowerShell module holding the one install/repair implementation the
#: gate and ``test.ps1`` both call -- never reimplemented here.
_VENV_PS1_RELPATH = ("datrix", "scripts", "common", "venv.ps1")
#: The flag by which a caller tells ``test.ps1`` (and ``test_project.py`` below
#: it) that the shared venv's installs were already verified for this run.
PACKAGES_ENSURED_ENV = "DATRIX_PACKAGES_ENSURED"
_PACKAGES_ENSURED_VALUE = "1"
_XDIST_WORKERS_ENV = "PYTEST_XDIST_AUTO_NUM_WORKERS"
#: Carries the venv.ps1 path into the install check, so the command text is a
#: constant and no path is ever spliced into PowerShell source.
_VENV_SCRIPT_ENV = "DATRIX_GATE_VENV_SCRIPT"
_POWERSHELL_EXE = "powershell"
#: The same two calls, with the same failure handling, ``test.ps1`` makes
#: before its project loop.
_ENSURE_PACKAGES_COMMAND = (
    "$ErrorActionPreference = 'Stop'; "
    "try { "
    ". $env:DATRIX_GATE_VENV_SCRIPT; "
    "if (-not (Ensure-DatrixVenv)) { exit 1 }; "
    "if (-not (Ensure-DatrixPackagesInstalled -SkipIfInstalled)) { exit 1 }; "
    "exit 0 "
    "} catch { [Console]::Error.WriteLine(\"Install check failed: $_\"); exit 1 }"
)


class UsageError(Exception):
    """Invalid usage or unschedulable request; the script exits with code 2."""


class InstallCheckError(Exception):
    """The one upstream package install check failed; the gate is RED and launches no child."""


# ---------------------------------------------------------------------------
# Affected-set derivation (delegates entirely to affected_set -- no
# reimplementation of graph/closure logic here).
# ---------------------------------------------------------------------------


def compute_closure(workspace: Path, changed: list[str]) -> list[str]:
    """The changed packages union their transitive reverse-dependency
    closure, via affected_set's own closure derivation.

    This is the upper bound on which suites can observe the change -- every
    package that imports a changed one -- not the set that runs; see
    :func:`select_affected`.

    Args:
        workspace: The Datrix monorepo root.
        changed: The caller's explicitly-named changed packages.

    Returns:
        Sorted, deduplicated list of package names.
    """
    packages = affected_set.discover_packages(workspace)
    import_names = {name: affected_set.discover_import_name(d) for name, d in packages.items()}
    # The cross-ecosystem map carries the edges no import scan can see (a Node
    # consumer of a Python package's build output). Building the graphs without
    # it silently drops that consumer from the closure -- the gate would print
    # GREEN having never run it. Same derivation as affected_set's own CLI.
    cross_ecosystem = affected_set.load_cross_ecosystem_deps(workspace, packages)
    source_graph, test_graph, deferred_graph = affected_set.build_source_test_and_deferred_graphs(
        packages, import_names, include_root_conftest=True, cross_ecosystem=cross_ecosystem
    )
    closures = affected_set.compute_affected_closures(source_graph, test_graph, deferred_graph)
    closure: set[str] = set(changed)
    for name in changed:
        closure |= closures.get(name, set())
    return sorted(closure)


def select_affected(
    changed: Sequence[str],
    closure: Sequence[str],
    consumers: Sequence[str] | None,
    no_consumers: bool,
) -> tuple[list[str], list[str]]:
    """The packages to run and the closure members excluded from the run.

    A package is affected when its suite reaches the changed SURFACE, which
    the caller establishes (verification-strategy.md, "Which packages a change
    reaches") and
    states here. The import closure is where most consumers sit, but it is
    not an upper bound: a suite that runs the generation pipeline reaches every
    installed generator through entry-point discovery, an edge no import scan
    sees. So a named consumer may lie outside the closure, and the decision is
    never defaulted in either direction -- running the whole closure re-tests
    packages the change cannot reach, and running only the changed packages
    would silently drop a real consumer.

    Args:
        changed: The changed packages (always run).
        closure: ``changed`` plus every package in their reverse-dependency
            closure (:func:`compute_closure`).
        consumers: The packages whose suites reach the changed surface, or
            None when the caller named none.
        no_consumers: The caller's statement that no other package's suite
            reaches the changed surface.

    Returns:
        ``(affected, excluded)``: the sorted packages to run, and the sorted
        closure members left out of the run.

    Raises:
        UsageError: when both or neither of ``consumers``/``no_consumers`` is
            given, or when a named consumer is also a changed package.
    """
    candidates = sorted(set(closure) - set(changed))
    named = list(consumers or [])
    if named and no_consumers:
        raise UsageError(
            "Pass either -Consumers <a,b> or -NoConsumers, not both. -Consumers names the "
            "packages whose suites reach the changed surface; -NoConsumers states that none does."
        )
    if not named and not no_consumers:
        importers = ", ".join(candidates) if candidates else "none"
        raise UsageError(
            f"Say which packages besides {', '.join(changed)} the change reaches. Packages that "
            f"import the changed package(s): {importers}. A package is a consumer when its src, "
            f"tests or conftest reference a changed module or symbol (by import or dotted-path "
            f"string), directly or through an unchanged caller inside the changed package, or when "
            f"its suite runs a changed generator through the generation pipeline (procedure: "
            f".claude/skills/_shared/verification-strategy.md, 'Which packages a change reaches'). Pass "
            f"-Consumers <those packages>, or -NoConsumers if there are none."
        )
    changed_named = sorted(set(named) & set(changed))
    if changed_named:
        raise UsageError(
            f"-Consumers names package(s) already in -Projects: {', '.join(changed_named)}. A "
            f"changed package always runs; list it once, in -Projects."
        )
    affected = sorted(set(changed) | set(named))
    excluded = sorted(set(candidates) - set(named))
    return affected, excluded


# ---------------------------------------------------------------------------
# Scheduling: longest-first ordering, proportional-share worker allotment,
# and admission under the logical-core budget.
# ---------------------------------------------------------------------------


def _src_loc(package_dir: Path) -> int:
    """Total line count under package_dir/src -- the fallback duration and
    CPU-demand proxy when no full run recorded one for a package."""
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


def _full_run_indexes_newest_first(package_dir: Path) -> Iterator[dict[str, object]]:
    """Every readable ``index.json`` of a FULL run of *package_dir*, newest first.

    Only a run recording ``selection.kind == "full"`` measures the package. A
    targeted run's timings measure its subset, and a run with no ``selection``
    (written before runs recorded one) is skipped too: such runs include
    targeted subsets that cannot be told apart from full ones, so one of them
    would predict a whole suite from a handful of tests. An unreadable run is
    skipped as well -- a prediction orders and sizes children, it never
    decides a verdict, so it never refuses; it falls back instead.
    """
    for run_dir in _run_dirs_newest_first(package_dir / _TEST_RESULTS_DIRNAME):
        try:
            raw = json.loads((run_dir / _INDEX_JSON_NAME).read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            logger.debug("prediction_skips_unreadable_run run_dir=%s error=%s", run_dir, type(exc).__name__)
            continue
        if not isinstance(raw, dict) or _SELECTION_KEY not in raw:
            continue
        selection = raw[_SELECTION_KEY]
        if not isinstance(selection, dict) or _SELECTION_KIND_KEY not in selection:
            continue
        if selection[_SELECTION_KIND_KEY] == _SELECTION_FULL:
            yield {str(key): value for key, value in raw.items()}


def _newest_full_run_seconds(package_dir: Path, key: str) -> float:
    """*key* (a seconds measure) from the newest full run that recorded it as
    a non-negative number -- a newer full run without it (an INCOMPLETE run)
    is passed over for an older one that has it -- else the package's src/
    line count, which is always available and grows with the package."""
    for index in _full_run_indexes_newest_first(package_dir):
        value = index[key] if key in index else None
        if isinstance(value, (int, float)) and not isinstance(value, bool) and value >= 0:
            return float(value)
    return float(_src_loc(package_dir))


def predicted_duration_seconds(package_dir: Path) -> float:
    """The newest full run's wall-clock ``duration_seconds``: what orders the
    children longest-first. Falls back to the src/ line count when no full
    run recorded one.

    Args:
        package_dir: Absolute path to one package directory.

    Returns:
        Predicted duration in seconds (never negative).
    """
    return _newest_full_run_seconds(package_dir, _DURATION_SECONDS_KEY)


def predicted_cpu_seconds(package_dir: Path) -> float:
    """The newest full run's ``test_time_seconds`` -- per-test time summed
    across its xdist workers, roughly workers x wall -- as the package's CPU
    demand: what sizes its worker allotment. Deliberately not
    ``duration_seconds``: wall time says how long a suite took at the worker
    count it was given, not how much work it is. Falls back to the src/ line
    count when no full run recorded it.

    Args:
        package_dir: Absolute path to one package directory.

    Returns:
        Predicted CPU demand in seconds (never negative).
    """
    return _newest_full_run_seconds(package_dir, _TEST_TIME_SECONDS_KEY)


def schedule_longest_first(packages: dict[str, Path]) -> list[str]:
    """Package names ordered by predicted duration, longest first -- bounds
    makespan near the slowest suite instead of leaving it for last."""
    return sorted(packages, key=lambda name: predicted_duration_seconds(packages[name]), reverse=True)


def proportional_worker_allotment(predicted_cpu: Mapping[str, float], logical_cores: int) -> dict[str, int]:
    """Each package's worker count, in proportion to its share of the
    predicted CPU work: ``w = clamp(ceil(c / L), MIN_WORKERS_PER_CHILD, n)``
    where ``n`` is the logical core count and ``L = sum(c) / n`` -- the CPU
    seconds each core would carry if the work divided perfectly. ``L`` is
    computed once over every package, so each allotment reflects that
    package's share of the whole, not of whatever remains after the others.

    A fixed slot count gives every package the same worker count, so the
    largest suite is held to a slot's share of the machine however much of
    the work it is; here a package carrying a third of the work gets about a
    third of the cores. The floor keeps small suites parallel; the ceiling
    keeps any one child within the machine, and wins on a machine with fewer
    cores than the floor.

    Args:
        predicted_cpu: Package name -> predicted CPU seconds
            (:func:`predicted_cpu_seconds`).
        logical_cores: The machine's logical core count.

    Returns:
        Package name -> ``PYTEST_XDIST_AUTO_NUM_WORKERS`` for that child, each
        within ``[min(MIN_WORKERS_PER_CHILD, logical_cores), logical_cores]``.

    Raises:
        UsageError: ``logical_cores < 1``, or a negative predicted demand.
    """
    if logical_cores < 1:
        raise UsageError(f"The logical core count must be >= 1, got {logical_cores}.")
    negative = sorted(name for name, cpu in predicted_cpu.items() if cpu < 0)
    if negative:
        raise UsageError(
            f"Predicted CPU demand is negative for {negative}; a demand is CPU seconds (>= 0), read from "
            f"a full run's {_TEST_TIME_SECONDS_KEY} or the src/ line count."
        )
    floor = min(MIN_WORKERS_PER_CHILD, logical_cores)
    total = sum(predicted_cpu.values())
    if total == 0:
        return {name: floor for name in predicted_cpu}
    cpu_per_core = total / logical_cores
    return {
        name: min(logical_cores, max(floor, math.ceil(cpu / cpu_per_core))) for name, cpu in predicted_cpu.items()
    }


def _require_workers_within_budget(workers: int, logical_cores: int) -> None:
    if not 1 <= workers <= logical_cores:
        raise UsageError(
            f"-WorkersPerChild must be between 1 and this machine's {logical_cores} logical cores, got "
            f"{workers}: one child with more workers than cores would alone exceed the core budget. Pass a "
            f"value in range, or omit -WorkersPerChild to allot workers by each package's predicted CPU share."
        )


def _require_scheduling_options(max_concurrent: int | None, workers_per_child: int | None, logical_cores: int) -> None:
    """Refuse a ``-MaxConcurrent`` cap below 1, or a ``-WorkersPerChild``
    override outside ``[1, logical_cores]``, before anything runs."""
    if max_concurrent is not None and max_concurrent < 1:
        raise UsageError(
            f"-MaxConcurrent must be >= 1, got {max_concurrent}. It is an optional cap on how many children "
            f"run at once; omit it to be limited by the core budget alone."
        )
    if workers_per_child is not None:
        _require_workers_within_budget(workers_per_child, logical_cores)


def worker_allotment(
    package_dirs: Mapping[str, Path], workers_per_child: int | None, logical_cores: int
) -> dict[str, int]:
    """The worker count for every package to be launched: ``-WorkersPerChild``,
    when given, as a uniform override for every child; otherwise each
    package's proportional share of the predicted CPU work of exactly these
    packages (:func:`proportional_worker_allotment`) -- a carried package
    launches no child, so it takes no share of the cores.

    Raises:
        UsageError: an override outside ``[1, logical_cores]``.
    """
    if workers_per_child is not None:
        _require_workers_within_budget(workers_per_child, logical_cores)
        return {name: workers_per_child for name in package_dirs}
    predicted_cpu = {name: predicted_cpu_seconds(package_dir) for name, package_dir in package_dirs.items()}
    return proportional_worker_allotment(predicted_cpu, logical_cores)


def mypy_concurrency(max_concurrent: int | None, logical_cores: int) -> int:
    """How many ``mypy.ps1`` children ``-Mypy`` runs at once: the
    ``-MaxConcurrent`` cap when given, else one per logical core -- a mypy
    run is one process, so the core budget alone bounds them."""
    return max_concurrent if max_concurrent is not None else logical_cores


def admits_next(
    active_workers: int, active_children: int, workers: int, logical_cores: int, max_concurrent: int | None
) -> bool:
    """The one admission rule :func:`simulate_schedule` and
    :func:`run_scheduled` share: the next child starts only when its worker
    allotment fits in the cores the active children leave free and, under a
    ``-MaxConcurrent`` cap, fewer children than the cap are active."""
    under_cap = max_concurrent is None or active_children < max_concurrent
    return under_cap and active_workers + workers <= logical_cores


def _require_schedulable(
    ordered_packages: Sequence[str], allotment: Mapping[str, int], logical_cores: int, max_concurrent: int | None
) -> None:
    """Refuse a request :func:`admits_next` could never drain: every package
    needs an allotment within ``[1, logical_cores]`` -- one allotted more
    cores than exist would wait forever, or break the budget if run alone."""
    if logical_cores < 1:
        raise UsageError(f"The logical core count must be >= 1, got {logical_cores}.")
    _require_scheduling_options(max_concurrent, None, logical_cores)
    missing = [name for name in ordered_packages if name not in allotment]
    out_of_range = sorted(
        f"{name}={allotment[name]}"
        for name in ordered_packages
        if name in allotment and not 1 <= allotment[name] <= logical_cores
    )
    if missing or out_of_range:
        raise UsageError(
            f"Unschedulable worker allotment: no allotment for {missing}; outside [1, {logical_cores}] for "
            f"{out_of_range}. Allot every package through worker_allotment."
        )


@dataclass(frozen=True)
class ScheduleEvent:
    """One package's simulated [start, end) interval, with the workers it
    was allotted, under the longest-first core-budget policy."""

    package: str
    start: float
    end: float
    workers: int


def simulate_schedule(
    ordered_packages: Sequence[str],
    predicted_durations: Mapping[str, float],
    allotment: Mapping[str, int],
    logical_cores: int,
    max_concurrent: int | None = None,
) -> list[ScheduleEvent]:
    """Deterministic discrete-event simulation of the scheduler: admits the
    pending packages in order by :func:`admits_next` -- the rule
    :func:`run_scheduled` applies to real children -- and advances to the
    next finish whenever the head of the queue does not fit. Used by the
    self-test to prove the core budget is never exceeded and to measure the
    predicted makespan before spawning any real process.

    Args:
        ordered_packages: Package names, already longest-first.
        predicted_durations: Package name -> wall seconds the package takes
            at its allotted worker count.
        allotment: Package name -> worker count (:func:`worker_allotment`).
        logical_cores: The core budget no instant may exceed.
        max_concurrent: Optional cap on concurrently active children;
            ``None`` means the core budget is the only limit.

    Raises:
        UsageError: an unschedulable allotment or cap
            (:func:`_require_schedulable`), or a package with no predicted
            duration.
    """
    _require_schedulable(ordered_packages, allotment, logical_cores, max_concurrent)
    unpredicted = [name for name in ordered_packages if name not in predicted_durations]
    if unpredicted:
        raise UsageError(f"No predicted duration for {unpredicted}; simulate every package it is given.")
    pending = list(ordered_packages)
    active: list[ScheduleEvent] = []
    events: list[ScheduleEvent] = []
    clock = 0.0
    while pending:
        while pending and admits_next(
            sum(event.workers for event in active), len(active), allotment[pending[0]], logical_cores, max_concurrent
        ):
            package = pending.pop(0)
            event = ScheduleEvent(
                package=package, start=clock, end=clock + predicted_durations[package], workers=allotment[package]
            )
            active.append(event)
            events.append(event)
        if pending:
            clock = min(event.end for event in active)
            active = [event for event in active if event.end > clock]
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
    return parse_package_list(raw_projects, "-Projects", testable)


def parse_package_list(raw: Sequence[str], flag: str, testable: Mapping[str, Path]) -> list[str]:
    """Split repeatable, comma-separated package arguments and validate them.

    Raises:
        UsageError: on an unknown package name, or the SAME package named
            twice -- a duplicate is rejected outright, never silently deduped.
    """
    names: list[str] = []
    for chunk in raw:
        names.extend(name.strip() for name in chunk.split(",") if name.strip())
    duplicates = sorted({name for name in names if names.count(name) > 1})
    if duplicates:
        raise UsageError(
            f"Package(s) named more than once in {flag}: {', '.join(duplicates)}. "
            f"Pass each package exactly once."
        )
    unknown = [name for name in names if name not in testable]
    if unknown:
        raise UsageError(
            f"Unknown package(s) in {flag}: {', '.join(unknown)}. "
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
# Carry: a recorded green FULL run whose suite-input fingerprint still holds
# stands in for a fresh run. A carried verdict is a trust decision, so every
# unknown resolves to running the package -- never to carrying it.
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class CarryDecision:
    """One package's carry-or-run decision.

    ``carried`` is True only when the run named by ``run_dir`` is the newest
    full run, green, complete, inside the carry window, and its recorded
    fingerprint equals ``fingerprint`` -- the one computed now. Otherwise
    ``reason`` says why the package runs, and ``diff_components`` lists every
    fingerprint component that no longer matches (empty when the refusal came
    before any component could be compared).
    """

    carried: bool
    run_dir: str | None
    fingerprint: str | None
    reason: str | None
    diff_components: tuple[str, ...] = ()


class _CarryRefused(Exception):
    """Raised by a carry check that cannot vouch for a recorded run."""

    def __init__(self, reason: str, run_dir: str | None = None, diff: Sequence[str] = ()) -> None:
        super().__init__(reason)
        self.decision = CarryDecision(
            carried=False, run_dir=run_dir, fingerprint=None, reason=reason, diff_components=tuple(diff)
        )


@dataclass(frozen=True)
class _CarryCandidate:
    """A newest full run that passed every check not needing a fingerprint."""

    run_dir: str
    inputs: dict[str, object]


def _read_run_index(run_dir: Path) -> dict[str, object]:
    """One run's ``index.json`` object; refuses carry when it cannot be read."""
    index_path = run_dir / _INDEX_JSON_NAME
    try:
        raw = json.loads(index_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise _CarryRefused(
            f"run {run_dir.name} has no readable {_INDEX_JSON_NAME} ({type(exc).__name__}); "
            f"cannot tell whether it was a full run",
            run_dir.name,
        ) from exc
    if not isinstance(raw, dict):
        raise _CarryRefused(f"run {run_dir.name}'s {_INDEX_JSON_NAME} is not a JSON object", run_dir.name)
    return {str(key): value for key, value in raw.items()}


def _selection_kind(index: dict[str, object], run_name: str) -> str:
    """The run's recorded selection kind -- read, never inferred from its log."""
    if _SELECTION_KEY not in index:
        raise _CarryRefused(_REASON_PREDATES_STAMPS, run_name)
    selection = index[_SELECTION_KEY]
    if not isinstance(selection, dict) or _SELECTION_KIND_KEY not in selection:
        raise _CarryRefused(f"run {run_name} records a malformed selection {selection!r}", run_name)
    kind = selection[_SELECTION_KIND_KEY]
    if kind not in (_SELECTION_FULL, _SELECTION_TARGETED):
        raise _CarryRefused(f"run {run_name} records an unknown selection kind {kind!r}", run_name)
    return str(kind)


def _run_dirs_newest_first(test_results_dir: Path) -> list[Path]:
    if not test_results_dir.is_dir():
        return []
    candidates = [d for d in test_results_dir.iterdir() if d.is_dir() and _RUN_DIR_PATTERN.match(d.name)]
    return sorted(candidates, key=lambda d: d.name, reverse=True)


def _newest_full_run(test_results_dir: Path) -> tuple[str, dict[str, object]]:
    """The newest FULL run's directory name and index.

    A targeted run is skipped over and never consulted, however new or green
    it is. A run newer than the full run whose selection cannot be read (no
    ``index.json``, unreadable, no or unknown ``selection``) refuses carry: it
    might itself be a newer full run, and skipping it could hide a RED one.
    """
    for run_dir in _run_dirs_newest_first(test_results_dir):
        index = _read_run_index(run_dir)
        if _selection_kind(index, run_dir.name) == _SELECTION_FULL:
            return run_dir.name, index
    raise _CarryRefused(_REASON_NO_FULL_RUN)


def _is_zero_count(counts: object, key: str) -> bool:
    if not isinstance(counts, dict) or key not in counts:
        return False
    value = counts[key]
    return isinstance(value, int) and not isinstance(value, bool) and value == 0


def _require_green_complete_stamped_schema(index: dict[str, object], run_name: str) -> None:
    schema = index[_SCHEMA_VERSION_KEY] if _SCHEMA_VERSION_KEY in index else None
    if not isinstance(schema, int) or isinstance(schema, bool) or schema < _STAMPED_SCHEMA_VERSION:
        raise _CarryRefused(_REASON_PREDATES_STAMPS, run_name)
    result = index[_RESULT_KEY] if _RESULT_KEY in index else None
    status = index[_STATUS_KEY] if _STATUS_KEY in index else None
    counts = index[_COUNTS_KEY] if _COUNTS_KEY in index else None
    if _INCOMPLETE_MARKER in (result, status) or counts is None:
        raise _CarryRefused(_REASON_RUN_IS_INCOMPLETE, run_name)
    if result != _RESULT_PASSED or not all(_is_zero_count(counts, key) for key in _ZERO_COUNT_KEYS):
        raise _CarryRefused(_REASON_RUN_IS_RED, run_name)


def _require_within_carry_window(run_name: str, now: datetime) -> None:
    started = parse_timestamp_from_log_file(run_name)
    if started is None:
        raise _CarryRefused(f"run {run_name} carries no readable timestamp", run_name)
    age_seconds = (now - started).total_seconds()
    if age_seconds < 0:
        raise _CarryRefused(f"run {run_name} is timestamped in the future", run_name)
    if age_seconds >= suite_inputs.CARRY_WINDOW_SECONDS:
        raise _CarryRefused(_REASON_STAMP_TOO_OLD, run_name)


def _recorded_inputs(index: dict[str, object], run_name: str) -> dict[str, object]:
    """The run's stamped ``inputs``, refused before any digest is computed
    when it is absent, malformed, or stamped under another algorithm."""
    if _INPUTS_KEY not in index:
        raise _CarryRefused(_REASON_PREDATES_STAMPS, run_name)
    inputs = index[_INPUTS_KEY]
    reasons = suite_inputs.incomparable_stamp_reasons(inputs)
    if reasons:
        raise _CarryRefused("; ".join(reasons), run_name, reasons)
    if not isinstance(inputs, dict):
        raise _CarryRefused(f"run {run_name} records inputs that are not an object", run_name)
    return {str(key): value for key, value in inputs.items()}


def _carry_candidate(package_dir: Path, now: datetime) -> _CarryCandidate:
    """The package's newest full run, when every check short of the
    fingerprint comparison passes; raises :class:`_CarryRefused` otherwise."""
    run_name, index = _newest_full_run(package_dir / _TEST_RESULTS_DIRNAME)
    _require_green_complete_stamped_schema(index, run_name)
    _require_within_carry_window(run_name, now)
    return _CarryCandidate(run_dir=run_name, inputs=_recorded_inputs(index, run_name))


def _verify_candidate(
    workspace: Path, package: str, candidate: _CarryCandidate, cone: tuple[str, ...]
) -> CarryDecision:
    """Recompute *package*'s fingerprint over exactly the inputs the candidate
    run recorded (its cone trees now, and the same foreign / ignored /
    executable paths it observed) and carry only on an exact match."""
    try:
        observed = suite_inputs.ObservedInputs.from_recorded(candidate.inputs)
        current = suite_inputs.compute_inputs(workspace, package, observed, cone=cone)
        reasons = suite_inputs.diff_components(candidate.inputs, current)
    except affected_set.UsageError as exc:
        raise _CarryRefused(
            f"suite-input fingerprint could not be computed: {exc}", candidate.run_dir
        ) from exc
    if reasons:
        raise _CarryRefused("; ".join(reasons), candidate.run_dir, reasons)
    fingerprint = current[_FINGERPRINT_KEY]
    if not isinstance(fingerprint, str) or fingerprint != candidate.inputs[_FINGERPRINT_KEY]:
        raise _CarryRefused(
            "recorded fingerprint does not equal the fingerprint computed now", candidate.run_dir
        )
    return CarryDecision(carried=True, run_dir=candidate.run_dir, fingerprint=fingerprint, reason=None)


def _verify_candidates(workspace: Path, candidates: Mapping[str, _CarryCandidate]) -> dict[str, CarryDecision]:
    """Verify every candidate against ONE derivation of the workspace's cones."""
    try:
        cones = suite_inputs.package_cones(workspace)
    except affected_set.UsageError as exc:
        reason = f"package cones could not be derived: {exc}"
        return {
            name: CarryDecision(carried=False, run_dir=candidate.run_dir, fingerprint=None, reason=reason)
            for name, candidate in candidates.items()
        }
    verified: dict[str, CarryDecision] = {}
    for name, candidate in candidates.items():
        try:
            if name not in cones:
                raise _CarryRefused(f"no dependency cone was derived for {name}", candidate.run_dir)
            verified[name] = _verify_candidate(workspace, name, candidate, cones[name])
        except _CarryRefused as refused:
            verified[name] = refused.decision
    return verified


def decide_carry(workspace: Path, package_dirs: Mapping[str, Path], *, enabled: bool) -> dict[str, CarryDecision]:
    """Decide, before any child is launched, which packages carry.

    A package carries only when its newest FULL run is green (``result``
    PASSED, zero failures and errors), complete, stamped (schema 2 with an
    ``inputs`` object under the current algorithm), younger than
    ``suite_inputs.CARRY_WINDOW_SECONDS``, and its recorded fingerprint equals
    the one computed now. Every other case -- including any error while
    reading a run or computing a digest -- runs the package, with the reason.
    The workspace's cones are derived at most once, and only when some
    package got as far as the fingerprint comparison.

    Args:
        workspace: The Datrix monorepo root.
        package_dirs: Affected package name -> package directory.
        enabled: False (``-NoCarry``) runs every package regardless.

    Returns:
        One decision per package in *package_dirs*, in the same order.
    """
    if not enabled:
        return {
            name: CarryDecision(carried=False, run_dir=None, fingerprint=None, reason=_REASON_CARRY_DISABLED)
            for name in package_dirs
        }
    now = datetime.now()
    decisions: dict[str, CarryDecision] = {}
    candidates: dict[str, _CarryCandidate] = {}
    for name, package_dir in package_dirs.items():
        try:
            candidates[name] = _carry_candidate(package_dir, now)
        except _CarryRefused as refused:
            decisions[name] = refused.decision
    if candidates:
        decisions.update(_verify_candidates(workspace, candidates))
    return {name: decisions[name] for name in package_dirs}


def split_by_carry(affected: Sequence[str], decisions: Mapping[str, CarryDecision]) -> tuple[list[str], list[str]]:
    """``(to_run, carried)``: the affected packages whose child must be
    launched, and those whose recorded run stands in -- never launched.

    Raises:
        UsageError: if an affected package has no decision.
    """
    missing = [name for name in affected if name not in decisions]
    if missing:
        raise UsageError(f"No carry decision for affected package(s) {missing}; decide_carry covers every one.")
    to_run = [name for name in affected if not decisions[name].carried]
    carried = [name for name in affected if decisions[name].carried]
    return to_run, carried


def _report_carry_decisions(decisions: Mapping[str, CarryDecision]) -> None:
    for name, decision in decisions.items():
        if decision.carried:
            print(f"{name}: {_VERDICT_CARRIED} run={decision.run_dir} fingerprint={decision.fingerprint}")
        else:
            print(f"{name}: running -- {decision.reason}")


# ---------------------------------------------------------------------------
# Child process launch + monitoring.
# ---------------------------------------------------------------------------


def _echo_to_stdout(line: str) -> None:
    sys.stdout.write(line)
    sys.stdout.flush()


def _discard(line: str) -> None:
    """The self-test's echo sink: fixture child output must not read as a real run."""


class ChildOutputRelay:
    """Tees one child's stdout to this process's stdout line by line -- so a
    hang stays visible while the child runs -- and records the ``Details:``
    line by which ``test.ps1`` names the run it owns."""

    def __init__(self, stream: Iterable[str], echo: Callable[[str], None] | None = None) -> None:
        self._stream = stream
        self._echo = echo if echo is not None else _echo_to_stdout
        self.reported_index_paths: list[str] = []
        self.thread = threading.Thread(target=self._pump, daemon=True)
        self.thread.start()

    def _pump(self) -> None:
        for line in self._stream:
            self._echo(line)
            index_path = details_index_path(line)
            if index_path is not None:
                self.reported_index_paths.append(index_path)


@dataclass
class RunningChild:
    """A test.ps1 child process currently executing for one package."""

    package: str
    process: subprocess.Popen[str]
    started_at: float
    relay: ChildOutputRelay
    workers: int


def details_index_path(line: str) -> str | None:
    """The absolute ``index.json`` path a ``Details:`` line names, else None."""
    match = _DETAILS_LINE_PATTERN.match(line)
    return match.group("index") if match is not None else None


def attributed_run_dir(test_results_dir: Path, reported_index_paths: list[str]) -> str | None:
    """The run directory a child attributed to ITSELF, or None when it named
    none (or named one outside its own package's ``.test_results``).

    This is the same rule ``test.ps1`` applies internally: a run directory is
    never guessed from the newest entry under ``.test_results``. ``test.ps1``
    holds the workspace package lock only through its install phase, so a
    targeted ``-Specific`` run from another session can create a newer
    directory while a child's full suite is still running -- and "newest at
    exit" then pins that unrelated run. That is how a 7-test GREEN targeted run
    once stood in for a child that exited 1 with two failures in 5,050 tests.
    """
    resolved_results = test_results_dir.resolve()
    for raw_path in reported_index_paths:
        index_path = Path(raw_path)
        run_dir = index_path.parent
        if run_dir.parent.resolve() != resolved_results:
            continue
        if _RUN_DIR_PATTERN.match(run_dir.name) is None:
            continue
        return run_dir.name
    return None


def venv_script_path(workspace: Path) -> Path:
    """The ``venv.ps1`` module holding ``Ensure-DatrixPackagesInstalled``."""
    return workspace.joinpath(*_VENV_PS1_RELPATH)


def ensure_packages_installed_once(venv_script: Path) -> None:
    """Verify (and repair) the shared venv's package installs ONCE for the gate.

    Every child is a ``test.ps1`` run against the one shared venv; each would
    otherwise spend its own ``Ensure-DatrixPackagesInstalled -SkipIfInstalled``
    check (a ``python -c "import ..."`` spawn per package) on the same answer.
    This runs the same two calls ``test.ps1`` makes -- ``Ensure-DatrixVenv``,
    then ``Ensure-DatrixPackagesInstalled -SkipIfInstalled`` -- by dot-sourcing
    the same ``venv.ps1``, so the install/repair logic has one home. Each child
    is then launched with ``DATRIX_PACKAGES_ENSURED=1`` (:func:`_child_environment`)
    and skips its own check.

    Its output streams through: with ``DATRIX_VENV_VERBOSE=1`` the check's
    progress lines appear once, here, and in no child.

    Raises:
        InstallCheckError: *venv_script* does not exist, or the check exited
            non-zero. Launching children against a venv that failed its check
            would only fail every child separately; the gate fails once, loud.
    """
    if not venv_script.is_file():
        raise InstallCheckError(
            f"The venv module {venv_script} does not exist, so the package install check cannot run. "
            f"Expected the workspace's datrix/scripts/common/venv.ps1; run the gate from the Datrix "
            f"workspace it belongs to."
        )
    env = os.environ.copy()
    env[_VENV_SCRIPT_ENV] = str(venv_script)
    logger.info("install_check_started venv_script=%s", venv_script)
    result = subprocess.run(
        [_POWERSHELL_EXE, "-NoProfile", "-NonInteractive", "-Command", _ENSURE_PACKAGES_COMMAND],
        env=env,
        check=False,
    )
    if result.returncode != 0:
        raise InstallCheckError(
            f"The package install check (Ensure-DatrixVenv, then Ensure-DatrixPackagesInstalled "
            f"-SkipIfInstalled, from {venv_script}) exited {result.returncode} before any child was "
            f"launched. Fix the venv/install error printed above -- set DATRIX_VENV_VERBOSE=1 to see "
            f"each package it checked -- then re-run the gate."
        )
    logger.info("install_check_passed venv_script=%s", venv_script)


def _child_environment(workers: int) -> dict[str, str]:
    """A child's environment: this process's, with the child's xdist worker
    budget and the flag saying the gate already ran the install check."""
    env = os.environ.copy()
    env[_XDIST_WORKERS_ENV] = str(workers)
    env[PACKAGES_ENSURED_ENV] = _PACKAGES_ENSURED_VALUE
    return env


def _launch_child(workspace: Path, package: str, workers: int, dbg: bool) -> subprocess.Popen[str]:
    """Launch `test.ps1 <package>` as a child process with a capped xdist
    worker budget. The child's stdout is relayed line by line to this
    process's stdout by a :class:`ChildOutputRelay` (never suppressed, so a
    hang is visible while it runs); its stderr streams through directly."""
    env = _child_environment(workers)
    logger.info(
        "scheduling package=%s workers=%d PYTEST_XDIST_AUTO_NUM_WORKERS=%d",
        package, workers, workers,
    )
    test_ps1 = workspace / "datrix" / "scripts" / "test" / "test.ps1"
    args = ["powershell", "-File", str(test_ps1), package]
    if dbg:
        args.append("-Dbg")
    return subprocess.Popen(
        args, env=env, stdout=subprocess.PIPE, text=True, encoding="utf-8", errors="replace"
    )


def _start_child(workspace: Path, package: str, workers: int, dbg: bool) -> RunningChild:
    proc = _launch_child(workspace, package, workers, dbg)
    if proc.stdout is None:
        raise UsageError(f"child for {package} was launched without a stdout pipe")
    return RunningChild(
        package=package,
        process=proc,
        started_at=time.monotonic(),
        relay=ChildOutputRelay(proc.stdout),
        workers=workers,
    )


def run_scheduled(
    workspace: Path,
    ordered_packages: list[str],
    allotment: Mapping[str, int],
    logical_cores: int,
    max_concurrent: int | None,
    dbg: bool,
) -> tuple[set[str], dict[str, str], dict[str, float]]:
    """Launch `ordered_packages` (already longest-first) as `test.ps1`
    child processes, each with its own worker allotment, admitting the next
    one only by :func:`admits_next` -- the rule :func:`simulate_schedule`
    proves never lets the live children's workers sum above
    ``logical_cores``, nor (under a ``-MaxConcurrent`` cap) more than
    ``max_concurrent`` children run at once -- and never two live children
    for the same package (each package appears at most once in
    `ordered_packages` by construction of the affected set). Blocks until
    every child has exited. An empty `ordered_packages` (every affected
    package carried) launches nothing.

    Raises:
        UsageError: an allotment that could never be admitted
            (:func:`_require_schedulable`).

    Returns:
        ``(forced_red, produced_runs, wall_seconds)``. ``wall_seconds`` maps
        every launched package to its child's elapsed wall-clock seconds.
        ``forced_red`` names the packages
        whose child exited without naming a run directory of its own -- a
        hard crash before ``test.ps1`` printed its ``Details:`` line; the
        caller must treat these as forced-RED rather than trusting
        gate_verdict's own newest-run lookup, which would otherwise silently
        report a STALE prior (possibly GREEN) run. ``produced_runs`` maps
        every other package to the run directory its child attributed to
        itself on its own stdout (:func:`attributed_run_dir`); the caller
        must judge THAT run and no other. The newest directory under
        ``.test_results`` is never consulted: a targeted run from another
        session can land a newer directory before OR after the child exits
        (``test.ps1`` holds the package lock only through its install
        phase), and a newest-run lookup then reports that unrelated result
        -- a GREEN 59-test subset once stood in for a RED 5,950-test suite,
        and a GREEN 7-test subset for a child that exited 1.
    """
    _require_schedulable(ordered_packages, allotment, logical_cores, max_concurrent)
    pending = list(ordered_packages)
    running: list[RunningChild] = []
    forced_red: set[str] = set()
    produced_runs: dict[str, str] = {}
    wall_seconds: dict[str, float] = {}
    while pending or running:
        while pending and admits_next(
            sum(child.workers for child in running), len(running), allotment[pending[0]], logical_cores, max_concurrent
        ):
            package = pending.pop(0)
            running.append(_start_child(workspace, package, allotment[package], dbg))
        finished = [child for child in running if child.process.poll() is not None]
        for child in finished:
            elapsed = time.monotonic() - child.started_at
            wall_seconds[child.package] = elapsed
            child.relay.thread.join()
            own_run = attributed_run_dir(
                workspace / child.package / ".test_results", child.relay.reported_index_paths
            )
            if own_run is None:
                forced_red.add(child.package)
                print(
                    f"{child.package}: child exited code={child.process.returncode} "
                    f"after {elapsed:.1f}s WITHOUT naming a run directory of its own "
                    f"-- forcing RED (never trusting a stale prior result)"
                )
            else:
                produced_runs[child.package] = own_run
                print(
                    f"{child.package}: child exited code={child.process.returncode} "
                    f"after {elapsed:.1f}s run={own_run}"
                )
            running.remove(child)
        if running:
            time.sleep(_POLL_INTERVAL_SECONDS)
    return forced_red, produced_runs, wall_seconds


def run_mypy_for_changed(workspace: Path, changed: list[str], max_concurrent: int, dbg: bool) -> bool:
    """Run `mypy.ps1 <pkg>` for each CHANGED package (never the whole
    affected set), at most `max_concurrent` at once (:func:`mypy_concurrency`).

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
    produced_runs: dict[str, str],
    carry_decisions: Mapping[str, CarryDecision],
    output_path: Path,
    *,
    excluded: Sequence[str],
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

    `produced_runs` pins every other package to the run its child produced.
    The newest-run lookup is wrong in the other direction too: a run that
    lands AFTER the child exits (a targeted subset from another session)
    would replace the child's RED whole-suite result with an unrelated GREEN.

    `carry_decisions` holds one decision per affected package. A carried
    package is pinned to the run its fingerprint matched and passed as
    ``carried`` (its row is CARRIED, naming that run, its age and the
    fingerprint); every row in ``affected-gate.json`` also records
    ``carry_reason`` and ``diff_components`` -- why a package ran instead of
    carrying, component by component.

    `excluded` names the packages that import a changed package but that the
    caller established the change does not reach; the payload records them so
    a narrowed run is never mistaken for a closure-wide one.

    Raises:
        UsageError: if an affected package has no carry decision, or a
            carried package was also launched.
    """
    missing = sorted(set(affected) - set(carry_decisions))
    carried = {name: decision for name, decision in carry_decisions.items() if decision.carried}
    launched_and_carried = sorted(set(carried) & (set(produced_runs) | set(forced_red)))
    if missing or launched_and_carried:
        raise UsageError(
            f"Inconsistent aggregation request: no carry decision for {missing}; carried "
            f"but also launched {launched_and_carried}. Every affected package needs exactly "
            f"one decision, and a carried package is never launched."
        )
    pinned_runs = dict(produced_runs)
    carried_fingerprints: dict[str, str] = {}
    for name, decision in carried.items():
        if decision.run_dir is None or decision.fingerprint is None:
            raise UsageError(f"Carried package {name} names no run directory or fingerprint: {decision}.")
        pinned_runs[name] = decision.run_dir
        carried_fingerprints[name] = decision.fingerprint
    result = gate_verdict.evaluate_projects(
        workspace,
        affected,
        forced_red=forced_red,
        pinned_runs=pinned_runs,
        carried=carried_fingerprints,
    )
    rows = [
        {
            **row.to_json(),
            "carry_reason": carry_decisions[row.project].reason,
            "diff_components": list(carry_decisions[row.project].diff_components),
        }
        for row in result.rows
    ]
    payload = {**result.payload, "projects": rows, "excluded": sorted(excluded)}
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False) + "\n",
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
# Completion row: the gate's own record, in the full-suite audit log, of what
# a sweep ran and what carry saved.
# ---------------------------------------------------------------------------


@dataclass
class CompletionRecord:
    """What one gate invocation did, filled in as it progresses.

    ``overall`` stays ``ABORTED`` unless the invocation reaches a verdict (or
    a usage / self-test failure), so an interrupted sweep is still recorded
    and never recorded as green.
    """

    changed: list[str] = field(default_factory=list)
    consumers: list[str] = field(default_factory=list)
    excluded: list[str] = field(default_factory=list)
    ran: list[str] = field(default_factory=list)
    carried: list[str] = field(default_factory=list)
    wall_seconds: dict[str, float] = field(default_factory=dict)
    overall: str = _OVERALL_ABORTED


def audit_log_path(workspace: Path) -> Path:
    """The full-suite audit log the guard and the gate both append to."""
    return workspace.joinpath(*_AUDIT_LOG_RELPATH)


def append_completion_row(audit_path: Path, record: CompletionRecord) -> dict[str, object]:
    """Append one completion row to *audit_path* and return it.

    ``ts`` is integer epoch seconds -- the same JSON type the full-suite
    guard's decision rows carry -- so a reader sorting or ageing rows by
    ``ts`` handles both writers; ``source`` distinguishes this row from the
    guard's. A failure to write is raised, never swallowed: a sweep that
    leaves no record is not allowed to look like one that did.
    """
    row: dict[str, object] = {
        "ts": int(time.time()),
        "source": _AUDIT_SOURCE,
        "changed": list(record.changed),
        "consumers": list(record.consumers),
        "excluded": list(record.excluded),
        "ran": list(record.ran),
        "carried": list(record.carried),
        "wall_seconds": {
            name: round(seconds, _WALL_SECONDS_DECIMALS) for name, seconds in sorted(record.wall_seconds.items())
        },
        "overall": record.overall,
    }
    audit_path.parent.mkdir(parents=True, exist_ok=True)
    with audit_path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(row, ensure_ascii=False) + "\n")
    return row


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
        except (AssertionError, UsageError, InstallCheckError, affected_set.UsageError, gate_verdict.UsageError) as e:
            _fail(f"{name}: {type(e).__name__}: {e}")
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
    parser.add_argument(
        "--consumers", action="append",
        help=(
            "Packages (besides the changed ones) whose suites reach the changed surface; repeatable "
            "and/or comma-separated. Required, or --no-consumers, unless --all"
        ),
    )
    parser.add_argument(
        "--no-consumers", action="store_true",
        help="State that no package besides the changed ones reaches the changed surface",
    )
    parser.add_argument("--all", action="store_true", help="Treat every discovered package as changed")
    parser.add_argument(
        "--max-concurrent", type=int, default=None,
        help=(
            "Optional cap on concurrently running package suites (default: none -- children are admitted "
            "while their worker allotments fit in the logical core count)"
        ),
    )
    parser.add_argument(
        "--workers-per-child", type=int, default=None,
        help=(
            "Uniform PYTEST_XDIST_AUTO_NUM_WORKERS override for every child, 1..logical cores (default: each "
            f"package's share of the predicted CPU work, ceil(c / (sum(c) / cores)), clamped to "
            f"[{MIN_WORKERS_PER_CHILD}, cores])"
        ),
    )
    parser.add_argument("--mypy", action="store_true", help="Also run mypy.ps1 for the changed packages, inside the same budget")
    parser.add_argument("--force", action="store_true", help="Start even if a requested package's newest run looks in-progress")
    parser.add_argument(
        "--no-carry",
        action="store_true",
        help=(
            "Run every affected package even when its recorded green full run's "
            "fingerprint still matches (flakiness hunts, a scheduled full sweep)"
        ),
    )
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


def _select_for_run(
    args: argparse.Namespace, workspace: Path, changed: list[str], testable: Mapping[str, Path]
) -> tuple[list[str], list[str]]:
    """``(affected, excluded)`` for this invocation; ``-All`` runs every package."""
    if args.all:
        if args.consumers or args.no_consumers:
            raise UsageError("-All runs every package; drop -Consumers/-NoConsumers.")
        return list(changed), []
    consumers = parse_package_list(args.consumers, "-Consumers", testable) if args.consumers else None
    closure = compute_closure(workspace, changed)
    return select_affected(changed, closure, consumers, args.no_consumers)


def _run(args: argparse.Namespace, workspace: Path, record: CompletionRecord) -> int:
    testable = affected_set.discover_packages(workspace)
    changed = _resolve_requested_packages(args.projects, args.all, testable)
    record.changed = list(changed)
    affected, record.excluded = _select_for_run(args, workspace, changed, testable)
    record.consumers = sorted(set(affected) - set(changed))
    if record.excluded:
        print(f"Excluded (import a changed package; change does not reach them): {', '.join(record.excluded)}")

    _reject_in_progress_unless_forced(workspace, affected, args.force)

    logical_cores = os.cpu_count() or 1
    _require_scheduling_options(args.max_concurrent, args.workers_per_child, logical_cores)

    # Once per gate, before the carry decision and before any child: the carry
    # fingerprint's installed-distributions component is then computed over the
    # venv exactly as the children will find it, including after a repair.
    ensure_packages_installed_once(venv_script_path(workspace))

    carry_decisions = decide_carry(
        workspace, {name: testable[name] for name in affected}, enabled=not args.no_carry
    )
    _report_carry_decisions(carry_decisions)
    to_run, record.carried = split_by_carry(affected, carry_decisions)

    to_run_dirs = {name: testable[name] for name in to_run}
    ordered = schedule_longest_first(to_run_dirs)
    record.ran = list(ordered)
    allotment = worker_allotment(to_run_dirs, args.workers_per_child, logical_cores)
    logger.info(
        "scheduling to_run=%s carried=%s allotment=%s max_concurrent=%s logical_cores=%d",
        ordered, record.carried, allotment, args.max_concurrent, logical_cores,
    )

    forced_red_set, produced_runs, wall_seconds = run_scheduled(
        workspace, ordered, allotment, logical_cores, args.max_concurrent, args.debug
    )
    record.wall_seconds = wall_seconds
    forced_red = {pkg: _REASON_CHILD_PRODUCED_NO_RUN for pkg in forced_red_set}

    mypy_ok = True
    if args.mypy:
        mypy_ok = run_mypy_for_changed(
            workspace, changed, mypy_concurrency(args.max_concurrent, logical_cores), args.debug
        )
        if not mypy_ok:
            print("mypy: at least one changed package failed type-checking", file=sys.stderr)

    output_path = _resolve_output_path(args.output, workspace)
    exit_code = _aggregate_verdict(
        workspace, affected, forced_red, produced_runs, carry_decisions, output_path, excluded=record.excluded
    )
    if args.mypy and not mypy_ok:
        return _EXIT_RED
    return exit_code


def _run_recorded(args: argparse.Namespace, workspace: Path, self_test_passed: bool, record: CompletionRecord) -> int:
    """Run the gate, setting ``record.overall`` for every way it can end
    short of an interrupt (which leaves it ``ABORTED``)."""
    if not self_test_passed:
        record.overall = _OVERALL_SELF_TEST_FAILED
        print(
            "\nError: self-test failed -- refusing to trust the scheduler for a real run.",
            file=sys.stderr,
        )
        return _EXIT_RED
    try:
        exit_code = _run(args, workspace, record)
    except UsageError as exc:
        record.overall = _OVERALL_USAGE_ERROR
        print(f"ERROR: {exc}", file=sys.stderr)
        return _EXIT_USAGE
    except InstallCheckError as exc:
        record.overall = _OVERALL_INSTALL_CHECK_FAILED
        print(f"ERROR: {exc}", file=sys.stderr)
        return _EXIT_RED
    record.overall = _VERDICT_GREEN if exit_code == _EXIT_GREEN else _VERDICT_RED
    return exit_code


# ---------------------------------------------------------------------------
# Self-test checks (pure-function scheduling/validation/aggregation checks --
# none spawn a real test.ps1 subprocess; see Success Criterion 8's POSITIVE
# check for the real end-to-end proof).
# ---------------------------------------------------------------------------


#: Per-package CPU seconds (``test_time_seconds``) measured over the full runs
#: of 2026-09-23 on a 12-logical-core machine: a fixed table, so the
#: scheduling checks judge the policy on real proportions, not a toy.
_COST_TABLE_CPU_SECONDS: dict[str, float] = {
    "python": 7589.0, "typescript": 3181.0, "codegen-common": 3251.0, "dotnet": 2748.0,
    "java": 1690.0, "docker": 1234.0, "cli": 1138.0, "common": 1095.0, "azure": 953.0,
    "angular": 753.0, "component": 716.0, "sql": 667.0, "language": 460.0, "aws": 203.0,
    "vscode": 27.0, "extensions": 5.0,
}
_COST_TABLE_LOGICAL_CORES = 12
_BUDGET_CHECK_CORE_COUNTS = (1, 2, 8, _COST_TABLE_LOGICAL_CORES, 32)
#: The bound the proportional policy's simulated makespan must stay within,
#: as a multiple of the CPU lower bound sum(c) / n -- the makespan of a
#: perfect division of the work across every core.
_MAKESPAN_BOUND_OVER_CPU_LOWER_BOUND = 1.25
#: The -MaxConcurrent default the retired fixed-slot policy shipped with (that
#: many slots, floor(n / slots) workers each). A historical baseline for the
#: makespan self-test only -- never live scheduling configuration.
_RETIRED_FIXED_SLOT_COUNT = 4
_FIXTURE_FULL_RUN = "test-results-20260729-120000"


def _durations_at_allotted_workers(cpu: Mapping[str, float], allotment: Mapping[str, int]) -> dict[str, float]:
    """Wall seconds each package takes at its allotted worker count: CPU
    seconds are roughly workers x wall, so wall = c / w."""
    return {name: cpu[name] / allotment[name] for name in cpu}


def _fixed_slot_makespan(cpu: dict[str, float], logical_cores: int, slots: int) -> float:
    """The retired fixed-slot policy's makespan on *cpu*, under the same
    wall = c / w model: ``slots`` slots of ``floor(logical_cores / slots)``
    workers each, packages placed longest-first on whichever slot frees
    first. The makespan self-test's baseline only; nothing schedules by it."""
    workers = max(1, logical_cores // slots)
    slot_free_at = [0.0] * slots
    heapq.heapify(slot_free_at)
    for name in sorted(cpu, key=lambda package: cpu[package], reverse=True):
        start = heapq.heappop(slot_free_at)
        heapq.heappush(slot_free_at, start + cpu[name] / workers)
    return max(slot_free_at)


def _simulate_cost_table(logical_cores: int, max_concurrent: int | None = None) -> list[ScheduleEvent]:
    """The cost table under the proportional allotment, longest-first by the
    wall time each package takes at its allotted worker count."""
    allotment = proportional_worker_allotment(_COST_TABLE_CPU_SECONDS, logical_cores)
    durations = _durations_at_allotted_workers(_COST_TABLE_CPU_SECONDS, allotment)
    ordered = sorted(durations, key=lambda name: durations[name], reverse=True)
    return simulate_schedule(ordered, durations, allotment, logical_cores, max_concurrent)


def _check_budget_never_exceeds_cores_across_simulated_schedule() -> None:
    """The core budget holds at every simulated instant, on every machine
    size -- including one with fewer cores than the per-child floor -- and is
    actually filled on the table's own machine, so the bound is not met by
    leaving cores idle. The peak measure is proven to see an over-budget
    overlap, and an allotment larger than the machine is refused rather than
    run alone past the budget."""
    for cores in _BUDGET_CHECK_CORE_COUNTS:
        events = _simulate_cost_table(cores)
        peak = max_concurrent_workers(events)
        assert peak <= cores, f"peak worker demand {peak} exceeds {cores} logical cores"
        assert sorted(event.package for event in events) == sorted(_COST_TABLE_CPU_SECONDS), events
        if cores == _COST_TABLE_LOGICAL_CORES:
            assert peak == cores, f"the schedule never used all {cores} cores (peak {peak}); the check is vacuous"
    overlapping = [ScheduleEvent("pkg-a", 0.0, 10.0, 8), ScheduleEvent("pkg-b", 5.0, 15.0, 8)]
    assert max_concurrent_workers(overlapping) == 16, "the peak measure missed an over-budget overlap"
    try:
        simulate_schedule(["pkg-a"], {"pkg-a": 1.0}, {"pkg-a": 13}, 12)
    except UsageError:
        pass
    else:
        raise AssertionError("an allotment above the core count must be refused, never run alone past the budget")


def _check_proportional_allotment_follows_the_cpu_share_rule() -> None:
    """w = clamp(ceil(c / L), 2, n) with one L = sum(c) / n for every package.
    Concrete expectations, so a check that re-derived the formula could not
    pass a wrong one: the table's largest suite gets 4 of 12 cores and 10 of
    32; a 60/25/15 split of the work over 10 cores gets 6/3/2 workers (an L
    recomputed from the shrinking remainder would inflate the later ones); the
    ceiling holds a dominant package to the machine and wins over the floor
    on a one-core machine; zero demand gets the floor; negative demand and a
    zero-core machine are refused."""
    at_twelve = proportional_worker_allotment(_COST_TABLE_CPU_SECONDS, _COST_TABLE_LOGICAL_CORES)
    assert at_twelve["python"] == 4 and at_twelve["codegen-common"] == 2, at_twelve
    assert at_twelve["extensions"] == MIN_WORKERS_PER_CHILD, at_twelve
    assert proportional_worker_allotment(_COST_TABLE_CPU_SECONDS, 32)["python"] == 10
    shares = proportional_worker_allotment({"pkg-a": 600.0, "pkg-b": 250.0, "pkg-c": 150.0}, 10)
    assert shares == {"pkg-a": 6, "pkg-b": 3, "pkg-c": 2}, shares
    assert proportional_worker_allotment({"pkg-huge": 1000.0, "pkg-tiny": 1.0}, 8) == {"pkg-huge": 8, "pkg-tiny": 2}
    assert proportional_worker_allotment({"pkg-a": 50.0, "pkg-b": 5.0}, 1) == {"pkg-a": 1, "pkg-b": 1}
    assert proportional_worker_allotment({"pkg-a": 0.0, "pkg-b": 0.0}, 12) == {"pkg-a": 2, "pkg-b": 2}
    for demand, cores in (({"pkg-a": -1.0}, 12), ({"pkg-a": 1.0}, 0)):
        try:
            proportional_worker_allotment(demand, cores)
        except UsageError:
            continue
        raise AssertionError(f"allotting {demand} over {cores} cores must raise UsageError")


def _check_proportional_makespan_within_bound_of_the_cpu_lower_bound() -> None:
    """On the fixed cost table and its own machine, the proportional
    policy's simulated makespan is at least the CPU lower bound sum(c) / n
    (no schedule beats a perfect division of the work, so a simulation that
    did would be wrong) and within the stated multiple of it."""
    events = _simulate_cost_table(_COST_TABLE_LOGICAL_CORES)
    makespan = max(event.end for event in events)
    lower_bound = sum(_COST_TABLE_CPU_SECONDS.values()) / _COST_TABLE_LOGICAL_CORES
    assert makespan >= lower_bound, f"simulated makespan {makespan:.1f}s beats the CPU lower bound {lower_bound:.1f}s"
    assert makespan <= _MAKESPAN_BOUND_OVER_CPU_LOWER_BOUND * lower_bound, (
        f"simulated makespan {makespan:.1f}s exceeds {_MAKESPAN_BOUND_OVER_CPU_LOWER_BOUND} x the CPU lower "
        f"bound {lower_bound:.1f}s on the fixed cost table"
    )


def _check_proportional_makespan_no_worse_than_retired_fixed_slot_policy() -> None:
    """On the fixed cost table and its own machine, under the same
    wall = c / w model, the proportional policy's simulated makespan is no
    worse than the fixed-slot policy it replaces as shipped
    (``_RETIRED_FIXED_SLOT_COUNT`` slots of floor(n / slots) workers)."""
    events = _simulate_cost_table(_COST_TABLE_LOGICAL_CORES)
    proportional = max(event.end for event in events)
    fixed_slot = _fixed_slot_makespan(_COST_TABLE_CPU_SECONDS, _COST_TABLE_LOGICAL_CORES, _RETIRED_FIXED_SLOT_COUNT)
    assert proportional <= fixed_slot, (
        f"proportional makespan {proportional:.1f}s must be <= the retired fixed-slot policy's "
        f"{fixed_slot:.1f}s ({_RETIRED_FIXED_SLOT_COUNT} slots x "
        f"{_COST_TABLE_LOGICAL_CORES // _RETIRED_FIXED_SLOT_COUNT} workers) on the fixed cost table"
    )
    logger.info(
        "makespan_comparison proportional_seconds=%.1f retired_fixed_slot_seconds=%.1f", proportional, fixed_slot
    )


def _check_worker_allotment_override_is_uniform_and_bounded() -> None:
    """-WorkersPerChild is a uniform override, accepted only within
    [1, logical cores]; without it the allotment is the proportional share of
    the packages' recorded CPU demand; a -MaxConcurrent cap below 1 is
    refused before anything runs."""
    with tempfile.TemporaryDirectory(prefix="affected-gate-selftest-") as tmp:
        root = Path(tmp)
        package_dirs = {
            name: _make_package_with_full_run(root, name, duration_seconds=60.0, cpu_seconds=cpu)
            for name, cpu in (("datrix-heavy", 900.0), ("datrix-light", 300.0))
        }
        assert worker_allotment(package_dirs, 3, 12) == {"datrix-heavy": 3, "datrix-light": 3}
        assert worker_allotment(package_dirs, None, 12) == {"datrix-heavy": 9, "datrix-light": 3}
        for workers in (0, 13):
            try:
                worker_allotment(package_dirs, workers, 12)
            except UsageError:
                continue
            raise AssertionError(f"-WorkersPerChild {workers} on 12 cores must raise UsageError")
    try:
        _require_scheduling_options(0, None, 12)
    except UsageError:
        pass
    else:
        raise AssertionError("-MaxConcurrent 0 must raise UsageError")


def _make_package_with_full_run(
    root: Path, name: str, *, duration_seconds: float, cpu_seconds: float, run_name: str = _FIXTURE_FULL_RUN
) -> Path:
    pkg_dir = root / name
    payload: dict[str, object] = {
        "selection": {"kind": _SELECTION_FULL},
        "duration_seconds": duration_seconds,
        "test_time_seconds": cpu_seconds,
    }
    _write_run(pkg_dir, run_name, payload)
    return pkg_dir


def _check_longest_first_ordering() -> None:
    """Ordered by the newest FULL run's wall time: a newer, shorter targeted
    run of the slowest package does not move it to the back."""
    with tempfile.TemporaryDirectory(prefix="affected-gate-selftest-") as tmp:
        root = Path(tmp)
        package_dirs = {
            name: _make_package_with_full_run(root, name, duration_seconds=duration, cpu_seconds=duration)
            for name, duration in (("datrix-slow", 500.0), ("datrix-fast", 10.0), ("datrix-mid", 90.0))
        }
        _write_run(
            package_dirs["datrix-slow"],
            "test-results-20260729-130000",
            {"selection": {"kind": _SELECTION_TARGETED}, "duration_seconds": 5.0, "test_time_seconds": 4.0},
        )
        ordered = schedule_longest_first(package_dirs)
        assert ordered == ["datrix-slow", "datrix-mid", "datrix-fast"], ordered


def _check_predicted_cpu_seconds_reads_test_time_of_the_newest_full_run() -> None:
    """The CPU demand is ``test_time_seconds`` (not ``duration_seconds``) of
    the newest FULL run that recorded it: newer targeted, selection-less and
    unreadable runs are passed over, as is a newer full run that recorded no
    measure; with no full run at all the src/ line count stands in."""
    with tempfile.TemporaryDirectory(prefix="affected-gate-selftest-") as tmp:
        root = Path(tmp)
        package_dir = _make_package_with_full_run(
            root, "datrix-mixed", duration_seconds=30.0, cpu_seconds=210.0, run_name="test-results-20260924-000000"
        )
        newer_runs: tuple[tuple[str, dict[str, object]], ...] = (
            ("test-results-20260924-000100", {"selection": {"kind": _SELECTION_FULL}, "result": _INCOMPLETE_MARKER}),
            ("test-results-20260924-000200", {"selection": {"kind": _SELECTION_TARGETED}, "test_time_seconds": 5.0}),
            ("test-results-20260924-000300", {"schema_version": 1, "test_time_seconds": 7.0, "duration_seconds": 3.0}),
        )
        for run_name, payload in newer_runs:
            _write_run(package_dir, run_name, payload)
        unreadable = package_dir / _TEST_RESULTS_DIRNAME / "test-results-20260924-000400"
        unreadable.mkdir()
        (unreadable / _INDEX_JSON_NAME).write_text("{ not json", encoding="utf-8")
        cpu = predicted_cpu_seconds(package_dir)
        assert cpu == 210.0, f"expected the full run's test_time_seconds (210.0), got {cpu}"
        assert predicted_duration_seconds(package_dir) == 30.0, predicted_duration_seconds(package_dir)

        no_full_run = root / "datrix-targeted-only"
        targeted_only = {"selection": {"kind": _SELECTION_TARGETED}, "test_time_seconds": 9.0}
        _write_run(no_full_run, "test-results-20260924-000000", targeted_only)
        src_dir = no_full_run / "src" / "datrix_targeted_only"
        src_dir.mkdir(parents=True)
        (src_dir / "module.py").write_text("\n".join(f"line_{i} = {i}" for i in range(11)) + "\n", encoding="utf-8")
        assert predicted_cpu_seconds(no_full_run) == 11.0, predicted_cpu_seconds(no_full_run)


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
            {},
            _not_carried(["datrix-crashed"]),
            output_path,
            excluded=[],
        )
        assert exit_code == _EXIT_RED, f"forced_red package must make the overall verdict RED, got {exit_code}"
        payload = json.loads(output_path.read_text(encoding="utf-8"))
        row = payload["projects"][0]
        assert row["verdict"] == _VERDICT_RED, row
        assert row["reason"] == _REASON_CHILD_PRODUCED_NO_RUN, row


def _write_index(run_dir: Path, *, status: str, passed: int, failed: int) -> None:
    """A minimal ``index.json`` in the shape ``test.ps1`` writes and
    ``status_tests.parse_pytest_summary`` reads (``result`` + ``counts``)."""
    run_dir.mkdir(parents=True)
    (run_dir / "index.json").write_text(
        json.dumps(
            {
                "schema_version": 1,
                "result": status,
                "counts": {"passed": passed, "failed": failed, "error": 0, "skipped": 0},
                "failures": [],
                "errors": [],
            }
        ),
        encoding="utf-8",
    )


def _check_verdict_is_pinned_to_the_childs_run_never_a_newer_one() -> None:
    """The run the child produced is RED; a NEWER run (a targeted subset
    another session landed after the child exited) is GREEN. The aggregate
    must judge the child's run and report RED. The newest-run lookup would
    report the later GREEN -- the false green that was actually observed:
    a 59-test targeted run standing in for a 5,950-test RED suite."""
    with tempfile.TemporaryDirectory(prefix="affected-gate-selftest-") as tmp:
        workspace = Path(tmp)
        results = workspace / "datrix-raced" / ".test_results"
        child_run = "test-results-20260101-000100"
        _write_index(results / child_run, status="FAILED", passed=5949, failed=1)
        _write_index(results / "test-results-20260101-000200", status="PASSED", passed=59, failed=0)
        output_path = workspace / ".tmp" / "test" / "affected-gate.json"
        exit_code = _aggregate_verdict(
            workspace, ["datrix-raced"], {}, {"datrix-raced": child_run}, _not_carried(["datrix-raced"]), output_path,
            excluded=[],
        )
        assert exit_code == _EXIT_RED, f"the pinned RED run must make the verdict RED, got {exit_code}"
        payload = json.loads(output_path.read_text(encoding="utf-8"))
        row = payload["projects"][0]
        assert row["verdict"] == _VERDICT_RED, row
        assert row["run_dir"].endswith(child_run), row
        assert row["counts"]["failed"] == 1, row


def _check_child_run_is_attributed_from_its_own_details_line_never_the_newest_dir() -> None:
    """A child's run is pinned from the ``Details:`` line the child itself
    printed -- never from the newest directory under ``.test_results``. A
    targeted run from another session lands a NEWER GREEN directory while
    the child's RED full suite is still running (``test.ps1`` releases the
    package lock after its install phase); "newest at exit" pinned that
    unrelated run and reported a child that exited 1 as GREEN 7 passed."""
    with tempfile.TemporaryDirectory(prefix="affected-gate-selftest-") as tmp:
        workspace = Path(tmp)
        results = workspace / "datrix-overtaken" / ".test_results"
        child_run = "test-results-20260101-000100"
        concurrent_run = "test-results-20260101-000200"
        _write_index(results / child_run, status="FAILED", passed=5047, failed=2)
        _write_index(results / concurrent_run, status="PASSED", passed=7, failed=0)
        assert _newest_run_dir_any_state(results) == concurrent_run, (
            "fixture must make the concurrent run the newest directory, or the check is vacuous"
        )
        child_stdout = io.StringIO(
            "[FAILED] datrix-overtaken\n"
            "  pass: 5047, fail: 2, skip: 1\n"
            f"  Details: {results / child_run / 'index.json'}\n"
            "\n"
            "[FAIL] Tests failed for datrix-overtaken (exit code: 1)\n"
        )
        relay = ChildOutputRelay(child_stdout, echo=_discard)
        relay.thread.join()
        own_run = attributed_run_dir(results, relay.reported_index_paths)
        assert own_run == child_run, (
            f"the child's own Details line must pin {child_run}, got {own_run!r}"
        )

        no_details = ChildOutputRelay(
            io.StringIO("[1/1] Testing: datrix-overtaken\n"), echo=_discard
        )
        no_details.thread.join()
        assert attributed_run_dir(results, no_details.reported_index_paths) is None, (
            "a child that never named its run must attribute nothing (forced RED), "
            "never fall through to the newest directory"
        )

        foreign = ChildOutputRelay(
            io.StringIO(f"  Details: {workspace / 'datrix-other' / '.test_results' / child_run / 'index.json'}\n"),
            echo=_discard,
        )
        foreign.thread.join()
        assert attributed_run_dir(results, foreign.reported_index_paths) is None, (
            "a Details line naming another package's run directory must not be attributed"
        )


def _check_pinned_run_without_results_is_red_never_a_fallthrough() -> None:
    """A pinned run directory with no index.json and no full.log is RED
    with its own reason -- never a fall-through to the newest run, which
    here is a GREEN one that must not be consulted."""
    with tempfile.TemporaryDirectory(prefix="affected-gate-selftest-") as tmp:
        workspace = Path(tmp)
        results = workspace / "datrix-empty" / ".test_results"
        (results / "test-results-20260101-000100").mkdir(parents=True)
        _write_index(results / "test-results-20260101-000200", status="PASSED", passed=10, failed=0)
        output_path = workspace / ".tmp" / "test" / "affected-gate.json"
        exit_code = _aggregate_verdict(
            workspace,
            ["datrix-empty"],
            {},
            {"datrix-empty": "test-results-20260101-000100"},
            _not_carried(["datrix-empty"]),
            output_path,
            excluded=[],
        )
        assert exit_code == _EXIT_RED, f"an unreadable pinned run must be RED, got {exit_code}"
        row = json.loads(output_path.read_text(encoding="utf-8"))["projects"][0]
        assert row["verdict"] == _VERDICT_RED, row
        assert row["reason"] == "PINNED_RUN_HAS_NO_RESULTS", row


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


def _peak_active_children(events: Sequence[ScheduleEvent]) -> int:
    return max(sum(1 for other in events if other.start <= event.start < other.end) for event in events)


def _check_max_concurrent_one_is_sequential() -> None:
    """-MaxConcurrent is a cap, not a divisor: at 1 no two children overlap,
    at 2 no more than two run at once -- on allotments the core budget alone
    would let overlap (proven first, or the cap checks are vacuous)."""
    allotment = {"pkg-a": 4, "pkg-b": 4, "pkg-c": 2}
    durations = {"pkg-a": 50.0, "pkg-b": 30.0, "pkg-c": 10.0}
    uncapped = simulate_schedule(list(durations), durations, allotment, 12)
    assert _peak_active_children(uncapped) == 3, f"precondition: all three must overlap uncapped; {uncapped}"
    events = simulate_schedule(list(durations), durations, allotment, 12, max_concurrent=1)
    ordered_events = sorted(events, key=lambda e: e.start)
    for earlier, later in zip(ordered_events, ordered_events[1:]):
        assert later.start >= earlier.end, (
            f"-MaxConcurrent 1 must run sequentially; {later.package} started "
            f"at {later.start} before {earlier.package} ended at {earlier.end}"
        )
    capped_at_two = simulate_schedule(list(durations), durations, allotment, 12, max_concurrent=2)
    assert _peak_active_children(capped_at_two) == 2, capped_at_two
    peak_cost_table = _peak_active_children(_simulate_cost_table(_COST_TABLE_LOGICAL_CORES, max_concurrent=3))
    assert peak_cost_table == 3, f"-MaxConcurrent 3 must bound the cost table at 3 children, got {peak_cost_table}"


def _check_cross_ecosystem_consumer_is_in_the_gates_affected_set() -> None:
    """The gate's own closure honours the cross-ecosystem map.

    Plant/observe: the same synthetic tree with the edge declared puts the Node
    consumer in the affected set; with an empty map it does not. Without the
    second half a derivation that swept every discovered package into every
    closure would pass the first.
    """
    with tempfile.TemporaryDirectory(prefix="affected-gate-selftest-") as tmp:
        root = Path(tmp)
        affected_set._make_pkg(root, "datrix-language")
        affected_set._make_node_pkg(root, "datrix-client")
        affected_set._write_cross_ecosystem_config(root, {"datrix-client": ["datrix-language"]})
        assert "datrix-client" in compute_closure(root, ["datrix-language"]), (
            "a consumer declared in the cross-ecosystem map must be in the gate's "
            "closure for its target"
        )
        affected_set._write_cross_ecosystem_config(root, {})
        assert "datrix-client" not in compute_closure(root, ["datrix-language"]), (
            "an undeclared Node package must not be swept into the closure"
        )


def _expect_usage_error(call: Callable[[], object], fragment: str) -> None:
    """Assert *call* raises UsageError whose message contains *fragment*."""
    try:
        call()
    except UsageError as exc:
        assert fragment in str(exc), f"UsageError must mention {fragment!r}; got: {exc}"
    else:
        raise AssertionError(f"expected UsageError mentioning {fragment!r}")


def _check_select_affected_runs_named_consumers_and_records_the_rest_as_excluded() -> None:
    """Plant/observe over one closure: naming a consumer runs exactly the
    changed packages plus that consumer and records every other importer as
    excluded; -NoConsumers runs only the changed packages and excludes every
    importer; a consumer outside the import closure (a pipeline-runner edge
    no import scan sees) is honoured, not rejected."""
    changed = ["datrix-a"]
    closure = ["datrix-a", "datrix-b", "datrix-c", "datrix-d"]
    affected, excluded = select_affected(changed, closure, ["datrix-b"], False)
    assert affected == ["datrix-a", "datrix-b"] and excluded == ["datrix-c", "datrix-d"], (affected, excluded)
    affected, excluded = select_affected(changed, closure, None, True)
    assert affected == ["datrix-a"] and excluded == ["datrix-b", "datrix-c", "datrix-d"], (affected, excluded)
    affected, excluded = select_affected(changed, closure, ["datrix-b", "datrix-z"], False)
    assert affected == ["datrix-a", "datrix-b", "datrix-z"], affected
    assert excluded == ["datrix-c", "datrix-d"], excluded


def _check_select_affected_never_defaults_the_consumer_decision() -> None:
    """Neither flag is a usage error naming the importers -- even when nothing
    imports the changed package, since a pipeline runner can still reach it;
    both flags, or a changed package named as its own consumer, is a usage
    error too."""
    closure = ["datrix-a", "datrix-b"]
    _expect_usage_error(lambda: select_affected(["datrix-a"], closure, None, False), "datrix-b")
    _expect_usage_error(lambda: select_affected(["datrix-a"], ["datrix-a"], None, False), "none")
    _expect_usage_error(lambda: select_affected(["datrix-a"], closure, ["datrix-b"], True), "not both")
    _expect_usage_error(lambda: select_affected(["datrix-a"], closure, ["datrix-a"], False), "already in -Projects")


# ---------------------------------------------------------------------------
# Carry, CARRIED-row and completion-row self-tests. Real run directories and,
# wherever a fingerprint is computed, real git repositories built by
# suite_inputs' own fingerprint fixture -- nothing stubbed.
# ---------------------------------------------------------------------------

#: The package suite_inputs' fingerprint fixture builds.
_STAMPED_PACKAGE = "datrix-solo"
_FRESH_RUN_AGE = timedelta(minutes=5)
_PLACEHOLDER_STAMP: dict[str, object] = {"algorithm": suite_inputs.ALGORITHM, "fingerprint": "0", "components": {}}
_GUARD_HOOK_PARTS = ("claude-config", ".claude", "hooks", "guard-full-suite-runs.py")
_GUARD_ENTRY_POINT = "main"
_GUARD_TS_EXPRESSION = "int(time.time())"
_SHOWCASE_REPO_DEPTH = 3


def _not_carried(names: Iterable[str]) -> dict[str, CarryDecision]:
    return {
        name: CarryDecision(carried=False, run_dir=None, fingerprint=None, reason=_REASON_CARRY_DISABLED)
        for name in names
    }


def _run_dir_name(age: timedelta) -> str:
    return (datetime.now() - age).strftime("test-results-%Y%m%d-%H%M%S")


def _write_run(package_dir: Path, run_name: str, payload: dict[str, object]) -> Path:
    run_dir = package_dir / _TEST_RESULTS_DIRNAME / run_name
    run_dir.mkdir(parents=True, exist_ok=True)
    (run_dir / _INDEX_JSON_NAME).write_text(json.dumps(payload), encoding="utf-8")
    return run_dir


def _run_index(
    *,
    inputs: dict[str, object] | None,
    kind: str = _SELECTION_FULL,
    result: str = _RESULT_PASSED,
    failed: int = 0,
    schema_version: int = _STAMPED_SCHEMA_VERSION,
) -> dict[str, object]:
    """An index.json in the shape the runner writes (schema 2)."""
    payload: dict[str, object] = {
        "schema_version": schema_version,
        "result": result,
        "counts": {"passed": 7, "failed": failed, "error": 0, "skipped": 0},
        "failures": [],
        "errors": [],
        "selection": {"kind": kind},
    }
    if inputs is not None:
        payload["inputs"] = inputs
    return payload


def _decide_one(workspace: Path, package_dir: Path) -> CarryDecision:
    return decide_carry(workspace, {package_dir.name: package_dir}, enabled=True)[package_dir.name]


def _expect_run(decision: CarryDecision, reason: str, diff: tuple[str, ...] = ()) -> None:
    assert not decision.carried, f"expected the package to run ({reason}), but it carried: {decision}"
    assert decision.reason == reason, f"expected reason {reason!r}, got {decision.reason!r}"
    assert decision.diff_components == diff, f"expected diff_components {diff}, got {decision.diff_components}"


@dataclass(frozen=True)
class _StampedFixture:
    """suite_inputs' fingerprint workspace plus one recorded green full run
    of its package, stamped with the inputs computed over it."""

    built: suite_inputs._FingerprintWorkspace
    run_name: str
    observed: suite_inputs.ObservedInputs
    cone: tuple[str, ...]

    @property
    def workspace(self) -> Path:
        return self.built.workspace

    @property
    def package_dir(self) -> Path:
        return self.built.package_dir

    def current_inputs(self) -> dict[str, object]:
        return suite_inputs.compute_inputs(self.workspace, _STAMPED_PACKAGE, self.observed, cone=self.cone)

    def stamp(self, inputs: dict[str, object]) -> None:
        """(Re)write the recorded full run's index.json with *inputs*."""
        _write_run(self.package_dir, self.run_name, _run_index(inputs=inputs))

    def decide(self) -> CarryDecision:
        return _decide_one(self.workspace, self.package_dir)


def _stamped_fixture(root: Path) -> _StampedFixture:
    built = suite_inputs._build_fingerprint_workspace(root)
    cone = suite_inputs.package_cones(built.workspace)[_STAMPED_PACKAGE]
    observed = suite_inputs.classify_observed(built.records, cone, built.workspace)
    fixture = _StampedFixture(built=built, run_name=_run_dir_name(_FRESH_RUN_AGE), observed=observed, cone=cone)
    fixture.stamp(fixture.current_inputs())
    return fixture


def _flip_first_digit(path: Path) -> None:
    """A one-byte, same-size edit that keeps a source file parseable (its first
    ASCII digit's low bit flipped: ``VALUE = 1`` <-> ``VALUE = 0``). The
    workspace scan parses every package's source, so the edit must stay valid
    Python; applying it twice restores the file."""
    data = bytearray(path.read_bytes())
    position = next((i for i, byte in enumerate(data) if chr(byte).isdigit()), None)
    assert position is not None, f"{path} holds no digit to flip"
    data[position] ^= 1
    path.write_bytes(bytes(data))


def _expect_carried(fixture: _StampedFixture, fingerprint: object) -> CarryDecision:
    decision = fixture.decide()
    assert decision.carried, f"identical inputs must carry; refused with: {decision.reason}"
    assert decision.run_dir == fixture.run_name, decision
    assert decision.fingerprint == fingerprint, (decision.fingerprint, fingerprint)
    assert decision.reason is None and decision.diff_components == (), decision
    return decision


def _check_carry_refused_without_any_full_run() -> None:
    """No run at all, and a history holding only a (green) targeted run, are
    both "no full run recorded": a targeted run is never consulted."""
    with tempfile.TemporaryDirectory(prefix="affected-gate-selftest-") as tmp:
        workspace = Path(tmp)
        package_dir = workspace / "datrix-empty"
        package_dir.mkdir()
        _expect_run(_decide_one(workspace, package_dir), _REASON_NO_FULL_RUN)
        _write_run(
            package_dir, _run_dir_name(_FRESH_RUN_AGE), _run_index(inputs=None, kind=_SELECTION_TARGETED)
        )
        _expect_run(_decide_one(workspace, package_dir), _REASON_NO_FULL_RUN)


def _check_carry_refused_for_red_and_incomplete_runs() -> None:
    with tempfile.TemporaryDirectory(prefix="affected-gate-selftest-") as tmp:
        workspace = Path(tmp)
        red = workspace / "datrix-red"
        _write_run(red, _run_dir_name(_FRESH_RUN_AGE), _run_index(inputs=_PLACEHOLDER_STAMP, result="FAILED", failed=1))
        _expect_run(_decide_one(workspace, red), _REASON_RUN_IS_RED)
        failing_but_passed = workspace / "datrix-contradictory"
        _write_run(failing_but_passed, _run_dir_name(_FRESH_RUN_AGE), _run_index(inputs=_PLACEHOLDER_STAMP, failed=1))
        _expect_run(_decide_one(workspace, failing_but_passed), _REASON_RUN_IS_RED)
        incomplete = workspace / "datrix-incomplete"
        _write_run(
            incomplete,
            _run_dir_name(_FRESH_RUN_AGE),
            {"schema_version": _STAMPED_SCHEMA_VERSION, "result": _INCOMPLETE_MARKER, "counts": None,
             "selection": {"kind": _SELECTION_FULL}},
        )
        _expect_run(_decide_one(workspace, incomplete), _REASON_RUN_IS_INCOMPLETE)


def _check_carry_refused_outside_the_carry_window() -> None:
    with tempfile.TemporaryDirectory(prefix="affected-gate-selftest-") as tmp:
        workspace = Path(tmp)
        stale = workspace / "datrix-stale"
        over_age = timedelta(seconds=suite_inputs.CARRY_WINDOW_SECONDS + 60)
        _write_run(stale, _run_dir_name(over_age), _run_index(inputs=_PLACEHOLDER_STAMP))
        _expect_run(_decide_one(workspace, stale), _REASON_STAMP_TOO_OLD)
        future = workspace / "datrix-future"
        future_name = _run_dir_name(-timedelta(hours=1))
        _write_run(future, future_name, _run_index(inputs=_PLACEHOLDER_STAMP))
        _expect_run(_decide_one(workspace, future), f"run {future_name} is timestamped in the future")


def _check_carry_refused_for_unstamped_runs() -> None:
    """A schema-1 run, a legacy run with no selection field, and a schema-2
    full run with no inputs stamp all predate stamps: never carried."""
    with tempfile.TemporaryDirectory(prefix="affected-gate-selftest-") as tmp:
        workspace = Path(tmp)
        schema_one = workspace / "datrix-schema-one"
        _write_run(schema_one, _run_dir_name(_FRESH_RUN_AGE), _run_index(inputs=_PLACEHOLDER_STAMP, schema_version=1))
        _expect_run(_decide_one(workspace, schema_one), _REASON_PREDATES_STAMPS)
        legacy = workspace / "datrix-legacy"
        legacy_index = _run_index(inputs=None)
        del legacy_index["selection"]
        _write_run(legacy, _run_dir_name(_FRESH_RUN_AGE), legacy_index)
        _expect_run(_decide_one(workspace, legacy), _REASON_PREDATES_STAMPS)
        no_inputs = workspace / "datrix-no-inputs"
        _write_run(no_inputs, _run_dir_name(_FRESH_RUN_AGE), _run_index(inputs=None))
        _expect_run(_decide_one(workspace, no_inputs), _REASON_PREDATES_STAMPS)


def _check_carry_refused_for_foreign_algorithm_and_malformed_stamps() -> None:
    """Refused before any digest is computed, in diff_components' vocabulary."""
    with tempfile.TemporaryDirectory(prefix="affected-gate-selftest-") as tmp:
        workspace = Path(tmp)
        old_algorithm = workspace / "datrix-old-algorithm"
        stale_stamp = {**_PLACEHOLDER_STAMP, "algorithm": "suite-inputs/1"}
        _write_run(old_algorithm, _run_dir_name(_FRESH_RUN_AGE), _run_index(inputs=stale_stamp))
        expected = tuple(suite_inputs.incomparable_stamp_reasons(stale_stamp))
        assert expected == ("algorithm version differs",), expected
        _expect_run(_decide_one(workspace, old_algorithm), expected[0], expected)
        malformed = workspace / "datrix-malformed"
        _write_run(malformed, _run_dir_name(_FRESH_RUN_AGE), _run_index(inputs=_PLACEHOLDER_STAMP))
        decision = _decide_one(workspace, malformed)
        assert not decision.carried and len(decision.diff_components) == 1, decision
        assert decision.diff_components[0].startswith("recorded inputs are malformed"), decision
        assert decision.reason == decision.diff_components[0], decision


def _check_identical_inputs_carry_and_launch_no_child() -> None:
    with tempfile.TemporaryDirectory(prefix="affected-gate-selftest-") as tmp:
        fixture = _stamped_fixture(Path(tmp).resolve())
        recorded = fixture.current_inputs()
        decisions = decide_carry(fixture.workspace, {_STAMPED_PACKAGE: fixture.package_dir}, enabled=True)
        assert decisions[_STAMPED_PACKAGE].carried, decisions
        _expect_carried(fixture, recorded[_FINGERPRINT_KEY])
        to_run, carried = split_by_carry([_STAMPED_PACKAGE], decisions)
        assert to_run == [] and carried == [_STAMPED_PACKAGE], (to_run, carried)
        assert run_scheduled(fixture.workspace, to_run, {}, 1, 1, False) == (set(), {}, {}), (
            "a fully carried set must launch no child"
        )


def _check_no_carry_runs_a_carriable_package() -> None:
    with tempfile.TemporaryDirectory(prefix="affected-gate-selftest-") as tmp:
        fixture = _stamped_fixture(Path(tmp).resolve())
        package_dirs = {_STAMPED_PACKAGE: fixture.package_dir}
        assert decide_carry(fixture.workspace, package_dirs, enabled=True)[_STAMPED_PACKAGE].carried, (
            "precondition: the package must be carriable, or the -NoCarry check is vacuous"
        )
        disabled = decide_carry(fixture.workspace, package_dirs, enabled=False)
        _expect_run(disabled[_STAMPED_PACKAGE], _REASON_CARRY_DISABLED)
        assert split_by_carry([_STAMPED_PACKAGE], disabled) == ([_STAMPED_PACKAGE], [])


def _check_newer_targeted_runs_never_hide_a_carriable_full_run() -> None:
    """Newer targeted runs -- one RED, one GREEN -- are skipped over: the
    older full run still carries. A newer run whose index cannot be read
    refuses carry, since it might itself be a newer (RED) full run."""
    with tempfile.TemporaryDirectory(prefix="affected-gate-selftest-") as tmp:
        fixture = _stamped_fixture(Path(tmp).resolve())
        fingerprint = fixture.current_inputs()[_FINGERPRINT_KEY]
        _write_run(
            fixture.package_dir,
            _run_dir_name(timedelta(minutes=2)),
            _run_index(inputs=None, kind=_SELECTION_TARGETED, result="FAILED", failed=3),
        )
        _write_run(fixture.package_dir, _run_dir_name(timedelta(minutes=1)), _run_index(inputs=None, kind=_SELECTION_TARGETED))
        _expect_carried(fixture, fingerprint)
        unreadable = fixture.package_dir / _TEST_RESULTS_DIRNAME / _run_dir_name(timedelta(seconds=30))
        unreadable.mkdir(parents=True)
        (unreadable / _INDEX_JSON_NAME).write_text("{ not json", encoding="utf-8")
        decision = fixture.decide()
        assert not decision.carried and decision.reason is not None, decision
        assert decision.reason.startswith(f"run {unreadable.name} has no readable {_INDEX_JSON_NAME}"), decision


def _check_every_component_change_forces_a_run_naming_it() -> None:
    """A one-byte change in each of the seven fingerprint components -- a
    cone tree file, an in-cone ignored file, a foreign tree, an observed
    executable, the installed set, the interpreter string, the algorithm --
    runs the package, and diff_components names exactly that component."""
    suite_inputs._SELF_TEST_OUTSIDE_TEMP_ROOT.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(
        prefix="affected-gate-selftest-", dir=str(suite_inputs._SELF_TEST_OUTSIDE_TEMP_ROOT)
    ) as tmp:
        # Rooted outside every transient location (the OS temp directory
        # included), like suite_inputs' own transient-executable fixtures:
        # built.executable must be a real, kept fingerprint input here, since
        # this check asserts a one-byte change to it forces a run. Every
        # other self-test fixture in this module stays under the OS temp
        # directory (an isolation convenience with no bearing on its checks).
        root = Path(tmp).resolve()
        fixture = _stamped_fixture(root)
        recorded = fixture.current_inputs()
        _expect_carried(fixture, recorded[_FINGERPRINT_KEY])
        built = fixture.built
        filesystem_changes: tuple[tuple[Path, Callable[[Path], None], str], ...] = (
            (built.package_dir / "src" / "datrix_solo" / "__init__.py", _flip_first_digit, f"{_STAMPED_PACKAGE} tree changed"),
            (built.ignored_input, suite_inputs._flip_last_byte, f"ignored input {built.ignored_input} changed"),
            (built.foreign_file, suite_inputs._flip_last_byte, "foreign tree datrix/examples changed"),
            (built.executable, suite_inputs._flip_last_byte, f"executable {built.executable} changed"),
        )
        for path, flip, reason in filesystem_changes:
            flip(path)
            _expect_run(fixture.decide(), reason, (reason,))
            flip(path)
        _expect_carried(fixture, recorded[_FINGERPRINT_KEY])

        components = copy.deepcopy(recorded["components"])
        assert isinstance(components, dict)
        interpreter = components["interpreter"]
        assert isinstance(interpreter, dict)
        interpreter["version"] = suite_inputs._one_byte_changed(str(interpreter["version"]))
        fixture.stamp(
            {**recorded, "fingerprint": suite_inputs.fingerprint_of(suite_inputs.ALGORITHM, components),
             "components": components}
        )
        _expect_run(fixture.decide(), suite_inputs._REASON_INTERPRETER, (suite_inputs._REASON_INTERPRETER,))

        other_algorithm = suite_inputs._one_byte_changed(suite_inputs.ALGORITHM)
        original_components = recorded["components"]
        assert isinstance(original_components, dict)
        fixture.stamp(
            {**recorded, "algorithm": other_algorithm,
             "fingerprint": suite_inputs.fingerprint_of(other_algorithm, original_components)}
        )
        _expect_run(fixture.decide(), suite_inputs._REASON_ALGORITHM, (suite_inputs._REASON_ALGORITHM,))

        site = root / "site"
        suite_inputs._write_selftest_distribution(site, "1.0")
        sys.path.insert(0, str(site))
        try:
            with_distribution = fixture.current_inputs()
            fixture.stamp(with_distribution)
            _expect_carried(fixture, with_distribution[_FINGERPRINT_KEY])
            suite_inputs._write_selftest_distribution(site, "1.1")
            _expect_run(fixture.decide(), suite_inputs._REASON_INSTALLED, (suite_inputs._REASON_INSTALLED,))
        finally:
            sys.path.remove(str(site))


def _check_affected_gate_json_names_the_carried_run_and_the_changed_component() -> None:
    """A carried row names its run, age and fingerprint and counts as green;
    after a one-byte cone change the same package runs, and its row carries
    the component diff that forced the run."""
    with tempfile.TemporaryDirectory(prefix="affected-gate-selftest-") as tmp:
        fixture = _stamped_fixture(Path(tmp).resolve())
        output_path = Path(tmp) / "out" / "affected-gate.json"
        decisions = decide_carry(fixture.workspace, {_STAMPED_PACKAGE: fixture.package_dir}, enabled=True)
        exit_code = _aggregate_verdict(
            fixture.workspace, [_STAMPED_PACKAGE], {}, {}, decisions, output_path, excluded=["datrix-unreached"]
        )
        payload = json.loads(output_path.read_text(encoding="utf-8"))
        row = payload["projects"][0]
        assert exit_code == _EXIT_GREEN and payload["overall_verdict"] == _VERDICT_GREEN, payload
        assert payload["excluded"] == ["datrix-unreached"], payload
        assert row["verdict"] == _VERDICT_CARRIED and row["carried"] is True, row
        assert Path(row["run_dir"]).name == fixture.run_name, row
        assert isinstance(row["age_minutes"], float) and row["age_minutes"] >= 0, row
        assert row["fingerprint"] == decisions[_STAMPED_PACKAGE].fingerprint, row
        assert row["counts"]["passed"] == 7 and row["carry_reason"] is None and row["diff_components"] == [], row

        _flip_first_digit(fixture.package_dir / "src" / "datrix_solo" / "__init__.py")
        decisions = decide_carry(fixture.workspace, {_STAMPED_PACKAGE: fixture.package_dir}, enabled=True)
        produced = _run_dir_name(timedelta(minutes=1))
        _write_run(fixture.package_dir, produced, _run_index(inputs=None))
        exit_code = _aggregate_verdict(
            fixture.workspace, [_STAMPED_PACKAGE], {}, {_STAMPED_PACKAGE: produced}, decisions, output_path,
            excluded=[],
        )
        row = json.loads(output_path.read_text(encoding="utf-8"))["projects"][0]
        expected_diff = [f"{_STAMPED_PACKAGE} tree changed"]
        assert exit_code == _EXIT_GREEN and row["verdict"] == _VERDICT_GREEN and row["carried"] is False, row
        assert Path(row["run_dir"]).name == produced and row["fingerprint"] is None, row
        assert row["diff_components"] == expected_diff and row["carry_reason"] == expected_diff[0], row


def _check_gate_verdict_checks_every_carry_claim_against_the_run() -> None:
    """gate_verdict renders CARRIED only when the pinned run's own index.json
    is a green FULL run stamped with the claimed fingerprint; any other claim
    is RED, and a carried package with no pinned run is a usage error."""
    with tempfile.TemporaryDirectory(prefix="affected-gate-selftest-") as tmp:
        workspace = Path(tmp)
        stamp = {**_PLACEHOLDER_STAMP, "fingerprint": "f" * 8}
        full_run = _run_dir_name(_FRESH_RUN_AGE)
        _write_run(workspace / "datrix-full", full_run, _run_index(inputs=stamp))
        targeted_run = _run_dir_name(_FRESH_RUN_AGE)
        _write_run(workspace / "datrix-targeted", targeted_run, _run_index(inputs=stamp, kind=_SELECTION_TARGETED))

        def carry(project: str, run_name: str, fingerprint: str) -> gate_verdict.GateVerdictResult:
            return gate_verdict.evaluate_projects(
                workspace, [project], pinned_runs={project: run_name}, carried={project: fingerprint}
            )

        accepted = carry("datrix-full", full_run, "f" * 8)
        assert accepted.overall == _VERDICT_GREEN and accepted.rows[0].verdict == _VERDICT_CARRIED, accepted.rows
        assert accepted.rows[0].carried and accepted.rows[0].fingerprint == "f" * 8, accepted.rows
        assert accepted.report_lines[0].startswith(f"datrix-full: {_VERDICT_CARRIED} 7 passed"), accepted.report_lines
        for project, run_name, fingerprint in (
            ("datrix-full", full_run, "0" * 8),
            ("datrix-targeted", targeted_run, "f" * 8),
        ):
            rejected = carry(project, run_name, fingerprint)
            row = rejected.rows[0]
            assert rejected.overall == _VERDICT_RED and row.verdict == _VERDICT_RED and not row.carried, row
            assert row.reason is not None and row.reason.startswith("CARRY_REJECTED"), row
        try:
            gate_verdict.evaluate_projects(workspace, ["datrix-full"], carried={"datrix-full": "f" * 8})
        except gate_verdict.UsageError:
            pass
        else:
            raise AssertionError("a carried package with no pinned run must be a usage error")


def _guard_row_keys_and_ts_expressions() -> tuple[set[str], list[str]]:
    """Every string key the full-suite guard's ``main`` puts in an audit row,
    and the source text of each value it assigns to ``ts`` -- read from the
    guard's own source, so the seam is checked against the real writer."""
    guard_path = Path(__file__).resolve().parents[_SHOWCASE_REPO_DEPTH].joinpath(*_GUARD_HOOK_PARTS)
    assert guard_path.is_file(), f"the full-suite guard must exist at {guard_path}"
    tree = ast.parse(guard_path.read_text(encoding="utf-8"))
    entry_points = [
        node for node in ast.walk(tree) if isinstance(node, ast.FunctionDef) and node.name == _GUARD_ENTRY_POINT
    ]
    assert len(entry_points) == 1, f"expected one {_GUARD_ENTRY_POINT}() in {guard_path}"
    keys: set[str] = set()
    ts_expressions: list[str] = []
    for node in ast.walk(entry_points[0]):
        if not isinstance(node, ast.Dict):
            continue
        for key, value in zip(node.keys, node.values):
            if isinstance(key, ast.Constant) and isinstance(key.value, str):
                keys.add(key.value)
                if key.value == "ts":
                    ts_expressions.append(ast.unparse(value))
    return keys, ts_expressions


def _check_completion_row_shares_the_guards_ts_type_and_is_distinguishable() -> None:
    """Both writers of the audit log agree on ``ts`` (integer epoch seconds),
    the completion row is told apart by ``source``, and one call appends
    exactly one row naming what ran and what carried."""
    guard_keys, ts_expressions = _guard_row_keys_and_ts_expressions()
    assert ts_expressions == [_GUARD_TS_EXPRESSION], (
        f"the guard's audit rows must stamp ts as {_GUARD_TS_EXPRESSION}; found {ts_expressions}"
    )
    with tempfile.TemporaryDirectory(prefix="affected-gate-selftest-") as tmp:
        audit_path = audit_log_path(Path(tmp))
        audit_path.parent.mkdir(parents=True)
        guard_row: dict[str, object] = {key: "" for key in sorted(guard_keys)}
        guard_row["ts"] = int(time.time())
        audit_path.write_text(json.dumps(guard_row) + "\n", encoding="utf-8")
        record = CompletionRecord(
            changed=["datrix-common"],
            consumers=["datrix-cli"],
            excluded=["datrix-codegen-sql"],
            ran=["datrix-common"],
            carried=[_STAMPED_PACKAGE],
            wall_seconds={"datrix-common": 12.345},
            overall=_VERDICT_GREEN,
        )
        written = append_completion_row(audit_path, record)
        lines = audit_path.read_text(encoding="utf-8").splitlines()
        assert len(lines) == 2, f"one call must append exactly one row; the log holds {len(lines)} lines"
        guard_read, completion = (json.loads(line) for line in lines)
        assert completion == written, (completion, written)
        shared = set(guard_read) & set(completion)
        assert shared == {"ts"}, f"the only key both writers share must be ts; shared {sorted(shared)}"
        for key in shared:
            assert type(guard_read[key]) is type(completion[key]) is int, (key, guard_read[key], completion[key])
        assert "source" not in guard_read and completion["source"] == _AUDIT_SOURCE, completion
        assert completion["changed"] == ["datrix-common"] and completion["ran"] == ["datrix-common"], completion
        assert completion["carried"] == [_STAMPED_PACKAGE] and completion["overall"] == _VERDICT_GREEN, completion
        assert completion["consumers"] == ["datrix-cli"], completion
        assert completion["excluded"] == ["datrix-codegen-sql"], completion
        assert completion["wall_seconds"] == {"datrix-common": 12.3}, completion
        assert CompletionRecord().overall == _OVERALL_ABORTED, "an unfinished invocation must never record a verdict"


# ---------------------------------------------------------------------------
# Install-once self-tests: the flag every child carries, the one upstream
# check, and the reader that honours the flag -- checked against the real
# test.ps1 / test_project.py / venv.ps1 sources, and the check's exit-code
# wiring against real PowerShell processes over planted venv modules.
# ---------------------------------------------------------------------------

_SELF_TEST_CHECK_PREFIX = "_check_"
_TEST_PS1_PARTS = ("scripts", "test", "test.ps1")
_TEST_PROJECT_NAME = "test_project.py"
_INSTALL_CALL = "Ensure-DatrixPackagesInstalled -SkipIfInstalled"
_INSTALL_GUARD = f'$env:{PACKAGES_ENSURED_ENV} -ne "{_PACKAGES_ENSURED_VALUE}"'
_SIGNAL_TO_TEST_PROJECT = f'$env:{PACKAGES_ENSURED_ENV} = "{_PACKAGES_ENSURED_VALUE}"'
_CALLER_VALUE_RESTORE = f"$env:{PACKAGES_ENSURED_ENV} = $script:CallerPackagesEnsured"
_ENSURED_MARKER = "packages-ensured.marker"
_PLANTED_VENV_OK = """
function Ensure-DatrixVenv { return $true }
function Ensure-DatrixPackagesInstalled {
    param([switch]$SkipIfInstalled)
    if (-not $SkipIfInstalled) { return $false }
    Set-Content -LiteralPath (Join-Path $PSScriptRoot 'packages-ensured.marker') -Value 'ensured'
    return $true
}
"""
_PLANTED_VENV_PACKAGES_FAIL = """
function Ensure-DatrixVenv { return $true }
function Ensure-DatrixPackagesInstalled { param([switch]$SkipIfInstalled) return $false }
"""
_PLANTED_VENV_THROWS = """
function Ensure-DatrixVenv { throw 'self-test fixture: planted venv activation failure (expected)' }
function Ensure-DatrixPackagesInstalled { param([switch]$SkipIfInstalled) return $true }
"""


def _showcase_repo() -> Path:
    return Path(__file__).resolve().parents[_SHOWCASE_REPO_DEPTH]


def _call_is_guarded_by(text: str, call: str, guard: str) -> bool:
    """True when the one line invoking *call* sits directly inside an ``if``
    block whose condition contains *guard*. Walks back from the call,
    balancing braces, to the line that opened the enclosing block."""
    lines = text.splitlines()
    call_lines = [index for index, line in enumerate(lines) if call in line]
    assert len(call_lines) == 1, f"expected exactly one line invoking {call!r}, found {len(call_lines)}"
    depth = 0
    for line in reversed(lines[: call_lines[0]]):
        depth += line.count("}") - line.count("{")
        if depth < 0:
            return line.strip().startswith("if") and guard in line
    return False


def _check_children_carry_the_install_flag_and_test_ps1_honours_it() -> None:
    """The seam between the gate that ran the check and the child that skips
    it: every child's environment carries the flag, test.ps1's one install
    call sits inside the guard reading that same flag, test.ps1 still hands
    the flag to test_project.py and restores its caller's value on exit, and
    test_project.py reads the same name. The guard finder is proven
    non-vacuous on an unguarded call and on a call guarded by another flag."""
    env = _child_environment(3)
    assert env[PACKAGES_ENSURED_ENV] == _PACKAGES_ENSURED_VALUE, env.get(PACKAGES_ENSURED_ENV)
    assert env[_XDIST_WORKERS_ENV] == "3", env.get(_XDIST_WORKERS_ENV)

    unguarded = f"try {{\n    $ok = {_INSTALL_CALL}\n}}\n"
    other_flag = f'if ($env:SOME_OTHER_FLAG -ne "1") {{\n    $ok = {_INSTALL_CALL}\n}}\n'
    closed_before = f'if ({_INSTALL_GUARD}) {{\n    $x = 1\n}}\n$ok = {_INSTALL_CALL}\n'
    for planted in (unguarded, other_flag, closed_before):
        assert not _call_is_guarded_by(planted, _INSTALL_CALL, _INSTALL_GUARD), (
            f"the guard finder accepted an install call the flag does not guard:\n{planted}"
        )
    guarded = f'if ({_INSTALL_GUARD}) {{\n    # comment\n    $ok = {_INSTALL_CALL}\n}}\n'
    assert _call_is_guarded_by(guarded, _INSTALL_CALL, _INSTALL_GUARD), "the guard finder missed a guarded call"

    test_ps1 = _showcase_repo().joinpath(*_TEST_PS1_PARTS).read_text(encoding="utf-8-sig")
    assert _call_is_guarded_by(test_ps1, _INSTALL_CALL, _INSTALL_GUARD), (
        f"test.ps1's {_INSTALL_CALL} call is not inside `if ({_INSTALL_GUARD}) {{ ... }}`: every gate "
        f"child would repeat the install check the gate already ran"
    )
    assert _SIGNAL_TO_TEST_PROJECT in test_ps1, f"test.ps1 no longer sets {_SIGNAL_TO_TEST_PROJECT} for test_project.py"
    assert _CALLER_VALUE_RESTORE in test_ps1, (
        f"test.ps1 no longer restores its caller's {PACKAGES_ENSURED_ENV} on exit; run in-process it "
        f"would leave the flag set and make later direct runs skip their install check"
    )
    test_project = (Path(__file__).resolve().parent / _TEST_PROJECT_NAME).read_text(encoding="utf-8")
    assert f'"{PACKAGES_ENSURED_ENV}"' in test_project, f"test_project.py no longer reads {PACKAGES_ENSURED_ENV}"


def _function_calls_by_line(function: ast.FunctionDef) -> list[tuple[int, str]]:
    calls = [
        (node.lineno, node.func.id)
        for node in ast.walk(function)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
    ]
    return sorted(calls)


def _check_install_check_runs_once_before_carry_and_any_child() -> None:
    """Read from this module's own source: the install check is called
    exactly once in the whole module, from ``_run``, after its usage checks
    and before the carry decision and the scheduler; ``main`` returns for
    ``--self-test`` before ``_run_recorded`` can reach it. The command
    dot-sources the real workspace's venv.ps1 through the environment and
    calls the two functions that module defines."""
    tree = ast.parse(Path(__file__).read_text(encoding="utf-8"))
    functions = {node.name: node for node in ast.walk(tree) if isinstance(node, ast.FunctionDef)}
    install_name = ensure_packages_installed_once.__name__
    gate_install_callers = [
        name for name, function in functions.items() if not name.startswith(_SELF_TEST_CHECK_PREFIX)
        for _, callee in _function_calls_by_line(function) if callee == install_name
    ]
    assert gate_install_callers == ["_run"], (
        f"the install check must be called once per gate, from _run only; callers: {gate_install_callers}"
    )
    order = [callee for _, callee in _function_calls_by_line(functions["_run"])]
    sequence = (
        "_reject_in_progress_unless_forced",
        _require_scheduling_options.__name__,
        install_name,
        "decide_carry",
        "split_by_carry",
        worker_allotment.__name__,
        "run_scheduled",
    )
    absent = [name for name in sequence if name not in order]
    assert not absent, f"_run no longer calls {absent}; call order: {order}"
    positions = [order.index(name) for name in sequence]
    assert positions == sorted(positions), (
        f"_run must refuse an in-progress conflict and bad scheduling options, then run the install check, "
        f"then decide carry, then allot workers to the packages that did not carry, then schedule children; "
        f"call order: {order}"
    )

    main = functions["main"]
    run_recorded_lines = [line for line, callee in _function_calls_by_line(main) if callee == _run_recorded.__name__]
    assert len(run_recorded_lines) == 1, f"main() must call _run_recorded exactly once; found {run_recorded_lines}"
    run_recorded_line = run_recorded_lines[0]
    self_test_returns = [
        node.lineno for node in ast.walk(main)
        if isinstance(node, ast.If) and "self_test" in ast.unparse(node.test)
        and any(isinstance(statement, ast.Return) for statement in node.body)
    ]
    assert self_test_returns and min(self_test_returns) < run_recorded_line, (
        "main() must return for --self-test before _run_recorded, so a self-test runs no install check"
    )

    venv_script = venv_script_path(get_datrix_root())
    assert venv_script == _showcase_repo() / "scripts" / "common" / "venv.ps1", venv_script
    venv_source = venv_script.read_text(encoding="utf-8-sig")
    for function_name in ("Ensure-DatrixVenv", "Ensure-DatrixPackagesInstalled"):
        assert f"function {function_name}" in venv_source, f"{venv_script} no longer defines {function_name}"
        assert function_name in _ENSURE_PACKAGES_COMMAND, f"the install check no longer calls {function_name}"
    assert _INSTALL_CALL in _ENSURE_PACKAGES_COMMAND, "the gate's install check must match test.ps1's -SkipIfInstalled call"
    assert f"$env:{_VENV_SCRIPT_ENV}" in _ENSURE_PACKAGES_COMMAND, "the command must dot-source the path the gate passes"


def _check_install_check_passes_through_and_fails_loud() -> None:
    """Real PowerShell processes over planted venv modules: a module whose
    two functions succeed passes, and its install function was called with
    -SkipIfInstalled; a module whose install function returns false, one
    whose venv function throws, and a missing module each raise
    InstallCheckError -- never a silent pass."""
    with tempfile.TemporaryDirectory(prefix="affected-gate-selftest-") as tmp:
        root = Path(tmp)
        passing = root / "ok" / "venv.ps1"
        passing.parent.mkdir()
        passing.write_text(_PLANTED_VENV_OK, encoding="utf-8")
        ensure_packages_installed_once(passing)
        assert (passing.parent / _ENSURED_MARKER).is_file(), (
            "the install check passed without calling Ensure-DatrixPackagesInstalled -SkipIfInstalled"
        )
        failing = (
            ("packages-fail", _PLANTED_VENV_PACKAGES_FAIL),
            ("venv-throws", _PLANTED_VENV_THROWS),
        )
        for name, source in failing:
            script = root / name / "venv.ps1"
            script.parent.mkdir()
            script.write_text(source, encoding="utf-8")
            try:
                ensure_packages_installed_once(script)
            except InstallCheckError as exc:
                assert str(script) in str(exc), f"the failure does not name the module it ran: {exc}"
            else:
                raise AssertionError(f"a failing install check ({name}) did not raise InstallCheckError")
        try:
            ensure_packages_installed_once(root / "absent" / "venv.ps1")
        except InstallCheckError as exc:
            assert "does not exist" in str(exc), exc
        else:
            raise AssertionError("a missing venv module did not raise InstallCheckError")


_SELF_TEST_CHECKS: list[tuple[str, Callable[[], None]]] = [
    (
        "cross_ecosystem_consumer_is_in_the_gates_affected_set",
        _check_cross_ecosystem_consumer_is_in_the_gates_affected_set,
    ),
    (
        "budget_never_exceeds_cores_across_simulated_schedule",
        _check_budget_never_exceeds_cores_across_simulated_schedule,
    ),
    (
        "proportional_allotment_follows_the_cpu_share_rule",
        _check_proportional_allotment_follows_the_cpu_share_rule,
    ),
    (
        "proportional_makespan_within_bound_of_the_cpu_lower_bound",
        _check_proportional_makespan_within_bound_of_the_cpu_lower_bound,
    ),
    (
        "proportional_makespan_no_worse_than_retired_fixed_slot_policy",
        _check_proportional_makespan_no_worse_than_retired_fixed_slot_policy,
    ),
    (
        "worker_allotment_override_is_uniform_and_bounded",
        _check_worker_allotment_override_is_uniform_and_bounded,
    ),
    ("longest_first_ordering", _check_longest_first_ordering),
    (
        "predicted_cpu_seconds_reads_test_time_of_the_newest_full_run",
        _check_predicted_cpu_seconds_reads_test_time_of_the_newest_full_run,
    ),
    ("missing_index_falls_back_to_loc", _check_missing_index_falls_back_to_loc),
    (
        "resolve_requested_packages_distinct_ok_and_duplicate_rejected",
        _check_resolve_requested_packages_distinct_ok_and_duplicate_rejected,
    ),
    (
        "select_affected_runs_named_consumers_and_records_the_rest_as_excluded",
        _check_select_affected_runs_named_consumers_and_records_the_rest_as_excluded,
    ),
    (
        "select_affected_never_defaults_the_consumer_decision",
        _check_select_affected_never_defaults_the_consumer_decision,
    ),
    (
        "child_with_no_new_run_forces_red_never_stale_green",
        _check_child_with_no_new_run_forces_red_never_stale_green,
    ),
    (
        "verdict_is_pinned_to_the_childs_run_never_a_newer_one",
        _check_verdict_is_pinned_to_the_childs_run_never_a_newer_one,
    ),
    (
        "child_run_is_attributed_from_its_own_details_line_never_the_newest_dir",
        _check_child_run_is_attributed_from_its_own_details_line_never_the_newest_dir,
    ),
    (
        "pinned_run_without_results_is_red_never_a_fallthrough",
        _check_pinned_run_without_results_is_red_never_a_fallthrough,
    ),
    ("is_run_in_progress_missing_index_json", _check_is_run_in_progress_missing_index_json),
    ("is_run_in_progress_incomplete_status", _check_is_run_in_progress_incomplete_status),
    (
        "is_run_in_progress_completed_index_is_not_in_progress",
        _check_is_run_in_progress_completed_index_is_not_in_progress,
    ),
    ("max_concurrent_one_is_sequential", _check_max_concurrent_one_is_sequential),
    ("carry_refused_without_any_full_run", _check_carry_refused_without_any_full_run),
    ("carry_refused_for_red_and_incomplete_runs", _check_carry_refused_for_red_and_incomplete_runs),
    ("carry_refused_outside_the_carry_window", _check_carry_refused_outside_the_carry_window),
    ("carry_refused_for_unstamped_runs", _check_carry_refused_for_unstamped_runs),
    (
        "carry_refused_for_foreign_algorithm_and_malformed_stamps",
        _check_carry_refused_for_foreign_algorithm_and_malformed_stamps,
    ),
    ("identical_inputs_carry_and_launch_no_child", _check_identical_inputs_carry_and_launch_no_child),
    ("no_carry_runs_a_carriable_package", _check_no_carry_runs_a_carriable_package),
    (
        "newer_targeted_runs_never_hide_a_carriable_full_run",
        _check_newer_targeted_runs_never_hide_a_carriable_full_run,
    ),
    ("every_component_change_forces_a_run_naming_it", _check_every_component_change_forces_a_run_naming_it),
    (
        "affected_gate_json_names_the_carried_run_and_the_changed_component",
        _check_affected_gate_json_names_the_carried_run_and_the_changed_component,
    ),
    (
        "gate_verdict_checks_every_carry_claim_against_the_run",
        _check_gate_verdict_checks_every_carry_claim_against_the_run,
    ),
    (
        "completion_row_shares_the_guards_ts_type_and_is_distinguishable",
        _check_completion_row_shares_the_guards_ts_type_and_is_distinguishable,
    ),
    (
        "children_carry_the_install_flag_and_test_ps1_honours_it",
        _check_children_carry_the_install_flag_and_test_ps1_honours_it,
    ),
    (
        "install_check_runs_once_before_carry_and_any_child",
        _check_install_check_runs_once_before_carry_and_any_child,
    ),
    ("install_check_passes_through_and_fails_loud", _check_install_check_passes_through_and_fails_loud),
]


def main() -> int:
    """Entry point."""
    args = _parse_args()
    _configure_logging(args.debug)

    _step("Self-test: affected-gate scheduling, carry and completion-row edge cases")
    self_test_passed = run_self_test_checks(_SELF_TEST_CHECKS)
    if args.self_test:
        return _EXIT_GREEN if self_test_passed else _EXIT_RED

    workspace = get_datrix_root()
    record = CompletionRecord()
    try:
        return _run_recorded(args, workspace, self_test_passed, record)
    finally:
        row = append_completion_row(audit_log_path(workspace), record)
        print(
            f"Completion row: overall={row['overall']} ran={row['ran']} carried={row['carried']} "
            f"excluded={row['excluded']} -> {audit_log_path(workspace)}"
        )


if __name__ == "__main__":
    sys.exit(main())
