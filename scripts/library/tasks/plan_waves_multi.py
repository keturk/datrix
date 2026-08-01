#!/usr/bin/env python3
"""Plan execution waves for SEVERAL phases run as one batch.

``plan_waves.py`` plans one phase. Running phases back to back therefore restarts
the topological sort at every phase boundary and reports each cross-phase edge as
an ``UNMET_CROSS_PHASE_DEP`` blocker until the earlier phase is fully COMPLETED.
Batching the phases removes both costs: a dependency into another batched phase
becomes an ordinary graph edge, so the program collapses to its real dependency
depth instead of the sum of several independent plans.

Batching also removes a guard, and this module's job is to put it back.
``plan_waves.py`` splits a wave whose tasks write the same file, but it only ever
sees ONE phase, so two tasks in different phases that write the same file are
invisible to it: nothing keeps them out of the same wave, and nothing keeps the
later phase's task from being scheduled FIRST. Closed in two steps:

1. **Phase-order repair** (``implicit_order_edges``). When two tasks write the
   same file, sit in different phases, and have no dependency path between them,
   the later phase's task must not be scheduled at or before the earlier phase's
   task. Each such inversion gets a real edge (later-phase task depends on
   earlier-phase task) and the plan is recomputed, to a fixpoint. Edges are added
   only where an inversion actually occurs, so a conflict the wave order already
   resolves costs nothing and a file with many writers does not become a chain.
   Every edge added this way is reported -- an implicit ordering nobody can see
   is worse than no ordering at all.
2. **Residual-conflict assertion.** After planning, no wave may contain two tasks
   claiming the same file. ``residual_file_conflicts`` must be empty; a non-empty
   list fails the run rather than being reported as advice.

Everything else -- Kahn waves, quality-gate-last ordering, same-file wave
splitting, cycle detection, MISSING_DEP_FILE / MIXED_LANGUAGE_TASK / DEP_MISMATCH
detection -- is ``plan_waves.py``'s implementation, imported rather than
re-derived, so the two planners can never drift on shared semantics.

Usage:
  python scripts/library/tasks/plan_waves_multi.py 5-8
  python scripts/library/tasks/plan_waves_multi.py 5,6,7,8 --include-completed
  .\\scripts\\tasks\\plan-waves-multi.ps1 5-8
"""

from __future__ import annotations

import argparse
import io
import logging
import sys
from collections import defaultdict
from datetime import datetime
from pathlib import Path

# Configure UTF-8 encoding for stdout/stderr on Windows
if sys.platform == "win32" and __name__ == "__main__":
    if hasattr(sys.stdout, "buffer"):
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    if hasattr(sys.stderr, "buffer"):
        sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

from plan_waves import (
    BLOCKER_DEP_MISMATCH,
    BLOCKER_MISSING_DEP_FILE,
    BLOCKER_MIXED_LANGUAGE_TASK,
    BLOCKER_UNMET_CROSS_PHASE_DEP,
    EXIT_BLOCKED,
    EXIT_CLEAN,
    EXIT_USAGE,
    OUTPUT_CATEGORY,
    _apply_quality_gate_ordering,
    _blocker,
    _canonical_file_key,
    _compute_kahn_waves,
    _split_wave_on_conflicts,
    _wave_file_conflicts,
    find_dependency_cycle,
)
from task_metadata import (
    DEPENDENCIES_FORMAT_JSON,
    TaskMetadata,
    default_output_path,
    dependencies_md_path,
    discover_phase_task_files,
    find_task_file,
    format_phase,
    get_datrix_root,
    parse_dependencies_md,
    parse_task_file,
    task_id_number,
    task_id_phase,
    write_json_output,
)

logger = logging.getLogger(__name__)

SCHEMA_VERSION = 1

_PYTHON_EXTENSION = ".py"
_TYPESCRIPT_EXTENSION = ".ts"
_UNSPECIFIED_PACKAGE = "(unspecified)"

_MINIMUM_BATCH_PHASES = 2

#: A phase-order repair can expose a further inversion, so the repair iterates.
#: This bound is a runaway guard, not a tuning knob: every pass adds at least one
#: edge to a finite graph, so a real batch converges in a handful of passes.
_MAX_ORDER_REPAIR_PASSES = 50


