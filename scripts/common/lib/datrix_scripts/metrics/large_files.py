"""
List the top N files by line count in each selected Datrix project's src/ and tests/ trees.

``scripts/metrics/large-files.ps1`` (and its ``.sh`` twin) runs this module. Each project (``--projects`` /
``--all``) is walked under ``src/`` and ``tests/`` (at least one must exist); the default suffix is ``py``.
The listing is printed as ``<lines>  <path>`` rows (``--format summary``) or as one JSON document
(``--format json``). With ``--threshold N`` only files of at least N lines are listed, each project's
listing ends on ``LARGE_FILES_COUNT: <n>`` and the run ends on a per-project count table.

A report only: no count is a limit, so a file of any size never fails the run. A project fails only when it
cannot be read (no ``src/`` nor ``tests/``, or an unreadable file).

Exit codes: 0 = every project listed; 1 = a project failed, or a refused selection; 2 = a usage error.

Usage (PYTHONPATH=scripts/common/lib; the wrapper sets it):
    python -m datrix_scripts.metrics.large_files datrix-common
    python -m datrix_scripts.metrics.large_files datrix-common --top=30 --format=json
    python -m datrix_scripts.metrics.large_files datrix-language --suffix=
    python -m datrix_scripts.metrics.large_files datrix-common --threshold=500
    python -m datrix_scripts.metrics.large_files --self-test
"""

from __future__ import annotations

import argparse
import contextlib
import io
import json
import sys
import tempfile
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Final

from datrix_scripts.framework_repos import PackageMarker
from datrix_scripts.gate_harness import WRAPPER_DEBUG_FLAG, write_files
from datrix_scripts.metrics.projects import (
    CODE_SHAPE_WORDING,
    EXIT_FAILED,
    EXIT_PASSED,
    STOP_MESSAGE_FLAG,
    ProjectSelectionError,
    add_project_arguments,
    plant_workspace,
    print_stderr,
    run_projects,
    select_projects,
)
from datrix_scripts.paths import WORKSPACE_DIR
from datrix_scripts.test.wrappers import METRICS_SCRIPTS_DIR, module_main, run_self_test

MODULE: Final = "datrix_scripts.metrics.large_files"
WRAPPER: Final = "large-files"

DEFAULT_FOLDERS_TO_SKIP: Final = frozenset({"__pycache__", ".git", ".venv", "node_modules", ".pytest_cache"})
FORMAT_SUMMARY: Final = "summary"
FORMAT_JSON: Final = "json"
FORMATS: Final = (FORMAT_SUMMARY, FORMAT_JSON)
DEFAULT_SUFFIX: Final = "py"
DEFAULT_TOP: Final = 20
NO_THRESHOLD: Final = 0
COUNT_MARKER: Final = "LARGE_FILES_COUNT"
_RULE: Final = "=" * 40
_ROOT_DIRS: Final = (PackageMarker.SRC.value, PackageMarker.TESTS.value)

USAGE_LINES: Final = (
    "Usage:",
    " .\\large-files.ps1 <project-name> [options]",
    " .\\large-files.ps1 <folder-path> [options]",
    " .\\large-files.ps1 -All [options]",
    "",
    "Examples:",
    " .\\large-files.ps1 datrix-common",
    " .\\large-files.ps1 datrix-language -Top 30 -Format json",
    " .\\large-files.ps1 -All -Suffix \\ \\",
    "",
    "Parameters:",
    " -Top Number of largest files per project (default: 20)",
    " -Threshold Only show files with at least this many lines (0 = no filter)",
    " -Format summary | json (default: summary)",
    " -Suffix Comma-separated suffixes (default: py). Use \\ \\ for all",
    " -All Run for all datrix-* projects",
    " -StopOnError Stop on first project failure",
    " -VerboseOutput Verbose output from the script",
    " -Dbg Debug output",
)


class LargeFilesError(RuntimeError):
    """A project cannot be listed; the message says why."""


