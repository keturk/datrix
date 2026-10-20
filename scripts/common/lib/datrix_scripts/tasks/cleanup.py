"""List the task artifacts of the workspace's ``.tasks`` folders; with ``--force``, delete them after a yes/no
confirmation and remove the folders they leave empty.

``scripts/tasks/cleanup.ps1`` (and its ``.sh`` twin) runs this module. It reads ``<base>/.tasks`` (listed as
``(root)``) and the ``.tasks`` folder of every ``datrix`` and ``datrix-*`` repository. A task artifact is a file
at any depth of those folders named ``task-*`` (task Markdown, review JSON, debug attempts, backups) or
``dependencies.md``; its phase is the number of the first ``phase-<number>`` in its path below ``.tasks``. With
``--phase N`` only the artifacts of phases before N are listed and deleted (``--phase 60`` deletes phases 1..59).

Nothing is deleted without ``--force`` and a typed ``yes``: an end of input answers no. Deleting removes the
artifacts, then every folder of each ``.tasks`` tree left empty, the ``.tasks`` folder included; nothing at or
above the base directory is removed, and no symbolic link or junction is entered.

Exit codes: 0 = listed, deleted or cancelled; 1 = the base directory does not exist, or a self-test check
failed; 2 = a usage error.

Usage:
  python -m datrix_scripts.tasks.cleanup [--base-dir D:/datrix] [--force] [--phase 60] [--dbg]
  .\\scripts\\tasks\\cleanup.ps1 [-BaseDir <path>] [-Force] [-Phase <number>] [-Dbg]
"""

from __future__ import annotations

import argparse
import re
import stat
import sys
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Final

from datrix_scripts.cleanup_utils import (
    confirm_yes_no,
    plant_directory_link,
    read_answer_from_stdin,
    remove_empty_folders,
    remove_file,
    tree_lines,
)
from datrix_scripts.gate_harness import WRAPPER_DEBUG_FLAG, write_files
from datrix_scripts.logging_utils import ColorCodes, colorize
from datrix_scripts.tasks.task_listing import (
    DEPENDENCIES_FILE,
    EXIT_LISTED,
    RULE,
    TASKS_FOLDER,
    files_named,
    missing_base_dir_check,
    planted_folder,
    planted_name,
    projects,
    run_on_base,
)
from datrix_scripts.test.wrappers import TASKS_SCRIPTS_DIR, module_main, run_self_test

MODULE: Final = "datrix_scripts.tasks.cleanup"
WRAPPER: Final = "cleanup"

ARTIFACT_PATTERNS: Final = ("task-*", DEPENDENCIES_FILE)
NO_PHASE_LIMIT: Final = 0
_PHASE_IN_PATH: Final = re.compile(r"phase-(\d+)", re.IGNORECASE)
_LIST_RULE: Final = "-" * 40

AnswerReader = Callable[[], str]


@dataclass(frozen=True)
class TasksFolder:
    """An existing ``.tasks`` folder and the repository it is listed under (``(root)`` for the base directory)."""

    project: str
    path: Path


@dataclass(frozen=True)
class Artifact:
    """A task artifact, the ``.tasks`` folder it was found in, and its phase (None outside a phase folder)."""

    folder: TasksFolder
    path: Path
    phase: int | None


@dataclass
class _Tally:
    deleted: int = 0
    errors: int = 0


def tasks_folders(base: Path) -> list[TasksFolder]:
    """The ``.tasks`` folders of *base* and of its repositories that exist."""
    return [TasksFolder(project, folder / TASKS_FOLDER) for project, folder in projects(base)
            if (folder / TASKS_FOLDER).is_dir()]


def _phase_of(path: Path, folder: TasksFolder) -> int | None:
    match = _PHASE_IN_PATH.search(str(path.relative_to(folder.path)))
    return int(match.group(1)) if match else None


def artifacts(folders: Sequence[TasksFolder], phase_limit: int) -> list[Artifact]:
    """Every task artifact of *folders*, in the order found; with a positive *phase_limit*, only those of the
    phases before it."""
    found = [Artifact(folder, path, _phase_of(path, folder))
             for folder in folders for path in files_named(folder.path, ARTIFACT_PATTERNS)]
    if phase_limit <= NO_PHASE_LIMIT:
        return found
    return [artifact for artifact in found if artifact.phase is not None and artifact.phase < phase_limit]