def parse_phase_spec(spec: str) -> list[int]:
    """Parse ``5-8`` / ``5,6,7,8`` / ``5-6,8`` into a sorted unique phase list."""
    phases: set[int] = set()
    for chunk in spec.split(","):
        piece = chunk.strip()
        if not piece:
            continue
        if "-" in piece:
            low_text, _, high_text = piece.partition("-")
            low, high = _phase_int(low_text, piece, spec), _phase_int(high_text, piece, spec)
            if high < low:
                raise ValueError(
                    f"Phase range '{piece}' in '{spec}' runs backwards: {low} > "
                    f"{high}. Write it as {high}-{low}."
                )
            phases.update(range(low, high + 1))
            continue
        phases.add(_phase_int(piece, piece, spec))
    if len(phases) < _MINIMUM_BATCH_PHASES:
        raise ValueError(
            f"Phase spec '{spec}' selects {len(phases)} phase(s), but batch "
            f"planning needs at least {_MINIMUM_BATCH_PHASES}. Valid forms: a "
            "range (5-8), a comma list (5,6,7,8), or a mix (5-6,8). For a single "
            "phase use plan-waves.ps1 instead."
        )
    return sorted(phases)


def _phase_int(text: str, piece: str, spec: str) -> int:
    """Parse one phase number, naming the offending fragment when it is not one."""
    try:
        return int(text.strip())
    except ValueError as exc:
        raise ValueError(
            f"'{text.strip()}' in '{piece}' (from '{spec}') is not a phase number. "
            "Valid forms: a range (5-8), a comma list (5,6,7,8), or a mix (5-6,8)."
        ) from exc


def _phase_slug(phases: list[int]) -> str:
    """Default output-file stem for a phase set.

    A contiguous run is abbreviated to ``05-08``; anything else lists every
    phase (``05-06-08``). Abbreviating a gapped spec to its endpoints would give
    ``5-6,8`` the same file name as ``5-8`` and silently overwrite a different
    plan with a different task set.
    """
    contiguous = phases == list(range(phases[0], phases[-1] + 1))
    if contiguous:
        return f"{format_phase(phases[0])}-{format_phase(phases[-1])}"
    return "-".join(format_phase(phase) for phase in phases)


def _collect_tasks(base_dir: Path, phases: list[int]) -> dict[str, TaskMetadata]:
    """Parse every task file in the batched phases, keyed by task id."""
    by_id: dict[str, TaskMetadata] = {}
    empty: list[int] = []
    for phase in phases:
        paths = discover_phase_task_files(base_dir, phase)
        if not paths:
            empty.append(phase)
            continue
        for path in paths:
            task = parse_task_file(path)
            existing = by_id.get(task.task_id)
            if existing is not None:
                raise ValueError(
                    f"Duplicate task ID {task.task_id}: {existing.task_path} and "
                    f"{task.task_path}. Task numbers must be unique within a phase "
                    "across all repos; renumber one of the files."
                )
            by_id[task.task_id] = task
    if empty:
        joined = ", ".join(format_phase(phase) for phase in empty)
        raise ValueError(
            f"No task files found for phase(s) {joined} under {base_dir} "
            "(searched */.tasks/phase-NN/task-*.md). Check the phase numbers or "
            "pass -BaseDir."
        )
    return by_id


def _classify_dependency(
    base_dir: Path,
    batched_phases: set[int],
    task: TaskMetadata,
    dep: str,
    all_ids: set[str],
    selected_ids: set[str],
) -> tuple[bool, dict[str, str] | None]:
    """Return (dependency is an edge within the batch, blocker or None).

    Differs from the single-phase classifier in the one way that is the point of
    batching: a dependency on another phase *inside the batch* is an ordinary
    edge, not an ``UNMET_CROSS_PHASE_DEP`` blocker. A dependency on a phase
    OUTSIDE the batch is still held to the original rule -- it must exist and be
    COMPLETED, because nothing in this run will produce it.
    """
    if dep in selected_ids:
        return True, None
    dep_phase = task_id_phase(dep)
    if dep_phase in batched_phases:
        if dep in all_ids:
            return False, None  # completed, inside the batch: satisfied
        return False, _blocker(
            BLOCKER_MISSING_DEP_FILE,
            task.task_id,
            f"depends on {dep} but no task file exists for it in phase "
            f"{format_phase(dep_phase)} of any repo",
        )
    dep_file = find_task_file(base_dir, dep)
    if dep_file is None:
        return False, _blocker(
            BLOCKER_MISSING_DEP_FILE,
            task.task_id,
            f"dependency {dep} is outside the batched phases and has no task file "
            f"in phase {format_phase(dep_phase)} of any repo",
        )
    if not parse_task_file(dep_file).is_completed:
        return False, _blocker(
            BLOCKER_UNMET_CROSS_PHASE_DEP,
            task.task_id,
            f"dependency {dep} is outside the batched phases, exists ({dep_file}), "
            "and is not COMPLETED -- nothing in this batch will produce it",
        )
    return False, None


