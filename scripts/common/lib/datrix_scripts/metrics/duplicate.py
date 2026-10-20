"""
Run Pylint duplicate-code detection (R0801) on Datrix project(s) Python code.

``scripts/metrics/duplicate.ps1`` (and its ``.sh`` twin) runs this module; ``dev/code_scan.py`` imports its
Pylint run and parser. Each selected project with a ``src/`` is scanned on its own (``--projects`` / ``--all``),
or every repository is scanned as one run (``--mono``). By default a scan reads ``src/``; with ``--tests`` it
reads ``src/`` and ``tests/`` together. A project passes when Pylint reports no duplicate above the threshold.

Exit codes: 0 = no duplicates (or nothing with a ``src/`` to scan); 1 = duplicates found, a refused selection,
or Pylint could not run; 2 = a usage error.

Usage (PYTHONPATH=scripts/common/lib; the wrapper sets it):
    python -m datrix_scripts.metrics.duplicate datrix-common
    python -m datrix_scripts.metrics.duplicate datrix-common --min-lines=6 --tests
    python -m datrix_scripts.metrics.duplicate --mono
    python -m datrix_scripts.metrics.duplicate --self-test
"""

from __future__ import annotations

import argparse
import contextlib
import importlib.util
import io
import os
import re
import subprocess
import sys
import tempfile
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Final

from datrix_scripts.framework_repos import PackageMarker, workspace_package_dirs
from datrix_scripts.gate_harness import write_files
from datrix_scripts.local_llm import (
    ChatRequest,
    LocalLlmSettings,
    add_wrapper_llm_arguments,
    advisory_text,
    wrapper_llm_settings,
)
from datrix_scripts.metrics.projects import (
    EXIT_FAILED,
    EXIT_PASSED,
    USAGE_ONLY_WORDING,
    ProjectSelectionError,
    add_project_arguments,
    plant_workspace,
    print_stderr,
    print_summary,
    run_projects,
    select_projects,
)
from datrix_scripts.paths import WORKSPACE_DIR
from datrix_scripts.test.wrappers import METRICS_SCRIPTS_DIR, module_main, run_self_test
from datrix_scripts.venv import PACKAGE_DEV_EXTRAS, missing_declared_tool

MODULE: Final = "datrix_scripts.metrics.duplicate"
WRAPPER: Final = "duplicate"

# Pylint runs as a module of this interpreter, so the shared venv's copy is the one that scans.
_PYLINT_MODULE = "pylint"
DEFAULT_MIN_LINES = 4
#: A multi-root (--mono) run's threshold unless --min-lines is given: cross-language pairs stay unreported.
MONO_MIN_LINES: Final = 30
_MIN_LINES_FLOOR: Final = 2
DEFAULT_LLM_NUM_PREDICT = 4096
DEFAULT_LLM_TEMPERATURE = 0.1
DEFAULT_LLM_GROUP_LIMIT = 20
DEFAULT_LLM_TIMEOUT_SECONDS: Final = 180
_EVIDENCE_CHARS: Final = 5000
EXIT_PYLINT_MISSING: Final = 2

USAGE_LINES: Final = (
    "Usage: .\\duplicate.ps1 <project> [options] or .\\duplicate.ps1 -All [options] or .\\duplicate.ps1 -Mono [options]",
    " -MinLines N -Tests -StopOnError -VerboseOutput",
)
ALL_AND_MONO: Final = "Error: -All and -Mono are mutually exclusive. Use one or the other."
NO_MONO_PROJECTS: Final = "ERROR: No mono project directories found under: {workspace}"
NOTHING_TO_SCAN: Final = "No projects with src/ to scan."
MONO_RESULT: Final = "mono"
SUMMARY_TITLE: Final = "Duplicate-Code Summary"
_SRC_DIR: Final = PackageMarker.SRC.value
_TESTS_DIR: Final = PackageMarker.TESTS.value

_DUPLICATE_START_RE = re.compile(
    r"^(.+?):(\d+):(?:(\d+):)? R0801: Similar lines in (\d+) files"
)
_DUPLICATE_FILE_RE = re.compile(r"^==(.+):\[(\d+):(\d+)\]")


class DuplicateScanError(RuntimeError):
    """Pylint could not run the duplicate-code check; the message says why."""


@dataclass(frozen=True)
class ScanOptions:
    """What every scan of one run shares: the wrapper's ``-MinLines``, ``-Tests``, ``-VerboseOutput`` and
    the advisory refactor plan."""

    min_lines: int | None
    tests: bool
    verbose: bool
    llm_refactor_plan: bool
    llm_limit: int
    llm_num_predict: int
    llm_temperature: float
    llm_settings: LocalLlmSettings