def _print_folder(folder: TasksFolder) -> None:
    print(colorize(f"=== {folder.project} ===", ColorCodes.CYAN))
    print(f" {TASKS_FOLDER}")
    print(colorize(f" {folder.path}", ColorCodes.GRAY))
    print(colorize("\n".join(tree_lines(folder.path)) or " (empty)", ColorCodes.GRAY))
    print()


def _phase_note(phase_limit: int) -> str:
    return f"Only task artifacts in phases < {phase_limit} will be deleted."


def _print_listing(found: Sequence[Artifact], folders: Sequence[TasksFolder], phase_limit: int) -> None:
    if not found:
        print(colorize("No task artifacts found in .tasks folders.", ColorCodes.GREEN))
        print()
        if folders:
            print(colorize(f"Found {len(folders)} .tasks folder(s) (may contain empty subfolders):", ColorCodes.CYAN))
            print()
        for folder in folders:
            _print_folder(folder)
        return
    print(colorize(f"Found {len(found)} task artifact(s):", ColorCodes.CYAN))
    if phase_limit > NO_PHASE_LIMIT:
        print(colorize(_phase_note(phase_limit), ColorCodes.CYAN))
    print()
    print(colorize("Full list of task artifacts:", ColorCodes.YELLOW))
    print(colorize(_LIST_RULE, ColorCodes.YELLOW))
    for number, artifact in enumerate(found, start=1):
        print(f"{number}. [{artifact.folder.project}] {artifact.path}")
    print(colorize(_LIST_RULE, ColorCodes.YELLOW))
    print()
    for folder in dict.fromkeys(artifact.folder for artifact in found):
        _print_folder(folder)


def _print_warning(file_count: int, folder_count: int, phase_limit: int) -> None:
    print(colorize(RULE, ColorCodes.YELLOW))
    if phase_limit > NO_PHASE_LIMIT:
        print(colorize(_phase_note(phase_limit), ColorCodes.YELLOW))
    if file_count:
        print(colorize(f"WARNING: You are about to delete {file_count} task artifact(s)", ColorCodes.YELLOW))
    if folder_count:
        lead = "and" if file_count else "WARNING: You are about to"
        print(colorize(f"{lead} clean up empty folders in {folder_count} .tasks folder(s)", ColorCodes.YELLOW))
    print(colorize(RULE, ColorCodes.YELLOW))
    print()


def _delete_artifacts(found: Sequence[Artifact]) -> _Tally:
    tally = _Tally()
    print(colorize("Deleting task artifacts...", ColorCodes.YELLOW))
    for artifact in found:
        try:
            remove_file(artifact.path)
        except OSError as exc:
            print(colorize(f" Error deleting {artifact.path}: {exc}", ColorCodes.RED))
            tally.errors += 1
            continue
        print(colorize(f" Deleted: {artifact.path}", ColorCodes.GREEN))
        tally.deleted += 1
    return tally


def _print_summary(found: Sequence[Artifact], folders: Sequence[TasksFolder], tally: _Tally) -> None:
    print()
    print(colorize(RULE, ColorCodes.CYAN))
    if found and tally.errors == 0:
        print(colorize(f"Successfully deleted {tally.deleted} artifact(s)", ColorCodes.GREEN))
    elif found:
        print(colorize(f"Deleted {tally.deleted} artifact(s), {tally.errors} error(s)", ColorCodes.YELLOW))
    if folders:
        print(colorize("Cleaned up empty folders in .tasks directories", ColorCodes.GREEN))
    print(colorize(RULE, ColorCodes.CYAN))


def _delete(found: Sequence[Artifact], folders: Sequence[TasksFolder], *, base: Path, phase_limit: int,
            read_answer: AnswerReader) -> None:
    _print_warning(len(found), len(folders), phase_limit)
    if not confirm_yes_no(read_answer):
        print()
        print(colorize("Deletion cancelled.", ColorCodes.YELLOW))
        return
    print()
    tally = _delete_artifacts(found) if found else _Tally()
    if folders:
        print()
        print(colorize("Cleaning up empty folders...", ColorCodes.YELLOW))
    for folder in folders:
        remove_empty_folders(folder.path, base)
    _print_summary(found, folders, tally)


