#!/usr/bin/env python3
"""Plan parallel execution waves for a phase's tasks.

Implements the wave rules the orchestration skills apply by hand:

1. Kahn topological sort over the task-file ``**Depends on:**`` graph — a wave
   is every task whose dependencies are satisfied by previous waves (or by
   already-COMPLETED tasks). Deterministic: ready sets are ordered by task_id.
2. Quality-gate ordering (task-orchestrator SKILL.md step 2e): tasks whose
   ``**Category:**`` marks them as a quality gate are pushed into the final
   wave(s) after every other task — except tasks that themselves (transitively)
   depend on a quality gate (e.g. a phase acceptance run), which stay after the
   gates. Verification/Acceptance tasks need no special handling beyond the
   topological order (2e: "after their dependency tasks").
3. Any wave in which two tasks touch the same file (from the ``## Files to
   Create / Modify`` sections) is split into sequential conflict-free
   sub-waves (greedy first-fit in task_id order).

Blocker detection follows execute-tasks-parallel SKILL.md Phase 1:
MISSING_DEP_FILE, UNMET_CROSS_PHASE_DEP, MIXED_LANGUAGE_TASK (a task mixing
.py and .ts files), DEP_MISMATCH (task file vs JSON dependencies.md; legacy
'Group N' docs carry no per-task arrays and are validated by
validate_dependencies.py instead). ``can_parallelize`` is true iff there are
no blockers and no dependency cycle.

Usage:
  python scripts/library/tasks/plan_waves.py 31
  python scripts/library/tasks/plan_waves.py 31 --include-completed
  .\\scripts\\tasks\\plan-waves.ps1 31 -IncludeCompleted
"""

from __future__ import annotations

import argparse
import io
import logging
import sys
from datetime import datetime
from pathlib import Path

# Configure UTF-8 encoding for stdout/stderr on Windows
if sys.platform == "win32" and __name__ == "__main__":
    if hasattr(sys.stdout, "buffer"):
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    if hasattr(sys.stderr, "buffer"):
        sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

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
    task_id_phase,
    write_json_output,
)

logger = logging.getLogger(__name__)

SCHEMA_VERSION = 1
OUTPUT_CATEGORY = "tasks"

EXIT_CLEAN = 0
EXIT_BLOCKED = 1
EXIT_USAGE = 2

BLOCKER_MISSING_DEP_FILE = "MISSING_DEP_FILE"
BLOCKER_UNMET_CROSS_PHASE_DEP = "UNMET_CROSS_PHASE_DEP"
BLOCKER_MIXED_LANGUAGE_TASK = "MIXED_LANGUAGE_TASK"
BLOCKER_DEP_MISMATCH = "DEP_MISMATCH"

_PYTHON_EXTENSION = ".py"
_TYPESCRIPT_EXTENSION = ".ts"

_UNSPECIFIED_PACKAGE = "(unspecified)"


def _blocker(kind: str, task_id: str, detail: str) -> dict[str, str]:
    return {"type": kind, "task_id": task_id, "detail": detail}


def _classify_dependency(
    base_dir: Path,
    phase: int,
    task: TaskMetadata,
    dep: str,
    all_ids: set[str],
    selected_ids: set[str],
) -> tuple[bool, dict[str, str] | None]:
    """Return (dependency is an edge within the selected set, blocker or None)."""
    if dep in selected_ids:
        return True, None
    if task_id_phase(dep) == phase:
        if dep in all_ids:
            return False, None  # completed same-phase dependency: satisfied
        return False, _blocker(
            BLOCKER_MISSING_DEP_FILE,
            task.task_id,
            f"depends on {dep} but no task file exists for it in phase "
            f"{format_phase(phase)} of any repo",
        )
    dep_file = find_task_file(base_dir, dep)
    if dep_file is None:
        return False, _blocker(
            BLOCKER_MISSING_DEP_FILE,
            task.task_id,
            f"cross-phase dependency {dep} has no task file in phase "
            f"{format_phase(task_id_phase(dep))} of any repo",
        )
    if not parse_task_file(dep_file).is_completed:
        return False, _blocker(
            BLOCKER_UNMET_CROSS_PHASE_DEP,
            task.task_id,
            f"cross-phase dependency {dep} exists ({dep_file}) but is not COMPLETED",
        )
    return False, None


def _dep_mismatch_blockers(
    base_dir: Path, phase: int, selected: dict[str, TaskMetadata]
) -> list[dict[str, str]]:
    """DEP_MISMATCH blockers from a JSON dependencies.md (legacy docs carry none)."""
    doc_path = dependencies_md_path(base_dir, phase)
    if not doc_path.is_file():
        return []
    try:
        doc = parse_dependencies_md(doc_path)
    except ValueError as exc:
        logger.warning("dependencies.md unusable for mismatch check: %s", exc)
        return []
    if doc.doc_format != DEPENDENCIES_FORMAT_JSON:
        logger.debug("dependencies.md is %s format; DEP_MISMATCH skipped", doc.doc_format)
        return []
    blockers: list[dict[str, str]] = []
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


