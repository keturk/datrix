"""
Count lines of code with pygount for each selected Datrix project's src/ tree.

``scripts/metrics/loc.ps1`` (and its ``.sh`` twin) runs this module. Each project (``--projects`` / ``--all``)
gets one pygount run over its ``src/``, printed in pygount's own ``summary``, ``cloc-xml`` or ``json`` format,
and a ``[PASS]``/``[FAIL]`` line. With ``--all`` every project that passed is counted a second time as JSON,
and the run prints a workspace-wide rollup (code, documentation, empty, source, string and file totals, and
the per-language sums) before the framed summary.

A report only: no count is compared with a limit. A project fails only when pygount cannot count it (no
``src/``, pygount missing from the shared venv, or pygount's own non-zero exit).

Exit codes: 0 = every project counted; 1 = a project failed, or a refused selection; 2 = a usage error.

Usage (PYTHONPATH=scripts/common/lib; the wrapper sets it):
    python -m datrix_scripts.metrics.loc datrix-common
    python -m datrix_scripts.metrics.loc datrix-common --format=json
    python -m datrix_scripts.metrics.loc --all --suffix=py
    python -m datrix_scripts.metrics.loc --self-test
"""

from __future__ import annotations

import argparse
import contextlib
import importlib.util
import io
import json
import os
import subprocess
import sys
import tempfile
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Final, TextIO

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
    print_summary,
    printed_lines,
    run_projects,
    select_projects,
)
from datrix_scripts.paths import WORKSPACE_DIR
from datrix_scripts.test.wrappers import METRICS_SCRIPTS_DIR, module_main, run_self_test
from datrix_scripts.venv import SCRIPTS_DEPENDENCY_GROUP, missing_declared_tool

MODULE: Final = "datrix_scripts.metrics.loc"
WRAPPER: Final = "loc"

# pygount runs as a module of this interpreter (its package has no __main__, its command module
# does), so the shared venv's copy counts -- never whichever pygount PATH finds first.
_PYGOUNT_PACKAGE: Final = "pygount"
_PYGOUNT_MODULE: Final = "pygount.command"
_CHILD_ENCODING: Final = "utf-8"
DEFAULT_IGNORE_DIRS: Final = ("tests", "test", "__pycache__", ".git", ".venv", "node_modules")
FORMAT_SUMMARY: Final = "summary"
FORMAT_JSON: Final = "json"
FORMATS: Final = (FORMAT_SUMMARY, "cloc-xml", FORMAT_JSON)
EXIT_PYGOUNT_MISSING: Final = 2
_RULE: Final = "=" * 40
_INDENT: Final = "  "
_LANGUAGE_RULE: Final = _INDENT + "-" * 76

#: The rollup's total lines: label, pygount ``summary`` key.
_SUMMARY_FIELDS: Final = (
    ("Code:", "totalCodeCount"),
    ("Documentation:", "totalDocumentationCount"),
    ("Empty:", "totalEmptyCount"),
    ("Source:", "totalSourceCount"),
    ("Strings:", "totalStringCount"),
    ("Files:", "totalFileCount"),
)
#: The per-language table's count columns: pygount ``languages[]`` keys, in column order.
_LANGUAGE_FIELDS: Final = ("fileCount", "codeCount", "documentationCount", "emptyCount")
_CODE_FIELD: Final = "codeCount"

USAGE_LINES: Final = (
    "Usage:",
    " .\\loc.ps1 <project-name> [options]",
    " .\\loc.ps1 <folder-path> [options]",
    " .\\loc.ps1 -All [options]",
    "",
    "Examples:",
    " .\\loc.ps1 datrix-common",
    " .\\loc.ps1 datrix-common -Format json",
    " .\\loc.ps1 -All -Suffix py",
    " .\\loc.ps1 datrix-language -Format cloc-xml",
    " .\\loc.ps1 datrix-common datrix-language -VerboseOutput",
    "",
    "Parameters:",
    " -Format summary | cloc-xml | json (default: summary)",
    " -Suffix Comma-separated suffixes to include (e.g. py,js)",
    " -All Run for all datrix-* projects",
    " -StopOnError Stop on first project failure",
    " -VerboseOutput Verbose output from the check script",
    " -Dbg Debug output",
)


class LocRollupError(ValueError):
    """A project's pygount JSON document does not have the shape the rollup reads; the message says where."""


def _echo(data: bytes, stream: TextIO) -> None:
    """pygount's UTF-8 *data* written to *stream* line by line, its line ends left to the stream (so a
    console gets the bytes pygount wrote); a last line without an end gets one (pygount's JSON has none), so
    the next line printed starts a line of its own."""
    sys.stdout.flush()
    text = data.decode(_CHILD_ENCODING).replace("\r\n", "\n")
    if text and not text.endswith("\n"):
        text += "\n"
    print(text, end="", file=stream, flush=True)