def _print_usage_hint() -> None:
    print(colorize(RULE, ColorCodes.CYAN))
    print(colorize("To delete files and clean up empty folders, run with -Force parameter", ColorCodes.CYAN))
    print(colorize("Example: .\\scripts\\tasks\\cleanup.ps1 -Force", ColorCodes.GRAY))
    print(colorize("Example: .\\scripts\\tasks\\cleanup.ps1 -Force -Phase 60  (delete only phases before 60)",
                   ColorCodes.GRAY))
    print(colorize(RULE, ColorCodes.CYAN))


def run(base: Path, *, force: bool, phase_limit: int, read_answer: AnswerReader = read_answer_from_stdin) -> int:
    """List the task artifacts under *base*; with *force*, confirm, delete them and remove the folders they
    leave empty. Returns the exit code."""
    print(colorize(RULE, ColorCodes.CYAN))
    print(colorize("Task Artifacts Cleanup", ColorCodes.CYAN))
    print(colorize(RULE, ColorCodes.CYAN))
    print()
    folders = tasks_folders(base)
    found = artifacts(folders, phase_limit)
    _print_listing(found, folders, phase_limit)
    if force:
        _delete(found, folders, base=base, phase_limit=phase_limit, read_answer=read_answer)
    else:
        _print_usage_hint()
    print()
    return EXIT_LISTED


# ---------------------------------------------------------------------------
# Self-test: a planted workspace in a temporary directory.
# ---------------------------------------------------------------------------

_ROOT_PHASE: Final = 3
_EARLY_PHASE: Final = 5
_LATE_PHASE: Final = 7
_PHASE_LIMIT: Final = 6


def _planted_artifacts() -> list[tuple[str, int | None]]:
    """The artifacts the self-test plants, in the order a scan finds them, each with its phase."""
    early = planted_folder("datrix-alpha", _EARLY_PHASE)
    late = planted_folder("datrix-alpha", _LATE_PHASE)
    return [
        (f"{planted_folder('', _ROOT_PHASE)}/{planted_name(_ROOT_PHASE, 1, 'root')}", _ROOT_PHASE),
        (f"{early}/{DEPENDENCIES_FILE}", _EARLY_PHASE),
        (f"{early}/{planted_name(_EARLY_PHASE, 1, 'early')}", _EARLY_PHASE),
        (f"{early}/review/task-review.json", _EARLY_PHASE),
        (f"{late}/{planted_name(_LATE_PHASE, 1, 'late')}", _LATE_PHASE),
        (f"datrix-beta/{TASKS_FOLDER}/task-loose.md", None),
    ]


def _planted_others() -> list[str]:
    """The planted files that are not artifacts of a listed ``.tasks`` folder."""
    return [
        f"{planted_folder('datrix-alpha', _EARLY_PHASE)}/notes.md",
        f"{planted_folder('other', _ROOT_PHASE)}/{planted_name(_ROOT_PHASE, 2, 'outside')}",
    ]


def _plant(root: Path) -> Path:
    write_files(root, {name: "x\n" for name in [path for path, _ in _planted_artifacts()] + _planted_others()})
    return root


def _relative(path: Path, root: Path) -> str:
    return path.relative_to(root).as_posix()


def _files(root: Path) -> list[str]:
    return sorted(_relative(path, root) for path in root.rglob("*") if path.is_file())


def _replies(*answers: str) -> AnswerReader:
    pending = iter(answers)

    def read() -> str:
        try:
            return next(pending)
        except StopIteration as exc:
            raise EOFError from exc

    return read


def _check_artifacts_are_found_by_name_and_phase() -> None:
    with TemporaryDirectory() as raw:
        root = _plant(Path(raw))
        every = [(_relative(item.path, root), item.phase) for item in artifacts(tasks_folders(root), NO_PHASE_LIMIT)]
        early = [(_relative(item.path, root), item.phase) for item in artifacts(tasks_folders(root), _PHASE_LIMIT)]
    planted = _planted_artifacts()
    assert every == planted, every
    assert early == [(path, phase) for path, phase in planted if phase is not None and phase < _PHASE_LIMIT], early


