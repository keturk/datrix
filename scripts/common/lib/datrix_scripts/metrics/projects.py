"""The projects a metrics script runs on, and the loop and summary around them.

The metrics scripts take the same selection: ``-Projects`` (package names or folder paths,
positional and variadic) or ``-All`` (every ``datrix-*`` package), the ``datrix`` showcase repo never
included, then run one tool per project, honour ``-StopOnError`` and end on a ``[PASS]``/``[FAIL]``
summary. This module is the one home for that behaviour; a script's own module adds only its tool.
Where the scripts word a fact differently (the refusal lines, the per-project banner, the framed summary
with a ``Total:`` line) the difference is a parameter here, never a second function.

A refused selection exits 1 (``EXIT_FAILED``), as the scripts always did -- never ``UsageError``, which is 2.

Self-test: ``python -m datrix_scripts.metrics.projects`` (``PYTHONPATH=scripts/common/lib``) runs
``SELF_TEST_CHECKS``; each consumer's ``--self-test`` runs them too.
"""

from __future__ import annotations

import argparse
import contextlib
import io
import os
import sys
import tempfile
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from types import MappingProxyType
from typing import Final

from datrix_scripts.framework_repos import SHOWCASE_REPO_NAME, PackageMarker, workspace_package_dirs
from datrix_scripts.gate_harness import CheckFunc, run_checks
from datrix_scripts.test.test import normalize_project

#: Excluded from every selection, as the scripts exclude ``datrix``.
SHOWCASE: Final = SHOWCASE_REPO_NAME
EXIT_FAILED: Final = 1
EXIT_PASSED: Final = 0

_PASS_LABEL: Final = "[PASS]"
_FAIL_LABEL: Final = "[FAIL]"
#: The ``pass_label`` and ``count_label`` of a fix run's summary.
DONE_LABEL: Final = "[DONE]"
COMPLETED_COUNT_LABEL: Final = "Completed"
_PASSED_COUNT_LABEL: Final = "Passed"
#: Between a summary line's label and its project; ``test-gen`` passes ``" "`` (`` [PASS] <project>``).
SUMMARY_SEPARATOR: Final = " : "
_DETAIL_INDENT: Final = "       "
_HEADER_RULE: Final = "========"
_BANNER_RULE: Final = "=" * 40
_AVAILABLE_HEADING: Final = "Available projects:"
#: What a loop prints when ``-StopOnError`` stops it; the scripts that say "flag" pass ``STOP_MESSAGE_FLAG``.
STOP_MESSAGE: Final = "Stopping due to -StopOnError"
STOP_MESSAGE_FLAG: Final = "Stopping due to -StopOnError flag"
_SELF_TEST_PREFIX: Final = "metrics-projects-selftest-"
_PLANTED_FULL: Final = "datrix-a"
_PLANTED_SRC_ONLY: Final = "datrix-b"
_PLANTED_MISSING: Final = "datrix-q"
_NO_DETAILS: Final[Mapping[str, str]] = MappingProxyType({})


class ProjectSelectionError(Exception):
    """The projects asked for cannot be run (exit 1); ``lines`` are printed as the scripts print them."""

    def __init__(self, lines: Sequence[str]) -> None:
        super().__init__("\n".join(lines))
        self.lines = tuple(lines)


def add_project_arguments(parser: argparse.ArgumentParser) -> None:
    """``projects`` (positional, variadic) and ``--projects`` (repeatable) plus ``--all``: the wrappers'
    ``-Projects`` and ``-All``."""
    parser.add_argument(
        "positional_projects", nargs="*", metavar="PROJECT", help="as --projects, for a caller of the .sh twin"
    )
    parser.add_argument(
        "--projects", action="append", default=[], help="A project name or folder path to run; repeatable"
    )
    parser.add_argument("--all", action="store_true", help="Run every datrix-* package (the showcase repo excluded)")


def requested_projects(args: argparse.Namespace) -> list[str]:
    """The project arguments given positionally and as --projects, as package names, in order, the showcase
    repo dropped."""
    names = [normalize_project(raw) for raw in [*args.positional_projects, *args.projects]]
    return [name for name in names if name != SHOWCASE]