def run_pygount(project_root: Path, output_format: str, suffix: str, *, verbose: bool, echo: bool) -> tuple[int, bytes]:
    """One pygount run over *project_root*'s ``src/``: its exit code and stdout.

    With *echo* the stdout is printed. pygount's stderr is printed when *verbose* or when it fails; a refusal
    (pygount missing, no project root, no ``src/``) is printed on stderr with its exit code.
    """
    if importlib.util.find_spec(_PYGOUNT_PACKAGE) is None:
        print_stderr(missing_declared_tool(_PYGOUNT_PACKAGE, SCRIPTS_DEPENDENCY_GROUP))
        return EXIT_PYGOUNT_MISSING, b""
    root = project_root.resolve()
    if not root.is_dir():
        print_stderr(f"Error: project root is not a directory: {root}")
        return EXIT_FAILED, b""
    src = root / PackageMarker.SRC.value
    if not src.is_dir():
        print_stderr(f"Error: project has no src/ directory: {root}")
        return EXIT_FAILED, b""
    command = [
        sys.executable, "-m", _PYGOUNT_MODULE, "--format", output_format,
        "--folders-to-skip", ",".join(DEFAULT_IGNORE_DIRS), str(src),
    ]
    if suffix:
        command.extend(["--suffix", suffix])
    if verbose:
        print_stderr(f"Running: {' '.join(command)}")
    # pygount draws its summary with box characters: the child writes UTF-8, decoded here as UTF-8.
    child_env = {**os.environ, "PYTHONIOENCODING": _CHILD_ENCODING}
    result = subprocess.run(command, cwd=str(root), capture_output=True, env=child_env, check=False)
    if echo:
        _echo(result.stdout, sys.stdout)
    if result.stderr and (verbose or result.returncode != 0):
        _echo(result.stderr, sys.stderr)
    return result.returncode, result.stdout


def _object(value: object, where: str) -> Mapping[str, object]:
    if not isinstance(value, dict):
        raise LocRollupError(f"{where} is not a JSON object")
    return value


def _field(mapping: Mapping[str, object], key: str, where: str) -> object:
    if key not in mapping:
        raise LocRollupError(f"{where} has no '{key}'")
    return mapping[key]


def _count(mapping: Mapping[str, object], key: str, where: str) -> int:
    value = _field(mapping, key, where)
    if isinstance(value, bool) or not isinstance(value, int):
        raise LocRollupError(f"{where}.{key} is {value!r}, expected an integer")
    return value


def _language_counts(document: Mapping[str, object]) -> dict[str, dict[str, int]]:
    """The counts of each non-pseudo language of *document*, by language name."""
    languages = _field(document, "languages", "the document")
    if not isinstance(languages, list):
        raise LocRollupError("languages is not a JSON array")
    counts: dict[str, dict[str, int]] = {}
    for index, raw in enumerate(languages):
        where = f"languages[{index}]"
        entry = _object(raw, where)
        pseudo = _field(entry, "isPseudoLanguage", where)
        name = _field(entry, "language", where)
        if not isinstance(pseudo, bool) or not isinstance(name, str):
            raise LocRollupError(f"{where} has isPseudoLanguage={pseudo!r}, language={name!r}; expected a bool, a string")
        if not pseudo:
            counts[name] = {key: _count(entry, key, where) for key in _LANGUAGE_FIELDS}
    return counts


@dataclass
class LocRollup:
    """The workspace-wide sums of the projects' pygount JSON documents."""

    projects: int = 0
    totals: dict[str, int] = field(default_factory=lambda: {key: 0 for _, key in _SUMMARY_FIELDS})
    languages: dict[str, dict[str, int]] = field(default_factory=dict)

    def add(self, document_text: str) -> None:
        """Add one project's pygount JSON document; nothing is added when it does not parse.

        Raises:
            LocRollupError: The document is not JSON, or lacks a count the rollup reads.
        """
        try:
            document = _object(json.loads(document_text), "the document")
        except json.JSONDecodeError as exc:
            raise LocRollupError(f"not JSON: {exc}") from exc
        summary = _object(_field(document, "summary", "the document"), "summary")
        totals = {key: _count(summary, key, "summary") for _, key in _SUMMARY_FIELDS}
        languages = _language_counts(document)
        for key, value in totals.items():
            self.totals[key] += value
        for name, counts in languages.items():
            sums = self.languages.setdefault(name, {key: 0 for key in _LANGUAGE_FIELDS})
            for key, value in counts.items():
                sums[key] += value
        self.projects += 1

    def print(self) -> None:
        """The ``TOTAL (all projects)`` block: each total, then the languages by code lines, most first."""
        print("")
        print(_RULE)
        print(f"TOTAL (all projects) - LOC rollup ({self.projects} projects)")
        print(_RULE)
        for label, key in _SUMMARY_FIELDS:
            print(f"{_INDENT}{label:<17}{self.totals[key]:>16,}")
        if self.languages:
            print("")
            print(f"{_INDENT}Per language (non-pseudo, summed across projects):")
            print(f"{_INDENT}{'Language':<28} {'Files':>8} {'Code':>12} {'Comment':>12} {'Empty':>12}")
            print(_LANGUAGE_RULE)
            for name in sorted(self.languages, key=lambda language: (-self.languages[language][_CODE_FIELD], language)):
                files, code, comment, empty = (self.languages[name][key] for key in _LANGUAGE_FIELDS)
                print(f"{_INDENT}{name:<28} {files:>8,} {code:>12,} {comment:>12,} {empty:>12,}")
        print("")