def _dep_mismatch_blockers(
    base_dir: Path, phases: list[int], selected: dict[str, TaskMetadata]
) -> list[dict[str, str]]:
    """DEP_MISMATCH blockers from each batched phase's JSON dependencies.md."""
    blockers: list[dict[str, str]] = []
    for phase in phases:
        doc_path = dependencies_md_path(base_dir, phase)
        if not doc_path.is_file():
            continue
        try:
            doc = parse_dependencies_md(doc_path)
        except ValueError as exc:
            logger.warning(
                "dependencies.md for phase %s unusable for mismatch check: %s",
                format_phase(phase),
                exc,
            )
            continue
        if doc.doc_format != DEPENDENCIES_FORMAT_JSON:
            logger.debug(
                "phase %s dependencies.md is %s format; DEP_MISMATCH skipped",
                format_phase(phase),
                doc.doc_format,
            )
            continue
        for entry in doc.entries:
            task = selected.get(entry.task_id)
            if task is None or entry.dependencies is None:
                continue
            doc_deps = sorted(entry.dependencies)
            file_deps = sorted(task.depends_on)
            if doc_deps != file_deps:
                blockers.append(
                    _blocker(
                        BLOCKER_DEP_MISMATCH,
                        entry.task_id,
                        f"task file says {file_deps} but dependencies.md says {doc_deps}",
                    )
                )
    return blockers


def _reachable(deps_map: dict[str, list[str]], start: str) -> set[str]:
    """Every task ``start`` transitively depends on."""
    seen: set[str] = set()
    stack = list(deps_map.get(start, ()))
    while stack:
        node = stack.pop()
        if node in seen:
            continue
        seen.add(node)
        stack.extend(deps_map.get(node, ()))
    return seen


def _batch_sort_key(task_id: str) -> tuple[int, int, str]:
    """Authoring order across a batch: phase first, then task number."""
    return (task_id_phase(task_id), task_id_number(task_id), task_id)


def _plan_once(
    selected: dict[str, TaskMetadata],
    deps_map: dict[str, list[str]],
    files_by_task: dict[str, set[str]],
) -> tuple[list[list[str]], list[str], dict[str, int], list[dict[str, object]]]:
    """One planning pass -> (waves, leftover, wave index per task, pre-split conflicts)."""
    ordered = _apply_quality_gate_ordering(selected, deps_map)
    kahn_waves, leftover = _compute_kahn_waves(ordered)
    pre_split_conflicts = _wave_file_conflicts(kahn_waves, files_by_task)
    waves: list[list[str]] = []
    for wave in kahn_waves:
        waves.extend(_split_wave_on_conflicts(wave, files_by_task))
    wave_index = {task_id: index for index, wave in enumerate(waves) for task_id in wave}
    return waves, leftover, wave_index, pre_split_conflicts


def _phase_order_inversions(
    files_by_task: dict[str, set[str]],
    wave_index: dict[str, int],
    deps_map: dict[str, list[str]],
) -> list[tuple[str, str, str]]:
    """Cross-phase same-file pairs the current wave order schedules backwards.

    Returns ``(later_phase_task, earlier_phase_task, file)`` triples needing an
    edge. A pair the wave sequence already orders correctly, or one already
    connected by a dependency path in either direction, is left alone -- so this
    repair adds the minimum number of edges and never imposes a total order over
    a file's writers.
    """
    claimants: dict[str, list[str]] = defaultdict(list)
    for task_id, file_keys in files_by_task.items():
        for file_key in file_keys:
            claimants[file_key].append(task_id)

    inversions: list[tuple[str, str, str]] = []
    seen: set[tuple[str, str]] = set()
    for file_key in sorted(claimants):
        owners = sorted(claimants[file_key], key=_batch_sort_key)
        if len(owners) < 2:
            continue
        for index, earlier in enumerate(owners):
            for later in owners[index + 1 :]:
                if task_id_phase(earlier) == task_id_phase(later):
                    continue  # same phase: plan_waves' own splitter owns this
                if (later, earlier) in seen:
                    continue
                if wave_index[later] > wave_index[earlier]:
                    continue  # already scheduled in phase order
                if earlier in _reachable(deps_map, later):
                    continue  # already ordered by a real dependency path
                if later in _reachable(deps_map, earlier):
                    continue  # deliberately ordered the other way; respect it
                seen.add((later, earlier))
                inversions.append((later, earlier, file_key))
    return inversions