@dataclass(frozen=True)
class SelectionWording:
    """The refusal lines a script prints when its selection is empty (each exits 1)."""

    #: ``--all`` found no package; ``{workspace}`` is replaced by the workspace path.
    none_found: str
    #: Names were given but every one was the showcase repo.
    none_valid: str
    #: The lines printed before the usage when nothing was given (empty: the usage alone is printed).
    none_given_heading: tuple[str, ...]
    #: Nothing given: print ``Available projects:`` and `` - <name>`` lines after the usage.
    list_available: bool
    #: The heading of that list (``dependency`` says ``Available packages:``).
    available_heading: str = _AVAILABLE_HEADING


#: The wording of the tool-running scripts (coverage, ruff, bandit, ...).
DEFAULT_WORDING: Final = SelectionWording(
    none_found="ERROR: No Datrix projects in: {workspace}",
    none_valid=f"ERROR: No valid projects ({SHOWCASE} excluded).",
    none_given_heading=("", "ERROR: No projects specified.", ""),
    list_available=True,
)
#: The wording of ``complexity``, ``loc`` and ``large-files``.
CODE_SHAPE_WORDING: Final = SelectionWording(
    none_found="ERROR: No Datrix projects found in: {workspace}",
    none_valid=f"ERROR: No valid projects specified ({SHOWCASE} is excluded).",
    none_given_heading=("", "ERROR: No projects specified.", ""),
    list_available=True,
)
#: The wording of ``duplicate``: its usage lines alone when nothing is given.
USAGE_ONLY_WORDING: Final = SelectionWording(
    none_found=DEFAULT_WORDING.none_found,
    none_valid=DEFAULT_WORDING.none_valid,
    none_given_heading=(),
    list_available=False,
)


def _available_lines(workspace: Path, any_of: frozenset[PackageMarker], heading: str) -> list[str]:
    """The *heading* block of available packages (omitted when no package is found) and the blank line
    after it."""
    available = [path.name for path in workspace_package_dirs(workspace, any_of=any_of)]
    if not available:
        return [""]
    return [heading, *(f" - {name}" for name in available), ""]


def _usage_lines(
    workspace: Path, usage: Sequence[str], any_of: frozenset[PackageMarker], wording: SelectionWording
) -> list[str]:
    lines = [*wording.none_given_heading, *usage]
    if wording.list_available:
        lines.extend(["", *_available_lines(workspace, any_of, wording.available_heading)])
    return lines


def select_projects(
    args: argparse.Namespace,
    workspace: Path,
    *,
    usage: Sequence[str],
    any_of: frozenset[PackageMarker] = frozenset(),
    wording: SelectionWording = DEFAULT_WORDING,
) -> list[str]:
    """The projects to run: ``--all`` is every ``datrix-*`` package of *workspace* holding one of *any_of*
    (any when empty); otherwise the requested names, in order.

    Raises:
        ProjectSelectionError: No project is found under ``--all``; the names given were all the showcase
            repo; or nothing was given (then the lines are *usage*, framed as *wording* says). The lines
            are taken from *wording*.
    """
    if args.all:
        found = [path.name for path in workspace_package_dirs(workspace, any_of=any_of)]
        if not found:
            raise ProjectSelectionError([wording.none_found.format(workspace=workspace)])
        return found
    requested = requested_projects(args)
    if requested:
        return requested
    if [*args.positional_projects, *args.projects]:
        raise ProjectSelectionError([wording.none_valid])
    raise ProjectSelectionError(_usage_lines(workspace, usage, any_of, wording))


def print_project_banner(index: int, total: int, project: str, info: str) -> None:
    """A blank line, a 40-``=`` rule, ``[<index>/<total>] <project> (<info>)``, the rule and a blank line."""
    print("")
    print(_BANNER_RULE)
    print(f"[{index}/{total}] {project} ({info})")
    print(_BANNER_RULE)
    print("")


#: Prints the lines introducing one project of a run, given ``(index, total, project)``.
ProjectAnnouncer = Callable[[int, int, str], None]