def run_pylint_duplicates(scan_paths: list[Path], min_lines: int, cwd: Path) -> subprocess.CompletedProcess[str]:
    """Run Pylint's R0801 duplicate-code check over ``scan_paths``.

    Raises DuplicateScanError when this interpreter cannot import Pylint.
    """
    if importlib.util.find_spec(_PYLINT_MODULE) is None:
        raise DuplicateScanError(missing_declared_tool("pylint", PACKAGE_DEV_EXTRAS))
    cmd = [sys.executable, "-m", _PYLINT_MODULE, "--disable=all", "--enable=R0801",
           f"--min-similarity-lines={min_lines}", *(str(path) for path in scan_paths)]
    # Pylint R0801 embeds source snippets; Windows cp1252 stdout raises UnicodeEncodeError.
    child_env = {**os.environ, "PYTHONUTF8": "1", "PYTHONIOENCODING": "utf-8"}
    return subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace",
                          cwd=str(cwd), env=child_env, check=False)


def parse_duplicate_groups(pylint_output: str) -> list[dict[str, object]]:
    """Parse Pylint R0801 output into duplicate groups."""
    groups: list[dict[str, object]] = []
    current: dict[str, object] | None = None
    current_lines: list[str] = []

    for line in pylint_output.splitlines():
        start_match = _DUPLICATE_START_RE.match(line)
        if start_match:
            if current is not None:
                current["raw"] = "\n".join(current_lines).strip()
                groups.append(current)
            file_path, line_number, _column, file_count = start_match.groups()
            current = {
                "reported_file": file_path,
                "reported_line": int(line_number),
                "file_count": int(file_count),
                "locations": [],
            }
            current_lines = [line]
            continue

        if current is None:
            continue

        current_lines.append(line)
        location_match = _DUPLICATE_FILE_RE.match(line)
        if location_match:
            file_path, start_line, end_line = location_match.groups()
            locations = current["locations"]
            if isinstance(locations, list):
                locations.append({
                    "file": file_path,
                    "start_line": int(start_line),
                    "end_line": int(end_line),
                })

    if current is not None:
        current["raw"] = "\n".join(current_lines).strip()
        groups.append(current)

    return groups


def _build_llm_refactor_prompt(
    groups: list[dict[str, object]],
    project_roots: list[Path],
    min_lines: int,
    include_tests: bool,
    limit: int,
) -> str:
    """Build a compact advisory prompt from deterministic duplicate groups."""
    selected = groups[: max(0, limit)]
    parts: list[str] = [
        "Review these deterministic Pylint R0801 duplicate-code groups for Datrix.",
        "",
        "Datrix is a backend microservices application generator with separate Python, TypeScript, cloud, and deployment codegen packages.",
        "",
        "For each duplicate group, assess:",
        "- whether duplication is likely intentional parity",
        "- whether a shared helper or extraction is reasonable",
        "- the risk of over-abstraction",
        "",
        "Local rule:",
        "- Do not recommend collapsing language-parity implementations unless the shared abstraction already exists or the extraction is clearly low-risk.",
        "",
        "Guardrails:",
        "- Advisory only. Do not say to edit, delete, or refactor automatically.",
        "- Preserve the deterministic Pylint findings; this review only prioritizes follow-up.",
        "- If evidence is insufficient, say what local context should be inspected before action.",
        "",
        "Return markdown with:",
        "1. Overall duplicate-code triage summary.",
        "2. A table with columns: group, files, parity assessment, possible extraction, over-abstraction risk, recommended next action.",
        "",
        f"project_roots: {[str(root) for root in project_roots]}",
        f"min_similarity_lines: {min_lines}",
        f"tests_included: {include_tests}",
        "",
        "Duplicate groups:",
    ]

    if not selected:
        parts.append("No duplicate groups were reported.")
        return "\n".join(parts)

    for index, group in enumerate(selected, start=1):
        parts.extend([
            "",
            f"### Group {index}",
            f"reported_file: {group['reported_file']}",
            f"reported_line: {group['reported_line']}",
            f"file_count: {group['file_count']}",
            "locations:",
        ])
        locations = group["locations"]
        for location in locations if isinstance(locations, list) else []:
            parts.append(f"- {location['file']}:[{location['start_line']}:{location['end_line']}]")
        raw = str(group["raw"]).strip()
        if raw:
            parts.extend(["pylint_evidence:", "```text", raw[:_EVIDENCE_CHARS], "```"])

    return "\n".join(parts)


