#!/usr/bin/env python3
"""Validate a phase's dependencies.md against the task files on disk.

Mode A (default, ``--phase NN``): runs named checks, each with a status
(pass / fail / warn / info / skipped) and per-violation detail:

  1. dependencies_md_exists          — the phase-level file exists
  2. dependencies_md_is_json         — JSON preferred; legacy 'Group N' = WARN
  3. dependencies_md_complete        — lists every discovered task, nothing more
  4. dependency_ids_resolve          — every dep ID (files + doc) has a task file
  5. graph_acyclic                   — task-file graph (and JSON doc graph) acyclic
  6. dependencies_match_task_files   — doc's per-task arrays == files' Depends on
                                       (legacy: group ordering consistency, WARN)
  7. task_paths_absolute_and_existing— doc paths absolute + present on disk
  8. task_numbers_unique             — no task number reused across repos
  9. task_numbers_sequential         — numbers run 01..max with no gaps
 10. provenance_stamp                — provenance present (INFO either way)

Exit 0 = pass (warnings/infos allowed), 1 = any failed check, 2 = usage error.

Mode B (``--phase NN --next-task-number``): prints ONLY the next free
two-digit task number for the phase (for scripting), exit 0.

Usage:
  python scripts/library/tasks/validate_dependencies.py --phase 31
  python scripts/library/tasks/validate_dependencies.py --phase 31 --next-task-number
  .\\scripts\\tasks\\validate-dependencies.ps1 -Phase 31 [-NextTaskNumber]
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

from plan_waves import find_dependency_cycle
from task_metadata import (
    DEPENDENCIES_FORMAT_JSON,
    DependenciesDoc,
    TaskMetadata,
    default_output_path,
    dependencies_md_path,
    discover_phase_task_files,
    find_task_file,
    format_phase,
    get_datrix_root,
    parse_dependencies_md,
    parse_task_file,
    task_id_from_filename,
    task_id_number,
    task_id_phase,
    write_json_output,
)

logger = logging.getLogger(__name__)

SCHEMA_VERSION = 1
OUTPUT_CATEGORY = "tasks"

EXIT_PASS = 0
EXIT_FAIL = 1
EXIT_USAGE = 2

STATUS_PASS = "pass"
STATUS_FAIL = "fail"
STATUS_WARN = "warn"
STATUS_INFO = "info"
STATUS_SKIPPED = "skipped"

OVERALL_PASS = "PASS"
OVERALL_FAIL = "FAIL"

FIRST_TASK_NUMBER = 1


def _check(
    name: str, status: str, detail: str, violations: list[str] | None = None
) -> dict[str, object]:
    return {
        "check": name,
        "status": status,
        "detail": detail,
        "violations": violations or [],
    }


def _from_violations(
    name: str, violations: list[str], pass_detail: str, fail_detail: str
) -> dict[str, object]:
    if violations:
        return _check(name, STATUS_FAIL, fail_detail, violations)
    return _check(name, STATUS_PASS, pass_detail)


def _check_exists(doc_path: Path) -> dict[str, object]:
    if doc_path.is_file():
        return _check("dependencies_md_exists", STATUS_PASS, f"found at {doc_path}")
    return _check(
        "dependencies_md_exists",
        STATUS_FAIL,
        f"dependencies.md not found at {doc_path}. Generate it with "
        "/generate-tasks (JSON format per dependencies-format.md).",
        [f"missing file: {doc_path}"],
    )


def _check_format(doc: DependenciesDoc | None, error: str | None) -> dict[str, object]:
    if error is not None:
        return _check(
            "dependencies_md_is_json",
            STATUS_FAIL,
            "dependencies.md is neither valid JSON nor the legacy Group format",
            [error],
        )
    if doc is None:
        return _check("dependencies_md_is_json", STATUS_SKIPPED, "no dependencies.md")
    if doc.doc_format == DEPENDENCIES_FORMAT_JSON:
        return _check("dependencies_md_is_json", STATUS_PASS, "JSON format")
    return _check(
        "dependencies_md_is_json",
        STATUS_WARN,
        "legacy 'Group N' text format — executors fall back to reading every "
        "task file; regenerate as JSON with /generate-tasks",
    )


def _check_complete(
    doc: DependenciesDoc | None, tasks_by_id: dict[str, TaskMetadata]
) -> dict[str, object]:
    if doc is None:
        return _check("dependencies_md_complete", STATUS_SKIPPED, "no parseable dependencies.md")
    listed = {entry.task_id for entry in doc.entries}
    violations = [
        f"task on disk but not in dependencies.md: {task_id}"
        for task_id in sorted(set(tasks_by_id) - listed)
    ]
    violations.extend(
        f"listed in dependencies.md but no task file on disk: {task_id}"
        for task_id in sorted(listed - set(tasks_by_id))
    )
    return _from_violations(
        "dependencies_md_complete",
        violations,
        f"all {len(listed)} discovered tasks listed, nothing extra",
        "dependencies.md and the task files on disk disagree",
    )


def _check_deps_resolve(
    base_dir: Path,
    phase: int,
    tasks_by_id: dict[str, TaskMetadata],
    doc: DependenciesDoc | None,
) -> dict[str, object]:
    violations: list[str] = []
    referencing: list[tuple[str, list[str], str]] = [
        (task.task_id, task.depends_on, "task file") for task in tasks_by_id.values()
    ]
    if doc is not None:
        referencing.extend(
            (entry.task_id, entry.dependencies, "dependencies.md")
            for entry in doc.entries
            if entry.dependencies is not None
        )
    seen: set[tuple[str, str, str]] = set()
    for owner, deps, source in referencing:
        for dep in deps:
            key = (owner, dep, source)
            if key in seen:
                continue
            seen.add(key)
            if dep in tasks_by_id:
                continue
            if task_id_phase(dep) != phase and find_task_file(base_dir, dep) is not None:
                continue
            violations.append(f"{owner} ({source}) depends on {dep}: no task file found")
    return _from_violations(
        "dependency_ids_resolve",
        violations,
        "every dependency ID resolves to an existing task file",
        "unresolvable dependency IDs found",
    )


def _cycle_violations(deps_map: dict[str, list[str]], source: str) -> list[str]:
    filtered = {
        node: [dep for dep in deps if dep in deps_map] for node, deps in deps_map.items()
    }
    cycle = find_dependency_cycle(filtered)
    if cycle:
        return [f"{source}: dependency cycle: " + " -> ".join(cycle)]
    return []


def _check_acyclic(
    tasks_by_id: dict[str, TaskMetadata], doc: DependenciesDoc | None
) -> dict[str, object]:
    violations = _cycle_violations(
        {task.task_id: task.depends_on for task in tasks_by_id.values()}, "task files"
    )
    if doc is not None and doc.doc_format == DEPENDENCIES_FORMAT_JSON:
        violations.extend(
            _cycle_violations(
                {
                    entry.task_id: entry.dependencies
                    for entry in doc.entries
                    if entry.dependencies is not None
                },
                "dependencies.md",
            )
        )
    return _from_violations(
        "graph_acyclic",
        violations,
        "dependency graph is acyclic",
        "dependency cycle detected",
    )


def _check_deps_match(
    doc: DependenciesDoc | None, tasks_by_id: dict[str, TaskMetadata]
) -> dict[str, object]:
    if doc is None:
        return _check(
            "dependencies_match_task_files", STATUS_SKIPPED, "no parseable dependencies.md"
        )
    if doc.doc_format == DEPENDENCIES_FORMAT_JSON:
        violations: list[str] = []
        for entry in doc.entries:
            task = tasks_by_id.get(entry.task_id)
            if task is None or entry.dependencies is None:
                continue
            doc_deps = sorted(entry.dependencies)
            file_deps = sorted(task.depends_on)
            if doc_deps != file_deps:
                violations.append(
                    f"{entry.task_id}: task file says {file_deps}, "
                    f"dependencies.md says {doc_deps}"
                )
        return _from_violations(
            "dependencies_match_task_files",
            violations,
            "every dependencies array matches its task file's Depends on field",
            "dependencies.md disagrees with the task files",
        )
    return _check_deps_match_legacy(doc, tasks_by_id)


def _check_deps_match_legacy(
    doc: DependenciesDoc, tasks_by_id: dict[str, TaskMetadata]
) -> dict[str, object]:
    """Legacy docs have no per-task arrays; verify group-ordering consistency."""
    group_of = {entry.task_id: entry.group for entry in doc.entries}
    inconsistencies: list[str] = []
    for entry in doc.entries:
        task = tasks_by_id.get(entry.task_id)
        if task is None or entry.group is None:
            continue
        for dep in task.depends_on:
            dep_group = group_of.get(dep)
            if dep_group is not None and dep_group >= entry.group:
                inconsistencies.append(
                    f"{entry.task_id} (group {entry.group}) depends on {dep} "
                    f"(group {dep_group}): groups may only depend on earlier groups"
                )
    if inconsistencies:
        return _check(
            "dependencies_match_task_files",
            STATUS_WARN,
            "legacy format: group ordering contradicts the task files' "
            "Depends on fields",
            inconsistencies,
        )
    return _check(
        "dependencies_match_task_files",
        STATUS_WARN,
        "legacy format has no per-task dependency arrays to compare; group "
        "ordering is consistent with the task files' Depends on fields",
    )


def _check_task_paths(doc: DependenciesDoc | None) -> dict[str, object]:
    if doc is None:
        return _check(
            "task_paths_absolute_and_existing", STATUS_SKIPPED, "no parseable dependencies.md"
        )
    violations: list[str] = []
    for entry in doc.entries:
        if entry.task_path is None:
            continue
        path = Path(entry.task_path)
        if not path.is_absolute():
            violations.append(f"{entry.task_id}: task_path is not absolute: {entry.task_path}")
        elif not path.is_file():
            violations.append(f"{entry.task_id}: task_path does not exist: {entry.task_path}")
    return _from_violations(
        "task_paths_absolute_and_existing",
        violations,
        "all listed task paths are absolute and exist",
        "invalid task paths in dependencies.md",
    )


def _check_numbers_unique(task_files: list[Path]) -> dict[str, object]:
    owners: dict[str, list[str]] = {}
    for path in task_files:
        owners.setdefault(task_id_from_filename(path), []).append(str(path))
    violations = [
        f"{task_id} appears {len(paths)} times: " + "; ".join(sorted(paths))
        for task_id, paths in sorted(owners.items())
        if len(paths) > 1
    ]
    return _from_violations(
        "task_numbers_unique",
        violations,
        "task numbers are unique across repos",
        "duplicate task numbers across repos",
    )


def _check_numbers_sequential(tasks_by_id: dict[str, TaskMetadata]) -> dict[str, object]:
    numbers = sorted({task_id_number(task_id) for task_id in tasks_by_id})
    if not numbers:
        return _check("task_numbers_sequential", STATUS_SKIPPED, "no tasks discovered")
    missing = sorted(set(range(FIRST_TASK_NUMBER, numbers[-1] + 1)) - set(numbers))
    violations = [f"missing task number: {number:02d}" for number in missing]
    return _from_violations(
        "task_numbers_sequential",
        violations,
        f"task numbers run {FIRST_TASK_NUMBER:02d}..{numbers[-1]:02d} with no gaps",
        "task numbering has gaps",
    )


def _check_provenance(doc: DependenciesDoc | None) -> dict[str, object]:
    if doc is None:
        return _check("provenance_stamp", STATUS_SKIPPED, "no parseable dependencies.md")
    if doc.provenance is not None:
        return _check(
            "provenance_stamp",
            STATUS_INFO,
            f"provenance present: {doc.provenance}",
        )
    return _check(
        "provenance_stamp",
        STATUS_INFO,
        "provenance stamp absent — /task-orchestrator's readiness audit will "
        "run in full mode on this set",
    )


def validate_phase(base_dir: Path, phase: int) -> dict[str, object]:
    """Run all Mode-A checks; raises ValueError when the phase has no tasks."""
    task_files = discover_phase_task_files(base_dir, phase)
    if not task_files:
        raise ValueError(
            f"No task files found for phase {format_phase(phase)} under {base_dir} "
            f"(searched */.tasks/phase-{format_phase(phase)}/task-*.md). Check the "
            "phase number or pass -BaseDir."
        )
    tasks_by_id: dict[str, TaskMetadata] = {}
    for path in task_files:
        task = parse_task_file(path)
        tasks_by_id.setdefault(task.task_id, task)

    doc_path = dependencies_md_path(base_dir, phase)
    doc: DependenciesDoc | None = None
    doc_error: str | None = None
    if doc_path.is_file():
        try:
            doc = parse_dependencies_md(doc_path)
        except ValueError as exc:
            doc_error = str(exc)

    checks = [
        _check_exists(doc_path),
        _check_format(doc, doc_error),
        _check_complete(doc, tasks_by_id),
        _check_deps_resolve(base_dir, phase, tasks_by_id, doc),
        _check_acyclic(tasks_by_id, doc),
        _check_deps_match(doc, tasks_by_id),
        _check_task_paths(doc),
        _check_numbers_unique(task_files),
        _check_numbers_sequential(tasks_by_id),
        _check_provenance(doc),
    ]
    failed = [check for check in checks if check["status"] == STATUS_FAIL]
    violation_count = 0
    for check in failed:
        violations = check["violations"]
        if isinstance(violations, list):
            violation_count += len(violations)
    warn_count = sum(1 for check in checks if check["status"] == STATUS_WARN)
    return {
        "schema_version": SCHEMA_VERSION,
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "phase": phase,
        "base_dir": str(base_dir),
        "dependencies_md_path": str(doc_path),
        "dependencies_md_format": doc.doc_format if doc is not None else None,
        "overall": OVERALL_FAIL if failed else OVERALL_PASS,
        "violation_count": violation_count,
        "warning_count": warn_count,
        "task_count": len(tasks_by_id),
        "checks": checks,
    }


def next_task_number(base_dir: Path, phase: int) -> str:
    """Next free two-digit task number for the phase across all repos."""
    highest = 0
    for path in discover_phase_task_files(base_dir, phase):
        task_id = task_id_from_filename(path)
        if task_id_phase(task_id) == phase:
            highest = max(highest, task_id_number(task_id))
    return f"{highest + 1:02d}"


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Validate a phase's dependencies.md against its task files"
    )
    parser.add_argument("--phase", type=int, required=True, help="Phase number (e.g. 31)")
    parser.add_argument(
        "--next-task-number",
        action="store_true",
        help="Print only the next free two-digit task number and exit",
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
        help="Output JSON path (default: <workspace>/.tmp/tasks/phase-NN-validation.json)",
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

    if args.next_task_number:
        print(next_task_number(base_dir, args.phase))
        return EXIT_PASS

    try:
        payload = validate_phase(base_dir, args.phase)
    except ValueError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return EXIT_USAGE

    output_path = (
        args.output
        if args.output is not None
        else default_output_path(
            OUTPUT_CATEGORY, f"phase-{format_phase(args.phase)}-validation.json"
        )
    )
    write_json_output(payload, output_path)

    if payload["overall"] == OVERALL_PASS:
        print(
            "PASS (warnings: %s, info: see details)" % payload["warning_count"]
            if payload["warning_count"]
            else "PASS"
        )
    else:
        print(
            "FAIL (%s violations; warnings: %s)"
            % (payload["violation_count"], payload["warning_count"])
        )
    print(f"Details: {output_path.resolve()}")
    return EXIT_PASS if payload["overall"] == OVERALL_PASS else EXIT_FAIL


if __name__ == "__main__":
    sys.exit(main())
