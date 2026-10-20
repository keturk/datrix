"""Print the highest phase number of the workspace's ``.tasks`` folders.

``scripts/tasks/latest-phase.ps1`` (and its ``.sh`` twin) runs this module. It reads the ``phase-<number>``
folders of ``<base>/.tasks`` and of the ``.tasks`` folder of every ``datrix`` and ``datrix-*`` repository,
and prints only the highest number (``31``, not ``phase-31``), for use in scripts; nothing when there is no
phase folder. With ``--dbg`` it prints every number found, in the order found, and the latest instead.

Exit codes: 0 = done (a phase found or not); 1 = the base directory does not exist, or a self-test check failed.

Usage:
  python -m datrix_scripts.tasks.latest_phase [--base-dir D:/datrix] [--dbg]
  .\\scripts\\tasks\\latest-phase.ps1 [-BaseDir <path>] [-Dbg]
"""

from __future__ import annotations

import argparse
import re
import sys
import tempfile
from collections.abc import Sequence
from pathlib import Path
from typing import Final

from datrix_scripts.cleanup_utils import child_dirs
from datrix_scripts.gate_harness import WRAPPER_DEBUG_FLAG, write_files
from datrix_scripts.tasks.task_listing import (
    EXIT_LISTED,
    TASKS_FOLDER,
    missing_base_dir_check,
    printed_lines,
    run_on_base,
    tasks_roots,
)
from datrix_scripts.test.wrappers import TASKS_SCRIPTS_DIR, module_main, run_self_test

MODULE: Final = "datrix_scripts.tasks.latest_phase"
WRAPPER: Final = "latest-phase"

PHASE_FOLDER: Final = re.compile(r"^phase-(\d+)$", re.IGNORECASE)
NONE_FOUND: Final = "No phase folders found in .tasks directories."


def phase_numbers(base: Path) -> list[int]:
    """Every phase number of the ``.tasks`` folders under *base*, each once, in the order found."""
    found: list[int] = []
    for root in (root for root in tasks_roots(base) if root.is_dir()):
        for folder in child_dirs(root, include_hidden=False):
            match = PHASE_FOLDER.match(folder.name)
            if match and int(match.group(1)) not in found:
                found.append(int(match.group(1)))
    return found


def report(base: Path, verbose: bool) -> int:
    """Print the latest phase number under *base* (with *verbose*, every number found and the latest)."""
    numbers = phase_numbers(base)
    if not numbers:
        if verbose:
            print(NONE_FOUND)
        return EXIT_LISTED
    if verbose:
        print(f"Found phase numbers: {', '.join(str(number) for number in numbers)}")
        print(f"Latest phase: {max(numbers)}")
    else:
        print(max(numbers))
    return EXIT_LISTED


def _plant(root: Path) -> Path:
    folders = {
        "": ("phase-03",),
        "datrix-alpha/": ("phase-12", "Phase-07", "phase-01", "phase-x"),
        "datrix-beta/": ("phase-12",),
    }
    write_files(root, {f"{repo}{TASKS_FOLDER}/{name}/notes.md": "notes\n"
                       for repo, names in folders.items() for name in names})
    return root


def _check_the_latest_phase_is_printed_alone() -> None:
    with tempfile.TemporaryDirectory() as raw:
        root = _plant(Path(raw))
        plain = printed_lines(lambda base, _: report(base, False), root, "")
        verbose = printed_lines(lambda base, _: report(base, True), root, "")
    assert plain == ["12"], plain
    assert verbose == ["Found phase numbers: 3, 1, 7, 12", "Latest phase: 12"], verbose


def _check_no_phase_folder_prints_nothing() -> None:
    with tempfile.TemporaryDirectory() as raw:
        root = Path(raw)
        plain = printed_lines(lambda base, _: report(base, False), root, "")
        verbose = printed_lines(lambda base, _: report(base, True), root, "")
    assert plain == [] and verbose == [NONE_FOUND], (plain, verbose)


def build_parser() -> argparse.ArgumentParser:
    """The options of ``tasks/latest-phase.ps1``: one per wrapper parameter, spelled exactly."""
    parser = argparse.ArgumentParser(description="Print the latest phase number across the workspace's .tasks folders",
                                     allow_abbrev=False)
    parser.add_argument("--base-dir", default=None,
                        help="Workspace root holding .tasks and the datrix* repos (default: this workspace)")
    parser.add_argument(WRAPPER_DEBUG_FLAG, dest="debug", action="store_true",
                        help="Print every phase number found and the latest, instead of the number alone")
    parser.add_argument("--self-test", action="store_true", help="Run only the self-test over planted folders.")
    return parser


def _run(args: argparse.Namespace) -> int:
    if args.self_test:
        checks = [_check_the_latest_phase_is_printed_alone, _check_no_phase_folder_prints_nothing,
                  missing_base_dir_check(main)]
        return run_self_test(checks, wrapper=WRAPPER, module=MODULE, parser=build_parser(), folder=TASKS_SCRIPTS_DIR)
    return run_on_base(args, lambda base: report(base, args.debug))


def main(argv: Sequence[str] | None = None) -> int:
    """Entry point."""
    return module_main(build_parser(), _run, argv)


if __name__ == "__main__":
    sys.exit(main())
