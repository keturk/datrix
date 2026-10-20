"""Run all visualization and documentation steps for one or more projects.

The module behind ``visualize/all-reports.ps1`` (and its ``.sh`` twin). Runs, in order:

  1. Mermaid and SVG diagrams (``datrix_scripts.visualize.visualize``)
  2. OpenAPI / AsyncAPI specs (``datrix_scripts.visualize.openapi_gen``)
  3. Documentation status report (``datrix_scripts.visualize.status_docs``)

each as its own process, with the selection options given here (and ``--profile`` for the steps
that load the application). All output is written next to the .dtrx source files. A failing step is
reported and does not block the next one.

Exit codes: 0 = every step passed; 1 = a step failed, or neither a source nor a batch flag.

Usage:
    python -m datrix_scripts.visualize.all_reports --source=<system.dtrx> [--profile=<name>]
"""

from __future__ import annotations

import argparse
import contextlib
import io
import subprocess
import sys
import tempfile
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Final

from datrix_scripts.gate_harness import install_sigint_handler
from datrix_scripts.logging_utils import ColorCodes, colorize
from datrix_scripts.paths import script_env
from datrix_scripts.test.wrappers import VISUALIZE_SCRIPTS_DIR, module_main, run_self_test
from datrix_scripts.visualize.projects import ALL_TEST_SET, add_selection_arguments

MODULE: Final = "datrix_scripts.visualize.all_reports"
WRAPPER: Final = "all-reports"
DEFAULT_PROFILE: Final = "test"
BANNER: Final = "=" * 51
STEP_RULE: Final = "-" * 51
EXIT_OK: Final = 0
EXIT_FAILED: Final = 1
USAGE: Final = (
    "Usage:\n"
    "  .\\all-reports.ps1 <source.dtrx>               Single project\n"
    "  .\\all-reports.ps1 -All                         All projects\n"
    "  .\\all-reports.ps1 -Domains                     Domain examples\n"
    "\n"
    "Use Get-Help .\\all-reports.ps1 -Full for detailed help."
)


@dataclass(frozen=True)
class Step:
    """One report step: the module it runs, and whether it loads the application under a profile."""

    name: str
    module: str
    resolves_profile: bool


STEPS: Final = (
    Step("Mermaid Diagrams", "datrix_scripts.visualize.visualize", resolves_profile=True),
    Step("OpenAPI / AsyncAPI Specs", "datrix_scripts.visualize.openapi_gen", resolves_profile=True),
    Step("Documentation Status", "datrix_scripts.visualize.status_docs", resolves_profile=False),
)

StepRunner = Callable[[list[str]], int]


def step_arguments(args: argparse.Namespace, step: Step) -> list[str]:
    """The options *step* gets: the selection options given here, and ``--profile`` when it loads the app."""
    arguments: list[str] = []
    if args.source:
        arguments.append(f"--source={args.source}")
    if args.batch_all:
        arguments.append("--all")
    if args.domains:
        arguments.append("--domains")
    if args.test_set != ALL_TEST_SET:
        arguments.append(f"--test-set={args.test_set}")
    if args.debug:
        arguments.append("--dbg")
    if step.resolves_profile and args.profile != DEFAULT_PROFILE:
        arguments.append(f"--profile={args.profile}")
    return arguments


def run_child(command: list[str]) -> int:
    """Run one step's process, its output on this console; returns its exit code."""
    return subprocess.run(command, env=script_env(), check=False).returncode


