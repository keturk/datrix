"""Run one generation test set for every registered language and compare per-project outcomes: the module
behind ``scripts/test/dual-target.ps1``.

The languages are the registered ``datrix.languages`` targets, in name order, discovered at run time -- a newly
installed ``datrix-codegen-<lang>`` package adds a column with no edit here. ``--platform`` is validated against
the registered ``datrix.platforms`` targets the same way.

For each language it runs ``dev/generate.ps1 -TestSet -Language -Platform`` or, with both ``--skip4`` and
``--skip5``, the complete-run module with the deploy and test steps skipped, then reads the newest (by name)
``generate-results-*.log`` under ``<workspace>/.generated/.results``. It prints a Markdown table with one column
per language and a parity column: ``OK`` when every language reports the same outcome for a project,
``Mismatch`` otherwise, ``(missing)`` where a language's log does not name the project.

Exit codes: 0 = every run succeeded and every project is ``Success`` in every language; 1 = a run failed, a
project failed or is missing in a language, the platform is not registered, no language is registered, no
results log was found, or a self-test check failed; 2 = usage error; 130 = interrupted.
"""

from __future__ import annotations

import argparse
import logging
import re
import subprocess
import sys
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Final

from datrix_scripts.gate_harness import EXIT_INTERRUPTED, configure_logging, write_files
from datrix_scripts.paths import SCRIPTS_DIR, WORKSPACE_DIR, script_env
from datrix_scripts.registered_targets import registered_language_names, registered_platform_names
from datrix_scripts.test.run_complete import find_powershell
from datrix_scripts.test.wrappers import ensure_utf8_stdio, run_self_test

logger = logging.getLogger(__name__)

MODULE: Final = "datrix_scripts.test.dual_target"
WRAPPER: Final = "dual-target"
RUN_COMPLETE_MODULE: Final = "datrix_scripts.test.run_complete"

DEFAULT_TEST_SET: Final = "typescript-validation"
DEFAULT_PLATFORM: Final = "docker"
GENERATE_SCRIPT: Final[Path] = SCRIPTS_DIR / "dev" / "generate.ps1"
RESULTS_DIR: Final[Path] = WORKSPACE_DIR / ".generated" / ".results"
RESULTS_LOG_GLOB: Final = "generate-results-*.log"
STATUS_LINE: Final = re.compile(r"^\s*\[(\d+)/(\d+)\]\s+([^:]+):\s+(Success|Failed)\s*$")

STATUS_SUCCESS: Final = "Success"
STATUS_MISSING: Final = "(missing)"
PARITY_OK: Final = "OK"
PARITY_MISMATCH: Final = "Mismatch"
_LANGUAGE_RULE: Final = "--------"
_RESULTS_LOCATION: Final = "generation results under `.generated/.results/`"

_EXIT_PASS: Final = 0
_EXIT_FAIL: Final = 1


class DualTargetError(Exception):
    """A precondition of the comparison does not hold; the message says which and how to fix it."""


@dataclass(frozen=True)
class DualTargetRequest:
    """What one comparison runs: the test set, the platform, and the runner each language goes through."""

    test_set: str
    platform: str
    use_run_complete: bool
    fresh_build: bool
    debug_logging: bool


def request_from_args(args: argparse.Namespace) -> DualTargetRequest:
    """The request *args* name: the complete-run module only when both ``--skip4`` and ``--skip5`` are given."""
    return DualTargetRequest(
        test_set=args.test_set,
        platform=args.platform,
        use_run_complete=args.skip4 and args.skip5,
        fresh_build=args.fresh_build,
        debug_logging=args.debug_logging,
    )


def require_registered_platform(platform: str, registered: frozenset[str]) -> None:
    """Raise :class:`DualTargetError` unless *platform* is one of the *registered* platforms."""
    if platform in registered:
        return
    raise DualTargetError(
        f"Platform '{platform}' is not an installed datrix.platforms plugin. "
        f"Installed platforms: {', '.join(sorted(registered))}. "
        "Install the corresponding datrix-codegen-<platform> package to add it."
    )


