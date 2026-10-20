"""Phase status report: parse every task file of a phase across all repos.

The module behind ``scripts/tasks/phase-status.ps1`` (and its ``.sh`` twin). Discovers
``<base>/*/.tasks/phase-{NN}/task-*.md`` (repos = ``datrix*`` folders, including the ``datrix``
showcase repo), parses per-task metadata via task_metadata.py, merges the phase-level dependencies.md
(JSON preferred, legacy ``Group N`` fallback), and writes one JSON status document consumed by the
task-orchestration skills.

Console output is minimal (summary + Details line); everything else goes to
the JSON file. Task files are DATA — this script never modifies them.

Exit codes: 0 = written; 1 = a self-test check failed; 2 = usage error (no phase, no such base
directory, or no task file in the phase).

Usage:
  python -m datrix_scripts.tasks.phase_status --phase 31 [--base-dir D:/datrix] [--output out.json]
  .\\scripts\\tasks\\phase-status.ps1 31
"""

from __future__ import annotations

import argparse
import contextlib
import io
import logging
import sys
import tempfile
from collections.abc import Sequence
from datetime import datetime
from pathlib import Path
from typing import Final

from datrix_scripts.gate_harness import UsageError, expect_usage_error
from datrix_scripts.task_metadata import (
    DEPENDENCIES_FORMAT_LEGACY,
    DependenciesDoc,
    TaskMetadata,
    dependencies_md_path,
    discover_phase_task_files,
    find_task_file,
    format_phase,
    parse_dependencies_md,
    parse_task_file,
    task_id_phase,
    write_json_output,
)
from datrix_scripts.tasks.phase_cli import (
    FIRST_PHASE,
    add_workspace_options,
    chosen_base_dir,
    output_path,
    plant_phases,
    required_phase,
)
from datrix_scripts.test.wrappers import TASKS_SCRIPTS_DIR, module_main, run_self_test

logger = logging.getLogger(__name__)

MODULE: Final = "datrix_scripts.tasks.phase_status"
WRAPPER: Final = "phase-status"

SCHEMA_VERSION = 1

EXIT_DONE = 0

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


def build_parser() -> argparse.ArgumentParser:
    """The options of ``tasks/phase-status.ps1``: one per wrapper parameter, spelled exactly."""
    parser = argparse.ArgumentParser(
        description="Report per-task status for a phase across all repos", allow_abbrev=False
    )
    parser.add_argument("--phase", type=int, default=None, help="Phase number (e.g. 31); required")
    add_workspace_options(parser, output_name="phase-NN-status.json",
                          self_test_help="Run only the self-test over a planted phase.")
    return parser


def report(base: Path, phase: int, output: Path) -> int:
    """Write the status of *phase* under *base* to *output* and print its summary; the exit code."""
    try:
        payload = build_phase_status(base, phase)
    except ValueError as exc:
        raise UsageError(str(exc)) from exc
    write_json_output(payload, output)

    mismatches = payload["dep_mismatches"]
    repos = payload["repos"]
    mismatch_count = len(mismatches) if isinstance(mismatches, list) else 0
    repo_count = len(repos) if isinstance(repos, list) else 0
    print(
        f"Phase {format_phase(phase)}: {payload['task_count']} tasks "
        f"({payload['completed_count']} completed, {payload['pending_count']} pending) "
        f"in {repo_count} repos; mismatches: {mismatch_count}"
    )
    print(f"Details: {output.resolve()}")
    return EXIT_DONE


def _check_a_planted_phase_is_reported() -> None:
    with tempfile.TemporaryDirectory() as raw:
        root = plant_phases(Path(raw))
        payload = build_phase_status(root, FIRST_PHASE)
        printed = io.StringIO()
        with contextlib.redirect_stdout(printed):
            exit_code = report(root, FIRST_PHASE, root / "status.json")
        written = (root / "status.json").is_file()
    counts = (payload["task_count"], payload["completed_count"], payload["pending_count"])
    assert counts == (3, 1, 2), f"expected 3 tasks, 1 completed, 2 pending; got {counts}"
    assert payload["repos"] == ["datrix-alpha", "datrix-beta"], payload["repos"]
    assert payload["dep_mismatches"] == [], payload["dep_mismatches"]
    assert exit_code == EXIT_DONE and written, "the status document was not written"
    assert "3 tasks (1 completed, 2 pending) in 2 repos; mismatches: 0" in printed.getvalue(), printed.getvalue()


def _check_a_missing_phase_or_base_dir_is_a_usage_error() -> None:
    with tempfile.TemporaryDirectory() as raw:
        root = plant_phases(Path(raw))
        expect_usage_error(lambda: report(root, 99, root / "status.json"), "No task files found for phase 99")
        absent = build_parser().parse_args(["--phase=1", f"--base-dir={root / 'absent'}"])
        expect_usage_error(lambda: chosen_base_dir(absent), "Base directory does not exist")
    expect_usage_error(lambda: required_phase(build_parser().parse_args([]), WRAPPER), "-Phase is required")


def _run(args: argparse.Namespace) -> int:
    if args.self_test:
        checks = [_check_a_planted_phase_is_reported, _check_a_missing_phase_or_base_dir_is_a_usage_error]
        return run_self_test(checks, wrapper=WRAPPER, module=MODULE, parser=build_parser(), folder=TASKS_SCRIPTS_DIR)
    phase = required_phase(args, WRAPPER)
    return report(chosen_base_dir(args), phase, output_path(args, f"phase-{format_phase(phase)}-status.json"))


def main(argv: Sequence[str] | None = None) -> int:
    """Entry point."""
    return module_main(build_parser(), _run, argv)


if __name__ == "__main__":
    sys.exit(main())
