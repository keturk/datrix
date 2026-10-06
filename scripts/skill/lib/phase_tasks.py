"""A phase's task files, parsed, with the files each one names resolved against the workspace."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from common import AssistError
from datrix_scripts.task_metadata import TaskMetadata, discover_phase_task_files, format_phase, parse_task_file

ELLIPSES = ("...", "…")


@dataclass(frozen=True)
class PhaseTask:
    """One task file of a phase: its parsed metadata, its path and its text."""

    meta: TaskMetadata
    path: Path
    text: str

    @property
    def task_id(self) -> str:
        return self.meta.task_id

    @property
    def package(self) -> str:
        return self.meta.package or self.meta.repo


def phase_tasks(workspace: Path, phase: int, *, pending_only: bool) -> list[PhaseTask]:
    """Every task of ``phase`` across the workspace's repos (only the unfinished ones when asked)."""
    paths = discover_phase_task_files(workspace, phase)
    if not paths:
        raise AssistError(
            f"No task files found for phase {format_phase(phase)} under {workspace} (looked in every repo's "
            f".tasks/phase-{format_phase(phase)}/). Pass the number of a phase that has task-*.md files.")
    tasks: list[PhaseTask] = []
    for path in paths:
        try:
            meta = parse_task_file(path)
        except (ValueError, OSError) as exc:
            raise AssistError(f"Cannot parse task file {path}: {exc}. Fix the file, then run again.") from exc
        if pending_only and meta.is_completed:
            continue
        tasks.append(PhaseTask(meta, path, path.read_text(encoding="utf-8")))
    return tasks


def named_path(workspace: Path, repo: str, token: str) -> Path | None:
    """The file a task names, made absolute: as given when absolute, else under the workspace when its
    first segment is a directory there (``datrix-common/src/...``), else under the task's own repo.

    An abbreviated token (one with an ellipsis) names no file and yields None.
    """
    if any(mark in token for mark in ELLIPSES):
        return None
    cleaned = token.strip().strip("`").replace("\\", "/")
    if not cleaned:
        return None
    candidate = Path(cleaned)
    if candidate.is_absolute():
        return candidate.resolve()
    first = cleaned.split("/", 1)[0]
    if (workspace / first).is_dir():
        return (workspace / cleaned).resolve()
    return (workspace / repo / cleaned).resolve()


def edit_sites(workspace: Path, task: PhaseTask) -> list[Path]:
    """The files a task creates or changes, absolute, each once."""
    found = (named_path(workspace, task.meta.repo, token) for token in task.meta.files_to_create_modify)
    return list(dict.fromkeys(path for path in found if path is not None))


def review_sites(workspace: Path, task: PhaseTask) -> list[Path]:
    """The files a task tells its implementer to read first, absolute, each once."""
    found = (named_path(workspace, task.meta.repo, token) for token in task.meta.files_to_review)
    return list(dict.fromkeys(path for path in found if path is not None))
