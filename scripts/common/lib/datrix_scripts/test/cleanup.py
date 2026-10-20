"""List, delete or trim the ``.test_results`` folders of a workspace: the module behind ``scripts/test/cleanup.ps1``.

Where the folders are found, under ``--base-dir`` (default: the workspace root):

- ``datrix*/.test_results``: each framework package's own run folder;
- ``.generated``: a pruned walk. At the ``.generated`` root a direct ``.test_results`` is taken and every
  other subdirectory is still walked; deeper, a directory with a direct ``.test_results`` is a generated
  project, so that folder is taken and nothing else below the project is walked (``src/``, ``build/``, ...).
  When both ``project/.test_results`` and ``project/sub/.test_results`` exist, only the first is found;
- ``.projects``: every ``.test_results`` at any depth.

Without ``--force`` it lists each folder and its tree and changes nothing. ``--force`` deletes every folder,
then removes the parents the deletion left empty, never at or above ``--base-dir``; ``--force --trim`` keeps
the ``TRIM_KEEP_COUNT`` newest top-level items (by modification time) in each folder and deletes the rest.
Either asks "Are you sure? {yes/no}" first and deletes nothing without a typed yes: an end of input is no.
Below the folders it searches (``--base-dir`` itself, ``.generated``, ``.projects``) no walk follows a symbolic
link or junction, and none is taken as a ``.test_results`` folder: a link found there can point anywhere, so
nothing it leads to is listed, trimmed or deleted.

Exit codes: 0 = listed, deleted, trimmed or cancelled; 1 = ``--base-dir`` is not a directory, or a self-test
check failed; 2 = usage error.
"""

from __future__ import annotations

import argparse
import logging
import os
import stat
import sys
import warnings
from collections.abc import Iterator, Sequence
from dataclasses import dataclass
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Final

from datrix_scripts.cleanup_utils import (
    AnswerReader,
    child_dirs,
    children,
    confirm_yes_no,
    is_link,
    plant_directory_link,
    read_answer_from_stdin,
    refuse_answer,
    remove_empty_parent_folders,
    remove_tree,
    scripted_answers,
    tree_lines,
)
from datrix_scripts.gate_harness import configure_logging, write_files
from datrix_scripts.logging_utils import ColorCodes, colorize
from datrix_scripts.paths import WORKSPACE_DIR
from datrix_scripts.test.wrappers import ensure_utf8_stdio, run_self_test

logger = logging.getLogger(__name__)

MODULE: Final = "datrix_scripts.test.cleanup"
WRAPPER: Final = "cleanup"

TEST_RESULTS_DIR: Final = ".test_results"
GENERATED_DIR: Final = ".generated"
DOT_PROJECTS_DIR: Final = ".projects"
PACKAGE_DIR_PREFIX: Final = "datrix"
TRIM_KEEP_COUNT: Final = 10

_RULE: Final = "=" * 40
# A Python before cleanup_utils.ONEXC_PYTHON, for the self-test of the older rmtree error hook.
PRE_ONEXC_PYTHON: Final = (3, 11)
_EXIT_DONE: Final = 0
_EXIT_NO_BASE_DIR: Final = 1


@dataclass(frozen=True)
class TestResultsFolder:
    """One ``.test_results`` folder and the group it is listed under (``datrix-cli``, ``.generated\\python\\...``)."""

    parent: str
    path: Path


@dataclass(frozen=True)
class RemovalOutcome:
    """What deleting or trimming one folder did."""

    full_folder_removed: bool
    removed_something: bool


def _package_folders(base_dir: Path) -> list[TestResultsFolder]:
    packages = [
        entry for entry in child_dirs(base_dir, include_hidden=False)
        if entry.name.casefold().startswith(PACKAGE_DIR_PREFIX)
    ]
    return [
        TestResultsFolder(package.name, package / TEST_RESULTS_DIR)
        for package in packages
        if (package / TEST_RESULTS_DIR).exists() and not is_link(package / TEST_RESULTS_DIR)
    ]