def build_parser() -> argparse.ArgumentParser:
    """The options of ``metrics/loc.ps1``: one per wrapper parameter, spelled exactly."""
    parser = argparse.ArgumentParser(
        description="Pygount lines-of-code counts for one or more Datrix projects.",
        allow_abbrev=False,
    )
    add_project_arguments(parser)
    parser.add_argument(
        "--format", choices=FORMATS, default=FORMAT_SUMMARY, help=f"pygount's output format (default: {FORMAT_SUMMARY})."
    )
    parser.add_argument("--suffix", default="", help="Comma-separated file suffixes to include (e.g. py,js); empty = all.")
    parser.add_argument("--stop-on-error", action="store_true", help="Stop on the first project that fails.")
    parser.add_argument("--verbose-output", action="store_true", help="Print the pygount command and its stderr.")
    parser.add_argument(WRAPPER_DEBUG_FLAG, dest="debug", action="store_true", help="As --verbose-output, at DEBUG.")
    parser.add_argument("--self-test", action="store_true", help="Run only the self-test over planted packages.")
    return parser


def _add_to_rollup(rollup: LocRollup, project_root: Path, suffix: str, project: str) -> None:
    """The second, JSON pass of an ``--all`` run: *project*'s counts added to *rollup*, or a warning."""
    code, stdout = run_pygount(project_root, FORMAT_JSON, suffix, verbose=False, echo=False)
    text = stdout.decode(_CHILD_ENCODING).strip()
    if code != EXIT_PASSED or not text:
        print(f"[WARN] LOC rollup JSON failed for {project}; omitted from workspace total.")
        return
    try:
        rollup.add(text)
    except LocRollupError as exc:
        print(f"[WARN] Failed to parse LOC JSON for {project} : {exc}")


def run_loc(args: argparse.Namespace, workspace: Path) -> int:
    """The wrapper's run over *workspace*: select, count each project, the ``--all`` rollup, the summary."""
    try:
        projects = select_projects(args, workspace, usage=USAGE_LINES, wording=CODE_SHAPE_WORDING)
    except ProjectSelectionError as exc:
        for line in exc.lines:
            print(line)
        return EXIT_FAILED
    scope = "all projects" if args.all else "projects"
    print(f"Running LOC (format={args.format}) for {scope}: {', '.join(projects)}")

    verbose = args.verbose_output or args.debug
    rollup = LocRollup()

    def run_one(project: str) -> int:
        project_root = workspace / project
        code, _ = run_pygount(project_root, args.format, args.suffix, verbose=verbose, echo=True)
        print("")
        if code != EXIT_PASSED:
            print(f"[FAIL] LOC counting failed for {project} (exit code: {code})")
            return code
        print(f"[PASS] LOC counting passed for {project}")
        if args.all:
            _add_to_rollup(rollup, project_root, args.suffix, project)
        return EXIT_PASSED

    results = run_projects(
        projects,
        run_one,
        stop_on_error=args.stop_on_error,
        banner_info=f"format={args.format}",
        stop_message=STOP_MESSAGE_FLAG,
    )
    if args.all and rollup.projects:
        rollup.print()
    return print_summary(f"LOC Summary (format={args.format})", results, framed=True, total=len(projects))


# ---------------------------------------------------------------------------
# Self-test
# ---------------------------------------------------------------------------

_PLANTED_FILES: Final = {
    "datrix-a/src/one.py": "a = 1\nb = 2\nc = 3\n",
    "datrix-b/src/two.py": "d = 4\ne = 5\n",
}


def _printed_by_run(argv: Sequence[str], workspace: Path) -> tuple[int, list[str]]:
    """The exit code of ``run_loc`` on *argv* over *workspace*, and the lines it printed to stdout."""
    printed = io.StringIO()
    with contextlib.redirect_stdout(printed), contextlib.redirect_stderr(io.StringIO()):
        code = run_loc(build_parser().parse_args(list(argv)), workspace)
    return code, printed.getvalue().splitlines()


