"""List or delete the empty folders at and below a path: the module behind ``scripts/workspace/empty-folders.ps1``.

A folder is empty when it holds no entry at all, hidden ones included. The walk starts at ``--path`` (default:
the current directory), which is listed too when empty, and goes down every visible folder; it never enters a
hidden folder (as PowerShell's ``Get-ChildItem`` without ``-Force``) or a symbolic link or junction, and never
lists or deletes one: a link can point anywhere. Only the folders empty at the time of the scan are listed, the
deepest first.

Without ``--force`` it lists them and changes nothing. ``--force`` asks "Are you sure? {yes/no}" and deletes
nothing without a typed yes (an end of input is no); it then removes each listed folder, deepest first, after
checking again that it is still empty (one that is not is skipped). A folder is removed with ``rmdir``, which
never removes content, and nothing outside ``--path`` is touched.

Exit codes: 0 = listed, deleted or cancelled; 1 = ``--path`` does not exist, is not a directory or is a link,
or a self-test check failed; 2 = a usage error.
"""

from __future__ import annotations

import argparse
import os
import sys
from collections.abc import Iterator, Sequence
from dataclasses import dataclass
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Final

from datrix_scripts.cleanup_utils import (
    AnswerReader,
    child_dirs,
    confirm_yes_no,
    is_link,
    plant_directory_link,
    read_answer_from_stdin,
    refuse_answer,
    scripted_answers,
)
from datrix_scripts.gate_harness import WRAPPER_DEBUG_FLAG, write_files
from datrix_scripts.logging_utils import ColorCodes, colorize
from datrix_scripts.test.wrappers import WORKSPACE_SCRIPTS_DIR, module_main, run_self_test

MODULE: Final = "datrix_scripts.workspace.empty_folders"
WRAPPER: Final = "empty-folders"

_RULE: Final = "=" * 40
_LIST_RULE: Final = "-" * 40
_EXIT_DONE: Final = 0
_EXIT_BAD_PATH: Final = 1


def is_empty(folder: Path) -> bool:
    """True when *folder* holds no entry at all (hidden ones included); False when it cannot be listed."""
    try:
        with os.scandir(folder) as entries:
            return next(entries, None) is None
    except OSError:
        return False


def _folders(root: Path) -> Iterator[Path]:
    """*root*, then every visible real folder below it, each level's folders before their own."""
    yield root
    for child in child_dirs(root, include_hidden=False):
        yield from _folders(child)


def empty_folders(root: Path) -> list[Path]:
    """The empty folders at and below *root*, deepest first (folders of one depth in walk order)."""
    found = [folder for folder in _folders(root) if is_empty(folder)]
    return sorted(found, key=lambda folder: len(folder.parts), reverse=True)


@dataclass
class _Tally:
    deleted: int = 0
    errors: int = 0


def _delete_one(folder: Path, tally: _Tally) -> None:
    if is_link(folder) or not is_empty(folder):
        print(colorize(f" Skipped (no longer empty): {folder}", ColorCodes.DARK_YELLOW))
        return
    try:
        folder.rmdir()
    except OSError as exc:
        print(colorize(f" Error deleting {folder}: {exc}", ColorCodes.RED))
        tally.errors += 1
        return
    print(colorize(f" Deleted: {folder}", ColorCodes.GREEN))
    tally.deleted += 1


def _delete(folders: Sequence[Path], read_answer: AnswerReader) -> None:
    print(colorize(_RULE, ColorCodes.YELLOW))
    print(colorize(f"WARNING: You are about to delete {len(folders)} empty folder(s)", ColorCodes.YELLOW))
    print(colorize(_RULE, ColorCodes.YELLOW))
    print()
    if not confirm_yes_no(read_answer):
        print()
        print(colorize("Deletion cancelled.", ColorCodes.YELLOW))
        return
    print()
    print(colorize("Deleting empty folders...", ColorCodes.YELLOW))
    tally = _Tally()
    for folder in folders:
        _delete_one(folder, tally)
    print()
    print(colorize(_RULE, ColorCodes.CYAN))
    if tally.errors == 0:
        print(colorize(f"Successfully deleted {tally.deleted} empty folder(s)", ColorCodes.GREEN))
    else:
        print(colorize(f"Deleted {tally.deleted} folder(s), {tally.errors} error(s)", ColorCodes.YELLOW))
    print(colorize(_RULE, ColorCodes.CYAN))


