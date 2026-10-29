#!/usr/bin/env python3
"""Generate Datrix projects.

The module behind ``dev/generate.ps1`` (and its ``.sh`` twin). One run generates one project (--source, with
--output optional: derived from test-projects.json when omitted) or a batch (--all, --domains, or a --test-set
other than ``all``), always for one --language.

A run claims its own ``generate-results-<timestamp>-<language>[-<profile>].log`` under
``<workspace>/.generated/.results`` (whatever --output or --output-base say; --results-subdir names a folder
inside it for the log instead), checks the package installs, that
every plugin loads and that the ``datrix`` command runs, and validates --language against the registered
``datrix.languages`` set. It then runs ``datrix_scripts.dev.generate_projects`` as a child, showing its output
(without the detailed sections unless --verbose-output) and writing every line to the log, and ends with the
Generation Summary.

Exit codes: the child's; 1 when the run could not start (no language, an unregistered one, neither a source nor a
batch, a missing source, a failed install, plugin or ``datrix`` command check).
"""

from __future__ import annotations

import argparse
import os
import re
import subprocess
import sys
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Final

from datrix_scripts.gate_harness import WRAPPER_DEBUG_FLAG, install_sigint_handler
from datrix_scripts.logging_utils import ColorCodes, say, strip_ansi
from datrix_scripts.paths import WORKSPACE_DIR, script_env
from datrix_scripts.registered_targets import registered_language_names
from datrix_scripts.run_log import claim_run_log_file, run_log_base_name
from datrix_scripts.test.test import ensure_packages
from datrix_scripts.test.wrappers import DEV_SCRIPTS_DIR, module_main, run_self_test
from datrix_scripts.venv import WORKSPACE_LAYOUT, check_datrix_command, install_package, require_packages

MODULE: Final = "datrix_scripts.dev.generate"
WRAPPER: Final = "generate"
PROJECTS_MODULE: Final = "datrix_scripts.dev.generate_projects"
PLUGIN_DISCOVERY_MODULE: Final = "datrix_scripts.plugin_discovery"
CLI_PACKAGE: Final = "datrix-cli"

EXIT_OK: Final = 0
EXIT_FAILED: Final = 1

#: The output-path runtime segments -Runtime accepts (generation itself reads the runtime from the resolved
#: config, never from this flag); the child accepts exactly these.
RUNTIMES: Final = ("docker-compose", "azure-container-apps", "azure-app-service", "ecs-fargate", "app-runner")
DEFAULT_OUTPUT_BASE: Final = ".generated"
DEFAULT_TEST_SET: Final = "all"
DOMAINS_TEST_SET: Final = "domains"

LOG_PREFIX: Final = "generate-results"
#: Every run's log lands here, whatever --output or --output-base say.
RESULTS_DIR: Final = WORKSPACE_DIR / ".generated" / ".results"
#: Set for the child: this run writes the log, so the child must not open one of its own.
DISABLE_LOG_VARIABLE: Final = "DATRIX_DISABLE_LOG"
SEPARATOR: Final = "=" * 80
#: A longer output line holding "; " (an ERROR or Pipeline error line listing several errors) is split there,
#: one error per line.
MAX_LINE_LENGTH_BEFORE_SPLIT: Final = 200
#: Error lines the log's Errors section keeps per failed project.
MAX_ERROR_LINES_PER_PROJECT: Final = 5

_ERROR_SEPARATOR: Final = re.compile(r";\s")
_ERROR_SPLIT: Final = re.compile(r";\s*")
_DETAIL_START: Final = re.compile(r"^=== Detailed output for .* ===$", re.IGNORECASE)
_DETAIL_END: Final = re.compile(r"^=== End output for .* ===$", re.IGNORECASE)
#: ``[N/M] project-name: Success|Failed``, or ``[N/M] Failed: project-name`` (the child's exception path).
_RESULT: Final = re.compile(r"^.*\[(\d+)/(\d+)\]\s+(.+?):\s+(Success|Failed)\s*\r?$", re.IGNORECASE)
_RESULT_FAILED: Final = re.compile(r"^\s*\[(\d+)/(\d+)\]\s+Failed:\s+(.+?)\s*\r?$", re.IGNORECASE)
_ERROR_LINE: Final = re.compile(r"ERROR\s|Pipeline error:|Pipeline failed", re.IGNORECASE)
_SUCCESS: Final = "success"