def _run_llm_refactor_plan(
    groups: list[dict[str, object]], project_roots: list[Path], min_lines: int, options: ScanOptions
) -> str:
    """Run advisory local LLM planning over duplicate-code groups."""
    prompt = _build_llm_refactor_prompt(groups, project_roots, min_lines, options.tests, options.llm_limit)
    request = ChatRequest(
        system=(
            "You are reviewing duplicate-code findings for refactor planning. "
            "You do not edit files or override Pylint. You produce advisory markdown only."
        ),
        user=prompt,
        temperature=options.llm_temperature,
        max_tokens=options.llm_num_predict,
    )
    return advisory_text(options.llm_settings, request, "LLM refactor plan")


def _scan_paths(project_roots: list[Path], include_tests: bool) -> list[Path]:
    """Each root's ``src/`` (and ``tests/`` with *include_tests*), warning on stderr for what is missing."""
    scan_paths: list[Path] = []
    for project_root in project_roots:
        src_dir = project_root / _SRC_DIR
        if not src_dir.is_dir():
            print_stderr(f"Warning: skipping {project_root} (no src/)")
            continue
        scan_paths.append(src_dir)
        if not include_tests:
            continue
        tests_dir = project_root / _TESTS_DIR
        if tests_dir.is_dir():
            scan_paths.append(tests_dir)
        else:
            print_stderr(f"Warning: --tests specified but no tests/ in {project_root}")
    return scan_paths


def effective_min_lines(min_lines: int | None, root_count: int) -> int:
    """The Pylint threshold: *min_lines* when given (never below 2), else 4 -- or 30 for a multi-root run.

    Keyed on whether ``--min-lines`` was given, never on its value: an explicit 4 reports at 4 on a mono run.
    """
    if min_lines is not None:
        return max(_MIN_LINES_FLOOR, min_lines)
    return MONO_MIN_LINES if root_count > 1 else DEFAULT_MIN_LINES


def _print_refactor_plan(
    stdout: str, project_roots: list[Path], min_lines: int, options: ScanOptions
) -> None:
    groups = parse_duplicate_groups(stdout)
    print("\n---\n## Local LLM Advisory Refactor Plan\n")
    print("This section is advisory only. It does not change deterministic Pylint findings or authorize refactoring.\n")
    if not groups:
        print("No duplicate-code groups were available for advisory review.")
        return
    print(_run_llm_refactor_plan(groups, project_roots, min_lines, options))


def scan_duplicates(project_roots: list[Path], options: ScanOptions) -> int:
    """One Pylint duplicate-code run over *project_roots*; Pylint's exit code (0: none found)."""
    roots = [root.resolve() for root in project_roots]
    for root in roots:
        if not root.is_dir():
            print_stderr(f"Error: project root is not a directory: {root}")
            return EXIT_FAILED
    scan_paths = _scan_paths(roots, options.tests)
    if not scan_paths:
        print_stderr("Error: no project has src/ to scan.")
        return EXIT_FAILED

    min_lines = effective_min_lines(options.min_lines, len(roots))
    print_stderr(f"Effective min-similarity-lines: {min_lines}")
    try:
        result = run_pylint_duplicates(scan_paths, min_lines, roots[0])
    except DuplicateScanError as exc:
        print_stderr(f"Error: {exc}")
        return EXIT_PYLINT_MISSING

    if result.returncode != 0 and result.stdout:
        print(result.stdout, end="")
    if result.stderr:
        sys.stdout.flush()
        print(result.stderr, end="", file=sys.stderr, flush=True)
    elif result.stdout and options.verbose and result.returncode == 0:
        print(result.stdout, end="")

    if options.llm_refactor_plan:
        _print_refactor_plan(result.stdout or "", roots, min_lines, options)
    return result.returncode