def _generated_paths(directory: Path, *, is_root: bool) -> Iterator[Path]:
    subdirs = child_dirs(directory, include_hidden=False)
    if is_root:
        for child in subdirs:
            if child.name == TEST_RESULTS_DIR:
                yield child
            else:
                yield from _generated_paths(child, is_root=False)
        return
    direct = next((child for child in subdirs if child.name == TEST_RESULTS_DIR), None)
    if direct is not None:
        yield direct
        return
    for child in subdirs:
        yield from _generated_paths(child, is_root=False)


def _group_name(root_name: str, root: Path, test_results: Path) -> str:
    relative = test_results.parent.relative_to(root)
    return root_name if relative == Path() else str(Path(root_name) / relative)


def _generated_folders(base_dir: Path) -> list[TestResultsFolder]:
    root = base_dir / GENERATED_DIR
    if not root.is_dir():
        return []
    return [
        TestResultsFolder(_group_name(GENERATED_DIR, root, path), path)
        for path in _generated_paths(root, is_root=True)
    ]


def _all_dirs(directory: Path) -> Iterator[Path]:
    """Every directory below *directory*, hidden ones included: each level's entries, then each one's own."""
    subdirs = child_dirs(directory, include_hidden=True)
    yield from subdirs
    for child in subdirs:
        yield from _all_dirs(child)


def _dot_projects_folders(base_dir: Path) -> list[TestResultsFolder]:
    root = base_dir / DOT_PROJECTS_DIR
    if not root.is_dir():
        return []
    return [
        TestResultsFolder(_group_name(DOT_PROJECTS_DIR, root, path), path)
        for path in _all_dirs(root)
        if path.name == TEST_RESULTS_DIR
    ]


def discover(base_dir: Path) -> list[TestResultsFolder]:
    """Every ``.test_results`` folder under *base_dir*: packages, then ``.generated``, then ``.projects``."""
    return [*_package_folders(base_dir), *_generated_folders(base_dir), *_dot_projects_folders(base_dir)]


def _grouped(folders: Sequence[TestResultsFolder]) -> dict[str, list[TestResultsFolder]]:
    groups: dict[str, list[TestResultsFolder]] = {}
    for folder in folders:
        groups.setdefault(folder.parent, []).append(folder)
    return groups


def _print_listing(folders: Sequence[TestResultsFolder]) -> None:
    for parent, members in _grouped(folders).items():
        print(colorize(f"=== {parent} ===", ColorCodes.CYAN))
        for folder in members:
            print(f" {TEST_RESULTS_DIR}")
            print(colorize(f" {folder.path}", ColorCodes.GRAY))
            lines = tree_lines(folder.path)
            for line in lines or [" (empty)"]:
                print(colorize(line, ColorCodes.GRAY))
        print()


def remove_content(path: Path, *, trim: bool, keep_count: int = TRIM_KEEP_COUNT) -> RemovalOutcome:
    """Delete *path*, or with *trim* only its top-level items past the *keep_count* newest; ``OSError`` on failure."""
    if not path.exists():
        return RemovalOutcome(full_folder_removed=False, removed_something=False)
    if not trim:
        remove_tree(path)
        return RemovalOutcome(full_folder_removed=True, removed_something=True)
    items = children(path, include_hidden=False)
    if len(items) <= keep_count:
        return RemovalOutcome(full_folder_removed=False, removed_something=False)
    newest_first = sorted(items, key=lambda item: item.stat().st_mtime, reverse=True)
    for item in newest_first[keep_count:]:
        if item.is_dir():
            remove_tree(item)
        else:
            item.unlink()
    return RemovalOutcome(full_folder_removed=False, removed_something=True)


