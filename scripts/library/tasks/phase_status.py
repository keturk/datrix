#!/usr/bin/env python3
"""Phase status report: parse every task file of a phase across all repos.

Discovers ``<base>/*/.tasks/phase-{NN}/task-*.md`` (repos = ``datrix*``
folders, including the ``datrix`` showcase repo), parses per-task metadata via
task_metadata.py, merges the phase-level dependencies.md (JSON preferred,
legacy ``Group N`` fallback), and writes one JSON status document consumed by
the task-orchestration skills.

Console output is minimal (summary + Details line); everything else goes to
the JSON file. Task files are DATA — this script never modifies them.

Usage:
  python scripts/library/tasks/phase_status.py 31
  python scripts/library/tasks/phase_status.py 31 --base-dir D:/datrix --output out.json
  .\\scripts\\tasks\\phase-status.ps1 31
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
    DEPENDENCIES_FORMAT_LEGACY,
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
    task_id_phase,
    write_json_output,
)

logger = logging.getLogger(__name__)

SCHEMA_VERSION = 1
OUTPUT_CATEGORY = "tasks"

EXIT_DONE = 0
EXIT_USAGE = 2

DEPENDENCIES_ABSENT = "absent"
DEPENDENCIES_INVALID = "invalid"


def _dep_mismatches_json(
    doc: DependenciesDoc, tasks_by_id: dict[str, TaskMetadata]
) -> list[dict[str, object]]:
    """Per-task mismatch between the JSON doc's dependencies and the file's."""
    mismatches: list[dict[str, object]] = []
    for entry in doc.entries:
        task = tasks_by_id.get(entry.task_id)
        if task is None or entry.dependencies is None:
            continue
        doc_deps = sorted(entry.dependencies)
        file_deps = sorted(task.depends_on)
        if doc_deps != file_deps:
            mismatches.append(
                {
                    "task_id": entry.task_id,
                    "file_says": file_deps,
                    "dependencies_md_says": doc_deps,
                }
            )
    return mismatches


def _dep_mismatches_legacy(
    doc: DependenciesDoc, tasks_by_id: dict[str, TaskMetadata]
) -> list[dict[str, object]]:
    """Legacy 'Group N' docs encode dependencies as group ordering.

    A task-file dependency pointing at a task in the same or a later group
    contradicts the document (group K may only depend on groups < K).
    """
    group_of = {entry.task_id: entry.group for entry in doc.entries}
    mismatches: list[dict[str, object]] = []
    for entry in doc.entries:
        task = tasks_by_id.get(entry.task_id)
        if task is None or entry.group is None:
            continue
        for dep in task.depends_on:
            dep_group = group_of.get(dep)
            if dep_group is None or dep_group < entry.group:
                continue
            mismatches.append(
                {
                    "task_id": entry.task_id,
                    "file_says": f"depends on {dep}",
                    "dependencies_md_says": (
                        f"task is in group {entry.group} but dependency {dep} is in "
                        f"group {dep_group} (a group may only depend on earlier groups)"
                    ),
                }
            )
    return mismatches


def _missing_dependency_files(
    base_dir: Path, phase: int, tasks: list[TaskMetadata], known_ids: set[str]
) -> list[str]:
    """Dependency IDs referenced by task files that have no file on disk."""
    missing: list[str] = []
    for task in tasks:
        for dep in task.depends_on:
            if dep in known_ids or dep in missing:
                continue
            if task_id_phase(dep) == phase:
                missing.append(dep)
            elif find_task_file(base_dir, dep) is None:
                missing.append(dep)
    return sorted(missing)


def _merge_dependencies_md(
    base_dir: Path, phase: int, tasks_by_id: dict[str, TaskMetadata]
) -> dict[str, object]:
    """Read the phase dependencies.md and compare it against the task files."""
    doc_path = dependencies_md_path(base_dir, phase)
    result: dict[str, object] = {
        "dependencies_md": DEPENDENCIES_ABSENT,
        "dependencies_md_path": str(doc_path),
        "provenance": None,
        "dep_mismatches": [],
        "dependencies_md_unlisted_tasks": [],
        "dependencies_md_nonexistent_tasks": [],
    }
    if not doc_path.is_file():
        return result
    try:
        doc = parse_dependencies_md(doc_path)
    except ValueError as exc:
        result["dependencies_md"] = DEPENDENCIES_INVALID
        result["dependencies_md_error"] = str(exc)
        return result

    result["dependencies_md"] = doc.doc_format
    result["provenance"] = doc.provenance
    listed_ids = {entry.task_id for entry in doc.entries}
    result["dependencies_md_unlisted_tasks"] = sorted(
        task_id for task_id in tasks_by_id if task_id not in listed_ids
    )
    result["dependencies_md_nonexistent_tasks"] = sorted(
        task_id for task_id in listed_ids if task_id not in tasks_by_id
    )
    if doc.doc_format == DEPENDENCIES_FORMAT_LEGACY:
        result["dep_mismatches"] = _dep_mismatches_legacy(doc, tasks_by_id)
    else:
        result["dep_mismatches"] = _dep_mismatches_json(doc, tasks_by_id)
    return result


def build_phase_status(base_dir: Path, phase: int) -> dict[str, object]:
    """Assemble the full phase-status payload. Raises ValueError on bad input."""
    task_files = discover_phase_task_files(base_dir, phase)
    if not task_files:
        raise ValueError(
            f"No task files found for phase {format_phase(phase)} under {base_dir} "
            f"(searched */.tasks/phase-{format_phase(phase)}/task-*.md in every "
            "datrix* repo). Check the phase number (list phases with "
            "'ls <repo>/.tasks') or pass -BaseDir for a different workspace."
        )
    tasks = [parse_task_file(path) for path in task_files]
    tasks.sort(key=lambda task: (task.task_id, task.task_path))
    tasks_by_id: dict[str, TaskMetadata] = {}
    for task in tasks:
        tasks_by_id.setdefault(task.task_id, task)

    completed = sum(1 for task in tasks if task.is_completed)
    repos = sorted({task.repo for task in tasks})
    merged = _merge_dependencies_md(base_dir, phase, tasks_by_id)
    payload: dict[str, object] = {
        "schema_version": SCHEMA_VERSION,
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "phase": phase,
        "base_dir": str(base_dir),
        "task_count": len(tasks),
        "completed_count": completed,
        "pending_count": len(tasks) - completed,
        "repos": repos,
    }
    payload.update(merged)
    payload["missing_dependency_files"] = _missing_dependency_files(
        base_dir, phase, tasks, set(tasks_by_id)
    )
    payload["tasks"] = [task.to_dict() for task in tasks]
    return payload


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Report per-task status for a phase across all repos"
    )
    parser.add_argument("phase", type=int, help="Phase number (e.g. 31)")
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
        help="Output JSON path (default: <workspace>/.tmp/tasks/phase-NN-status.json)",
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
        payload = build_phase_status(base_dir, args.phase)
    except ValueError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return EXIT_USAGE

    output_path = (
        args.output
        if args.output is not None
        else default_output_path(
            OUTPUT_CATEGORY, f"phase-{format_phase(args.phase)}-status.json"
        )
    )
    write_json_output(payload, output_path)

    mismatches = payload["dep_mismatches"]
    repos = payload["repos"]
    mismatch_count = len(mismatches) if isinstance(mismatches, list) else 0
    repo_count = len(repos) if isinstance(repos, list) else 0
    print(
        f"Phase {format_phase(args.phase)}: {payload['task_count']} tasks "
        f"({payload['completed_count']} completed, {payload['pending_count']} pending) "
        f"in {repo_count} repos; mismatches: {mismatch_count}"
    )
    print(f"Details: {output_path.resolve()}")
    return EXIT_DONE


if __name__ == "__main__":
    sys.exit(main())