def _print_listing(folders: Sequence[Path]) -> None:
    print(colorize(f"Found {len(folders)} empty folder(s):", ColorCodes.CYAN))
    print()
    print(colorize("Empty folders (deepest first):", ColorCodes.YELLOW))
    print(colorize(_LIST_RULE, ColorCodes.YELLOW))
    for number, folder in enumerate(folders, start=1):
        print(f"{number}. {folder}")
    print(colorize(_LIST_RULE, ColorCodes.YELLOW))
    print()


def _print_usage_hint() -> None:
    print(colorize(_RULE, ColorCodes.CYAN))
    print(colorize("To delete these folders, run with -Force parameter", ColorCodes.CYAN))
    print()
    print(colorize("Usage:", ColorCodes.GRAY))
    print(colorize(" .\\scripts\\workspace\\empty-folders.ps1 -Force   # in the current directory", ColorCodes.GRAY))
    print(colorize(" .\\scripts\\workspace\\empty-folders.ps1 -Path <path> -Force   # in <path>", ColorCodes.GRAY))
    print(colorize(_RULE, ColorCodes.CYAN))


def _path_problem(root: Path) -> str | None:
    if not root.exists():
        return f"Error: Path '{root}' does not exist. Expected an existing directory; pass -Path <directory>."
    if is_link(root):
        return f"Error: Path '{root}' is a link. Expected the real directory it points to; pass that as -Path."
    if not root.is_dir():
        return f"Error: Path '{root}' is not a directory. Expected a directory; pass -Path <directory>."
    return None


def run(path: Path, *, force: bool, read_answer: AnswerReader = read_answer_from_stdin) -> int:
    """List the empty folders at and below *path*; with *force*, confirm and delete them. Returns the exit code."""
    print(colorize(_RULE, ColorCodes.CYAN))
    print(colorize("Empty Folders Cleanup", ColorCodes.CYAN))
    print(colorize(_RULE, ColorCodes.CYAN))
    print()
    root = Path(os.path.abspath(path))
    problem = _path_problem(root)
    if problem is not None:
        print(colorize(problem, ColorCodes.RED), file=sys.stderr)
        return _EXIT_BAD_PATH
    print(colorize(f"Searching for empty folders in: {root}", ColorCodes.CYAN))
    print()
    print(colorize("Scanning for empty folders...", ColorCodes.YELLOW))
    folders = empty_folders(root)
    if not folders:
        print(colorize("No empty folders found.", ColorCodes.GREEN))
        print()
        return _EXIT_DONE
    _print_listing(folders)
    if force:
        _delete(folders, read_answer)
    else:
        _print_usage_hint()
    print()
    return _EXIT_DONE


def build_parser() -> argparse.ArgumentParser:
    """The options of ``empty-folders.ps1``: its parameters as ``--kebab-name`` flags."""
    parser = argparse.ArgumentParser(
        prog=WRAPPER,
        description="List the empty folders at and below a path; with --force delete them after a yes/no "
                    "confirmation.",
        allow_abbrev=False,
    )
    parser.add_argument("--path", type=Path, default=Path.cwd(), help="the folder to search (default: the current directory)")
    parser.add_argument("--force", action="store_true", help="delete the listed folders after confirmation")
    parser.add_argument(WRAPPER_DEBUG_FLAG, dest="debug", action="store_true", help="debug logging")
    parser.add_argument("--self-test", action="store_true", help="run the self-test and exit")
    return parser


# ---------------------------------------------------------------------------
# Self-test: planted trees in a temporary directory.
# ---------------------------------------------------------------------------

_KEEP: Final = "keep.txt"


