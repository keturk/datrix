"""What the cleanup scripts share: an explicit yes/no confirmation, removing a tree or a file, pruning emptied
parents and empty folders, and listing a folder as PowerShell's ``Get-ChildItem`` does.

Every cleanup script asks before it deletes anything, and a deletion never reaches above the directory the
script was pointed at. The confirmation fails closed: an end of input (a closed or exhausted stdin) answers
"no", so a cleanup run with nobody at the keyboard deletes nothing. The listing never enters a symbolic link
or junction: its target can lie anywhere, so nothing it leads to is listed or deleted.
"""

from __future__ import annotations

import logging
import os
import shutil
import stat
import sys
from collections.abc import Callable
from pathlib import Path
from types import TracebackType
from typing import Final

from datrix_scripts.logging_utils import ColorCodes, colorize

logger = logging.getLogger(__name__)

# The first Python whose shutil.rmtree takes onexc; datrix/pyproject.toml's requires-python floor is older.
ONEXC_PYTHON: Final = (3, 12)
CONFIRM_PROMPT: Final = "Are you sure? {yes/no}: "
CONFIRM_RETRY: Final = "Please enter 'yes' or 'no'."
_YES: Final = "yes"
_NO: Final = "no"
# Windows' hidden attribute: PowerShell's Get-ChildItem without -Force leaves such items out, so the listings do too.
_HIDDEN_ATTRIBUTE: Final = getattr(stat, "FILE_ATTRIBUTE_HIDDEN", 0)
# Windows' junction reparse tag (absent elsewhere, where only symbolic links link directories).
_JUNCTION_REPARSE_TAG: Final = getattr(stat, "IO_REPARSE_TAG_MOUNT_POINT", 0)


def _is_hidden(path: Path) -> bool:
    attributes = getattr(path.lstat(), "st_file_attributes", 0)
    return bool(attributes & _HIDDEN_ATTRIBUTE)


def is_link(path: Path) -> bool:
    """A symbolic link or a junction. Its target can lie anywhere, so no walk enters one."""
    if path.is_symlink():
        return True
    reparse_tag = getattr(path.lstat(), "st_reparse_tag", 0)
    return bool(_JUNCTION_REPARSE_TAG) and reparse_tag == _JUNCTION_REPARSE_TAG


def children(path: Path, *, include_hidden: bool) -> list[Path]:
    """The entries of *path* in name order (case-insensitive, as the file system lists them); none when unreadable."""
    try:
        entries = list(path.iterdir())
    except OSError as exc:
        logger.debug("Cannot list %s: %s", path, exc)
        return []
    visible = entries if include_hidden else [entry for entry in entries if not _is_hidden(entry)]
    return sorted(visible, key=lambda entry: entry.name.casefold())


def child_dirs(path: Path, *, include_hidden: bool) -> list[Path]:
    """The real directories of *path* (``children`` order); a link to a directory is not one."""
    return [
        entry for entry in children(path, include_hidden=include_hidden)
        if entry.is_dir() and not is_link(entry)
    ]


def tree_lines(path: Path, indent: str = " ") -> list[str]:
    """``<indent>[DIR] name`` / ``<indent>[FILE] name`` for everything under *path*, one more space per level;
    a link to a directory is listed as ``[LINK]`` and not entered."""
    lines: list[str] = []
    for entry in children(path, include_hidden=False):
        if entry.is_dir() and is_link(entry):
            lines.append(f"{indent}[LINK] {entry.name}")
            continue
        is_dir = entry.is_dir()
        lines.append(f"{indent}{'[DIR]' if is_dir else '[FILE]'} {entry.name}")
        if is_dir:
            lines.extend(tree_lines(entry, indent + " "))
    return lines


_KIB: Final = 1024
#: (bytes per unit, unit), largest first: the thresholds a cleanup listing switches unit at.
_SIZE_UNITS: Final = ((_KIB**3, "GB"), (_KIB**2, "MB"), (_KIB, "KB"))


def format_cleanup_size(size: int) -> str:
    """*size* bytes as the cleanup scripts show it: ``N.NN GB`` / ``MB`` / ``KB`` (thousands separated) from
    one unit up, else ``N bytes``."""
    for unit_bytes, unit in _SIZE_UNITS:
        if size >= unit_bytes:
            return f"{size / unit_bytes:,.2f} {unit}"
    return f"{size} bytes"


AnswerReader = Callable[[], str]


def read_answer_from_stdin() -> str:
    """One line from stdin after the prompt; ``EOFError`` when stdin is closed or exhausted."""
    return input(CONFIRM_PROMPT)


def scripted_answers(*replies: str) -> AnswerReader:
    """A self-test's stdin: each call returns the next of *replies*, then ``EOFError`` as a closed stdin does."""
    pending = list(replies)

    def read() -> str:
        if not pending:
            raise EOFError
        return pending.pop(0)

    return read


def refuse_answer() -> str:
    """A self-test's stdin for a run that must not ask: being asked fails the check."""
    raise AssertionError("the confirmation was asked although nothing should have been deleted")