def run_projects(
    projects: Sequence[str],
    run_one: Callable[[str], int],
    *,
    stop_on_error: bool,
    banner_info: str | None = None,
    header_info: str | None = None,
    stop_message: str = STOP_MESSAGE,
    announce: ProjectAnnouncer | None = None,
) -> dict[str, bool]:
    """Run *run_one* per project in order; a non-zero result prints *stop_message* and stops the loop
    when *stop_on_error*.

    Each project is introduced by ``======== <project> ========`` (``======== <project> (<header_info>)
    ========`` when *header_info* is given), by the numbered banner carrying *banner_info* when that
    is given, or by *announce* (``test-gen``'s ``Running test-gen for <project> ...``) when that is given.

    Returns project -> passed, for the projects that ran.
    """
    results: dict[str, bool] = {}
    for index, project in enumerate(projects, start=1):
        if announce is not None:
            announce(index, len(projects), project)
        elif banner_info is None:
            label = project if header_info is None else f"{project} ({header_info})"
            print("")
            print(f"{_HEADER_RULE} {label} {_HEADER_RULE}")
        else:
            print_project_banner(index, len(projects), project, banner_info)
        passed = run_one(project) == 0
        results[project] = passed
        if not passed and stop_on_error:
            print(stop_message)
            break
    return results


def print_summary(
    title: str,
    results: Mapping[str, bool],
    details: Mapping[str, str] = _NO_DETAILS,
    *,
    framed: bool = False,
    pass_label: str = _PASS_LABEL,
    count_label: str = _PASSED_COUNT_LABEL,
    total: int | None = None,
    separator: str = SUMMARY_SEPARATOR,
) -> int:
    """*title* (between two 40-``=`` rules when *framed*), then `` <pass_label> : <project>`` /
    `` [FAIL] : <project>`` sorted by name (the label and the name joined by *separator*; a project's
    detail on the line under it when given), then ``Total: <total> | <count_label>: <n> | Failed: <n>``
    after a blank line when *total* is given; 0 when every project passed, else 1.

    Every package name is lower-case, so ``sorted`` orders them as PowerShell's ``Sort-Object`` does.
    """
    print("")
    if framed:
        print(_BANNER_RULE)
        print(title)
        print(_BANNER_RULE)
    else:
        print(title)
    for project in sorted(results):
        print(f" {pass_label if results[project] else _FAIL_LABEL}{separator}{project}")
        if project in details:
            print(f"{_DETAIL_INDENT}{details[project]}")
    failed = sum(1 for passed in results.values() if not passed)
    if total is not None:
        print("")
        print(f"Total: {total} | {count_label}: {len(results) - failed} | Failed: {failed}")
    return EXIT_FAILED if failed else EXIT_PASSED


def print_stderr(text: str) -> None:
    """*text* on stderr, after whatever stdout holds: a ``2>&1`` capture keeps the order the lines were
    printed in, as it did when a script's tool ran as a child process."""
    sys.stdout.flush()
    print(text, file=sys.stderr, flush=True)


def line_buffered_stdout() -> None:
    """Flush stdout at every line end, for a run whose tool prints to stdout and stderr in many places: a
    ``2>&1`` capture keeps the order the lines were printed in, as it did when the tool ran as a child
    process. A stdout that is not a text stream (a self-test's capture) is left as it is."""
    if isinstance(sys.stdout, io.TextIOWrapper):
        sys.stdout.reconfigure(line_buffering=True)


def plant_workspace(root: Path) -> Path:
    """A workspace under *root* for a metrics self-test: ``datrix-a`` (src/, tests/, pyproject.toml),
    ``datrix-b`` (src/ only) and a ``datrix`` showcase directory."""
    full = root / _PLANTED_FULL
    for subdir in (PackageMarker.SRC, PackageMarker.TESTS):
        (full / subdir.value).mkdir(parents=True)
    (full / PackageMarker.PYPROJECT.value).write_text("[project]\nname = 'datrix-a'\n", encoding="utf-8")
    (root / _PLANTED_SRC_ONLY / PackageMarker.SRC.value).mkdir(parents=True)
    (root / SHOWCASE).mkdir()
    return root


# ---------------------------------------------------------------------------
# Self-test
# ---------------------------------------------------------------------------

_SELF_TEST_USAGE: Final = ("Usage:", " .\\tool.ps1 <project-name> [options]")