def compared_languages(registered: frozenset[str]) -> list[str]:
    """The *registered* languages in name order; raise :class:`DualTargetError` when there are none."""
    if not registered:
        raise DualTargetError("No datrix.languages targets are installed; cannot run the language comparison.")
    return sorted(registered)


def child_command(request: DualTargetRequest, language: str, powershell: str) -> list[str]:
    """The argument vector that generates *request*'s test set for *language*."""
    if request.use_run_complete:
        command = [
            sys.executable,
            "-m",
            RUN_COMPLETE_MODULE,
            f"--test-set={request.test_set}",
            f"--language={language}",
            f"--platform={request.platform}",
            "--skip4",
            "--skip5",
        ]
        if request.fresh_build:
            command.append("--fresh-build")
        if request.debug_logging:
            command.append("--debug-logging")
        return command
    command = [
        powershell,
        "-File",
        str(GENERATE_SCRIPT),
        "-TestSet",
        request.test_set,
        "-Language",
        language,
        "-Platform",
        request.platform,
    ]
    if request.debug_logging:
        command.append("-Dbg")
    return command


def latest_results_log(results_dir: Path) -> Path:
    """The ``generate-results-*.log`` in *results_dir* whose name sorts last (the names carry the timestamp)."""
    if not results_dir.exists():
        raise DualTargetError(f"Results directory not found: {results_dir}")
    logs = [path for path in results_dir.glob(RESULTS_LOG_GLOB) if path.is_file()]
    if not logs:
        raise DualTargetError(f"No {RESULTS_LOG_GLOB} files found in {results_dir}")
    return max(logs, key=lambda path: path.name)


def read_status_map(log_text: str) -> dict[str, str]:
    """Project name -> ``Success``/``Failed`` for every ``[n/m] project: status`` line; a later line wins."""
    statuses: dict[str, str] = {}
    for line in log_text.splitlines():
        match = STATUS_LINE.match(line)
        if match:
            statuses[match.group(3).strip()] = match.group(4)
    return statuses


def results_table(
    request: DualTargetRequest, languages: Sequence[str], maps: Mapping[str, Mapping[str, str]]
) -> tuple[list[str], bool]:
    """The Markdown table of *maps* (language -> project -> status), and whether any cell is not ``Success``."""
    lines = [
        "",
        "## Multi-language generation results",
        "",
        f"Test set: **{request.test_set}** | Platform: **{request.platform}** | "
        f"Languages: **{', '.join(languages)}** | Log (latest): {_RESULTS_LOCATION}",
        "",
        f"| Project | {' | '.join(languages)} | Parity |",
        f"|---------| {' | '.join(_LANGUAGE_RULE for _ in languages)} |--------|",
    ]
    projects = sorted({project for language in languages for project in maps[language]})
    any_failure = False
    for project in projects:
        statuses = [maps[language].get(project, STATUS_MISSING) for language in languages]
        parity = PARITY_OK if len(set(statuses)) == 1 else PARITY_MISMATCH
        any_failure = any_failure or any(status != STATUS_SUCCESS for status in statuses)
        lines.append(f"| {project} | {' | '.join(statuses)} | {parity} |")
    lines.append("")
    return lines, any_failure


def _powershell_for(request: DualTargetRequest) -> str:
    """The PowerShell host generate.ps1 runs under; the complete-run path needs none and gets an empty name."""
    if request.use_run_complete:
        return ""
    if not GENERATE_SCRIPT.exists():
        raise DualTargetError(f"generate.ps1 not found at: {GENERATE_SCRIPT}")
    powershell = find_powershell()
    if powershell is None:
        raise DualTargetError(
            "PowerShell not found; generate.ps1 needs it. Install PowerShell (pwsh), or on Windows make "
            "powershell.exe reachable on PATH."
        )
    return powershell