LANGUAGE_REQUIRED: Final = "Error: -Language (-L) parameter is required (any registered datrix.languages target)."
NO_MODE: Final = "Error: Either -All, -Domains, -TestSet <set>, or Source parameter must be provided."
INSTALL_CHECK_FAILED: Final = (
    "The datrix packages are not installed, or a Datrix plugin failed to load; fix what is named above, then re-run."
)
_HELP: Final = (
    ("", ""),
    ("Usage:", ColorCodes.YELLOW),
    (" Generate single project:", ColorCodes.CYAN),
    (" .\\generate.ps1 <Source> [Output] -Language <lang> [-Runtime <runtime>] [-ConfigProfile <profile>] "
     "[-ValidationLevel <level>] [-Dbg]", ""),
    ("   (Output optional; derived from test-projects.json when omitted)", ColorCodes.GRAY),
    ("", ""),
    (" Generate all projects:", ColorCodes.CYAN),
    (" .\\generate.ps1 -All -Language <lang> [-Runtime <runtime>] [-ConfigProfile <profile>] [-OutputBase <dir>] "
     "[-TestSet <set>] [-Dbg]", ""),
    (" Generate by example folder:", ColorCodes.CYAN),
    (" .\\generate.ps1 -Domains -Language <lang> [-Runtime <runtime>] [-ConfigProfile <profile>] [-Dbg]", ""),
    ("", ""),
    ("Examples:", ColorCodes.YELLOW),
    (" .\\generate.ps1 examples/02-features/01-core-data-modeling/entities/system.dtrx -L python", ColorCodes.GRAY),
    (" .\\generate.ps1 -All -L python", ColorCodes.GRAY),
    (" .\\generate.ps1 -Domains -L python", ColorCodes.GRAY),
    (" .\\generate.ps1 -All -Language typescript -Runtime azure-app-service -ConfigProfile pilot -Dbg",
     ColorCodes.GRAY),
    ("", ""),
    ("Use Get-Help .\\generate.ps1 -Full for detailed help.", ColorCodes.YELLOW),
    ("", ""),
)


class GenerateError(Exception):
    """The run cannot go on; the message says why (reported as ``Error occurred: <message>``)."""