def _print_warning(count: int, trim: bool) -> None:
    print(colorize(_RULE, ColorCodes.YELLOW))
    if trim:
        print(colorize(
            f"WARNING: You are about to delete older test results under {count} {TEST_RESULTS_DIR} folder(s).",
            ColorCodes.YELLOW,
        ))
        print(colorize(
            f"The {TRIM_KEEP_COUNT} newest top-level item(s) in each folder will be kept (by LastWriteTime).",
            ColorCodes.YELLOW,
        ))
    else:
        print(colorize(f"WARNING: You are about to delete ALL {count} {TEST_RESULTS_DIR} folder(s)", ColorCodes.YELLOW))
    print(colorize(_RULE, ColorCodes.YELLOW))
    print()


@dataclass
class _Tally:
    deleted: int = 0
    trimmed: int = 0
    errors: int = 0


def _remove_one(folder: TestResultsFolder, *, trim: bool, base_dir: Path, tally: _Tally) -> None:
    try:
        outcome = remove_content(folder.path, trim=trim)
    except OSError as exc:
        print(colorize(f" Error at {folder.path}: {exc}", ColorCodes.RED))
        tally.errors += 1
        return
    if outcome.full_folder_removed:
        print(colorize(f" Deleted: {folder.path}", ColorCodes.GREEN))
        tally.deleted += 1
        remove_empty_parent_folders(folder.path, base_dir)
    elif outcome.removed_something:
        print(colorize(f" Trimmed: {folder.path} (kept {TRIM_KEEP_COUNT} newest)", ColorCodes.GREEN))
        tally.trimmed += 1
    elif trim:
        print(colorize(
            f" Skipped: {folder.path} (at most {TRIM_KEEP_COUNT} item(s), nothing to remove)", ColorCodes.GRAY
        ))
    else:
        print(colorize(f" Skipped: {folder.path} (empty or missing)", ColorCodes.GRAY))


def _summary(tally: _Tally, total: int, trim: bool) -> str:
    if tally.errors == 0 and trim:
        return (
            f"Finished: removed older results in {tally.trimmed} folder(s); {total - tally.trimmed} folder(s) "
            f"had at most {TRIM_KEEP_COUNT} top-level item(s) already."
        )
    if tally.errors == 0:
        return f"Successfully deleted {tally.deleted} folder(s)."
    if trim:
        return f"Done with {tally.errors} error(s) (trimmed in {tally.trimmed} folder(s))."
    return f"Deleted {tally.deleted} folder(s), {tally.errors} error(s)"


def _delete(folders: Sequence[TestResultsFolder], *, trim: bool, base_dir: Path, read_answer: AnswerReader) -> None:
    _print_warning(len(folders), trim)
    if not confirm_yes_no(read_answer):
        print()
        print(colorize("Deletion cancelled.", ColorCodes.YELLOW))
        return
    print()
    action = "Trimming" if trim else "Deleting"
    print(colorize(f"{action} {TEST_RESULTS_DIR} folders...", ColorCodes.YELLOW))
    tally = _Tally()
    for folder in folders:
        _remove_one(folder, trim=trim, base_dir=base_dir, tally=tally)
    print()
    print(colorize(_RULE, ColorCodes.CYAN))
    print(colorize(_summary(tally, len(folders), trim), ColorCodes.GREEN if tally.errors == 0 else ColorCodes.YELLOW))
    print(colorize(_RULE, ColorCodes.CYAN))


def _print_usage_hint() -> None:
    print(colorize(_RULE, ColorCodes.CYAN))
    print(colorize("To delete these folders, run with -Force parameter", ColorCodes.CYAN))
    print()
    print(colorize("Usage:", ColorCodes.GRAY))
    print(colorize(" .\\scripts\\test\\cleanup.ps1 -Force", ColorCodes.GRAY))
    print(colorize(
        f" .\\scripts\\test\\cleanup.ps1 -Force -Trim   # keep {TRIM_KEEP_COUNT} newest per {TEST_RESULTS_DIR}",
        ColorCodes.GRAY,
    ))
    print(colorize(_RULE, ColorCodes.CYAN))