def compare(request: DualTargetRequest, languages: Sequence[str], results_dir: Path) -> int:
    """Generate the test set for each language, print the comparison table, and return the exit code."""
    powershell = _powershell_for(request)
    any_failure = False
    maps: dict[str, dict[str, str]] = {}
    for language in languages:
        command = child_command(request, language, powershell)
        logger.debug("Running %s", command)
        if subprocess.run(command, env=script_env(), check=False).returncode != 0:
            any_failure = True
        latest = latest_results_log(results_dir)
        maps[language] = read_status_map(latest.read_text(encoding="utf-8"))
    lines, failed_cell = results_table(request, languages, maps)
    print("\n".join(lines))
    return _EXIT_FAIL if any_failure or failed_cell else _EXIT_PASS


def run(request: DualTargetRequest) -> int:
    """Validate *request* against the registered targets and run the comparison."""
    require_registered_platform(request.platform, registered_platform_names())
    languages = compared_languages(registered_language_names())
    return compare(request, languages, RESULTS_DIR)


# ---------------------------------------------------------------------------
# Self-test
# ---------------------------------------------------------------------------

_SELF_TEST_REQUEST: Final = DualTargetRequest(
    test_set="set-x", platform="platform-x", use_run_complete=False, fresh_build=False, debug_logging=False
)
_SELF_TEST_LOG: Final = (
    "Generating set-x\n"
    "  [1/3] shop: Success\n"
    "[2/3] catalog : Failed  \n"
    "[3/3] catalog: Success\n"
    "[x/3] broken: Success\n"
    "summary: 2 Success\n"
)


def _check_status_lines_parse() -> None:
    statuses = read_status_map(_SELF_TEST_LOG)
    assert statuses == {"shop": "Success", "catalog": "Success"}, statuses


def _check_latest_log_is_the_last_name() -> None:
    with TemporaryDirectory() as tmp:
        root = Path(tmp)
        results = root / "results"
        write_files(
            results,
            {
                "generate-results-20260101-000000-a.log": "[1/1] old: Failed\n",
                "generate-results-20260102-000000-a.log": "[1/1] new: Success\n",
                "other-20270101.log": "[1/1] ignored: Success\n",
            },
        )
        assert latest_results_log(results).name == "generate-results-20260102-000000-a.log"
        for missing, expected in ((root / "absent", "Results directory not found"), (root, "No generate-results")):
            try:
                latest_results_log(missing)
            except DualTargetError as error:
                assert str(error).startswith(expected), error
            else:
                raise AssertionError(f"{missing} gave a log; expected {expected!r}")


def _check_table_marks_parity_and_missing() -> None:
    maps = {
        "lang-a": {"shop": "Success", "catalog": "Success", "billing": "Failed"},
        "lang-b": {"shop": "Success", "catalog": "Failed"},
    }
    lines, any_failure = results_table(_SELF_TEST_REQUEST, ["lang-a", "lang-b"], maps)
    expected = [
        "",
        "## Multi-language generation results",
        "",
        "Test set: **set-x** | Platform: **platform-x** | Languages: **lang-a, lang-b** | "
        "Log (latest): generation results under `.generated/.results/`",
        "",
        "| Project | lang-a | lang-b | Parity |",
        "|---------| -------- | -------- |--------|",
        "| billing | Failed | (missing) | Mismatch |",
        "| catalog | Success | Failed | Mismatch |",
        "| shop | Success | Success | OK |",
        "",
    ]
    assert lines == expected, "\n".join(lines)
    assert any_failure
    _, clean_failure = results_table(_SELF_TEST_REQUEST, ["lang-a"], {"lang-a": {"shop": "Success"}})
    assert not clean_failure