def build_parser() -> argparse.ArgumentParser:
    """The options of ``metrics/duplicate.ps1``: one per wrapper parameter, spelled exactly."""
    parser = argparse.ArgumentParser(
        description="Pylint duplicate-code detection (R0801) for one or more Datrix projects.",
        allow_abbrev=False,
    )
    parser.set_defaults(debug=False)
    add_project_arguments(parser)
    parser.add_argument(
        "--mono",
        action="store_true",
        help="One run across the whole monorepo (datrix + every datrix-* package); not with --all.",
    )
    parser.add_argument(
        "--min-lines",
        type=int,
        default=None,
        metavar="N",
        help=f"Minimum similar lines to report (default: {DEFAULT_MIN_LINES}; {MONO_MIN_LINES} for --mono).",
    )
    parser.add_argument("--tests", action="store_true", help="Also include tests/ in duplicate-code detection.")
    parser.add_argument("--stop-on-error", action="store_true", help="Stop on the first project that fails.")
    parser.add_argument("--verbose-output", action="store_true", help="Print Pylint's output for a clean run too.")
    parser.add_argument(
        "--llm-refactor-plan",
        action="store_true",
        help="Add an advisory local LLM refactor plan for duplicate-code groups.",
    )
    parser.add_argument(
        "--llm-limit",
        type=int,
        default=DEFAULT_LLM_GROUP_LIMIT,
        metavar="N",
        help=f"Maximum duplicate groups to include in LLM plan (default: {DEFAULT_LLM_GROUP_LIMIT}).",
    )
    parser.add_argument(
        "--llm-num-predict",
        type=int,
        default=DEFAULT_LLM_NUM_PREDICT,
        metavar="N",
        help=f"Max generated tokens for LLM plan (default: {DEFAULT_LLM_NUM_PREDICT}).",
    )
    parser.add_argument(
        "--llm-temperature",
        type=float,
        default=DEFAULT_LLM_TEMPERATURE,
        metavar="FLOAT",
        help=f"Sampling temperature for LLM plan (default: {DEFAULT_LLM_TEMPERATURE}).",
    )
    add_wrapper_llm_arguments(parser, timeout_seconds=DEFAULT_LLM_TIMEOUT_SECONDS)
    parser.add_argument("--self-test", action="store_true", help="Run only the self-test over planted packages.")
    return parser


def _scan_options(args: argparse.Namespace) -> ScanOptions:
    return ScanOptions(
        min_lines=args.min_lines,
        tests=args.tests,
        verbose=args.verbose_output,
        llm_refactor_plan=args.llm_refactor_plan,
        llm_limit=args.llm_limit,
        llm_num_predict=args.llm_num_predict,
        llm_temperature=args.llm_temperature,
        llm_settings=wrapper_llm_settings(args),
    )


def _selected(args: argparse.Namespace, workspace: Path) -> list[str]:
    """The projects to scan and the line announcing them.

    Raises:
        ProjectSelectionError: ``--all`` with ``--mono``, or an empty selection (the wrapper's wording).
    """
    if args.all and args.mono:
        raise ProjectSelectionError([ALL_AND_MONO])
    if args.mono:
        found = [path.name for path in workspace_package_dirs(workspace, include_showcase=True)]
        if not found:
            raise ProjectSelectionError([NO_MONO_PROJECTS.format(workspace=workspace)])
        print(f"Running duplicate-code detection across monorepo (Mono): {', '.join(found)}")
        return found
    projects = select_projects(args, workspace, usage=USAGE_LINES, wording=USAGE_ONLY_WORDING)
    scope = " all projects" if args.all else ""
    print(f"Running duplicate-code detection for{scope}: {', '.join(projects)}")
    return projects


def _with_src(projects: list[str], workspace: Path) -> list[str]:
    """The projects holding a ``src/``; each one without is named as skipped."""
    kept: list[str] = []
    for project in projects:
        if (workspace / project / _SRC_DIR).is_dir():
            kept.append(project)
        else:
            print(f"Skipping {project} (no src/ directory)")
    return kept


def run_duplicate(args: argparse.Namespace, workspace: Path) -> int:
    """The wrapper's run over *workspace*: select, skip what has no ``src/``, scan, summarize."""
    try:
        projects = _with_src(_selected(args, workspace), workspace)
    except ProjectSelectionError as exc:
        for line in exc.lines:
            print(line)
        return EXIT_FAILED
    if not projects:
        print(NOTHING_TO_SCAN)
        return EXIT_PASSED

    options = _scan_options(args)
    if args.mono:
        print("")
        print(f"======== {MONO_RESULT} (all projects) ========")
        roots = [workspace / project for project in projects]
        results = {MONO_RESULT: scan_duplicates(roots, options) == 0}
    else:
        results = run_projects(
            projects, lambda project: scan_duplicates([workspace / project], options), stop_on_error=args.stop_on_error
        )
    return print_summary(SUMMARY_TITLE, results)


# ---------------------------------------------------------------------------
# Self-test
# ---------------------------------------------------------------------------

