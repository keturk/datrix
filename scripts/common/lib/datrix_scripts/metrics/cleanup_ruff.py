"""List, and on request delete, the Ruff run logs ``metrics/ruff.ps1`` writes.

The logs live under ``<base>/.test-output/ruff/<project>/`` (``ruff-yyyyMMdd-HHmmss.log``), outside every
package repo on purpose: each datrix-* package is its own git repository, so run output created inside one
is committed and pushed unless a human notices. This module runs no Ruff: it lists those files, newest first
per project, and with ``--force`` deletes them (``--keep-latest``: all but each project's newest) after a
typed ``yes``, then removes each per-project folder left empty. Only plain files directly inside a
per-project folder are touched; a linked folder is not entered.

Run by ``metrics/cleanup-ruff.ps1`` (POSIX twin ``cleanup-ruff.sh``): ``--base-dir`` (default: the
workspace root), ``--force``, ``--keep-latest``, ``--dbg``, ``--self-test``. Always exits 0 outside the
self-test.
"""

from __future__ import annotations

import argparse
import contextlib
import io
import logging
import sys
import tempfile
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Final

from datrix_scripts.cleanup_utils import (
    child_dirs,
    children,
    confirm_yes_no,
    format_cleanup_size,
    read_answer_from_stdin,
    remove_file,
)
from datrix_scripts.gate_harness import WRAPPER_DEBUG_FLAG
from datrix_scripts.metrics.ruff import RUFF_LOG_SUBDIR
from datrix_scripts.paths import WORKSPACE_DIR
from datrix_scripts.test.wrappers import METRICS_SCRIPTS_DIR, module_main, run_self_test

logger = logging.getLogger(__name__)

MODULE: Final = "datrix_scripts.metrics.cleanup_ruff"
WRAPPER: Final = "cleanup-ruff"
EXIT_OK: Final = 0
_RULE: Final = "=" * 40
_LATEST_TAG: Final = " [LATEST]"
OPTIONS_LINES: Final = (
    _RULE,
    "To delete these files, run with -Force parameter",
    "",
    "Options:",
    " .\\cleanup-ruff.ps1 -Force # Delete all log files and empty per-project folders",
    " .\\cleanup-ruff.ps1 -Force -KeepLatest # Keep latest log per project",
    _RULE,
)


@dataclass(frozen=True)
class RuffLog:
    """One log file of one project; ``latest`` marks the project's newest (first by name, descending)."""

    project: str
    path: Path
    size: int
    latest: bool


def collect_logs(log_root: Path) -> list[RuffLog]:
    """Every log under *log_root*, grouped by project folder (in listing order), newest first in each."""
    logs: list[RuffLog] = []
    for folder in child_dirs(log_root, include_hidden=False) if log_root.is_dir() else []:
        files = [entry for entry in children(folder, include_hidden=False) if entry.is_file()]
        files.sort(key=lambda entry: entry.name.lower(), reverse=True)
        logs.extend(
            RuffLog(project=folder.name, path=entry, size=entry.stat().st_size, latest=index == 0)
            for index, entry in enumerate(files)
        )
    return logs


def _print_listing(logs: Sequence[RuffLog]) -> None:
    total = sum(log.size for log in logs)
    print(f"Found {len(logs)} file(s) (Total: {format_cleanup_size(total)}):")
    print("")
    projects = list(dict.fromkeys(log.project for log in logs))
    for project in projects:
        print(f"=== {project} ===")
        for log in (entry for entry in logs if entry.project == project):
            tag = _LATEST_TAG if log.latest else ""
            print(f" {log.path.name} ({format_cleanup_size(log.size)}){tag}")
            print(f" {log.path}")
        print("")


def _print_warning(doomed: Sequence[RuffLog], keep_latest: bool) -> None:
    print(_RULE)
    if keep_latest:
        print(f"WARNING: You are about to delete {len(doomed)} old log file(s)")
        print(" (keeping latest log for each project)")
    else:
        print(f"WARNING: You are about to delete ALL {len(doomed)} log file(s)")
    print(f" Total size: {format_cleanup_size(sum(log.size for log in doomed))}")
    print(_RULE)
    print("")