@dataclass(frozen=True)
class ListingOptions:
    """What every project's listing of one run shares: the wrapper's ``-Top``, ``-Threshold``, ``-Format``,
    ``-Suffix`` and ``-VerboseOutput`` / ``-Dbg``."""

    top: int
    threshold: int
    output_format: str
    suffixes: frozenset[str] | None
    verbose: bool


def parse_suffixes(suffix: str) -> frozenset[str] | None:
    """The lower-cased suffixes of the comma-separated *suffix*; None (every suffix) when it is blank."""
    if not suffix.strip():
        return None
    return frozenset(part.strip().lower() for part in suffix.split(",") if part.strip())


def _has_suffix(path: Path, suffixes: frozenset[str] | None) -> bool:
    return suffixes is None or path.suffix.removeprefix(".").lower() in suffixes


def _collect_files(project_root: Path, roots: Sequence[Path], suffixes: frozenset[str] | None) -> list[tuple[str, int]]:
    """``(path relative to project_root, line count)`` for every file under *roots*.

    Raises:
        LargeFilesError: A file cannot be read as UTF-8.
    """
    results: list[tuple[str, int]] = []
    for root in roots:
        for path in root.rglob("*"):
            relative = path.relative_to(project_root)
            if not path.is_file() or any(part in DEFAULT_FOLDERS_TO_SKIP for part in relative.parts):
                continue
            if not _has_suffix(path, suffixes):
                continue
            try:
                lines = len(path.read_text(encoding="utf-8").splitlines())
            except (OSError, UnicodeDecodeError) as exc:
                raise LargeFilesError(f"Error reading {relative}: {exc}") from exc
            results.append((relative.as_posix(), lines))
    return results


def _print_listing(project_root: Path, listed: Sequence[tuple[str, int]], options: ListingOptions) -> None:
    if options.output_format == FORMAT_JSON:
        document = {
            "project_root": str(project_root),
            "top": options.top,
            "files": [{"path": path, "lines": lines} for path, lines in listed],
        }
        print(json.dumps(document, indent=2))
        return
    width = max((len(str(lines)) for _, lines in listed), default=1)
    for path, lines in listed:
        print(f"{lines:>{width}}  {path}")


def list_large_files(project_root: Path, options: ListingOptions) -> int:
    """Print the largest files of *project_root*; the number of files listed.

    Raises:
        LargeFilesError: *project_root* is not a directory, holds neither ``src/`` nor ``tests/``, or holds an
            unreadable file.
    """
    project_root = project_root.resolve()
    if not project_root.is_dir():
        raise LargeFilesError(f"project root is not a directory: {project_root}")
    roots = [project_root / name for name in _ROOT_DIRS if (project_root / name).is_dir()]
    if not roots:
        raise LargeFilesError(f"project has neither src/ nor tests/: {project_root}")
    if options.verbose:
        print_stderr(f"Scanning {[str(root) for root in roots]} (suffixes={options.suffixes or 'all'})")
    collected = _collect_files(project_root, roots, options.suffixes)
    if options.threshold > NO_THRESHOLD:
        collected = [entry for entry in collected if entry[1] >= options.threshold]
    collected.sort(key=lambda entry: (-entry[1], entry[0]))
    listed = collected[: options.top]
    _print_listing(project_root, listed, options)
    if options.threshold > NO_THRESHOLD:
        print(f"{COUNT_MARKER}: {len(listed)}", flush=True)
    return len(listed)