def _language(name: str, counts: Sequence[int], *, pseudo: bool = False) -> dict[str, object]:
    return {"language": name, "isPseudoLanguage": pseudo, **dict(zip(_LANGUAGE_FIELDS, counts, strict=True))}


def _document(totals: Sequence[int], languages: Sequence[dict[str, object]]) -> str:
    summary = dict(zip((key for _, key in _SUMMARY_FIELDS), totals, strict=True))
    return json.dumps({"summary": summary, "languages": list(languages)})


def _check_rollup_sums_documents_and_formats_thousands() -> None:
    rollup = LocRollup()
    rollup.add(_document([1_000_000, 5, 7, 11, 13, 3], [_language("Python", [3, 1_000_000, 5, 7]),
                                                         _language("__empty__", [1, 0, 0, 0], pseudo=True)]))
    rollup.add(_document([234_567, 1, 1, 1, 1, 2], [_language("Python", [1, 4, 0, 0]),
                                                    _language("Markdown", [1, 234_563, 1, 1])]))
    lines, _ = printed_lines(rollup.print)
    assert lines == [
        "",
        _RULE,
        "TOTAL (all projects) - LOC rollup (2 projects)",
        _RULE,
        "  Code:                   1,234,567",
        "  Documentation:                  6",
        "  Empty:                          8",
        "  Source:                        12",
        "  Strings:                       14",
        "  Files:                          5",
        "",
        "  Per language (non-pseudo, summed across projects):",
        "  Language                        Files         Code      Comment        Empty",
        _LANGUAGE_RULE,
        "  Python                              4    1,000,004            5            7",
        "  Markdown                            1      234,563            1            1",
        "",
    ], lines


def _check_rollup_refuses_a_document_without_a_count_and_adds_nothing() -> None:
    rollup = LocRollup()
    try:
        rollup.add(json.dumps({"summary": {"totalCodeCount": 1}, "languages": []}))
    except LocRollupError as exc:
        assert "totalDocumentationCount" in str(exc), exc
    else:
        raise AssertionError("a summary without its counts must be refused")
    assert rollup.projects == 0 and rollup.totals["totalCodeCount"] == 0, rollup


def _check_nothing_given_prints_usage_and_available() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        code, lines = _printed_by_run([], plant_workspace(Path(tmp)))
    expected = [
        "", "ERROR: No projects specified.", "", *USAGE_LINES, "", "Available projects:", " - datrix-a", " - datrix-b", ""
    ]
    assert (code, lines) == (EXIT_FAILED, expected), (code, lines)


def _check_all_counts_each_project_and_prints_the_rollup() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        workspace = plant_workspace(Path(tmp))
        write_files(workspace, _PLANTED_FILES)
        code, lines = _printed_by_run(["--all", "--format=json"], workspace)
    assert code == EXIT_PASSED, (code, lines)
    assert lines[0] == "Running LOC (format=json) for all projects: datrix-a, datrix-b", lines
    assert "[PASS] LOC counting passed for datrix-a" in lines and "[PASS] LOC counting passed for datrix-b" in lines
    assert "TOTAL (all projects) - LOC rollup (2 projects)" in lines, lines
    assert f"{_INDENT}{'Code:':<17}{5:>16,}" in lines, lines
    assert lines[-3:] == [" [PASS] : datrix-b", "", "Total: 2 | Passed: 2 | Failed: 0"], lines


def _check_a_project_without_src_fails_and_stop_on_error_stops() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        code, lines = _printed_by_run(["datrix-q", "datrix-a", "--stop-on-error"], plant_workspace(Path(tmp)))
    assert code == EXIT_FAILED, (code, lines)
    stopped = lines.index(STOP_MESSAGE_FLAG)
    assert lines[stopped - 1] == "[FAIL] LOC counting failed for datrix-q (exit code: 1)", lines
    assert "[2/2] datrix-a (format=summary)" not in lines, lines
    assert lines[-1] == "Total: 2 | Passed: 0 | Failed: 1", lines


_SELF_TEST_CHECKS: Final = (
    _check_rollup_sums_documents_and_formats_thousands,
    _check_rollup_refuses_a_document_without_a_count_and_adds_nothing,
    _check_nothing_given_prints_usage_and_available,
    _check_all_counts_each_project_and_prints_the_rollup,
    _check_a_project_without_src_fails_and_stop_on_error_stops,
)


def _run(args: argparse.Namespace) -> int:
    if args.self_test:
        return run_self_test(
            _SELF_TEST_CHECKS, wrapper=WRAPPER, module=MODULE, parser=build_parser(), folder=METRICS_SCRIPTS_DIR
        )
    return run_loc(args, WORKSPACE_DIR)


def main(argv: Sequence[str] | None = None) -> int:
    """Entry point."""
    return module_main(build_parser(), _run, argv)


if __name__ == "__main__":
    sys.exit(main())