def _remove_emptied_folders(folders: Sequence[Path]) -> None:
    for folder in folders:
        if not folder.is_dir() or any(folder.iterdir()):
            continue
        try:
            folder.rmdir()
        except OSError as exc:
            print(f" Error removing folder {folder} : {exc}")
            continue
        print(f" Removed empty folder: {folder}")


def _delete(doomed: Sequence[RuffLog]) -> None:
    print("")
    print("Deleting log files...")
    deleted = errors = deleted_size = 0
    folders: dict[Path, None] = {}
    for log in doomed:
        try:
            remove_file(log.path)
        except OSError as exc:
            print(f" Error deleting {log.path}: {exc}")
            errors += 1
            continue
        print(f" Deleted: {log.path}")
        deleted += 1
        deleted_size += log.size
        folders[log.path.parent] = None
    _remove_emptied_folders(list(folders))
    print("")
    print(_RULE)
    if errors:
        print(f"Deleted {deleted} file(s), {errors} error(s)")
    else:
        print(f"Successfully deleted {deleted} file(s) ({format_cleanup_size(deleted_size)})")
    print(_RULE)


def run_cleanup(args: argparse.Namespace, read_answer: Callable[[], str] = read_answer_from_stdin) -> int:
    """The wrapper's run: list the logs under ``--base-dir``; with ``--force`` confirm and delete them."""
    log_root = args.base_dir / RUFF_LOG_SUBDIR
    logger.debug("Ruff log root: %s", log_root)
    print(_RULE)
    print("Ruff Check Output Cleanup")
    print(_RULE)
    print("")
    logs = collect_logs(log_root)
    if not logs:
        print("No Ruff check log files found.")
        print("")
        return EXIT_OK
    _print_listing(logs)
    doomed = [log for log in logs if not (args.keep_latest and log.latest)]
    if not args.force:
        for line in OPTIONS_LINES:
            print(line)
        print("")
        return EXIT_OK
    if not doomed:
        print("No files to delete (keeping latest log per project).")
        print("")
        return EXIT_OK
    _print_warning(doomed, args.keep_latest)
    if not confirm_yes_no(read_answer):
        print("")
        print("Deletion cancelled.")
        return EXIT_OK
    _delete(doomed)
    print("")
    return EXIT_OK


def build_parser() -> argparse.ArgumentParser:
    """The options of ``metrics/cleanup-ruff.ps1``: one per wrapper parameter, spelled exactly."""
    parser = argparse.ArgumentParser(description="List or delete the Ruff run logs.", allow_abbrev=False)
    parser.add_argument(
        "--base-dir", type=Path, default=WORKSPACE_DIR, help="The folder holding .test-output/ruff (default: workspace)."
    )
    parser.add_argument("--force", action="store_true", help="Delete the listed logs after a typed yes.")
    parser.add_argument("--keep-latest", action="store_true", help="With --force: keep each project's newest log.")
    parser.add_argument(WRAPPER_DEBUG_FLAG, dest="debug", action="store_true", help="Debug logging.")
    parser.add_argument("--self-test", action="store_true", help="Run only the self-test over planted logs.")
    return parser


def _run(args: argparse.Namespace) -> int:
    if args.self_test:
        return run_self_test(
            SELF_TEST_CHECKS, wrapper=WRAPPER, module=MODULE, parser=build_parser(), folder=METRICS_SCRIPTS_DIR
        )
    return run_cleanup(args)


# ---------------------------------------------------------------------------
# Self-test
# ---------------------------------------------------------------------------

_OLD_LOG: Final = "ruff-20260101-000000.log"
_NEW_LOG: Final = "ruff-20260102-000000.log"
_NEW_LOG_BYTES: Final = 2048


def _plant(base: Path) -> Path:
    """Under *base*: ``datrix-a`` and ``datrix-b`` each with an old (3 bytes) and a new (2 KB) log, an empty
    ``datrix-empty`` folder, and a stray file outside the log root that no run may touch."""
    root = base / RUFF_LOG_SUBDIR
    for project in ("datrix-a", "datrix-b"):
        (root / project).mkdir(parents=True)
        (root / project / _OLD_LOG).write_text("old", encoding="utf-8")
        (root / project / _NEW_LOG).write_text("n" * _NEW_LOG_BYTES, encoding="utf-8")
    (root / "datrix-empty").mkdir()
    (base / "keep.txt").write_text("outside", encoding="utf-8")
    return base