def build_parser() -> argparse.ArgumentParser:
    """The options of ``metrics/large-files.ps1``: one per wrapper parameter, spelled exactly."""
    parser = argparse.ArgumentParser(
        description="Top N files by line count (src + tests) for one or more Datrix projects.",
        allow_abbrev=False,
    )
    add_project_arguments(parser)
    parser.add_argument(
        "--top", type=int, default=DEFAULT_TOP, metavar="N", help=f"Files to list per project (default: {DEFAULT_TOP})."
    )
    parser.add_argument(
        "--threshold",
        type=int,
        default=NO_THRESHOLD,
        metavar="N",
        help="Only list files of at least this many lines (0 = no filter); never a failure.",
    )
    parser.add_argument(
        "--format", choices=FORMATS, default=FORMAT_SUMMARY, help=f"Output format (default: {FORMAT_SUMMARY})."
    )
    parser.add_argument(
        "--suffix",
        default=DEFAULT_SUFFIX,
        help=f"Comma-separated file suffixes to include (default: {DEFAULT_SUFFIX}); empty for every file.",
    )
    parser.add_argument("--stop-on-error", action="store_true", help="Stop on the first project that fails.")
    parser.add_argument("--verbose-output", action="store_true", help="Name the scanned trees on stderr.")
    parser.add_argument(WRAPPER_DEBUG_FLAG, dest="debug", action="store_true", help="As --verbose-output, at DEBUG.")
    parser.add_argument("--self-test", action="store_true", help="Run only the self-test over planted packages.")
    return parser


def _listing_options(args: argparse.Namespace) -> ListingOptions:
    return ListingOptions(
        top=args.top,
        threshold=args.threshold,
        output_format=args.format,
        suffixes=parse_suffixes(args.suffix),
        verbose=args.verbose_output or args.debug,
    )


def _run_info(args: argparse.Namespace) -> str:
    info = f"top={args.top}, format={args.format}"
    if args.threshold > NO_THRESHOLD:
        info += f", threshold={args.threshold}"
    return info


def _print_threshold_table(threshold: int, projects: Sequence[str], counts: dict[str, int]) -> None:
    """The ``Files with >= N lines`` table: each project's count (``(error)`` when it did not list), sorted."""
    print("")
    print(_RULE)
    print(f"Files with >= {threshold} lines")
    print(_RULE)
    total = 0
    for project in sorted(projects):
        if project in counts:
            print(f" {project} : {counts[project]} files")
            total += counts[project]
        else:
            print(f" {project} : (error)")
    print("")
    print(f"Total: {total} files above threshold")


def run_large_files(args: argparse.Namespace, workspace: Path) -> int:
    """The wrapper's run over *workspace*: select, list each project, then the threshold table."""
    try:
        projects = select_projects(args, workspace, usage=USAGE_LINES, wording=CODE_SHAPE_WORDING)
    except ProjectSelectionError as exc:
        for line in exc.lines:
            print(line)
        return EXIT_FAILED
    info = _run_info(args)
    scope = "all projects" if args.all else "projects"
    print(f"Running large-files ({info}) for {scope}: {', '.join(projects)}")

    options = _listing_options(args)
    counts: dict[str, int] = {}

    def run_one(project: str) -> int:
        try:
            counts[project] = list_large_files(workspace / project, options)
        except LargeFilesError as exc:
            print_stderr(f"Error: {exc}")
            print("")
            print(f"Error: {project} failed (exit code: {EXIT_FAILED})")
            return EXIT_FAILED
        return EXIT_PASSED

    results = run_projects(
        projects, run_one, stop_on_error=args.stop_on_error, banner_info=info, stop_message=STOP_MESSAGE_FLAG
    )
    if args.threshold > NO_THRESHOLD:
        _print_threshold_table(args.threshold, projects, counts)
    return EXIT_PASSED if all(results.values()) else EXIT_FAILED


# ---------------------------------------------------------------------------
# Self-test
# ---------------------------------------------------------------------------

_PLANTED_FILES: Final = {
    "datrix-a/src/big.py": "a = 1\n" * 30,
    "datrix-a/src/small.py": "a = 1\n" * 3,
    "datrix-a/tests/test_mid.py": "a = 1\n" * 10,
    "datrix-a/src/notes.md": "line\n" * 50,
    "datrix-a/src/__pycache__/cached.py": "a = 1\n" * 99,
}


def _printed_by_run(argv: Sequence[str], workspace: Path) -> tuple[int, list[str]]:
    """The exit code of ``run_large_files`` on *argv* over *workspace*, and the lines it printed to stdout."""
    printed = io.StringIO()
    with contextlib.redirect_stdout(printed), contextlib.redirect_stderr(io.StringIO()):
        code = run_large_files(build_parser().parse_args(list(argv)), workspace)
    return code, printed.getvalue().splitlines()


