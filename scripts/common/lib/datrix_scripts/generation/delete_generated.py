"""Rename ``.generated`` and delete the renamed tree (in a background process by default).

The module behind ``generation/delete-generated.ps1`` (and its ``.sh`` twin). Renames
``<base-dir>/.generated`` to ``.generated_old``, or the first free name of ``.generated_old_01``
through ``.generated_old_99``, then removes the renamed directory: in a detached process that
outlives this one (its output in ``<workspace>/.tmp/delete-generated/``), or before returning with
``--wait``. ``--dry-run`` prints the rename and the removal and touches nothing.

Containment: only a real directory ``<base-dir>/.generated`` is renamed (a link or junction is
refused, never followed), and only a real directory directly under ``<base-dir>`` named
``.generated_old`` or ``.generated_old_NN`` is removed. The background process checks the second
again before it removes anything.

Exit codes: 0 = removed, started, previewed, or nothing to do; 1 = refused by the containment
check, no free name, or the removal failed.

Usage:
    python -m datrix_scripts.generation.delete_generated [--base-dir=<dir>] [--wait] [--dry-run]
"""

from __future__ import annotations

import argparse
import contextlib
import io
import os
import re
import stat
import subprocess
import sys
import tempfile
from collections.abc import Callable, Sequence
from datetime import datetime
from pathlib import Path
from typing import Final

from datrix_scripts.cleanup_utils import plant_directory_link, remove_tree
from datrix_scripts.code_index.background import Launcher, launch_detached
from datrix_scripts.logging_utils import ColorCodes, colorize
from datrix_scripts.paths import WORKSPACE_DIR, resolve_output_path, script_env
from datrix_scripts.test.wrappers import GENERATION_SCRIPTS_DIR, module_main, run_self_test

MODULE: Final = "datrix_scripts.generation.delete_generated"
WRAPPER: Final = "delete-generated"
GENERATED_FOLDER_NAME: Final = ".generated"
OLD_FOLDER_BASE_NAME: Final = ".generated_old"
MAX_NUMERIC_SUFFIX: Final = 99
OLD_FOLDER_NAME: Final = re.compile(rf"^{re.escape(OLD_FOLDER_BASE_NAME)}(_\d{{2}})?$")
LOG_SUBDIR: Final = "delete-generated"
# The background process: base and target arrive as argv entries, never inside the code string.
_REMOVE_IN_CHILD: Final = (
    "import sys; from datrix_scripts.generation.delete_generated import remove_renamed_cli; "
    "sys.exit(remove_renamed_cli(sys.argv[1:]))"
)
EXIT_OK: Final = 0
EXIT_REFUSED: Final = 1


class ContainmentError(Exception):
    """A path is not one this script may rename or remove."""


def _is_link(path: Path) -> bool:
    return path.is_symlink() or path.is_junction()


def checked_source(base: Path) -> Path:
    """``<base>/.generated`` when it is a real directory.

    Raises:
        ContainmentError: It is a link, a junction or not a directory.
    """
    source = base / GENERATED_FOLDER_NAME
    if _is_link(source):
        raise ContainmentError(f"{source} is a link or junction; only a real directory is renamed, never one it points to")
    if not source.is_dir():
        raise ContainmentError(f"{source} is not a directory; expected the generated output tree")
    return source


def checked_target(base: Path, target: Path) -> Path:
    """*target* when it is a real directory directly under *base* named ``.generated_old[_NN]``.

    Raises:
        ContainmentError: Any other path: a link or junction, another name, or not a direct child.
    """
    if not OLD_FOLDER_NAME.match(target.name):
        raise ContainmentError(f"{target} is not named {OLD_FOLDER_BASE_NAME} or {OLD_FOLDER_BASE_NAME}_NN")
    if _is_link(target) or not target.is_dir():
        raise ContainmentError(f"{target} is not a real directory (a link, a junction, a file or absent)")
    if target.resolve().parent != base.resolve():
        raise ContainmentError(f"{target} is not directly under {base.resolve()}")
    return target


def free_target(base: Path) -> Path:
    """The first of ``.generated_old``, ``.generated_old_01`` … ``_99`` under *base* that does not exist.

    Raises:
        ContainmentError: Every name is taken.
    """
    names = [OLD_FOLDER_BASE_NAME, *(f"{OLD_FOLDER_BASE_NAME}_{index:02d}" for index in range(1, MAX_NUMERIC_SUFFIX + 1))]
    for name in names:
        candidate = base / name
        if not os.path.lexists(candidate):
            return candidate
    raise ContainmentError(
        f"No free name for old generated folder. Tried '{OLD_FOLDER_BASE_NAME}' and "
        f"'{OLD_FOLDER_BASE_NAME}_01' through '{OLD_FOLDER_BASE_NAME}_{MAX_NUMERIC_SUFFIX:02d}'. "
        "Remove the old folders, then retry."
    )


