"""List or delete the temporary cache folders and files of a Datrix workspace: the module behind
``scripts/workspace/cleanup-temps.ps1``.

What is found, under ``--base-dir`` (default: the workspace root):

- at the base itself, only its direct entries: each cache folder name (``CACHE_FOLDERS`` plus
  ``--additional-folders``), each cache file name (``CACHE_FILES``) and each file matching a cache pattern
  (``CACHE_FILE_PATTERNS``);
- below every ``datrix*`` directory of the base, at any depth: each folder with a cache folder name (taken
  whole, not walked further) and each file with a cache file name or pattern. The walk does not enter
  ``SKIP_DIRS`` (``.git``, venvs, ``node_modules``, ``.generated``) or the ``PRESERVED_FOLDERS``
  (``.test_results``, ``.tasks``), and a preserved name is never taken, even when passed as an additional
  folder.

No walk enters a symbolic link or junction, and none is taken: a link can point anywhere, so nothing it leads
to is listed or deleted. An additional folder must be one plain name (no path separator, not ``.`` or ``..``):
it is joined onto the base, so a path would reach outside it; such a value is refused as a usage error.

Without ``--force`` it lists each item with its size and changes nothing. ``--force`` asks
"Are you sure? {yes/no}" and deletes nothing without a typed yes (an end of input is no); it then deletes each
item and removes the parents a deleted folder left empty, never at or above ``--base-dir``.

Exit codes: 0 = listed, deleted or cancelled; 1 = ``--base-dir`` is not a directory, or a self-test check
failed; 2 = a usage error.
"""

from __future__ import annotations

import argparse
import fnmatch
import os
import stat
import sys
from collections.abc import Iterator, Sequence
from dataclasses import dataclass
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Final

from datrix_scripts.cleanup_utils import (
    AnswerReader,
    children,
    confirm_yes_no,
    format_cleanup_size,
    is_link,
    plant_directory_link,
    read_answer_from_stdin,
    refuse_answer,
    remove_empty_parent_folders,
    remove_file,
    remove_tree,
    scripted_answers,
)
from datrix_scripts.dev.arguments import comma_values
from datrix_scripts.gate_harness import WRAPPER_DEBUG_FLAG, UsageError, write_files
from datrix_scripts.logging_utils import ColorCodes, colorize
from datrix_scripts.paths import WORKSPACE_DIR
from datrix_scripts.test.wrappers import WORKSPACE_SCRIPTS_DIR, module_main, run_self_test

MODULE: Final = "datrix_scripts.workspace.cleanup_temps"
WRAPPER: Final = "cleanup-temps"

CACHE_FOLDERS: Final = (
    ".hypothesis", ".ruff_cache", ".ruff_check", ".mypy_cache", ".pytest_cache", "htmlcov", ".benchmarks",
    "__pycache__", ".tox", ".nox", ".cache", ".pyre", ".pytype", "cython_debug",
)
CACHE_FILES: Final = (".coverage", "coverage.xml", ".dmypy.json", "dmypy.json")
CACHE_FILE_PATTERNS: Final = (".coverage.*",)
PRESERVED_FOLDERS: Final = frozenset({".test_results", ".tasks"})
SKIP_DIRS: Final = frozenset({".git", ".venv", "venv", "env", "node_modules", ".generated"})
PROJECT_PREFIX: Final = "datrix"

_RULE: Final = "=" * 40
_UNSAFE_NAMES: Final = frozenset({"", ".", ".."})
_SEPARATORS: Final = ("/", "\\")
_EXIT_DONE: Final = 0
_EXIT_NO_BASE_DIR: Final = 1


@dataclass(frozen=True)
class CacheItem:
    """One cache folder or file and the group it is listed under (the base's name or a project's)."""

    parent: str
    path: Path
    size: int
    is_directory: bool