def confirm_yes_no(read_answer: AnswerReader = read_answer_from_stdin) -> bool:
    """Ask "Are you sure? {yes/no}" until the answer is yes or no (any case); True only for yes.

    Any other answer re-prompts. An end of input answers no: nothing is deleted without a typed yes.
    """
    while True:
        try:
            answer = read_answer().strip().lower()
        except EOFError:
            print()
            logger.debug("stdin closed before a yes/no answer; treating it as no")
            return False
        if answer == _YES:
            return True
        if answer == _NO:
            return False
        print(colorize(CONFIRM_RETRY, ColorCodes.YELLOW))


def _clear_read_only_and_retry(function: Callable[[str], object], path: str, error: BaseException) -> None:
    """``shutil.rmtree``'s error hook: a read-only file (git objects, a copied build) is made writable and
    removed again, as PowerShell's ``Remove-Item -Force`` does; any other failure is raised."""
    if not isinstance(error, PermissionError):
        raise error
    os.chmod(path, stat.S_IWRITE)
    function(path)


def _clear_read_only_and_retry_exc_info(
    function: Callable[[str], object],
    path: str,
    exc_info: tuple[type[BaseException], BaseException, TracebackType],
) -> None:
    """The same hook in the ``onerror`` shape ``shutil.rmtree`` takes before Python 3.12."""
    _clear_read_only_and_retry(function, path, exc_info[1])


def remove_tree(path: Path, *, python: tuple[int, int] = sys.version_info[:2]) -> None:
    """Delete *path* and everything under it, read-only files included; raises ``OSError`` on failure.

    A symbolic link or junction at *path* is refused (``OSError``), never followed. *python* picks the
    ``shutil.rmtree`` error hook (the running interpreter's; a self-test passes an older one).
    """
    if python >= ONEXC_PYTHON:
        shutil.rmtree(path, onexc=_clear_read_only_and_retry)
    else:
        shutil.rmtree(path, onerror=_clear_read_only_and_retry_exc_info)


def remove_file(path: Path) -> None:
    """Delete the file *path*, a read-only one included, as ``Remove-Item -Force`` does; raises ``OSError`` on
    failure."""
    try:
        path.unlink()
    except PermissionError as exc:
        _clear_read_only_and_retry(os.unlink, str(path), exc)


def plant_directory_link(link: Path, target: Path) -> None:
    """A link at *link* to the directory *target*, for a self-test proving no walk enters one: a junction on
    Windows (it needs no privilege), else a symbolic link."""
    if sys.platform == "win32":
        import _winapi

        _winapi.CreateJunction(str(target), str(link))
        return
    link.symlink_to(target, target_is_directory=True)


def _is_strictly_inside(path: Path, base_dir: Path) -> bool:
    """True when *path* is below *base_dir* (never *base_dir* itself, never outside it)."""
    return path != base_dir and path.is_relative_to(base_dir)


def remove_empty_parent_folders(item_path: Path, base_dir: Path) -> list[Path]:
    """After *item_path* was deleted, remove each parent that is now empty, walking up and stopping at the
    first non-empty one, at *base_dir*, or at anything outside *base_dir*. Prints and returns what it removed.

    A parent that cannot be listed or removed ends the walk (logged at debug level): pruning is tidying,
    never a reason to fail the deletion that already happened.
    """
    base = Path(os.path.abspath(base_dir))
    parent = Path(os.path.abspath(item_path)).parent
    removed: list[Path] = []
    while _is_strictly_inside(parent, base) and parent.is_dir():
        try:
            if any(parent.iterdir()):
                break
            parent.rmdir()
        except OSError as exc:
            logger.debug("Stopped removing empty parents at %s: %s", parent, exc)
            break
        print(colorize(f" Removed empty folder: {parent}", ColorCodes.GREEN))
        removed.append(parent)
        parent = parent.parent
    return removed


def remove_empty_folders(folder: Path, base_dir: Path) -> list[Path]:
    """Remove *folder* and every folder below it that is empty once the folders below it are gone, deepest
    first. Prints and returns what it removed.

    Only folders strictly inside *base_dir* are removed. No link is entered or removed, and no hidden folder is
    entered; a hidden entry keeps its folder. A folder that cannot be listed or removed is reported and kept.
    """
    base = Path(os.path.abspath(base_dir))
    here = Path(os.path.abspath(folder))
    if not _is_strictly_inside(here, base) or not here.is_dir() or is_link(here):
        return []
    removed: list[Path] = []
    for below in child_dirs(here, include_hidden=False):
        removed.extend(remove_empty_folders(below, base))
    try:
        if any(here.iterdir()):
            return removed
        here.rmdir()
    except OSError as exc:
        print(colorize(f" Warning: Could not remove empty folder {here} : {exc}", ColorCodes.YELLOW))
        return removed
    print(colorize(f" Removed empty folder: {here}", ColorCodes.GREEN))
    removed.append(here)
    return removed