def build_parser() -> argparse.ArgumentParser:
    """The options of ``dev/generate.ps1``: one per wrapper parameter, spelled exactly."""
    parser = argparse.ArgumentParser(allow_abbrev=False, description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--source", default="", help="The source .dtrx file or directory (single-project mode).")
    parser.add_argument("--output", default="",
                        help="The output directory (single-project mode); derived from test-projects.json when omitted.")
    parser.add_argument("--all", action="store_true", help="Generate every project of the test set.")
    parser.add_argument("--domains", action="store_true", help="Generate the domain examples (test set domains).")
    parser.add_argument("--language", default="", help="Target language: any registered datrix.languages target.")
    parser.add_argument("--runtime", default="", type=str.lower, choices=RUNTIMES,
                        help="The output-path runtime segment (generation reads the runtime from the config).")
    parser.add_argument("--config-profile", default="",
                        help="The .dcfg profile that selects the deployment target (the CLI's default when omitted).")
    parser.add_argument("--output-base", default=DEFAULT_OUTPUT_BASE,
                        help=f"Output base directory of a batch (default: {DEFAULT_OUTPUT_BASE}).")
    parser.add_argument("--test-set", default=DEFAULT_TEST_SET,
                        help=f"The test set of a batch (default: {DEFAULT_TEST_SET}).")
    parser.add_argument("--validation-level", default="",
                        help="Post-generation validation level, forwarded to datrix generate (the CLI's when omitted).")
    parser.add_argument("--verbose-output", action="store_true",
                        help="Show the detailed output sections on the console too (the log always has them).")
    parser.add_argument("--results-subdir", default="",
                        help="Folder under <workspace>/.generated/.results to write the run's log in, so a product "
                             "repo keeps its logs apart from the others (default: .results itself).")
    parser.add_argument(WRAPPER_DEBUG_FLAG, dest="debug", action="store_true", help="Enable debug logging.")
    parser.add_argument("--self-test", action="store_true",
                        help="Run only the self-test: the child's arguments per mode, the output filter, the "
                             "summary, the language check, and the wrapper seam.")
    return parser


# ---------------------------------------------------------------------------
# The child's arguments
# ---------------------------------------------------------------------------


def batch_mode(args: argparse.Namespace) -> bool:
    """True when *args* asks for a batch (-All, -Domains, or a -TestSet other than ``all``)."""
    return bool(args.all or args.domains or args.test_set != DEFAULT_TEST_SET)


def _option(flag: str, value: str) -> list[str]:
    return [flag, value] if value.strip() else []


def _switches(args: argparse.Namespace) -> list[str]:
    return [*(["--debug"] if args.debug else []), *(["--verbose"] if args.verbose_output else [])]


def batch_arguments(args: argparse.Namespace) -> list[str]:
    """The child's arguments for a batch; -Domains takes precedence over -TestSet."""
    test_set = DOMAINS_TEST_SET if args.domains else args.test_set
    return [
        "--language", args.language,
        *_option("--runtime", args.runtime),
        *_option("--profile", args.config_profile),
        *(["--output-base", args.output_base] if args.output_base != DEFAULT_OUTPUT_BASE else []),
        *(["--test-set", test_set] if test_set != DEFAULT_TEST_SET else []),
        *_option("--validation-level", args.validation_level),
        *_switches(args),
    ]


def single_arguments(args: argparse.Namespace, source: Path) -> list[str]:
    """The child's arguments for one project from *source* (absolute)."""
    return [
        "--source", str(source),
        *_option("--output", args.output),
        "--language", args.language,
        *_option("--runtime", args.runtime),
        *_option("--profile", args.config_profile),
        *_option("--validation-level", args.validation_level),
        *_switches(args),
    ]


def _path_option(flag: str, value: str) -> list[str]:
    """*flag* with *value* made absolute, so the child resolves it from any directory."""
    return [flag, str(Path(value).absolute())] if value.strip() else []


def results_dir(subdir: str) -> Path:
    """The folder the run's log goes in: ``RESULTS_DIR``, or its *subdir* folder (a plain relative path that stays
    inside ``RESULTS_DIR``)."""
    name = subdir.strip()
    if not name:
        return RESULTS_DIR
    folder = (RESULTS_DIR / name).resolve()
    if not folder.is_relative_to(RESULTS_DIR.resolve()) or folder == RESULTS_DIR.resolve():
        raise GenerateError(f"Error: -ResultsSubdir '{subdir}' must be a relative folder inside {RESULTS_DIR}.")
    return folder


def language_problem(language: str, installed: Sequence[str]) -> str:
    """Why *language* cannot be generated (not among *installed*, compared case-insensitively), or ``""``."""
    if language.lower() in {name.lower() for name in installed}:
        return ""
    return (f"Error: language '{language}' is not an installed datrix.languages target. Installed: "
            f"{', '.join(installed)}. Install the corresponding datrix-codegen-<language> package to add it.")


# ---------------------------------------------------------------------------
# Console and log
# ---------------------------------------------------------------------------


def tee(log: Path | None, text: str, color: str = "") -> None:
    """Show *text* and append it, without color codes, as a line of *log* (when there is one)."""
    say(text, color)
    if log is not None:
        with log.open("a", encoding="utf-8") as sink:
            sink.write(strip_ansi(text) + "\n")


def _print_help() -> None:
    for text, color in _HELP:
        say(text, color)


def split_long_line(line: str) -> list[str]:
    """*line*, or -- when longer than ``MAX_LINE_LENGTH_BEFORE_SPLIT`` and holding "; " -- its "; "-separated
    parts, every part after the first indented two spaces."""
    if len(line) <= MAX_LINE_LENGTH_BEFORE_SPLIT or not _ERROR_SEPARATOR.search(line):
        return [line]
    parts = [part.strip() for part in _ERROR_SPLIT.split(line)]
    return [part if index == 0 else f"  {part}" for index, part in enumerate(part for part in parts if part)]


@dataclass
class OutputFilter:
    """Which of the child's lines the console shows: in quiet mode, none of a detailed output section (its
    markers included). The log gets every line."""

    quiet: bool
    in_detail: bool = False

    def lines(self, raw: str) -> list[tuple[str, bool]]:
        """*raw* without color codes, split by ``split_long_line``, each with whether the console shows it."""
        plain = strip_ansi(raw)
        start = bool(_DETAIL_START.match(plain))
        end = bool(_DETAIL_END.match(plain))
        shown = not (self.quiet and (start or end or self.in_detail))
        if start:
            self.in_detail = True
        elif end:
            self.in_detail = False
        return [(line, shown) for line in split_long_line(plain)]


# ---------------------------------------------------------------------------
# Generation Summary
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ProjectResult:
    """One ``[N/M] ...`` result line of the log."""

    total: int
    name: str
    failed: bool
    line_index: int


def project_results(lines: Sequence[str]) -> list[ProjectResult]:
    """The result lines among *lines*, in order."""
    results: list[ProjectResult] = []
    for index, line in enumerate(lines):
        normal = _RESULT.match(line)
        if normal:
            results.append(ProjectResult(int(normal[2]), normal[3].strip(), normal[4].lower() != _SUCCESS, index))
            continue
        failed = _RESULT_FAILED.match(line)
        if failed:
            results.append(ProjectResult(int(failed[2]), failed[3].strip(), True, index))
    return results


def project_errors(lines: Sequence[str], results: Sequence[ProjectResult]) -> dict[str, list[str]]:
    """Per failed project, the first ``MAX_ERROR_LINES_PER_PROJECT`` error lines between the previous result
    line and its own."""
    errors: dict[str, list[str]] = {}
    for position, result in enumerate(results):
        if not result.failed:
            continue
        start = results[position - 1].line_index + 1 if position else 0
        found = [line.strip() for line in lines[start:result.line_index] if _ERROR_LINE.search(line)]
        if found:
            errors[result.name] = found[:MAX_ERROR_LINES_PER_PROJECT]
    return errors


def summary_report(results: Sequence[ProjectResult]) -> str:
    """The Generation Summary block (shown and logged)."""
    body = ["  No project results found."]
    if results:
        failed = [result.name for result in results if result.failed]
        body = [
            f"  Total projects: {results[0].total}",
            f"  Successful:     {len(results) - len(failed)}",
            f"  Failed:         {len(failed)}",
            *([f"  Failed projects: {', '.join(failed)}"] if failed else []),
        ]
    return "\n".join(["", SEPARATOR, "Generation Summary", SEPARATOR, *body, SEPARATOR, ""])


def errors_report(results: Sequence[ProjectResult], errors: dict[str, list[str]]) -> str:
    """The Errors block (logged only: the full messages are already in the log's detailed output), or ``""``."""
    failed = [result.name for result in results if result.failed]
    if not failed or not errors:
        return ""
    lines = ["", SEPARATOR, "Errors", SEPARATOR]
    for name in failed:
        if name in errors:
            lines.extend([f"  {name}:", *(f"    {error}" for error in errors[name])])
    return "\n".join([*lines, ""])


def append_summary(log: Path) -> None:
    """Append the Errors block and the Generation Summary to *log*, and show the summary."""
    if not log.is_file():
        return
    lines = log.read_text(encoding="utf-8", errors="replace").splitlines()
    results = project_results(lines)
    summary = summary_report(results)
    with log.open("a", encoding="utf-8") as sink:
        sink.write(errors_report(results, project_errors(lines, results)) + summary)
    say(summary)


# ---------------------------------------------------------------------------
# The checks before generation
# ---------------------------------------------------------------------------


def _check_installs(log: Path) -> None:
    """The package installs are current and every plugin loads (``plugin_discovery`` in a child)."""
    exit_code = EXIT_FAILED
    lines: list[str] = []
    if ensure_packages(os.environ, require_packages):
        result = subprocess.run([sys.executable, "-m", PLUGIN_DISCOVERY_MODULE], capture_output=True, check=False,
                                encoding="utf-8", errors="replace", env={**script_env(), "PYTHONIOENCODING": "utf-8"})
        exit_code = result.returncode
        lines = (result.stdout + result.stderr).splitlines()
    if exit_code == EXIT_OK:
        return
    tee(log, f"Package install check or plugin discovery failed (exit {exit_code}):", ColorCodes.RED)
    for line in lines:
        tee(log, line, ColorCodes.RED)
    raise GenerateError(INSTALL_CHECK_FAILED)


def _check_datrix_command(log: Path) -> None:
    """``datrix --version`` runs; when it does not, say why, reinstall datrix-cli once and check again."""
    check = check_datrix_command(WORKSPACE_LAYOUT)
    if check.ok:
        return
    tee(log, "datrix command verification failed:", ColorCodes.RED)
    tee(log, check.detail, ColorCodes.RED)
    tee(log, f"Attempting reinstall of {CLI_PACKAGE}...", ColorCodes.YELLOW)
    if not install_package(WORKSPACE_LAYOUT, CLI_PACKAGE, no_dev=True):
        raise GenerateError(f"Failed to reinstall {CLI_PACKAGE}\n{check.detail}")
    after = check_datrix_command(WORKSPACE_LAYOUT)
    if not after.ok:
        tee(log, "datrix command still not working after reinstall:", ColorCodes.RED)
        tee(log, after.detail, ColorCodes.RED)
        raise GenerateError(f"datrix command still not working after reinstall\n{after.detail}")
    tee(log, "datrix command verified successfully", ColorCodes.GREEN)


def _single_project_arguments(args: argparse.Namespace) -> list[str]:
    source = Path(os.path.abspath(args.source))
    if not source.exists():
        raise GenerateError(f"Error: Source file or directory not found: {source}")
    if args.output.strip():
        Path(args.output).mkdir(parents=True, exist_ok=True)
    return single_arguments(args, source)


# ---------------------------------------------------------------------------
# The run
# ---------------------------------------------------------------------------


def _run_projects(arguments: Sequence[str], log: Path, *, quiet: bool) -> int:
    """Run the per-project child, showing its output through ``OutputFilter`` and logging every line."""
    output_filter = OutputFilter(quiet)
    sys.stdout.flush()
    with (
        subprocess.Popen([sys.executable, "-m", PROJECTS_MODULE, *arguments], stdout=subprocess.PIPE,
                         stderr=subprocess.STDOUT, encoding="utf-8", errors="replace",
                         env={**script_env(), DISABLE_LOG_VARIABLE: "1"}) as process,
        log.open("a", encoding="utf-8") as sink,
    ):
        assert process.stdout is not None
        for raw in process.stdout:
            for line, shown in output_filter.lines(raw.rstrip("\r\n")):
                if shown:
                    say(line)
                sink.write(line + "\n")
                sink.flush()
        return process.wait()


def _generate(args: argparse.Namespace, log: Path) -> int:
    # Safe to write over: the claim created this file empty, and no other run owns it.
    log.write_text(f"Generate Results Log\nTimestamp: {datetime.now():%Y-%m-%d %H:%M:%S}\n{SEPARATOR}\n\n",
                   encoding="utf-8")
    tee(log, f"Log file: {log}", ColorCodes.CYAN)
    tee(log, "")
    _check_installs(log)
    _check_datrix_command(log)
    problem = language_problem(args.language, sorted(registered_language_names()))
    if problem:
        tee(log, problem, ColorCodes.RED)
        return EXIT_FAILED
    if batch_mode(args):
        arguments = batch_arguments(args)
        tee(log, f"Running generate {DOMAINS_TEST_SET if args.domains else DEFAULT_TEST_SET}...", ColorCodes.CYAN)
        tee(log, "")
    elif args.source:
        arguments = _single_project_arguments(args)
    else:
        say(NO_MODE, ColorCodes.RED)
        _print_help()
        return EXIT_FAILED
    exit_code = _run_projects(arguments, log, quiet=not args.verbose_output)
    append_summary(log)
    return exit_code


def _run(args: argparse.Namespace) -> int:
    if args.self_test:
        checks = [
            _check_child_arguments_follow_the_mode,
            _check_quiet_console_drops_detail_and_long_lines_split,
            _check_summary_counts_results_and_keeps_errors_for_the_log,
            _check_language_must_be_registered,
            _check_results_subdir_stays_inside_results_dir,
        ]
        return run_self_test(checks, wrapper=WRAPPER, module=MODULE, parser=build_parser(), folder=DEV_SCRIPTS_DIR)
    if not args.language.strip():
        say(LANGUAGE_REQUIRED, ColorCodes.RED)
        _print_help()
        return EXIT_FAILED
    log: Path | None = None
    try:
        log = claim_run_log_file(results_dir(args.results_subdir),
                                 run_log_base_name(LOG_PREFIX, [args.language, args.config_profile]))
        return _generate(args, log)
    except (GenerateError, OSError, RuntimeError, subprocess.SubprocessError) as exc:
        tee(log, f"\nError occurred: {exc}", ColorCodes.RED)
        if log is not None:
            append_summary(log)
        return EXIT_FAILED
    finally:
        if log is not None:
            say(f"\nLog saved to: {log}", ColorCodes.CYAN)


# ---------------------------------------------------------------------------
# Self-test
# ---------------------------------------------------------------------------


def _check_child_arguments_follow_the_mode() -> None:
    parser = build_parser()
    batch = parser.parse_args(["--all", "--language=python", "--test-set=features", "--output-base=out", "--dbg"])
    assert batch_mode(batch) and batch_arguments(batch) == [
        "--language", "python", "--output-base", "out", "--test-set", "features", "--debug"], batch_arguments(batch)
    domains = parser.parse_args(["--domains", "--test-set=features", "--language=python", "--runtime=ECS-Fargate"])
    assert batch_arguments(domains) == ["--language", "python", "--runtime", "ecs-fargate", "--test-set", "domains"], (
        batch_arguments(domains))
    test_set = parser.parse_args(["--language=python", "--test-set=features"])
    assert batch_mode(test_set), "a test set other than all is a batch"
    single = parser.parse_args(["--source=x.dtrx", "--language=python", "--config-profile=pilot", "--verbose-output"])
    source = Path("x.dtrx").absolute()
    assert not batch_mode(single) and single_arguments(single, source) == [
        "--source", str(source), "--language", "python", "--profile", "pilot", "--verbose"], (
        single_arguments(single, source))
    assert not batch_mode(parser.parse_args(["--language=python", "--test-set=all"])), "-TestSet all is no batch"
    assert parser.parse_known_args(["--carry-forward-live-snapshots=live"])[1] == [
        "--carry-forward-live-snapshots=live"], "the removed option is not a script parameter"


def _check_quiet_console_drops_detail_and_long_lines_split() -> None:
    raw = ["[1/1] alpha: Success", "=== Detailed output for alpha ===", "\x1b[91mdetail\x1b[0m",
           "=== End output for alpha ===", "ERROR " + "; ".join(f"error number {n} of many" for n in range(12))]
    quiet = OutputFilter(quiet=True)
    seen = [pair for line in raw for pair in quiet.lines(line)]
    assert [line for line, shown in seen if shown][0] == "[1/1] alpha: Success"
    assert ("detail", False) in seen and ("=== Detailed output for alpha ===", False) in seen, seen
    split = [line for line, _ in seen[4:]]
    assert len(split) == 12 and split[0] == "ERROR error number 0 of many" and split[1] == "  error number 1 of many", split
    verbose = OutputFilter(quiet=False)
    assert all(shown for line in raw for _, shown in verbose.lines(line)), "verbose output shows every line"
    assert split_long_line("short; line") == ["short; line"]


def _check_summary_counts_results_and_keeps_errors_for_the_log() -> None:
    lines = ["Running", "[1/3] alpha: Success", "ERROR pipeline x error=boom:", "Pipeline failed",
             "[2/3] beta: Failed", "[3/3] Failed: gamma"]
    results = project_results(lines)
    assert [(result.name, result.failed) for result in results] == [("alpha", False), ("beta", True), ("gamma", True)]
    summary = summary_report(results)
    assert "  Total projects: 3\n  Successful:     1\n  Failed:         2\n  Failed projects: beta, gamma\n" in summary, (
        summary)
    errors = project_errors(lines, results)
    assert errors == {"beta": ["ERROR pipeline x error=boom:", "Pipeline failed"]}, errors
    assert "\nErrors\n" in errors_report(results, errors) and "    Pipeline failed\n" in errors_report(results, errors)
    assert "No project results found." in summary_report([]) and errors_report([], {}) == ""


def _check_results_subdir_stays_inside_results_dir() -> None:
    assert results_dir("") == RESULTS_DIR and results_dir("  ") == RESULTS_DIR, "no subdir: the results folder"
    assert results_dir("product") == (RESULTS_DIR / "product").resolve()
    for escaping in ("..", "../other", ".", str(RESULTS_DIR.parent)):
        try:
            results_dir(escaping)
        except GenerateError:
            continue
        raise AssertionError(f"'{escaping}' must be refused")


def _check_language_must_be_registered() -> None:
    assert language_problem("Python", ["python", "typescript"]) == "", "the check is case-insensitive"
    assert language_problem("cobol", ["python", "typescript"]) == (
        "Error: language 'cobol' is not an installed datrix.languages target. Installed: python, typescript. "
        "Install the corresponding datrix-codegen-<language> package to add it.")


def main(argv: Sequence[str] | None = None) -> int:
    """Entry point."""
    install_sigint_handler()
    return module_main(build_parser(), _run, argv)


if __name__ == "__main__":
    sys.exit(main())