def run(base_dir: Path, *, force: bool, trim: bool, read_answer: AnswerReader = read_answer_from_stdin) -> int:
    """List the folders under *base_dir*; with *force*, confirm and delete (or trim) them. Returns the exit code."""
    base = Path(os.path.abspath(base_dir))
    if not base.is_dir():
        print(
            f"Error: base directory not found: {base}. Expected an existing directory holding the datrix* "
            "packages, .generated or .projects; pass -BaseDir <workspace root> or omit it for this workspace.",
            file=sys.stderr,
        )
        return _EXIT_NO_BASE_DIR
    print(colorize(_RULE, ColorCodes.CYAN))
    print(colorize("Test Results Cleanup", ColorCodes.CYAN))
    print(colorize(_RULE, ColorCodes.CYAN))
    print()
    folders = discover(base)
    if not folders:
        print(colorize(f"No {TEST_RESULTS_DIR} folders found.", ColorCodes.GREEN))
        print()
        return _EXIT_DONE
    print(colorize(f"Found {len(folders)} {TEST_RESULTS_DIR} folder(s).", ColorCodes.CYAN))
    print()
    _print_listing(folders)
    if trim and not force:
        print(colorize(
            f"Note: -Trim only applies with -Force. Re-run with -Force -Trim to remove older results "
            f"(keeps {TRIM_KEEP_COUNT} newest per folder).",
            ColorCodes.YELLOW,
        ))
        print()
    if force:
        _delete(folders, trim=trim, base_dir=base, read_answer=read_answer)
    else:
        _print_usage_hint()
    print()
    return _EXIT_DONE


def build_parser() -> argparse.ArgumentParser:
    """The options of ``cleanup.ps1``: its parameters as ``--kebab-name`` flags."""
    parser = argparse.ArgumentParser(
        prog=WRAPPER,
        description="List the .test_results folders of a workspace; with --force delete them, or trim each to "
                    f"its {TRIM_KEEP_COUNT} newest items with --force --trim, after a yes/no confirmation.",
        allow_abbrev=False,
    )
    parser.add_argument("--base-dir", type=Path, default=WORKSPACE_DIR,
                        help="the directory holding the datrix* packages, .generated and .projects "
                             "(default: this workspace's root)")
    parser.add_argument("--force", action="store_true", help="delete (or with --trim, trim) after confirmation")
    parser.add_argument("--trim", action="store_true",
                        help=f"with --force, keep the {TRIM_KEEP_COUNT} newest top-level items in each folder")
    parser.add_argument("--dbg", action="store_true", help="debug logging")
    parser.add_argument("--self-test", action="store_true", help="run the self-test and exit")
    return parser


# ---------------------------------------------------------------------------
# Self-test: a planted workspace in a temporary directory.
# ---------------------------------------------------------------------------

_PLANTED: Final = {
    "datrix-a/.test_results/run-old/full.log": "old\n",
    "datrix-b/.test_results/run1/full.log": "b\n",
    "datrix-c/src/main.py": "\n",
    ".generated/.test_results/root.log": "root\n",
    ".generated/python/docker/shop/.test_results/run1/full.log": "shop\n",
    ".generated/python/docker/shop/src/.test_results/hidden.log": "below a project: not walked\n",
    ".generated/typescript/docker/local/catalog/.test_results/run2/index.json": "{}\n",
    ".projects/.test_results/top.txt": "top\n",
    ".projects/foo/bar/.test_results/run.txt": "run\n",
    "other/.test_results/ignored.txt": "not a datrix* package\n",
}


def _sep(text: str) -> str:
    return text.replace("/", os.sep)


def _planted(root: Path) -> Path:
    write_files(root, _PLANTED)
    return root


def _end_of_input() -> str:
    raise EOFError