def _repair_phase_order(
    selected: dict[str, TaskMetadata],
    deps_map: dict[str, list[str]],
    files_by_task: dict[str, set[str]],
) -> tuple[list[list[str]], list[str], list[dict[str, str]], int]:
    """Plan, then add the minimum edges that stop a later phase running first."""
    waves, leftover, wave_index, _ = _plan_once(selected, deps_map, files_by_task)
    implicit_edges: list[dict[str, str]] = []
    passes = 0
    while not leftover and passes < _MAX_ORDER_REPAIR_PASSES:
        inversions = _phase_order_inversions(files_by_task, wave_index, deps_map)
        if not inversions:
            break
        for later, earlier, file_key in inversions:
            if earlier in deps_map[later]:
                continue
            deps_map[later] = sorted({*deps_map[later], earlier})
            implicit_edges.append(
                {
                    "task_id": later,
                    "depends_on": earlier,
                    "reason": "writes a file an earlier phase's task also writes",
                    "file": file_key,
                }
            )
        waves, leftover, wave_index, _ = _plan_once(selected, deps_map, files_by_task)
        passes += 1
    if passes >= _MAX_ORDER_REPAIR_PASSES:
        raise ValueError(
            f"Phase-order repair did not converge in {_MAX_ORDER_REPAIR_PASSES} "
            "passes: the same-file graph keeps producing new inversions. Inspect "
            "implicit_order_edges for a pair that keeps flipping -- that normally "
            "means two tasks in different phases each declare a dependency "
            "reaching the other."
        )
    return waves, leftover, implicit_edges, passes


def plan_waves_multi(
    base_dir: Path, phases: list[int], include_completed: bool
) -> dict[str, object]:
    """Assemble the batch wave-plan payload. Raises ValueError on bad input."""
    all_by_id = _collect_tasks(base_dir, phases)
    selected = {
        task_id: task
        for task_id, task in all_by_id.items()
        if include_completed or not task.is_completed
    }
    if not selected:
        joined = ", ".join(format_phase(phase) for phase in phases)
        raise ValueError(
            f"Every task in phase(s) {joined} is already COMPLETED, so there is "
            "nothing to plan. Pass --include-completed to plan them anyway."
        )

    batched = set(phases)
    blockers: list[dict[str, str]] = []
    deps_map: dict[str, list[str]] = {}
    for task_id in sorted(selected):
        task = selected[task_id]
        edges: list[str] = []
        for dep in task.depends_on:
            is_edge, blocker = _classify_dependency(
                base_dir, batched, task, dep, set(all_by_id), set(selected)
            )
            if is_edge:
                edges.append(dep)
            if blocker is not None:
                blockers.append(blocker)
        deps_map[task_id] = edges
        if _PYTHON_EXTENSION in task.languages and _TYPESCRIPT_EXTENSION in task.languages:
            blockers.append(
                _blocker(
                    BLOCKER_MIXED_LANGUAGE_TASK,
                    task_id,
                    "task mixes Python (.py) and TypeScript (.ts) files in its "
                    "Files to Create/Modify section",
                )
            )
    blockers.extend(_dep_mismatch_blockers(base_dir, phases, selected))

    files_by_task = {
        task_id: {
            _canonical_file_key(base_dir, selected[task_id], path_str)
            for path_str in selected[task_id].files_to_create_modify
        }
        for task_id in selected
    }

    declared_deps = {task_id: list(edges) for task_id, edges in deps_map.items()}
    pre_repair_conflicts = _plan_once(selected, declared_deps, files_by_task)[3]
    waves, leftover, implicit_edges, passes = _repair_phase_order(
        selected, deps_map, files_by_task
    )

    ordered_final = _apply_quality_gate_ordering(selected, deps_map)
    cycle = find_dependency_cycle({node: ordered_final[node] for node in leftover})

    # Post-condition: after splitting, no wave may hold two writers of one file.
    residual = _wave_file_conflicts(waves, files_by_task)

    wave_details = [
        {
            "wave": index + 1,
            "task_ids": wave,
            "phases": sorted({format_phase(task_id_phase(task_id)) for task_id in wave}),
            "packages": sorted(
                {selected[task_id].package or _UNSPECIFIED_PACKAGE for task_id in wave}
            ),
        }
        for index, wave in enumerate(waves)
    ]
    return {
        "schema_version": SCHEMA_VERSION,
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "phases": [format_phase(phase) for phase in phases],
        "base_dir": str(base_dir),
        "include_completed": include_completed,
        "task_count": len(selected),
        "completed_excluded": len(all_by_id) - len(selected),
        "waves": waves,
        "wave_details": wave_details,
        "unschedulable_tasks": leftover,
        "cycle": cycle if cycle else None,
        "file_conflicts": pre_repair_conflicts,
        "implicit_order_edges": implicit_edges,
        "order_repair_passes": passes,
        "residual_file_conflicts": residual,
        "blocking_issues": blockers,
        "can_parallelize": not blockers and not cycle and not leftover and not residual,
    }