def checked_folder_names(values: Sequence[str]) -> list[str]:
    """The additional folder names, comma lists split; ``UsageError`` for a value that is not one plain name."""
    names = comma_values(values)
    unsafe = [name for name in names if name in _UNSAFE_NAMES or any(sep in name for sep in _SEPARATORS)]
    if unsafe:
        raise UsageError(
            f"-AdditionalFolders takes folder names, not paths: {', '.join(repr(name) for name in unsafe)}. "
            "Expected one plain name each (e.g. .coverage_html or .scratch_cache); a path or '..' would reach "
            "outside -BaseDir."
        )
    return names


def _tree_size(path: Path) -> int:
    """The bytes of every file below *path*; links are neither entered nor counted."""
    total = 0
    for entry in children(path, include_hidden=True):
        if is_link(entry):
            continue
        total += _tree_size(entry) if entry.is_dir() else entry.lstat().st_size
    return total


def _item(parent: str, path: Path) -> CacheItem:
    is_directory = path.is_dir()
    return CacheItem(parent, path, _tree_size(path) if is_directory else path.lstat().st_size, is_directory)


def _is_cache_file(name: str) -> bool:
    return name in CACHE_FILES or any(fnmatch.fnmatchcase(name, pattern) for pattern in CACHE_FILE_PATTERNS)


def _root_items(base: Path, folders: Sequence[str]) -> list[CacheItem]:
    """The cache folders and files directly in *base*: folder names, then file names, then pattern matches."""
    named = [base / name for name in (*folders, *CACHE_FILES) if name not in PRESERVED_FOLDERS]
    patterned = [
        entry for entry in children(base, include_hidden=True)
        if entry.is_file() and not is_link(entry) and entry.name not in CACHE_FILES and _is_cache_file(entry.name)
    ]
    return [_item(base.name, path) for path in [*named, *patterned] if path.exists() and not is_link(path)]


def _real_dirs(directory: Path) -> list[Path]:
    return [entry for entry in children(directory, include_hidden=True) if entry.is_dir() and not is_link(entry)]


def _cache_folders_under(directory: Path, folders: frozenset[str]) -> Iterator[Path]:
    for child in _real_dirs(directory):
        if child.name in PRESERVED_FOLDERS or child.name in SKIP_DIRS:
            continue
        if child.name in folders:
            yield child
        else:
            yield from _cache_folders_under(child, folders)


def _cache_files_under(directory: Path, folders: frozenset[str]) -> Iterator[Path]:
    """Cache files below *directory*: each subfolder first, then this level's files; a skipped, preserved or
    cache-named folder (taken whole) is not walked."""
    for child in _real_dirs(directory):
        if child.name not in SKIP_DIRS | PRESERVED_FOLDERS | folders:
            yield from _cache_files_under(child, folders)
    for entry in children(directory, include_hidden=True):
        if entry.is_file() and not is_link(entry) and _is_cache_file(entry.name):
            yield entry


def _projects(base: Path) -> list[Path]:
    return [
        entry for entry in children(base, include_hidden=False)
        if entry.is_dir() and not is_link(entry) and entry.name.casefold().startswith(PROJECT_PREFIX)
    ]


def discover(base: Path, additional_folders: Sequence[str] = ()) -> list[CacheItem]:
    """Every cache item under *base*: the base's own, then each ``datrix*`` project's folders and files."""
    folders = (*CACHE_FOLDERS, *(name for name in additional_folders if name not in CACHE_FOLDERS))
    folder_set = frozenset(folders)
    items = _root_items(base, folders)
    for project in _projects(base):
        items.extend(_item(project.name, path) for path in _cache_folders_under(project, folder_set))
        items.extend(_item(project.name, path) for path in _cache_files_under(project, folder_set))
    return items


def _print_listing(items: Sequence[CacheItem]) -> None:
    groups: dict[str, list[CacheItem]] = {}
    for item in items:
        groups.setdefault(item.parent, []).append(item)
    for parent, members in groups.items():
        print(colorize(f"=== {parent} ===", ColorCodes.CYAN))
        for item in members:
            print(f" {item.path.name} ({format_cleanup_size(item.size)})")
            print(colorize(f" {item.path}", ColorCodes.GRAY))
        print()