def _check_nothing_is_deleted_without_a_typed_yes() -> None:
    runs = ((False, _replies("yes")), (True, _replies()), (True, _replies("maybe", "no")))
    for force, reader in runs:
        with TemporaryDirectory() as raw:
            root = _plant(Path(raw))
            before = _files(root)
            assert run(root, force=force, phase_limit=NO_PHASE_LIMIT, read_answer=reader) == EXIT_LISTED
            after = _files(root)
        assert before == after, f"force={force} changed the tree: {before} became {after}"


def _check_force_deletes_the_earlier_phases_and_their_empty_folders() -> None:
    with TemporaryDirectory() as raw:
        root = _plant(Path(raw))
        (root / _planted_artifacts()[2][0]).chmod(stat.S_IREAD)
        assert run(root, force=True, phase_limit=_PHASE_LIMIT, read_answer=_replies("maybe", "YES")) == EXIT_LISTED
        remaining = _files(root)
        root_tasks_gone = not (root / TASKS_FOLDER).exists()
        review_gone = not (root / planted_folder("datrix-alpha", _EARLY_PHASE) / "review").exists()
        base_kept = root.is_dir()
    kept = sorted([path for path, phase in _planted_artifacts() if phase is None or phase >= _PHASE_LIMIT]
                  + _planted_others())
    assert remaining == kept, f"left {remaining}, expected {kept}"
    assert root_tasks_gone and review_gone and base_kept, (root_tasks_gone, review_gone, base_kept)


def _check_links_are_never_followed() -> None:
    with TemporaryDirectory() as raw:
        base, outside = Path(raw) / "base", Path(raw) / "outside"
        write_files(outside, {"task-outside.md": "keep\n"})
        (outside / "empty").mkdir()
        write_files(base, {f"datrix-alpha/{TASKS_FOLDER}/task-inside.md": "x\n"})
        plant_directory_link(base / "datrix-alpha" / TASKS_FOLDER / "linked", outside)
        before = sorted(_relative(path, outside) for path in outside.rglob("*"))
        assert run(base, force=True, phase_limit=NO_PHASE_LIMIT, read_answer=_replies("yes")) == EXIT_LISTED
        after = sorted(_relative(path, outside) for path in outside.rglob("*"))
        inside_gone = not (base / "datrix-alpha" / TASKS_FOLDER / "task-inside.md").exists()
    assert before == after, f"a --force run reached through a link: {before} became {after}"
    assert inside_gone, "the artifact beside the link was not deleted"


def build_parser() -> argparse.ArgumentParser:
    """The options of ``tasks/cleanup.ps1``: one per wrapper parameter, spelled exactly."""
    parser = argparse.ArgumentParser(
        description="List the task artifacts of the workspace's .tasks folders; with --force delete them, and the "
                    "folders they leave empty, after a yes/no confirmation.",
        allow_abbrev=False,
    )
    parser.add_argument("--base-dir", default=None,
                        help="Workspace root holding .tasks and the datrix* repos (default: this workspace)")
    parser.add_argument("--force", action="store_true", help="Delete the listed artifacts after confirmation")
    parser.add_argument("--phase", type=int, default=NO_PHASE_LIMIT,
                        help="Only the artifacts of phases before this number (default: every phase)")
    parser.add_argument(WRAPPER_DEBUG_FLAG, dest="debug", action="store_true", help="Debug logging")
    parser.add_argument("--self-test", action="store_true", help="Run only the self-test over a planted workspace.")
    return parser


def _run(args: argparse.Namespace) -> int:
    if args.self_test:
        checks = [_check_artifacts_are_found_by_name_and_phase, _check_nothing_is_deleted_without_a_typed_yes,
                  _check_force_deletes_the_earlier_phases_and_their_empty_folders, _check_links_are_never_followed,
                  missing_base_dir_check(main)]
        return run_self_test(checks, wrapper=WRAPPER, module=MODULE, parser=build_parser(), folder=TASKS_SCRIPTS_DIR)
    return run_on_base(args, lambda base: run(base, force=args.force, phase_limit=args.phase))


def main(argv: Sequence[str] | None = None) -> int:
    """Entry point."""
    return module_main(build_parser(), _run, argv)


if __name__ == "__main__":
    sys.exit(main())