def _check_discovery_finds_each_kind_once() -> None:
    with TemporaryDirectory() as raw:
        found = [(folder.parent, folder.path.relative_to(raw)) for folder in discover(_planted(Path(raw)))]
    expected = [
        ("datrix-a", Path("datrix-a/.test_results")),
        ("datrix-b", Path("datrix-b/.test_results")),
        (".generated", Path(".generated/.test_results")),
        (_sep(".generated/python/docker/shop"), Path(".generated/python/docker/shop/.test_results")),
        (_sep(".generated/typescript/docker/local/catalog"),
         Path(".generated/typescript/docker/local/catalog/.test_results")),
        (".projects", Path(".projects/.test_results")),
        (_sep(".projects/foo/bar"), Path(".projects/foo/bar/.test_results")),
    ]
    assert found == expected, f"found {found}, expected {expected}"


def _check_tree_lines_indent_by_depth() -> None:
    with TemporaryDirectory() as raw:
        root = Path(raw)
        write_files(root, {"run1/full.log": "x\n", "run1/failures/001.txt": "x\n", "a.txt": "x\n"})
        lines = tree_lines(root)
    assert lines == [" [FILE] a.txt", " [DIR] run1", "  [DIR] failures", "   [FILE] 001.txt", "  [FILE] full.log"], lines


def _check_listing_deletes_nothing() -> None:
    with TemporaryDirectory() as raw:
        root = _planted(Path(raw))
        before = sorted(path.relative_to(root) for path in root.rglob("*"))
        assert run(root, force=False, trim=True, read_answer=refuse_answer) == _EXIT_DONE
        after = sorted(path.relative_to(root) for path in root.rglob("*"))
    assert before == after, "a run without --force changed the tree"


def _check_end_of_input_and_no_delete_nothing() -> None:
    for reader in (_end_of_input, scripted_answers("maybe", "no")):
        with TemporaryDirectory() as raw:
            root = _planted(Path(raw))
            before = sorted(path.relative_to(root) for path in root.rglob("*"))
            assert run(root, force=True, trim=False, read_answer=reader) == _EXIT_DONE
            after = sorted(path.relative_to(root) for path in root.rglob("*"))
        assert before == after, "an unconfirmed --force deleted something"


def _check_force_deletes_and_prunes_only_below_base() -> None:
    with TemporaryDirectory() as raw:
        root = _planted(Path(raw))
        read_only = root / "datrix-b/.test_results/run1/full.log"
        read_only.chmod(stat.S_IREAD)
        assert run(root, force=True, trim=False, read_answer=scripted_answers("maybe", "YES")) == _EXIT_DONE
        remaining = sorted(str(path.relative_to(root)).replace(os.sep, "/") for path in root.rglob("*"))
        base_kept = root.is_dir()
    # datrix-a, datrix-b, .projects and the typescript branch held only what was deleted, so they go too; the
    # shop project keeps the src/ folder the walk never entered, and nothing outside the found folders is touched.
    expected = sorted([
        ".generated", ".generated/python", ".generated/python/docker", ".generated/python/docker/shop",
        ".generated/python/docker/shop/src", ".generated/python/docker/shop/src/.test_results",
        ".generated/python/docker/shop/src/.test_results/hidden.log",
        "datrix-c", "datrix-c/src", "datrix-c/src/main.py",
        "other", "other/.test_results", "other/.test_results/ignored.txt",
    ])
    assert base_kept, "the base directory itself was removed"
    assert remaining == expected, f"left {remaining}, expected {expected}"


def _check_trim_keeps_the_newest() -> None:
    total = TRIM_KEEP_COUNT + 2
    with TemporaryDirectory() as raw:
        root = Path(raw)
        results = root / "datrix-a" / TEST_RESULTS_DIR
        write_files(results, {f"run-{index:02d}/full.log": "x\n" for index in range(1, total + 1)})
        for index in range(1, total + 1):
            mtime = 1_700_000_000 + index * 60
            os.utime(results / f"run-{index:02d}", (mtime, mtime))
        write_files(root, {"datrix-b/.test_results/only/full.log": "x\n"})
        assert run(root, force=True, trim=True, read_answer=scripted_answers("yes")) == _EXIT_DONE
        kept = sorted(entry.name for entry in results.iterdir())
        other_kept = (root / "datrix-b/.test_results/only/full.log").is_file()
    assert kept == [f"run-{index:02d}" for index in range(3, total + 1)], kept
    assert other_kept, "a folder with at most the keep count was trimmed"