@dataclass
class _Tally:
    deleted: int = 0
    deleted_size: int = 0
    errors: int = 0


def _delete_one(item: CacheItem, base: Path, tally: _Tally) -> None:
    if item.path == base or not item.path.is_relative_to(base) or is_link(item.path):
        print(colorize(f" Refused (not strictly inside {base}, or a link): {item.path}", ColorCodes.RED))
        tally.errors += 1
        return
    try:
        if item.is_directory:
            remove_tree(item.path)
            remove_empty_parent_folders(item.path, base)
        else:
            remove_file(item.path)
    except OSError as exc:
        print(colorize(f" Error deleting {item.path}: {exc}", ColorCodes.RED))
        tally.errors += 1
        return
    print(colorize(f" Deleted: {item.path}", ColorCodes.GREEN))
    tally.deleted += 1
    tally.deleted_size += item.size


def _delete(items: Sequence[CacheItem], base: Path, total: int, read_answer: AnswerReader) -> None:
    print(colorize(_RULE, ColorCodes.YELLOW))
    print(colorize(f"WARNING: You are about to delete ALL {len(items)} cache item(s)", ColorCodes.YELLOW))
    print(colorize(f" Total size: {format_cleanup_size(total)}", ColorCodes.YELLOW))
    print(colorize(_RULE, ColorCodes.YELLOW))
    print()
    if not confirm_yes_no(read_answer):
        print()
        print(colorize("Deletion cancelled.", ColorCodes.YELLOW))
        return
    print()
    print(colorize("Deleting cache items...", ColorCodes.YELLOW))
    tally = _Tally()
    for item in items:
        _delete_one(item, base, tally)
    print()
    print(colorize(_RULE, ColorCodes.CYAN))
    if tally.errors == 0:
        print(colorize(
            f"Successfully deleted {tally.deleted} item(s) ({format_cleanup_size(tally.deleted_size)})", ColorCodes.GREEN
        ))
    else:
        print(colorize(f"Deleted {tally.deleted} item(s), {tally.errors} error(s)", ColorCodes.YELLOW))
    print(colorize(_RULE, ColorCodes.CYAN))


def _print_usage_hint() -> None:
    print(colorize(_RULE, ColorCodes.CYAN))
    print(colorize("To delete these items, run with -Force parameter", ColorCodes.CYAN))
    print()
    print(colorize("Usage:", ColorCodes.GRAY))
    print(colorize(" .\\scripts\\workspace\\cleanup-temps.ps1 -Force   # delete every cache folder and file", ColorCodes.GRAY))
    print(colorize(
        " .\\scripts\\workspace\\cleanup-temps.ps1 -Force -AdditionalFolders .scratch_cache   # plus more folder names",
        ColorCodes.GRAY,
    ))
    print(colorize(_RULE, ColorCodes.CYAN))


def run(
    base_dir: Path,
    *,
    force: bool,
    additional_folders: Sequence[str] = (),
    read_answer: AnswerReader = read_answer_from_stdin,
) -> int:
    """List the cache items under *base_dir*; with *force*, confirm and delete them. Returns the exit code."""
    folders = checked_folder_names(additional_folders)
    base = Path(os.path.abspath(base_dir))
    if not base.is_dir():
        print(
            f"Error: base directory not found: {base}. Expected an existing directory holding the datrix* "
            "projects; pass -BaseDir <workspace root> or omit it for this workspace.",
            file=sys.stderr,
        )
        return _EXIT_NO_BASE_DIR
    print(colorize(_RULE, ColorCodes.CYAN))
    print(colorize("Temporary Cache Cleanup", ColorCodes.CYAN))
    print(colorize(_RULE, ColorCodes.CYAN))
    print()
    items = discover(base, folders)
    if not items:
        print(colorize("No cache items found.", ColorCodes.GREEN))
        print()
        return _EXIT_DONE
    total = sum(item.size for item in items)
    print(colorize(f"Found {len(items)} cache item(s) (Total: {format_cleanup_size(total)}):", ColorCodes.CYAN))
    print()
    _print_listing(items)
    if force:
        _delete(items, base, total, read_answer)
    else:
        _print_usage_hint()
    print()
    return _EXIT_DONE