def _cleaned(argv: Sequence[str], answers: Sequence[str] = ()) -> tuple[list[str], list[str]]:
    """The lines a run over planted logs prints, and the files left under the base after it."""
    pending = list(answers)

    def answer() -> str:
        if not pending:
            raise EOFError
        return pending.pop(0)

    printed = io.StringIO()
    with tempfile.TemporaryDirectory() as raw:
        base = _plant(Path(raw))
        with contextlib.redirect_stdout(printed):
            code = run_cleanup(build_parser().parse_args([f"--base-dir={base}", *argv]), answer)
        left = sorted(path.relative_to(base).as_posix() for path in base.rglob("*") if path.is_file())
    assert code == EXIT_OK, code
    return printed.getvalue().splitlines(), left


_ALL_FILES: Final = [
    ".test-output/ruff/datrix-a/" + _OLD_LOG, ".test-output/ruff/datrix-a/" + _NEW_LOG,
    ".test-output/ruff/datrix-b/" + _OLD_LOG, ".test-output/ruff/datrix-b/" + _NEW_LOG, "keep.txt",
]


def _check_listing_marks_latest_and_deletes_nothing() -> None:
    lines, left = _cleaned([])
    assert "Found 4 file(s) (Total: 4.01 KB):" in lines, lines
    assert lines.index(f" {_NEW_LOG} (2.00 KB){_LATEST_TAG}") < lines.index(f" {_OLD_LOG} (3 bytes)"), lines
    assert "=== datrix-empty ===" not in lines and lines[-len(OPTIONS_LINES) - 1:-1] == list(OPTIONS_LINES), lines
    assert left == _ALL_FILES, left


def _check_no_and_end_of_input_cancel() -> None:
    for answers in (["maybe", "no"], []):
        lines, left = _cleaned(["--force"], answers)
        assert "WARNING: You are about to delete ALL 4 log file(s)" in lines and lines[-1] == "Deletion cancelled.", lines
        assert left == _ALL_FILES, left


def _check_keep_latest_deletes_only_old_logs() -> None:
    lines, left = _cleaned(["--force", "--keep-latest"], ["yes"])
    assert " (keeping latest log for each project)" in lines and " Total size: 6 bytes" in lines, lines
    assert "Successfully deleted 2 file(s) (6 bytes)" in lines, lines
    assert left == [path for path in _ALL_FILES if _OLD_LOG not in path], left


def _check_all_deletes_logs_and_emptied_folders_only() -> None:
    lines, left = _cleaned(["--force"], ["YES"])
    assert sum(line.startswith(" Removed empty folder: ") for line in lines) == 2, lines
    assert left == ["keep.txt"], left


def _check_empty_root_and_size_units() -> None:
    printed = io.StringIO()
    with tempfile.TemporaryDirectory() as raw, contextlib.redirect_stdout(printed):
        run_cleanup(build_parser().parse_args([f"--base-dir={raw}"]))
    assert printed.getvalue().splitlines()[-2:] == ["No Ruff check log files found.", ""], printed.getvalue()
    sizes = [format_cleanup_size(size) for size in (1023, 1024, 5 * 1024**2, 1536 * 1024**3)]
    assert sizes == ["1023 bytes", "1.00 KB", "5.00 MB", "1,536.00 GB"], sizes


SELF_TEST_CHECKS: Final[tuple[Callable[[], None], ...]] = (
    _check_listing_marks_latest_and_deletes_nothing,
    _check_no_and_end_of_input_cancel,
    _check_keep_latest_deletes_only_old_logs,
    _check_all_deletes_logs_and_emptied_folders_only,
    _check_empty_root_and_size_units,
)


def main(argv: Sequence[str] | None = None) -> int:
    """Entry point."""
    return module_main(build_parser(), _run, argv)


if __name__ == "__main__":
    sys.exit(main())
