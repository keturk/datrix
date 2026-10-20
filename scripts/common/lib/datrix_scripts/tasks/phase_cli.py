"""What the phase tools share: their workspace options, the phase they are asked about, and a planted phase.

``phase-status``, ``plan-waves``, ``plan-waves-multi`` and ``validate-dependencies`` each read the task
files of one or more phases under ``-BaseDir`` (default: this workspace) and write a JSON document to
``-Output`` (default: ``<workspace>/.tmp/tasks/<name>``). A missing phase or base directory is a usage
error (exit 2), printed as ``ERROR: ...``.

``plant_phases`` writes the workspace their self-tests read: two phases across three repositories
(``datrix`` holding the phase-level ``dependencies.md``, ``datrix-alpha``, ``datrix-beta``). The first
phase is consistent: an open task, a completed task that depends on it, and a quality gate over both,
listed in a JSON ``dependencies.md``. The second phase has one open task that depends on the quality
gate of the first and no ``dependencies.md``.
"""

from __future__ import annotations

import argparse
import contextlib
import io
import json
import tempfile
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Final

from datrix_scripts.gate_harness import WRAPPER_DEBUG_FLAG, UsageError, write_files
from datrix_scripts.paths import WORKSPACE_DIR
from datrix_scripts.task_metadata import default_output_path, dependencies_md_path, format_phase
from datrix_scripts.tasks.complete import COMPLETED_PREFIX

OUTPUT_CATEGORY: Final = "tasks"

FIRST_PHASE: Final = 1
SECOND_PHASE: Final = 2
_SHOWCASE: Final = "datrix"
_ALPHA: Final = "datrix-alpha"
_BETA: Final = "datrix-beta"
_IMPLEMENTATION: Final = "Implementation"
_QUALITY_GATE: Final = "Quality Gate"
_ABSENT_PHASE: Final = 99
# What validate-task and retrofit-orientation print (exit 2) when neither a task file nor a phase holding one is given.
NO_TASK_FILES: Final = "Error: no task files. Pass task file paths, or --phase <NN>."


def add_workspace_options(parser: argparse.ArgumentParser, *, output_name: str, self_test_help: str) -> None:
    """``--base-dir``, ``--output``, ``--dbg`` and ``--self-test``, as the phase tools' wrappers declare them."""
    parser.add_argument("--base-dir", default=None,
                        help="Workspace root containing the datrix* repos (default: this workspace)")
    parser.add_argument("--output", type=Path, default=None,
                        help=f"Output JSON path (default: <workspace>/.tmp/{OUTPUT_CATEGORY}/{output_name})")
    parser.add_argument(WRAPPER_DEBUG_FLAG, dest="debug", action="store_true", help="Enable debug logging")
    parser.add_argument("--self-test", action="store_true", help=self_test_help)


def chosen_base_dir(args: argparse.Namespace) -> Path:
    """``--base-dir``, or this workspace when it is not given; a usage error when it is not a directory."""
    chosen = Path(args.base_dir) if args.base_dir else WORKSPACE_DIR
    if not chosen.is_dir():
        raise UsageError(f"Base directory does not exist: {chosen}")
    return chosen


def required_phase(args: argparse.Namespace, wrapper: str) -> int:
    """``--phase``; a usage error naming the wrapper's parameter when it is not given."""
    if args.phase is None:
        raise UsageError(f"-Phase is required: pass the phase number, e.g. {wrapper}.ps1 31.")
    phase: int = args.phase
    return phase


def output_path(args: argparse.Namespace, file_name: str) -> Path:
    """``--output``, or ``<workspace>/.tmp/tasks/<file_name>``."""
    chosen: Path = args.output if args.output is not None else default_output_path(OUTPUT_CATEGORY, file_name)
    return chosen


def no_task_file_check(main: Callable[[Sequence[str] | None], int], usage_exit: int) -> Callable[[], None]:
    """The self-test check that a task-file tool's ``main`` refuses a run naming no task file, with
    *usage_exit* and ``NO_TASK_FILES``: none given, and a phase no repository holds."""

    def _check_no_task_file_is_a_usage_error() -> None:
        with tempfile.TemporaryDirectory() as raw:
            refused = io.StringIO()
            with contextlib.redirect_stderr(refused):
                exit_code = main([f"--base-dir={raw}"])
                phase_code = main([f"--phase={_ABSENT_PHASE}", f"--base-dir={raw}"])
        assert exit_code == usage_exit and phase_code == usage_exit, (exit_code, phase_code)
        assert NO_TASK_FILES in refused.getvalue(), refused.getvalue()

    return _check_no_task_file_is_a_usage_error


def planted_task_id(phase: int, number: int) -> str:
    """The id of task *number* of *phase*."""
    return f"task-{format_phase(phase)}-{number:02d}"


@dataclass(frozen=True)
class _PlantedTask:
    repo: str
    phase: int
    number: int
    slug: str
    title: str
    depends_on: tuple[str, ...]
    category: str
    completed: bool
    edits: str

    def relative_path(self) -> str:
        return f"{self.repo}/.tasks/phase-{format_phase(self.phase)}/{planted_task_id(self.phase, self.number)}-{self.slug}.md"

    def text(self) -> str:
        status = COMPLETED_PREFIX if self.completed else ""
        depends = ", ".join(self.depends_on) if self.depends_on else "none"
        return (f"# {status}Task {format_phase(self.phase)}-{self.number:02d}: {self.title}\n\n"
                f"**Package:** `{self.repo}`\n**Depends on:** {depends}\n**Category:** {self.category}\n\n"
                f"## Files to Create/Modify\n\n- `{self.edits}`\n")


_PLANTED_TASKS: Final = (
    _PlantedTask(_ALPHA, FIRST_PHASE, 1, "base", "Base class", (), _IMPLEMENTATION, False,
                 "datrix-alpha/src/alpha/base.py"),
    _PlantedTask(_ALPHA, FIRST_PHASE, 2, "loader", "Loader", (planted_task_id(FIRST_PHASE, 1),), _IMPLEMENTATION, True,
                 "datrix-alpha/src/alpha/loader.py"),
    _PlantedTask(_BETA, FIRST_PHASE, 3, "gate", "Quality gate", (planted_task_id(FIRST_PHASE, 1), planted_task_id(FIRST_PHASE, 2)),
                 _QUALITY_GATE, False, "datrix-beta/src/beta/gate.py"),
    _PlantedTask(_BETA, SECOND_PHASE, 1, "next", "Next step", (planted_task_id(FIRST_PHASE, 3),), _IMPLEMENTATION, False,
                 "datrix-beta/src/beta/next.py"),
)


def _dependencies_doc(root: Path, phase: int) -> str:
    entries = [
        {
            "task_id": planted_task_id(task.phase, task.number),
            "task_path": str(root / task.relative_path()),
            "title": task.title,
            "is_completed": task.completed,
            "package": task.repo,
            "dependencies": list(task.depends_on),
            "category": task.category,
        }
        for task in _PLANTED_TASKS
        if task.phase == phase
    ]
    return json.dumps({"phase": phase, "tasks": entries}, indent=2) + "\n"


def plant_phases(root: Path) -> Path:
    """Write the planted phases (see the module docstring) under *root*; returns *root*."""
    for repo in (_SHOWCASE, _ALPHA, _BETA):
        (root / repo).mkdir(parents=True, exist_ok=True)
    write_files(root, {task.relative_path(): task.text() for task in _PLANTED_TASKS})
    doc = dependencies_md_path(root, FIRST_PHASE)
    write_files(doc.parent, {doc.name: _dependencies_doc(root, FIRST_PHASE)})
    return root