def _print_summary(payload: dict[str, object], output_path: Path, scope: str) -> bool:
    """Print the console summary; return True when the run must exit BLOCKED."""
    waves = payload["waves"]
    blockers = payload["blocking_issues"]
    cycle = payload["cycle"]
    unschedulable = payload["unschedulable_tasks"]
    residual = payload["residual_file_conflicts"]
    implicit = payload["implicit_order_edges"]
    wave_count = len(waves) if isinstance(waves, list) else 0
    blocker_count = len(blockers) if isinstance(blockers, list) else 0
    implicit_count = len(implicit) if isinstance(implicit, list) else 0
    parallel = "yes" if payload["can_parallelize"] else "no"
    phases = payload["phases"]
    joined_phases = "+".join(str(phase) for phase in phases) if isinstance(phases, list) else ""
    print(
        f"Phases {joined_phases}: {payload['task_count']} {scope} -> {wave_count} "
        f"waves; blockers: {blocker_count}; implicit order edges: "
        f"{implicit_count}; can_parallelize: {parallel}"
    )
    if isinstance(cycle, list) and cycle:
        print("Dependency cycle: " + " -> ".join(str(node) for node in cycle))
    if isinstance(residual, list) and residual:
        print(
            f"RESIDUAL FILE CONFLICTS ({len(residual)}): two tasks share a wave and "
            "write the same file. This plan is NOT safe to run in parallel."
        )
        for conflict in residual:
            print(f"  {conflict['file']}: {conflict['task_ids']}")
    print(f"Details: {output_path.resolve()}")
    return bool(
        blocker_count
        or (isinstance(cycle, list) and cycle)
        or (isinstance(unschedulable, list) and unschedulable)
        or (isinstance(residual, list) and residual)
    )


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Plan dependency-ordered execution waves for several phases as one batch"
    )
    parser.add_argument("phases", help="Phase range or list (e.g. 5-8, 5,6,7,8, 5-6,8)")
    parser.add_argument(
        "--include-completed",
        action="store_true",
        help="Plan every task, not just the non-completed ones",
    )
    parser.add_argument(
        "--base-dir",
        type=Path,
        default=None,
        help="Workspace root containing the datrix* repos (default: auto-detected)",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=None,
        help="Output JSON path (default: <workspace>/.tmp/tasks/phases-NN-MM-waves.json)",
    )
    parser.add_argument("--debug", action="store_true", help="Enable debug logging")
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.DEBUG if args.debug else logging.INFO,
        format="%(levelname)s: %(message)s",
    )

    base_dir = args.base_dir if args.base_dir is not None else get_datrix_root()
    if not base_dir.is_dir():
        print(f"ERROR: Base directory does not exist: {base_dir}", file=sys.stderr)
        return EXIT_USAGE

    try:
        phases = parse_phase_spec(args.phases)
        payload = plan_waves_multi(base_dir, phases, args.include_completed)
    except ValueError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return EXIT_USAGE

    output_path = (
        args.output
        if args.output is not None
        else default_output_path(OUTPUT_CATEGORY, f"phases-{_phase_slug(phases)}-waves.json")
    )
    write_json_output(payload, output_path)

    scope = "tasks" if args.include_completed else "pending tasks"
    return EXIT_BLOCKED if _print_summary(payload, output_path, scope) else EXIT_CLEAN


if __name__ == "__main__":
    sys.exit(main())