def child_command(base: Path, target: Path) -> list[str]:
    """The argument vector of the background process that removes *target*."""
    return [sys.executable, "-c", _REMOVE_IN_CHILD, str(base), str(target)]


def remove_renamed(base: Path, target: Path) -> None:
    """Remove *target* after checking it again: read-only files included, links inside the tree removed,
    never followed.

    Raises:
        ContainmentError: *target* is not a removable old generated folder.
        OSError: The removal failed.
    """
    remove_tree(checked_target(base, target))


def remove_renamed_cli(argv: Sequence[str]) -> int:
    """The background process's entry: ``<base> <target>``; returns its exit code."""
    base, target = (Path(value) for value in argv)
    try:
        remove_renamed(base, target)
    except (ContainmentError, OSError) as exc:
        print(f"ERROR: {target} was not removed: {exc}", file=sys.stderr)
        return EXIT_REFUSED
    print(f"Removed '{target}'.")
    return EXIT_OK


def _start_background(base: Path, target: Path, launch: Launcher) -> None:
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    log = resolve_output_path(None, LOG_SUBDIR, filename=f"{target.name}-{stamp}.log")
    launch(child_command(base, target), log)
    print(colorize(f"Started a background process to remove '{target}'.", ColorCodes.GREEN))
    print(colorize(f"Output and errors: {log}", ColorCodes.GRAY))
    print(colorize("For synchronous deletion next time, use -Wait.", ColorCodes.GRAY))


def delete_generated(base: Path, *, wait: bool, dry_run: bool, launch: Launcher = launch_detached) -> int:
    """Rename and remove ``<base>/.generated``; returns the exit code."""
    if not os.path.lexists(base / GENERATED_FOLDER_NAME):
        print(colorize(f"Nothing to do: not found: {base / GENERATED_FOLDER_NAME}", ColorCodes.YELLOW))
        return EXIT_OK
    try:
        source = checked_source(base)
        target = free_target(base)
    except ContainmentError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return EXIT_REFUSED
    if dry_run:
        print(f"Would rename '{source}' -> '{target.name}' and remove '{target}'. Nothing was changed.")
        return EXIT_OK
    print(colorize(f"Renaming '{source}' -> '{target.name}' ...", ColorCodes.CYAN))
    source.rename(target)
    if not wait:
        _start_background(base, target, launch)
        return EXIT_OK
    print(colorize(f"Removing '{target}' (waiting) ...", ColorCodes.CYAN))
    try:
        remove_renamed(base, target)
    except (ContainmentError, OSError) as exc:
        print(f"ERROR: {target} was not removed: {exc}", file=sys.stderr)
        return EXIT_REFUSED
    print(colorize("Done.", ColorCodes.GREEN))
    return EXIT_OK


def build_parser() -> argparse.ArgumentParser:
    """The options of ``generation/delete-generated.ps1``: one per wrapper parameter, spelled exactly."""
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter, allow_abbrev=False
    )
    parser.add_argument("--base-dir", default=str(WORKSPACE_DIR),
                        help="Directory holding .generated (default: the workspace root).")
    parser.add_argument("--wait", action="store_true", help="Remove the renamed folder before returning.")
    parser.add_argument("--dry-run", action="store_true",
                        help="Print the rename and the removal; change nothing.")
    parser.add_argument("--self-test", action="store_true",
                        help="Run only the self-test: deletion, dry run and every containment refusal on planted trees.")
    parser.set_defaults(debug=False)
    return parser


def _plant(base: Path) -> Path:
    """A ``.generated`` tree holding a read-only file (as git objects and copied builds are)."""
    tree = base / GENERATED_FOLDER_NAME / "sub"
    tree.mkdir(parents=True)
    planted = tree / "a.txt"
    planted.write_text("planted", encoding="utf-8")
    planted.chmod(stat.S_IREAD)
    return tree


def _quiet(call: Callable[[], int]) -> tuple[int, str]:
    with contextlib.redirect_stdout(io.StringIO()) as printed, contextlib.redirect_stderr(io.StringIO()) as errors:
        code = call()
    return code, printed.getvalue() + errors.getvalue()