def all_reports(args: argparse.Namespace, run: StepRunner = run_child) -> int:
    """Run every step; returns 0 when all passed, else 1."""
    if not args.source and not args.batch_all and not args.domains:
        print(colorize(USAGE, ColorCodes.YELLOW))
        return EXIT_FAILED

    print()
    print(colorize(BANNER, ColorCodes.CYAN))
    print(colorize("  Datrix Visualization - All Reports", ColorCodes.CYAN))
    print(colorize(BANNER, ColorCodes.CYAN))
    print()

    passed = 0
    for number, step in enumerate(STEPS, start=1):
        print(colorize(STEP_RULE, ColorCodes.GRAY))
        print(colorize(f"  Step {number}/{len(STEPS)} : {step.name}", ColorCodes.CYAN))
        print(colorize(STEP_RULE, ColorCodes.GRAY), flush=True)
        code = run([sys.executable, "-m", step.module, *step_arguments(args, step)])
        if code == EXIT_OK:
            print(colorize("  -> OK", ColorCodes.GREEN))
            passed += 1
        else:
            print(colorize(f"  -> FAILED (exit code {code})", ColorCodes.RED))
        print()

    failed = len(STEPS) - passed
    print(colorize(BANNER, ColorCodes.CYAN))
    print(colorize(f"  Summary: {passed} passed, {failed} failed (out of {len(STEPS)} steps)",
                   ColorCodes.YELLOW if failed else ColorCodes.GREEN))
    print(colorize(BANNER, ColorCodes.CYAN))
    return EXIT_FAILED if failed else EXIT_OK


def build_parser() -> argparse.ArgumentParser:
    """The options of ``visualize/all-reports.ps1``: one per wrapper parameter, spelled exactly."""
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter, allow_abbrev=False
    )
    add_selection_arguments(parser)
    parser.add_argument("--profile", default=DEFAULT_PROFILE,
                        help="Config profile the diagram and spec steps resolve (default: test).")
    parser.add_argument("--self-test", action="store_true",
                        help="Run only the self-test: every step runs with its options, a failing step fails the run.")
    return parser


def _quiet_reports(argv: list[str], run: StepRunner) -> tuple[int, str]:
    with contextlib.redirect_stdout(io.StringIO()) as printed:
        code = all_reports(build_parser().parse_args(argv), run)
    return code, printed.getvalue()


def _check_every_step_runs_with_its_options() -> None:
    commands: list[list[str]] = []
    code, text = _quiet_reports(["--source=a/system.dtrx", "--profile=staging", "--dbg"],
                                lambda command: commands.append(command) or EXIT_OK)
    assert code == EXIT_OK and "Summary: 3 passed, 0 failed" in text, text
    assert [command[2] for command in commands] == [step.module for step in STEPS], commands
    assert commands[0][3:] == ["--source=a/system.dtrx", "--dbg", "--profile=staging"], commands[0]
    assert commands[2][3:] == ["--source=a/system.dtrx", "--dbg"], commands[2]


def _check_a_failing_step_fails_the_run_and_the_rest_still_run() -> None:
    commands: list[list[str]] = []
    code, text = _quiet_reports(["--domains"], lambda command: commands.append(command) or (3 if len(commands) == 1 else 0))
    assert code == EXIT_FAILED and len(commands) == len(STEPS), (code, commands)
    assert "-> FAILED (exit code 3)" in text and "Summary: 2 passed, 1 failed" in text, text


def _check_no_selection_prints_usage_and_exits_1() -> None:
    code, text = _quiet_reports([], lambda command: EXIT_OK)
    assert code == EXIT_FAILED and "Usage:" in text, text


def _check_a_real_step_runs_as_a_child() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        (Path(tmp) / "docs" / "openapi").mkdir(parents=True)
        status_docs = [step for step in STEPS if step.module.endswith("status_docs")]
        code = run_child([sys.executable, "-m", status_docs[0].module, f"--source={tmp}"])
    assert code == EXIT_OK, code


def _run(args: argparse.Namespace) -> int:
    if args.self_test:
        checks = [
            _check_every_step_runs_with_its_options,
            _check_a_failing_step_fails_the_run_and_the_rest_still_run,
            _check_no_selection_prints_usage_and_exits_1,
            _check_a_real_step_runs_as_a_child,
        ]
        return run_self_test(checks, wrapper=WRAPPER, module=MODULE, parser=build_parser(),
                             folder=VISUALIZE_SCRIPTS_DIR)
    return all_reports(args)


def main(argv: Sequence[str] | None = None) -> int:
    """Entry point."""
    install_sigint_handler()
    return module_main(build_parser(), _run, argv)


if __name__ == "__main__":
    sys.exit(main())