def _quality_gate_descendants(
    selected: dict[str, TaskMetadata], deps_map: dict[str, list[str]]
) -> set[str]:
    """Tasks that transitively depend on a quality-gate task."""
    dependents: dict[str, set[str]] = {task_id: set() for task_id in selected}
    for task_id, deps in deps_map.items():
        for dep in deps:
            dependents[dep].add(task_id)
    frontier = [task_id for task_id, task in selected.items() if task.is_quality_gate]
    descendants: set[str] = set()
    while frontier:
        current = frontier.pop()
        for dependent in dependents[current]:
            if dependent not in descendants:
                descendants.add(dependent)
                frontier.append(dependent)
    return descendants


def _apply_quality_gate_ordering(
    selected: dict[str, TaskMetadata], deps_map: dict[str, list[str]]
) -> dict[str, list[str]]:
    """Add implicit edges pushing quality gates into the final wave(s).

    Every non-gate task that does not itself depend (transitively) on a gate
    becomes an implicit dependency of every gate, so gates land after all
    ordinary work while gate-dependent tasks (acceptance runs) stay last.
    """
    gates = [task_id for task_id, task in selected.items() if task.is_quality_gate]
    if not gates:
        return deps_map
    descendants = _quality_gate_descendants(selected, deps_map)
    ordinary = [
        task_id
        for task_id, task in selected.items()
        if not task.is_quality_gate and task_id not in descendants
    ]
    augmented = {task_id: list(deps) for task_id, deps in deps_map.items()}
    for gate in gates:
        merged = set(augmented[gate]) | set(ordinary)
        merged.discard(gate)
        augmented[gate] = sorted(merged)
    return augmented


def _compute_kahn_waves(
    deps_map: dict[str, list[str]]
) -> tuple[list[list[str]], list[str]]:
    """Kahn topological waves; second element is the leftover (cyclic) set."""
    remaining = set(deps_map)
    satisfied: set[str] = set()
    waves: list[list[str]] = []
    while remaining:
        ready = sorted(
            task_id
            for task_id in remaining
            if all(dep in satisfied for dep in deps_map[task_id])
        )
        if not ready:
            return waves, sorted(remaining)
        waves.append(ready)
        satisfied.update(ready)
        remaining.difference_update(ready)
    return waves, []


def find_dependency_cycle(deps_map: dict[str, list[str]]) -> list[str]:
    """Return one dependency cycle as [a, b, ..., a], or [] if acyclic."""
    white, gray, black = 0, 1, 2
    color = {node: white for node in deps_map}
    for root in sorted(deps_map):
        if color[root] != white:
            continue
        path: list[str] = []
        stack: list[tuple[str, int]] = [(root, 0)]
        while stack:
            node, index = stack.pop()
            if index == 0:
                color[node] = gray
                path.append(node)
            deps = [dep for dep in deps_map[node] if dep in color]
            if index >= len(deps):
                color[node] = black
                path.pop()
                continue
            stack.append((node, index + 1))
            nxt = deps[index]
            if color[nxt] == gray:
                return path[path.index(nxt) :] + [nxt]
            if color[nxt] == white:
                stack.append((nxt, 0))
    return []


def _canonical_file_key(base_dir: Path, task: TaskMetadata, path_str: str) -> str:
    """Comparable key for conflict detection across absolute/relative spellings."""
    normalized = path_str.replace("\\", "/").lower().rstrip("/")
    base_prefix = str(base_dir).replace("\\", "/").lower().rstrip("/") + "/"
    if normalized.startswith(base_prefix):
        return normalized[len(base_prefix) :]
    if ":" in normalized.split("/", 1)[0]:
        return normalized  # absolute path outside the workspace
    package = (task.package or task.repo or _UNSPECIFIED_PACKAGE).lower()
    return f"{package}/{normalized}"


def _split_wave_on_conflicts(
    wave: list[str], files_by_task: dict[str, set[str]]
) -> list[list[str]]:
    """Greedy first-fit split of one wave into conflict-free sub-waves."""
    sub_waves: list[list[str]] = []
    claimed: list[set[str]] = []
    for task_id in wave:
        task_files = files_by_task[task_id]
        placed = False
        for index, files in enumerate(claimed):
            if not (files & task_files):
                sub_waves[index].append(task_id)
                claimed[index] |= task_files
                placed = True
                break
        if not placed:
            sub_waves.append([task_id])
            claimed.append(set(task_files))
    return sub_waves


def _wave_file_conflicts(
    waves: list[list[str]], files_by_task: dict[str, set[str]]
) -> list[dict[str, object]]:
    """Files claimed by 2+ tasks of the same (pre-split) wave."""
    conflicts: list[dict[str, object]] = []
    for wave in waves:
        owners: dict[str, list[str]] = {}
        for task_id in wave:
            for file_key in sorted(files_by_task[task_id]):
                owners.setdefault(file_key, []).append(task_id)
        for file_key in sorted(owners):
            if len(owners[file_key]) >= 2:
                conflicts.append({"file": file_key, "task_ids": owners[file_key]})
    return conflicts