def build_parser() -> argparse.ArgumentParser:
    """The options of ``cleanup-temps.ps1``: its parameters as ``--kebab-name`` flags."""
    parser = argparse.ArgumentParser(
        prog=WRAPPER,
        description="List the cache folders and files of a Datrix workspace; with --force delete them after a "
                    "yes/no confirmation.",
        allow_abbrev=False,
    )
    parser.add_argument("--base-dir", type=Path, default=WORKSPACE_DIR,
                        help="the directory holding the datrix* projects (default: this workspace's root)")
    parser.add_argument("--force", action="store_true", help="delete the items after confirmation")
    parser.add_argument("--additional-folders", action="append", default=[],
                        help="one more cache folder name (a name, never a path); repeatable or comma-separated")
    parser.add_argument(WRAPPER_DEBUG_FLAG, dest="debug", action="store_true", help="debug logging")
    parser.add_argument("--self-test", action="store_true", help="run the self-test and exit")
    return parser


# ---------------------------------------------------------------------------
# Self-test: a planted workspace in a temporary directory.
# ---------------------------------------------------------------------------

_PLANTED: Final = {
    ".pytest_cache/v/x": "x\n",
    ".coverage.host1": "c\n",
    "keep.txt": "k\n",
    "datrix-a/src/a/__pycache__/m.cpython.pyc": "pyc\n",
    "datrix-a/src/a/__pycache__/nested/.coverage": "inside a taken folder\n",
    "datrix-a/src/a/m.py": "\n",
    "datrix-a/coverage.xml": "<x/>\n",
    "datrix-a/.coverage.run2": "c\n",
    "datrix-a/.git/__pycache__/x.pyc": "skipped dir\n",
    "datrix-a/node_modules/.cache/y": "skipped dir\n",
    "datrix-a/.test_results/run1/coverage.xml": "preserved\n",
    "datrix-a/.tasks/htmlcov/index.html": "preserved\n",
    "datrix-b/.scratch_cache/z": "additional\n",
    "other/__pycache__/o.pyc": "not a datrix project\n",
}


def _sep(text: str) -> str:
    return text.replace("/", os.sep)


def _tree(root: Path) -> list[str]:
    return sorted(str(path.relative_to(root)).replace(os.sep, "/") for path in root.rglob("*"))


def _check_discovery_finds_each_kind_once() -> None:
    with TemporaryDirectory() as raw:
        root = Path(raw)
        write_files(root, _PLANTED)
        found = [(item.parent, str(item.path.relative_to(root)), item.is_directory)
                 for item in discover(root, [".scratch_cache"])]
    expected = [
        (root.name, ".pytest_cache", True),
        (root.name, ".coverage.host1", False),
        ("datrix-a", _sep("datrix-a/src/a/__pycache__"), True),
        ("datrix-a", _sep("datrix-a/.coverage.run2"), False),
        ("datrix-a", _sep("datrix-a/coverage.xml"), False),
        ("datrix-b", _sep("datrix-b/.scratch_cache"), True),
    ]
    assert found == expected, f"found {found}, expected {expected}"


def _check_listing_and_refusals_delete_nothing() -> None:
    for force, reader in ((False, refuse_answer), (True, scripted_answers()), (True, scripted_answers("maybe", "no"))):
        with TemporaryDirectory() as raw:
            root = Path(raw)
            write_files(root, _PLANTED)
            before = _tree(root)
            assert run(root, force=force, read_answer=reader) == _EXIT_DONE
            after = _tree(root)
        assert before == after, f"force={force} without a typed yes changed the tree"