_DUPLICATED_BODY: Final = (
    "def {name}(values: list[int]) -> int:\n"
    "    total = 0\n"
    "    for value in values:\n"
    "        if value > 10:\n"
    "            total += value * 2\n"
    "        else:\n"
    "            total -= value\n"
    "    return total\n"
)


def _printed_by_run(argv: Sequence[str], workspace: Path) -> tuple[int, list[str]]:
    """The exit code of ``run_duplicate`` on *argv* over *workspace*, and the lines it printed to stdout."""
    printed = io.StringIO()
    with contextlib.redirect_stdout(printed), contextlib.redirect_stderr(io.StringIO()):
        code = run_duplicate(build_parser().parse_args(list(argv)), workspace)
    return code, printed.getvalue().splitlines()


def _check_all_and_mono_are_refused() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        code, lines = _printed_by_run(["--all", "--mono"], plant_workspace(Path(tmp)))
    assert (code, lines) == (EXIT_FAILED, [ALL_AND_MONO]), (code, lines)


def _check_nothing_given_prints_the_two_usage_lines() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        code, lines = _printed_by_run([], plant_workspace(Path(tmp)))
    assert (code, lines) == (EXIT_FAILED, list(USAGE_LINES)), (code, lines)


def _check_showcase_alone_is_refused() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        code, lines = _printed_by_run(["datrix"], plant_workspace(Path(tmp)))
    assert (code, lines) == (EXIT_FAILED, ["ERROR: No valid projects (datrix excluded)."]), (code, lines)


def _check_a_project_without_src_is_skipped_and_passes() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        code, lines = _printed_by_run(["datrix-q"], plant_workspace(Path(tmp)))
    expected = ["Running duplicate-code detection for: datrix-q", "Skipping datrix-q (no src/ directory)", NOTHING_TO_SCAN]
    assert (code, lines) == (EXIT_PASSED, expected), (code, lines)


def _check_mono_takes_the_showcase_first_and_skips_it_without_src() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        workspace = plant_workspace(Path(tmp))
        code, lines = _printed_by_run(["--mono"], workspace)
    assert lines[:2] == [
        "Running duplicate-code detection across monorepo (Mono): datrix, datrix-a, datrix-b",
        "Skipping datrix (no src/ directory)",
    ], lines
    assert lines[-2:] == [SUMMARY_TITLE, f" [PASS] : {MONO_RESULT}"], lines
    assert code == EXIT_PASSED, code


def _check_planted_duplicate_fails_its_project() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        workspace = plant_workspace(Path(tmp))
        write_files(workspace, {
            "datrix-a/src/one.py": _DUPLICATED_BODY.format(name="first"),
            "datrix-a/src/two.py": _DUPLICATED_BODY.format(name="second"),
        })
        code, lines = _printed_by_run(["datrix-a", "datrix-b"], workspace)
    assert code == EXIT_FAILED, (code, lines)
    assert any("R0801" in line for line in lines), lines
    assert lines[-3:] == [SUMMARY_TITLE, " [FAIL] : datrix-a", " [PASS] : datrix-b"], lines


def _check_mono_threshold_is_keyed_on_an_explicit_value() -> None:
    assert effective_min_lines(None, 1) == DEFAULT_MIN_LINES
    assert effective_min_lines(None, 3) == MONO_MIN_LINES
    assert effective_min_lines(DEFAULT_MIN_LINES, 3) == DEFAULT_MIN_LINES
    assert effective_min_lines(0, 1) == _MIN_LINES_FLOOR


_SELF_TEST_CHECKS: Final = (
    _check_all_and_mono_are_refused,
    _check_nothing_given_prints_the_two_usage_lines,
    _check_showcase_alone_is_refused,
    _check_a_project_without_src_is_skipped_and_passes,
    _check_mono_takes_the_showcase_first_and_skips_it_without_src,
    _check_planted_duplicate_fails_its_project,
    _check_mono_threshold_is_keyed_on_an_explicit_value,
)


def _run(args: argparse.Namespace) -> int:
    if args.self_test:
        return run_self_test(
            _SELF_TEST_CHECKS, wrapper=WRAPPER, module=MODULE, parser=build_parser(), folder=METRICS_SCRIPTS_DIR
        )
    return run_duplicate(args, WORKSPACE_DIR)


def main(argv: Sequence[str] | None = None) -> int:
    """Entry point."""
    return module_main(build_parser(), _run, argv)


if __name__ == "__main__":
    sys.exit(main())