def _parse(argv: Sequence[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    add_project_arguments(parser)
    return parser.parse_args(list(argv))


def printed_lines(print_it: Callable[[], object]) -> tuple[list[str], object]:
    """The lines *print_it* prints to stdout, and what it returns (for the metrics modules' self-tests)."""
    printed = io.StringIO()
    with contextlib.redirect_stdout(printed):
        returned = print_it()
    return printed.getvalue().splitlines(), returned


def _refusal_lines(
    argv: Sequence[str], workspace: Path, wording: SelectionWording = DEFAULT_WORDING
) -> tuple[str, ...]:
    try:
        select_projects(_parse(argv), workspace, usage=_SELF_TEST_USAGE, wording=wording)
    except ProjectSelectionError as exc:
        return exc.lines
    raise AssertionError(f"selecting {list(argv)} must be refused")


def _check_all_selects_every_package_but_the_showcase() -> None:
    with tempfile.TemporaryDirectory(prefix=_SELF_TEST_PREFIX) as tmp:
        workspace = plant_workspace(Path(tmp))
        selected = select_projects(_parse(["--all"]), workspace, usage=_SELF_TEST_USAGE)
        assert selected == [_PLANTED_FULL, _PLANTED_SRC_ONLY], selected


def _check_any_of_filters_by_marker() -> None:
    with tempfile.TemporaryDirectory(prefix=_SELF_TEST_PREFIX) as tmp:
        workspace = plant_workspace(Path(tmp))
        selected = select_projects(
            _parse(["--all"]), workspace, usage=_SELF_TEST_USAGE, any_of=frozenset({PackageMarker.PYPROJECT})
        )
        assert selected == [_PLANTED_FULL], selected


def _check_a_folder_path_names_its_package() -> None:
    with tempfile.TemporaryDirectory(prefix=_SELF_TEST_PREFIX) as tmp:
        workspace = plant_workspace(Path(tmp))
        existing = f"{workspace / _PLANTED_FULL}{os.sep}"
        missing = f"D:\\x\\{_PLANTED_MISSING}\\"
        args = _parse([existing, f"--projects={missing}"])
        assert requested_projects(args) == [_PLANTED_FULL, _PLANTED_MISSING], requested_projects(args)


def _check_showcase_alone_is_refused_with_exit_one_lines() -> None:
    with tempfile.TemporaryDirectory(prefix=_SELF_TEST_PREFIX) as tmp:
        lines = _refusal_lines([SHOWCASE], plant_workspace(Path(tmp)))
        assert any("datrix excluded" in line for line in lines), lines
    assert EXIT_FAILED == 1, "a selection refusal exits 1, never the usage code 2"


def _check_nothing_given_prints_usage_and_available() -> None:
    with tempfile.TemporaryDirectory(prefix=_SELF_TEST_PREFIX) as tmp:
        lines = _refusal_lines([], plant_workspace(Path(tmp)))
        for usage_line in _SELF_TEST_USAGE:
            assert usage_line in lines, lines
        header = lines.index("Available projects:")
        assert f" - {_PLANTED_FULL}" in lines[header + 1 :], lines
        assert f" - {SHOWCASE}" not in lines, lines


def _check_stop_on_error_stops_after_the_first_failure() -> None:
    def run_one(project: str) -> int:
        return 1 if project == _PLANTED_FULL else 0

    projects = [_PLANTED_FULL, _PLANTED_SRC_ONLY]
    with contextlib.redirect_stdout(io.StringIO()):
        stopped = run_projects(projects, run_one, stop_on_error=True)
        continued = run_projects(projects, run_one, stop_on_error=False)
    assert stopped == {_PLANTED_FULL: False}, stopped
    assert continued == {_PLANTED_FULL: False, _PLANTED_SRC_ONLY: True}, continued


def _check_summary_exit_code() -> None:
    printed = io.StringIO()
    with contextlib.redirect_stdout(printed):
        failed = print_summary("Summary", {_PLANTED_SRC_ONLY: False, _PLANTED_FULL: True}, {_PLANTED_FULL: "ok"})
        passed = print_summary("Summary", {_PLANTED_FULL: True})
    assert failed == EXIT_FAILED and passed == EXIT_PASSED, (failed, passed)
    text = printed.getvalue()
    assert f"{_FAIL_LABEL} : {_PLANTED_SRC_ONLY}" in text, text
    assert text.index(f": {_PLANTED_FULL}") < text.index(f": {_PLANTED_SRC_ONLY}"), text
    assert f"{_DETAIL_INDENT}ok" in text, text


def _check_code_shape_none_valid_wording() -> None:
    with tempfile.TemporaryDirectory(prefix=_SELF_TEST_PREFIX) as tmp:
        lines = _refusal_lines([SHOWCASE], plant_workspace(Path(tmp)), CODE_SHAPE_WORDING)
    assert list(lines) == ["ERROR: No valid projects specified (datrix is excluded)."], lines


def _check_code_shape_none_found_wording() -> None:
    with tempfile.TemporaryDirectory(prefix=_SELF_TEST_PREFIX) as tmp:
        lines = _refusal_lines(["--all"], Path(tmp), CODE_SHAPE_WORDING)
        assert list(lines) == [f"ERROR: No Datrix projects found in: {tmp}"], lines
        default_lines = _refusal_lines(["--all"], Path(tmp))
        assert list(default_lines) == [f"ERROR: No Datrix projects in: {tmp}"], default_lines


def _check_code_shape_usage_lists_available() -> None:
    with tempfile.TemporaryDirectory(prefix=_SELF_TEST_PREFIX) as tmp:
        lines = _refusal_lines([], plant_workspace(Path(tmp)), CODE_SHAPE_WORDING)
    expected = [
        "",
        "ERROR: No projects specified.",
        "",
        *_SELF_TEST_USAGE,
        "",
        "Available projects:",
        f" - {_PLANTED_FULL}",
        f" - {_PLANTED_SRC_ONLY}",
        "",
    ]
    assert list(lines) == expected, lines


def _check_no_available_package_prints_no_available_heading() -> None:
    with tempfile.TemporaryDirectory(prefix=_SELF_TEST_PREFIX) as tmp:
        lines = _refusal_lines([], Path(tmp), CODE_SHAPE_WORDING)
    assert list(lines) == ["", "ERROR: No projects specified.", "", *_SELF_TEST_USAGE, "", ""], lines


def _check_list_available_false_prints_usage_only() -> None:
    with tempfile.TemporaryDirectory(prefix=_SELF_TEST_PREFIX) as tmp:
        lines = _refusal_lines([], plant_workspace(Path(tmp)), USAGE_ONLY_WORDING)
    assert list(lines) == list(_SELF_TEST_USAGE), lines
    assert _AVAILABLE_HEADING not in lines, lines


def _check_project_banner_lines() -> None:
    lines, _ = printed_lines(lambda: print_project_banner(2, 3, _PLANTED_FULL, "mode=check"))
    expected = ["", "=" * 40, f"[2/3] {_PLANTED_FULL} (mode=check)", "=" * 40, ""]
    assert lines == expected, lines


def _check_run_projects_banner_info_and_stop_message() -> None:
    def run_one(project: str) -> int:
        return 1 if project == _PLANTED_FULL else 0

    projects = [_PLANTED_FULL, _PLANTED_SRC_ONLY]
    lines, _ = printed_lines(
        lambda: run_projects(
            projects, run_one, stop_on_error=True, banner_info="format=json", stop_message=STOP_MESSAGE_FLAG
        )
    )
    expected = ["", "=" * 40, f"[1/2] {_PLANTED_FULL} (format=json)", "=" * 40, "", STOP_MESSAGE_FLAG]
    assert lines == expected, lines
    plain, _ = printed_lines(lambda: run_projects([_PLANTED_FULL], run_one, stop_on_error=True))
    assert plain == ["", f"{_HEADER_RULE} {_PLANTED_FULL} {_HEADER_RULE}", STOP_MESSAGE], plain
    informed, _ = printed_lines(
        lambda: run_projects([_PLANTED_SRC_ONLY], run_one, stop_on_error=True, header_info="mode=check, src")
    )
    assert informed == ["", f"{_HEADER_RULE} {_PLANTED_SRC_ONLY} (mode=check, src) {_HEADER_RULE}"], informed


def _check_announce_replaces_the_header() -> None:
    def announce(index: int, total: int, project: str) -> None:
        print(f"[{index}/{total}] Running for {project}")

    lines, results = printed_lines(
        lambda: run_projects(
            [_PLANTED_SRC_ONLY, _PLANTED_FULL],
            lambda project: 1 if project == _PLANTED_FULL else 0,
            stop_on_error=True,
            announce=announce,
        )
    )
    expected = [f"[1/2] Running for {_PLANTED_SRC_ONLY}", f"[2/2] Running for {_PLANTED_FULL}", STOP_MESSAGE]
    assert lines == expected, lines
    assert results == {_PLANTED_SRC_ONLY: True, _PLANTED_FULL: False}, results


def _check_framed_summary_with_total() -> None:
    results = {_PLANTED_SRC_ONLY: False, _PLANTED_FULL: True}
    lines, returned = printed_lines(
        lambda: print_summary("Complexity Summary (mode=check)", results, framed=True, total=2)
    )
    expected = [
        "",
        "=" * 40,
        "Complexity Summary (mode=check)",
        "=" * 40,
        f" [PASS] : {_PLANTED_FULL}",
        f" [FAIL] : {_PLANTED_SRC_ONLY}",
        "",
        "Total: 2 | Passed: 1 | Failed: 1",
    ]
    assert lines == expected, lines
    assert returned == EXIT_FAILED, returned


def _check_fix_summary_labels() -> None:
    lines, returned = printed_lines(
        lambda: print_summary(
            "Complexity Summary (mode=check)",
            {_PLANTED_FULL: True},
            framed=True,
            pass_label=DONE_LABEL,
            count_label=COMPLETED_COUNT_LABEL,
            total=1,
        )
    )
    assert f" [DONE] : {_PLANTED_FULL}" in lines, lines
    assert lines[-1] == "Total: 1 | Completed: 1 | Failed: 0", lines
    assert returned == EXIT_PASSED, returned


def _check_unframed_summary_without_total_prints_no_total() -> None:
    lines, _ = printed_lines(lambda: print_summary("Duplicate-Code Summary", {_PLANTED_FULL: True}))
    assert lines == ["", "Duplicate-Code Summary", f" [PASS] : {_PLANTED_FULL}"], lines


def _check_summary_separator() -> None:
    results = {_PLANTED_SRC_ONLY: False, _PLANTED_FULL: True}
    lines, _ = printed_lines(lambda: print_summary("Test Generation Summary", results, separator=" "))
    assert lines == ["", "Test Generation Summary", f" [PASS] {_PLANTED_FULL}", f" [FAIL] {_PLANTED_SRC_ONLY}"], lines


def _check_available_heading_wording() -> None:
    wording = SelectionWording(
        none_found=DEFAULT_WORDING.none_found,
        none_valid=DEFAULT_WORDING.none_valid,
        none_given_heading=("",),
        list_available=True,
        available_heading="Available packages:",
    )
    with tempfile.TemporaryDirectory(prefix=_SELF_TEST_PREFIX) as tmp:
        workspace = plant_workspace(Path(tmp))
        try:
            select_projects(
                _parse([]), workspace, usage=_SELF_TEST_USAGE, any_of=frozenset({PackageMarker.PYPROJECT}),
                wording=wording,
            )
        except ProjectSelectionError as exc:
            lines = list(exc.lines)
        else:
            raise AssertionError("an empty selection must be refused")
    assert lines == ["", *_SELF_TEST_USAGE, "", "Available packages:", f" - {_PLANTED_FULL}", ""], lines


SELF_TEST_CHECKS: Final[tuple[CheckFunc, ...]] = (
    _check_all_selects_every_package_but_the_showcase,
    _check_any_of_filters_by_marker,
    _check_a_folder_path_names_its_package,
    _check_showcase_alone_is_refused_with_exit_one_lines,
    _check_nothing_given_prints_usage_and_available,
    _check_stop_on_error_stops_after_the_first_failure,
    _check_summary_exit_code,
    _check_code_shape_none_valid_wording,
    _check_code_shape_none_found_wording,
    _check_code_shape_usage_lists_available,
    _check_no_available_package_prints_no_available_heading,
    _check_list_available_false_prints_usage_only,
    _check_project_banner_lines,
    _check_run_projects_banner_info_and_stop_message,
    _check_announce_replaces_the_header,
    _check_framed_summary_with_total,
    _check_fix_summary_labels,
    _check_unframed_summary_without_total_prints_no_total,
    _check_summary_separator,
    _check_available_heading_wording,
)


if __name__ == "__main__":
    sys.exit(EXIT_PASSED if run_checks(SELF_TEST_CHECKS) else EXIT_FAILED)