def _check_child_commands() -> None:
    generate = child_command(
        DualTargetRequest("set-x", "platform-x", False, True, True), "lang-a", "pwsh"
    )
    assert generate == [
        "pwsh", "-File", str(GENERATE_SCRIPT), "-TestSet", "set-x", "-Language", "lang-a",
        "-Platform", "platform-x", "-Dbg",
    ], generate
    complete = child_command(DualTargetRequest("set-x", "platform-x", True, True, True), "lang-a", "")
    assert complete == [
        sys.executable, "-m", RUN_COMPLETE_MODULE, "--test-set=set-x", "--language=lang-a",
        "--platform=platform-x", "--skip4", "--skip5", "--fresh-build", "--debug-logging",
    ], complete
    one_skip = request_from_args(build_parser().parse_args(["--skip4"]))
    assert not one_skip.use_run_complete, one_skip


def _check_unregistered_targets_are_refused() -> None:
    registered = frozenset({"platform-b", "platform-a"})
    require_registered_platform("platform-a", registered)
    try:
        require_registered_platform("platform-z", registered)
    except DualTargetError as error:
        assert "Installed platforms: platform-a, platform-b." in str(error), error
    else:
        raise AssertionError("an unregistered platform was accepted")
    try:
        compared_languages(frozenset())
    except DualTargetError as error:
        assert "No datrix.languages targets are installed" in str(error), error
    else:
        raise AssertionError("an empty language set was accepted")
    assert compared_languages(frozenset({"lang-b", "lang-a"})) == ["lang-a", "lang-b"]


def _check_defaults_match_the_wrapper() -> None:
    args = build_parser().parse_args([])
    assert (args.test_set, args.platform) == (DEFAULT_TEST_SET, DEFAULT_PLATFORM), args


_SELF_TEST_CHECKS: Final = (
    _check_status_lines_parse,
    _check_latest_log_is_the_last_name,
    _check_table_marks_parity_and_missing,
    _check_child_commands,
    _check_unregistered_targets_are_refused,
    _check_defaults_match_the_wrapper,
)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def build_parser() -> argparse.ArgumentParser:
    """The options of ``scripts/test/dual-target.ps1``, each parameter spelled ``--kebab``."""
    parser = argparse.ArgumentParser(
        prog=WRAPPER,
        description="Generate one test set for every registered language and compare the per-project outcomes.",
        allow_abbrev=False,
    )
    parser.add_argument(
        "--test-set",
        default=DEFAULT_TEST_SET,
        help=f"Test set in scripts/config/test-projects.json (default: {DEFAULT_TEST_SET}).",
    )
    parser.add_argument(
        "--platform",
        default=DEFAULT_PLATFORM,
        help=f"A registered datrix.platforms target (default: {DEFAULT_PLATFORM}).",
    )
    parser.add_argument("--skip4", action="store_true", help="With --skip5: run the complete-run module, steps 1-2.")
    parser.add_argument("--skip5", action="store_true", help="With --skip4: run the complete-run module, steps 1-2.")
    parser.add_argument(
        "--fresh-build", action="store_true", help="Force fresh Docker builds when the complete-run module runs."
    )
    parser.add_argument("--debug-logging", action="store_true", help="Debug logging here and in each child run.")
    parser.add_argument("--self-test", action="store_true", help="Run the built-in checks and exit.")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    """Entry point; returns the process exit code."""
    ensure_utf8_stdio()
    args = build_parser().parse_args(argv)
    configure_logging(args.debug_logging)
    if args.self_test:
        return run_self_test(_SELF_TEST_CHECKS, wrapper=WRAPPER, module=MODULE, parser=build_parser())
    try:
        return run(request_from_args(args))
    except DualTargetError as error:
        print(f"ERROR: {error}", file=sys.stderr)
        return _EXIT_FAIL
    except KeyboardInterrupt:
        print("\nInterrupted.", file=sys.stderr)
        return EXIT_INTERRUPTED


if __name__ == "__main__":
    sys.exit(main())