def _check_missing_base_dir_is_refused() -> None:
    with TemporaryDirectory() as raw:
        assert run(Path(raw) / "absent", force=True, trim=False, read_answer=refuse_answer) == _EXIT_NO_BASE_DIR


def _tree(root: Path) -> list[Path]:
    return sorted(path.relative_to(root) for path in root.rglob("*"))


def _check_links_are_never_followed() -> None:
    with TemporaryDirectory() as raw:
        base, outside = Path(raw) / "base", Path(raw) / "outside"
        write_files(outside, {"project/.test_results/run1/full.log": "keep\n", "results/run1/full.log": "keep\n"})
        write_files(base, {"datrix-a/src/main.py": "\n", ".generated/python/docker/real/.test_results/a.log": "x\n"})
        (base / DOT_PROJECTS_DIR).mkdir()
        plant_directory_link(base / DOT_PROJECTS_DIR / "linked", outside)
        plant_directory_link(base / GENERATED_DIR / "python" / "docker" / "linked", outside / "project")
        plant_directory_link(base / "datrix-a" / TEST_RESULTS_DIR, outside / "results")
        found = [folder.path.relative_to(base) for folder in discover(base)]
        assert found == [Path(".generated/python/docker/real/.test_results")], f"found {found} through a link"
        listed = tree_lines(base / DOT_PROJECTS_DIR)
        assert listed == [" [LINK] linked"], f"the listing entered a link: {listed}"
        before = _tree(outside)
        assert run(base, force=True, trim=False, read_answer=scripted_answers("yes")) == _EXIT_DONE
        after = _tree(outside)
        try:
            remove_tree(base / "datrix-a" / TEST_RESULTS_DIR)
        except OSError:
            refused = True
        else:
            refused = False
        target_kept = (outside / "results/run1/full.log").is_file()
    assert before == after, f"a --force run reached through a link: {before} became {after}"
    assert refused and target_kept, "remove_tree followed a link instead of refusing it"


def _check_pre_312_hook_removes_read_only_files() -> None:
    with TemporaryDirectory() as raw:
        tree = Path(raw) / "results"
        write_files(tree, {"run1/full.log": "x\n"})
        (tree / "run1/full.log").chmod(stat.S_IREAD)
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", DeprecationWarning)
            remove_tree(tree, python=PRE_ONEXC_PYTHON)
        removed = not tree.exists()
    assert removed, "the onerror hook of the Pythons before 3.12 left a read-only file behind"


_SELF_TEST_CHECKS: Final = (
    _check_discovery_finds_each_kind_once,
    _check_tree_lines_indent_by_depth,
    _check_listing_deletes_nothing,
    _check_end_of_input_and_no_delete_nothing,
    _check_force_deletes_and_prunes_only_below_base,
    _check_trim_keeps_the_newest,
    _check_missing_base_dir_is_refused,
    _check_links_are_never_followed,
    _check_pre_312_hook_removes_read_only_files,
)


def main(argv: Sequence[str] | None = None) -> int:
    """Run the self-test, or list / delete / trim the ``.test_results`` folders under ``--base-dir``."""
    ensure_utf8_stdio()
    parser = build_parser()
    args = parser.parse_args(argv)
    configure_logging(args.dbg)
    if args.self_test:
        return run_self_test(_SELF_TEST_CHECKS, wrapper=WRAPPER, module=MODULE, parser=parser)
    return run(args.base_dir, force=args.force, trim=args.trim)


if __name__ == "__main__":
    sys.exit(main())