def plan_waves(
    base_dir: Path, phase: int, include_completed: bool
) -> dict[str, object]:
    """Assemble the wave-plan payload. Raises ValueError on bad input."""
    task_files = discover_phase_task_files(base_dir, phase)
    if not task_files:
        raise ValueError(
            f"No task files found for phase {format_phase(phase)} under {base_dir} "
            f"(searched */.tasks/phase-{format_phase(phase)}/task-*.md). Check the "
            "phase number or pass -BaseDir."
        )
    tasks = [parse_task_file(path) for path in task_files]
    all_by_id: dict[str, TaskMetadata] = {}
    for task in tasks:
        if task.task_id in all_by_id:
            raise ValueError(
                f"Duplicate task ID {task.task_id}: {all_by_id[task.task_id].task_path} "
                f"and {task.task_path}. Task numbers must be unique within a phase "
                "across all repos; renumber one of the files."
            )
        all_by_id[task.task_id] = task

    selected = {
        task_id: task
        for task_id, task in all_by_id.items()
        if include_completed or not task.is_completed
    }

    blockers: list[dict[str, str]] = []
    deps_map: dict[str, list[str]] = {}
    for task_id in sorted(selected):
        task = selected[task_id]
        edges: list[str] = []
        for dep in task.depends_on:
            is_edge, blocker = _classify_dependency(
                base_dir, phase, task, dep, set(all_by_id), set(selected)
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
    blockers.extend(_dep_mismatch_blockers(base_dir, phase, selected))

    ordered_deps = _apply_quality_gate_ordering(selected, deps_map)
    kahn_waves, leftover = _compute_kahn_waves(ordered_deps)
    cycle = find_dependency_cycle({node: ordered_deps[node] for node in leftover})

    files_by_task = {
        task_id: {
            _canonical_file_key(base_dir, selected[task_id], path_str)
            for path_str in selected[task_id].files_to_create_modify
        }
        for task_id in selected
    }
    file_conflicts = _wave_file_conflicts(kahn_waves, files_by_task)
    waves: list[list[str]] = []
    for wave in kahn_waves:
        waves.extend(_split_wave_on_conflicts(wave, files_by_task))

    wave_details = [
        {
            "wave": index + 1,
            "task_ids": wave,
            "packages": sorted(
                {selected[task_id].package or _UNSPECIFIED_PACKAGE for task_id in wave}
            ),
        }
        for index, wave in enumerate(waves)
    ]
    return {
        "schema_version": SCHEMA_VERSION,
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "phase": phase,
        "base_dir": str(base_dir),
        "include_completed": include_completed,
        "task_count": len(selected),
        "completed_excluded": len(all_by_id) - len(selected),
        "waves": waves,
        "wave_details": wave_details,
        "unschedulable_tasks": leftover,
        "cycle": cycle if cycle else None,
        "file_conflicts": file_conflicts,
        "blocking_issues": blockers,
        "can_parallelize": not blockers and not cycle and not leftover,
    }


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Plan dependency-ordered execution waves for a phase"
    )
    parser.add_argument("phase", type=int, help="Phase number (e.g. 31)")
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
        help="Output JSON path (default: <workspace>/.tmp/tasks/phase-NN-waves.json)",
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
        payload = plan_waves(base_dir, args.phase, args.include_completed)
    except ValueError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return EXIT_USAGE

    output_path = (
        args.output
        if args.output is not None
        else default_output_path(
            OUTPUT_CATEGORY, f"phase-{format_phase(args.phase)}-waves.json"
        )
    )
    write_json_output(payload, output_path)

    waves = payload["waves"]
    blockers = payload["blocking_issues"]
    cycle = payload["cycle"]
    unschedulable = payload["unschedulable_tasks"]
    wave_count = len(waves) if isinstance(waves, list) else 0
    blocker_count = len(blockers) if isinstance(blockers, list) else 0
    scope = "tasks" if args.include_completed else "pending tasks"
    parallel = "yes" if payload["can_parallelize"] else "no"
    print(
        "Phase %s: %s %s -> %s waves; blockers: %s; can_parallelize: %s"
        % (
            format_phase(args.phase),
            payload["task_count"],
            scope,
            wave_count,
            blocker_count,
            parallel,
        )
    )
    if isinstance(cycle, list) and cycle:
        print("Dependency cycle: %s" % " -> ".join(str(node) for node in cycle))
    print(f"Details: {output_path.resolve()}")
    has_cycle = isinstance(cycle, list) and bool(cycle)
    has_unschedulable = isinstance(unschedulable, list) and bool(unschedulable)
    if blocker_count or has_cycle or has_unschedulable:
        return EXIT_BLOCKED
    return EXIT_CLEAN


if __name__ == "__main__":
    sys.exit(main())