def _check_wait_renames_to_the_first_free_name_and_removes_it() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        base = Path(tmp)
        _plant(base)
        (base / OLD_FOLDER_BASE_NAME).mkdir()
        code, text = _quiet(lambda: delete_generated(base, wait=True, dry_run=False))
        assert code == EXIT_OK, text
        assert f"-> '{OLD_FOLDER_BASE_NAME}_01'" in text, text
        assert not (base / GENERATED_FOLDER_NAME).exists() and not (base / f"{OLD_FOLDER_BASE_NAME}_01").exists()
        assert (base / OLD_FOLDER_BASE_NAME).is_dir(), "an existing old folder was touched"
        code, text = _quiet(lambda: delete_generated(base, wait=True, dry_run=False))
        assert code == EXIT_OK and "Nothing to do: not found" in text, text


def _check_dry_run_changes_nothing() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        base = Path(tmp)
        planted = _plant(base) / "a.txt"
        code, text = _quiet(lambda: delete_generated(base, wait=True, dry_run=True))
        assert code == EXIT_OK and "Would rename" in text, text
        assert planted.is_file() and not (base / OLD_FOLDER_BASE_NAME).exists()


def _check_a_linked_generated_folder_is_refused_and_its_target_kept() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        base = Path(tmp) / "base"
        base.mkdir()
        outside = Path(tmp) / "outside"
        outside.mkdir()
        (outside / "keep.txt").write_text("keep", encoding="utf-8")
        plant_directory_link(base / GENERATED_FOLDER_NAME, outside)
        for dry_run in (True, False):
            code, text = _quiet(lambda dry_run=dry_run: delete_generated(base, wait=True, dry_run=dry_run))
            assert code == EXIT_REFUSED and "link or junction" in text, text
        assert (outside / "keep.txt").is_file() and _is_link(base / GENERATED_FOLDER_NAME)


def _check_only_a_direct_old_generated_child_is_removed() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        base = Path(tmp) / "base"
        (base / "nested" / OLD_FOLDER_BASE_NAME).mkdir(parents=True)
        (base / "other").mkdir()
        outside = Path(tmp) / "outside"
        outside.mkdir()
        plant_directory_link(base / f"{OLD_FOLDER_BASE_NAME}_07", outside)
        refused = {
            "a non-child": base / "nested" / OLD_FOLDER_BASE_NAME,
            "another name": base / "other",
            "a junction": base / f"{OLD_FOLDER_BASE_NAME}_07",
            "outside the base": Path(tmp) / OLD_FOLDER_BASE_NAME,
        }
        for label, target in refused.items():
            try:
                remove_renamed(base, target)
            except ContainmentError:
                continue
            raise AssertionError(f"{label} ({target}) was removed instead of refused")
        assert outside.is_dir() and (base / "other").is_dir() and (base / "nested" / OLD_FOLDER_BASE_NAME).is_dir()


def _check_the_background_command_removes_the_renamed_folder() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        base = Path(tmp)
        _plant(base)
        launched: list[list[str]] = []
        code, text = _quiet(lambda: delete_generated(base, wait=False, dry_run=False,
                                                     launch=lambda command, _log: launched.append(command)))
        assert code == EXIT_OK and len(launched) == 1, text
        target = base / OLD_FOLDER_BASE_NAME
        assert launched[0][-2:] == [str(base), str(target)], launched
        child = subprocess.run(launched[0], env=script_env(), capture_output=True, text=True, check=False)
        assert child.returncode == EXIT_OK and not target.exists(), child.stdout + child.stderr


def _check_no_free_name_exits_1() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        base = Path(tmp)
        _plant(base)
        (base / OLD_FOLDER_BASE_NAME).mkdir()
        for index in range(1, MAX_NUMERIC_SUFFIX + 1):
            (base / f"{OLD_FOLDER_BASE_NAME}_{index:02d}").mkdir()
        code, text = _quiet(lambda: delete_generated(base, wait=True, dry_run=False))
        assert code == EXIT_REFUSED and "No free name" in text, text
        assert (base / GENERATED_FOLDER_NAME).is_dir()


def _run(args: argparse.Namespace) -> int:
    if args.self_test:
        checks = [
            _check_wait_renames_to_the_first_free_name_and_removes_it,
            _check_dry_run_changes_nothing,
            _check_a_linked_generated_folder_is_refused_and_its_target_kept,
            _check_only_a_direct_old_generated_child_is_removed,
            _check_the_background_command_removes_the_renamed_folder,
            _check_no_free_name_exits_1,
        ]
        return run_self_test(checks, wrapper=WRAPPER, module=MODULE, parser=build_parser(),
                             folder=GENERATION_SCRIPTS_DIR)
    return delete_generated(Path(args.base_dir).resolve(), wait=args.wait, dry_run=args.dry_run)


def main(argv: Sequence[str] | None = None) -> int:
    """Entry point."""
    return module_main(build_parser(), _run, argv)


if __name__ == "__main__":
    sys.exit(main())