def _plant(root: Path) -> Path:
    write_files(root, {f"full/{_KEEP}": "x\n", f"hidden-content/.{_KEEP}": "x\n"})
    for folder in ("a/b/c", "a/d", "e"):
        (root / folder).mkdir(parents=True)
    return root


def _relative(root: Path, folders: Sequence[Path]) -> list[str]:
    return [folder.relative_to(root).as_posix() for folder in folders]


def _tree(root: Path) -> list[str]:
    return sorted(path.relative_to(root).as_posix() for path in root.rglob("*"))


def _check_lists_currently_empty_folders_deepest_first() -> None:
    with TemporaryDirectory() as raw:
        root = _plant(Path(raw))
        found = _relative(root, empty_folders(root))
    assert found == ["a/b/c", "a/d", "e"], found


def _check_an_empty_root_is_listed() -> None:
    with TemporaryDirectory() as raw:
        assert empty_folders(Path(raw)) == [Path(raw)]


def _check_listing_and_refusals_delete_nothing() -> None:
    for force, reader in ((False, refuse_answer), (True, scripted_answers()), (True, scripted_answers("maybe", "no"))):
        with TemporaryDirectory() as raw:
            root = _plant(Path(raw))
            before = _tree(root)
            assert run(root, force=force, read_answer=reader) == _EXIT_DONE
            after = _tree(root)
        assert before == after, f"force={force} without a typed yes changed the tree"


def _check_force_deletes_and_skips_a_refilled_folder() -> None:
    with TemporaryDirectory() as raw:
        root = _plant(Path(raw))

        def refill_then_yes() -> str:
            write_files(root, {f"e/{_KEEP}": "arrived after the scan\n"})
            return "yes"

        assert run(root, force=True, read_answer=refill_then_yes) == _EXIT_DONE
        remaining = _tree(root)
    expected = sorted(["a", "a/b", "e", f"e/{_KEEP}", "full", f"full/{_KEEP}", "hidden-content", f"hidden-content/.{_KEEP}"])
    assert remaining == expected, f"left {remaining}, expected {expected}"


def _check_links_are_never_listed_or_entered() -> None:
    with TemporaryDirectory() as raw:
        base, outside = Path(raw) / "base", Path(raw) / "outside"
        (outside / "empty-target").mkdir(parents=True)
        (outside / "holder" / "empty-inside").mkdir(parents=True)
        write_files(base, {f"real/{_KEEP}": "x\n"})
        plant_directory_link(base / "to-empty", outside / "empty-target")
        plant_directory_link(base / "to-holder", outside / "holder")
        assert empty_folders(base) == [], f"found through a link: {empty_folders(base)}"
        assert run(base / "to-holder", force=True, read_answer=refuse_answer) == _EXIT_BAD_PATH
        after = _tree(outside)
    assert after == ["empty-target", "holder", "holder/empty-inside"], f"outside changed: {after}"


def _check_bad_paths_are_refused() -> None:
    with TemporaryDirectory() as raw:
        file_path = write_files(Path(raw), {"f.txt": "x\n"})[0]
        assert run(Path(raw) / "absent", force=True, read_answer=refuse_answer) == _EXIT_BAD_PATH
        assert run(file_path, force=True, read_answer=refuse_answer) == _EXIT_BAD_PATH


_SELF_TEST_CHECKS: Final = (
    _check_lists_currently_empty_folders_deepest_first,
    _check_an_empty_root_is_listed,
    _check_listing_and_refusals_delete_nothing,
    _check_force_deletes_and_skips_a_refilled_folder,
    _check_links_are_never_listed_or_entered,
    _check_bad_paths_are_refused,
)


def main(argv: Sequence[str] | None = None) -> int:
    """Run the self-test, or list / delete the empty folders under ``--path``."""
    parser = build_parser()

    def dispatch(args: argparse.Namespace) -> int:
        if args.self_test:
            return run_self_test(
                _SELF_TEST_CHECKS, wrapper=WRAPPER, module=MODULE, parser=parser, folder=WORKSPACE_SCRIPTS_DIR
            )
        return run(args.path, force=args.force)

    return module_main(parser, dispatch, argv)


if __name__ == "__main__":
    sys.exit(main())