def _planted() -> tuple[tempfile.TemporaryDirectory[str], Path]:
    holder = tempfile.TemporaryDirectory()
    workspace = plant_workspace(Path(holder.name))
    write_files(workspace, _PLANTED_FILES)
    return holder, workspace


def _check_nothing_given_prints_usage_and_available() -> None:
    holder, workspace = _planted()
    with holder:
        code, lines = _printed_by_run([], workspace)
    expected = [
        "", "ERROR: No projects specified.", "", *USAGE_LINES, "", "Available projects:", " - datrix-a", " - datrix-b", ""
    ]
    assert (code, lines) == (EXIT_FAILED, expected), (code, lines)


def _check_summary_lists_largest_first_and_skips_cache_and_other_suffixes() -> None:
    holder, workspace = _planted()
    with holder:
        code, lines = _printed_by_run(["datrix-a", "--top=2"], workspace)
    assert code == EXIT_PASSED, (code, lines)
    assert lines[0] == "Running large-files (top=2, format=summary) for projects: datrix-a", lines
    assert lines[2:5] == [_RULE, "[1/1] datrix-a (top=2, format=summary)", _RULE], lines
    assert lines[-2:] == ["30  src/big.py", "10  tests/test_mid.py"], lines


def _check_threshold_is_a_filter_never_a_failure() -> None:
    holder, workspace = _planted()
    with holder:
        code, lines = _printed_by_run(["datrix-a", "datrix-b", "--threshold=5"], workspace)
    assert code == EXIT_PASSED, (code, lines)
    assert f"{COUNT_MARKER}: 2" in lines and f"{COUNT_MARKER}: 0" in lines, lines
    assert lines[-8:] == [
        "",
        _RULE,
        "Files with >= 5 lines",
        _RULE,
        " datrix-a : 2 files",
        " datrix-b : 0 files",
        "",
        "Total: 2 files above threshold",
    ], lines


def _check_unreadable_project_fails_and_stop_on_error_stops() -> None:
    holder, workspace = _planted()
    with holder:
        code, lines = _printed_by_run(["datrix-q", "datrix-a", "--threshold=5", "--stop-on-error"], workspace)
    assert code == EXIT_FAILED, (code, lines)
    stopped = lines.index(STOP_MESSAGE_FLAG)
    assert lines[stopped - 2 : stopped] == ["", "Error: datrix-q failed (exit code: 1)"], lines
    assert " datrix-a : (error)" in lines and " datrix-q : (error)" in lines, lines
    assert "[2/2] datrix-a (top=20, format=summary, threshold=5)" not in lines, lines


def _check_json_and_every_suffix() -> None:
    holder, workspace = _planted()
    with holder:
        code, lines = _printed_by_run(["datrix-a", "--format=json", "--suffix=", "--top=1"], workspace)
        root = str((workspace / "datrix-a").resolve())
    assert code == EXIT_PASSED, (code, lines)
    document = json.loads("\n".join(lines[lines.index("{") :]))
    assert document == {"project_root": root, "top": 1, "files": [{"path": "src/notes.md", "lines": 50}]}, document


_SELF_TEST_CHECKS: Final = (
    _check_nothing_given_prints_usage_and_available,
    _check_summary_lists_largest_first_and_skips_cache_and_other_suffixes,
    _check_threshold_is_a_filter_never_a_failure,
    _check_unreadable_project_fails_and_stop_on_error_stops,
    _check_json_and_every_suffix,
)


def _run(args: argparse.Namespace) -> int:
    if args.self_test:
        return run_self_test(
            _SELF_TEST_CHECKS, wrapper=WRAPPER, module=MODULE, parser=build_parser(), folder=METRICS_SCRIPTS_DIR
        )
    return run_large_files(args, WORKSPACE_DIR)


def main(argv: Sequence[str] | None = None) -> int:
    """Entry point."""
    return module_main(build_parser(), _run, argv)


if __name__ == "__main__":
    sys.exit(main())