def _check_force_deletes_only_the_items_below_base() -> None:
    with TemporaryDirectory() as raw:
        root = Path(raw) / "base"
        write_files(root, _PLANTED)
        (root / "datrix-a/coverage.xml").chmod(stat.S_IREAD)
        assert run(root, force=True, read_answer=scripted_answers("YES")) == _EXIT_DONE
        remaining = _tree(root)
    expected = sorted([
        "keep.txt", "datrix-a", "datrix-a/src", "datrix-a/src/a", "datrix-a/src/a/m.py",
        "datrix-a/.git", "datrix-a/.git/__pycache__", "datrix-a/.git/__pycache__/x.pyc",
        "datrix-a/node_modules", "datrix-a/node_modules/.cache", "datrix-a/node_modules/.cache/y",
        "datrix-a/.test_results", "datrix-a/.test_results/run1", "datrix-a/.test_results/run1/coverage.xml",
        "datrix-a/.tasks", "datrix-a/.tasks/htmlcov", "datrix-a/.tasks/htmlcov/index.html",
        "datrix-b", "datrix-b/.scratch_cache", "datrix-b/.scratch_cache/z",
        "other", "other/__pycache__", "other/__pycache__/o.pyc",
    ])
    assert remaining == expected, f"left {remaining}, expected {expected}"


def _check_emptied_parents_are_pruned_below_base_only() -> None:
    with TemporaryDirectory() as raw:
        root = Path(raw) / "base"
        write_files(root, {"datrix-a/pkg/sub/__pycache__/x.pyc": "x\n"})
        assert run(root, force=True, read_answer=scripted_answers("yes")) == _EXIT_DONE
        remaining = _tree(root)
        base_kept = root.is_dir()
    assert base_kept and remaining == [], f"left {remaining}; base kept: {base_kept}"


def _check_links_are_never_followed() -> None:
    with TemporaryDirectory() as raw:
        base, outside = Path(raw) / "base", Path(raw) / "outside"
        write_files(outside, {"__pycache__/x.pyc": "keep\n", "deep/.pytest_cache/y": "keep\n", ".coverage": "keep\n"})
        write_files(base, {"datrix-a/src/m.py": "\n"})
        plant_directory_link(base / "datrix-a" / "linked", outside)
        plant_directory_link(base / "datrix-a" / "src" / "__pycache__", outside / "__pycache__")
        plant_directory_link(base / ".pytest_cache", outside / "deep")
        assert discover(base) == [], f"found through a link: {discover(base)}"
        before = _tree(outside)
        assert run(base, force=True, read_answer=refuse_answer) == _EXIT_DONE
        after = _tree(outside)
    assert before == after, f"a run reached through a link: {before} became {after}"


def _check_unsafe_additional_folders_are_refused() -> None:
    for value in ("..", ".", "a/b", "..\\x", "ok,../up"):
        try:
            checked_folder_names([value])
        except UsageError:
            continue
        raise AssertionError(f"-AdditionalFolders {value!r} was not refused")
    assert checked_folder_names([".scratch_cache,htmlcov2"]) == [".scratch_cache", "htmlcov2"]


def _check_missing_base_dir_is_refused() -> None:
    with TemporaryDirectory() as raw:
        assert run(Path(raw) / "absent", force=True, read_answer=refuse_answer) == _EXIT_NO_BASE_DIR


_SELF_TEST_CHECKS: Final = (
    _check_discovery_finds_each_kind_once,
    _check_listing_and_refusals_delete_nothing,
    _check_force_deletes_only_the_items_below_base,
    _check_emptied_parents_are_pruned_below_base_only,
    _check_links_are_never_followed,
    _check_unsafe_additional_folders_are_refused,
    _check_missing_base_dir_is_refused,
)


def main(argv: Sequence[str] | None = None) -> int:
    """Run the self-test, or list / delete the cache items under ``--base-dir``."""
    parser = build_parser()

    def dispatch(args: argparse.Namespace) -> int:
        if args.self_test:
            return run_self_test(
                _SELF_TEST_CHECKS, wrapper=WRAPPER, module=MODULE, parser=parser, folder=WORKSPACE_SCRIPTS_DIR
            )
        return run(args.base_dir, force=args.force, additional_folders=args.additional_folders)

    return module_main(parser, dispatch, argv)


if __name__ == "__main__":
    sys.exit(main())
