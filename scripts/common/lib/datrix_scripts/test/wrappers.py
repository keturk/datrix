"""What the wrapper modules share: where the wrappers live, UTF-8 output and the self-test loop.

The wrappers live in ``scripts/test/`` unless a module names its own scripts folder (``folder=``:
``DEV_SCRIPTS_DIR`` for ``scripts/dev/``, and one constant each for ``generation/``, ``visualize/``,
``codemods/``, ``review/``, ``tasks/``, ``skill/``, ``git/``, ``scan/``, ``metrics/``, ``workspace/``,
``gates/realization/``,
``gates/ratchet/`` and ``gates/repo-hygiene/``).

Every module behind a wrapper rendered from ``common/templates/entrypoint.ps1`` proves, in its
``--self-test``, that the wrapper and its ``.sh`` twin are the templates rendered and that the
wrapper's parameters are exactly the module's options (``datrix_scripts.entrypoint.wrapper_problems``),
and that its parser accepts only those exact spellings: an abbreviation argparse would expand
(``test.sh --al`` read as ``--all``) is a flag the hooks that read a ``.sh`` twin's command line
(``guard-full-suite-runs.py``) cannot see. ``run_self_test`` runs a module's own checks and those two
seam checks through the one gate check loop, prints ``SELF-TEST PASSED`` or ``SELF-TEST FAILED``, and
returns the exit code. A module whose own self-test is one function printing its own lines and
returning whether it passed joins that loop as one check (``self_test_check``).

The wrappers whose ``-Command <command> [<argument> ...]`` runs a ``datrix_testing`` CLI (cases,
tables, model-contracts) share their options (``add_command_arguments``) and their ``main``
(``run_command_wrapper``); each module states only its commands and how its CLI line is built.
"""

from __future__ import annotations

import argparse
import contextlib
import importlib
import io
import sys
from collections.abc import Callable, Sequence
from pathlib import Path
from typing import Final

from datrix_scripts.entrypoint import wrapper_problems
from datrix_scripts.gate_harness import (
    EXIT_PASS,
    EXIT_USAGE,
    EXIT_VIOLATION,
    CheckFunc,
    NamedCheck,
    named_checks,
    run_checks,
    run_main,
)
from datrix_scripts.paths import SCRIPTS_DIR

TEST_SCRIPTS_DIR: Final = SCRIPTS_DIR / "test"
DEV_SCRIPTS_DIR: Final = SCRIPTS_DIR / "dev"
GENERATION_SCRIPTS_DIR: Final = SCRIPTS_DIR / "generation"
VISUALIZE_SCRIPTS_DIR: Final = SCRIPTS_DIR / "visualize"
CODEMODS_SCRIPTS_DIR: Final = SCRIPTS_DIR / "codemods"
REVIEW_SCRIPTS_DIR: Final = SCRIPTS_DIR / "review"
TASKS_SCRIPTS_DIR: Final = SCRIPTS_DIR / "tasks"
SKILL_SCRIPTS_DIR: Final = SCRIPTS_DIR / "skill"
GIT_SCRIPTS_DIR: Final = SCRIPTS_DIR / "git"
SCAN_SCRIPTS_DIR: Final = SCRIPTS_DIR / "scan"
METRICS_SCRIPTS_DIR: Final = SCRIPTS_DIR / "metrics"
WORKSPACE_SCRIPTS_DIR: Final = SCRIPTS_DIR / "workspace"
REALIZATION_GATES_DIR: Final = SCRIPTS_DIR / "gates" / "realization"
RATCHET_GATES_DIR: Final = SCRIPTS_DIR / "gates" / "ratchet"
PARITY_GATES_DIR: Final = SCRIPTS_DIR / "gates" / "parity"
REPO_HYGIENE_GATES_DIR: Final = SCRIPTS_DIR / "gates" / "repo-hygiene"
_SEAM_CHECK_NAME: Final = "wrapper_seam"
_EXACT_SPELLING_CHECK_NAME: Final = "exact_option_spelling"
_WINDOWS_PLATFORM: Final = "win32"
_UTF8: Final = "utf-8"
_REPLACE: Final = "replace"


def add_command_arguments(parser: argparse.ArgumentParser, commands: Sequence[str]) -> None:
    """The options of a wrapper whose ``-Command <command> [<argument> ...]`` runs a ``datrix_testing`` CLI.

    The ``.ps1`` passes ``--command=<command>`` and one ``--arguments=<argument>`` per argument; a
    caller of the ``.sh`` twin may write them positionally (``cases.sh check <package>``) instead.
    Parse with ``parser.parse_intermixed_args`` so options may sit between the positionals.
    """
    parser.add_argument("positional_command", nargs="?", choices=list(commands), metavar="COMMAND",
                        help="as --command, for a caller of the .sh twin")
    parser.add_argument("positional_arguments", nargs="*", metavar="ARGUMENT",
                        help="as --arguments, for a caller of the .sh twin")
    parser.add_argument("--command", choices=list(commands), help=f"one of: {', '.join(commands)}")
    parser.add_argument("--arguments", action="append", default=[], metavar="ARGUMENT",
                        help="one positional argument of the command (repeat for each)")


def command_and_arguments(parser: argparse.ArgumentParser, args: argparse.Namespace) -> tuple[str, list[str]]:
    """The command and its arguments from *args* (options or positionals, never both); a usage error
    (``parser.error``, exit 2) when no command is given or it is given twice."""
    if args.command and args.positional_command:
        parser.error(f"the command was given twice ({args.command} and {args.positional_command}); give it once")
    command = args.command or args.positional_command
    if not command:
        parser.error("a command is required: the first argument, or --command")
    return command, [*args.arguments, *args.positional_arguments]


class CommandUsageError(Exception):
    """A command wrapper's arguments do not make a CLI command line (printed as ``Error: ...``, exit 2)."""


#: Builds the CLI's argument vector from the parsed options, the command and its arguments.
CliArgv = Callable[[argparse.Namespace, str, list[str]], list[str]]


def plain_cli_argv(args: argparse.Namespace, command: str, arguments: list[str]) -> list[str]:
    """``<command> <argument> ...``: the CLI line of a wrapper with no options besides the command's."""
    del args  # Such a wrapper has no option the CLI takes.
    return [command, *arguments]


def run_command_wrapper(
    parser: argparse.ArgumentParser,
    argv: Sequence[str] | None,
    *,
    commands: Sequence[str],
    wrapper: str,
    module: str,
    cli_module: str,
    cli_argv: CliArgv = plain_cli_argv,
    checks: Sequence[CheckFunc] = (),
    folder: Path = TEST_SCRIPTS_DIR,
) -> int:
    """The ``main`` of a command wrapper module: parse *argv*, then run the self-test (*checks*, the
    command-line cases and the seam of ``<folder>/<wrapper>.ps1``) or the CLI *cli_module* on the line
    *cli_argv* builds.

    ``--dbg`` prints the interpreter and the CLI arguments before the run, as the wrapper's ``-Dbg``
    always has, and nothing more: logging is left to the CLI, which runs in this process. A
    ``CommandUsageError`` from *cli_argv* is printed as ``Error: ...`` and exits 2.
    """
    args = parser.parse_intermixed_args(argv)
    if args.self_test:
        def _check_command_line() -> None:
            failures = command_line_problems(parser, commands)
            assert not failures, "\n".join(failures)

        return run_self_test([*checks, _check_command_line], wrapper=wrapper, module=module, parser=parser,
                             folder=folder)
    command, arguments = command_and_arguments(parser, args)
    try:
        line = cli_argv(args, command, arguments)
    except CommandUsageError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return EXIT_USAGE
    if args.dbg:
        print(f"Python executable: {sys.executable}")
        print(f"Arguments: -m {cli_module} {' '.join(line)}", flush=True)
    cli_main: Callable[[Sequence[str] | None], int] = importlib.import_module(cli_module).main
    return cli_main(line)


def command_line_problems(parser: argparse.ArgumentParser, commands: Sequence[str]) -> list[str]:
    """The command-line cases every command wrapper module must parse alike; the failures, empty when all hold."""
    first, second = commands[0], commands[-1]
    cases = (
        ([f"--command={first}", "--arguments=a", "--arguments=b"], (first, ["a", "b"])),
        ([first, "a", "b"], (first, ["a", "b"])),
        ([second], (second, [])),
    )
    failures = [
        f"{argv} parsed as {parsed}, expected {expected}"
        for argv, expected in cases
        if (parsed := command_and_arguments(parser, parser.parse_intermixed_args(argv))) != expected
    ]
    for refused in ([], [f"--command={first}", second], ["no-such-command"]):
        try:
            with contextlib.redirect_stderr(io.StringIO()):  # argparse's usage text for a case refused on purpose.
                command_and_arguments(parser, parser.parse_intermixed_args(refused))
        except SystemExit as exc:
            if exc.code == EXIT_USAGE:
                continue
        failures.append(f"{refused} was not refused as a usage error")
    return failures


def ensure_utf8_stdio() -> None:
    """Write stdout and stderr as UTF-8 on Windows, whose console code page (cp1252) cannot encode the
    box-drawing rules these modules print or the test output they relay; elsewhere a no-op."""
    if sys.platform != _WINDOWS_PLATFORM:
        return
    for stream in (sys.stdout, sys.stderr):
        if isinstance(stream, io.TextIOWrapper):
            stream.reconfigure(encoding=_UTF8, errors=_REPLACE)


def module_main(
    parser: argparse.ArgumentParser, run: Callable[[argparse.Namespace], int], argv: Sequence[str] | None
) -> int:
    """The ``main`` of a module behind a rendered wrapper: UTF-8 stdio, then *run* on *argv* parsed by *parser*
    (``gate_harness.run_main``: logging from ``--dbg``, a ``UsageError`` exits 2)."""
    ensure_utf8_stdio()
    return run_main(lambda: parser.parse_args(argv), run)


def seam_checks(
    *, wrapper: str, module: str, parser: argparse.ArgumentParser, folder: Path = TEST_SCRIPTS_DIR
) -> list[NamedCheck]:
    """The seam checks of ``<folder>/<wrapper>.ps1`` (``scripts/test/`` unless *folder* names another
    scripts folder) against *module*'s *parser*: the wrapper and its twin are the templates rendered
    with exactly the parser's options, spelled exactly."""

    def check_wrapper_seam() -> None:
        problems = wrapper_problems(folder / f"{wrapper}.ps1", module, parser)
        assert not problems, "\n".join(problems)

    def check_exact_option_spelling() -> None:
        assert not parser.allow_abbrev, (
            f"{module}'s parser accepts abbreviated options (an option such as --al would be read as --all), "
            "a spelling no hook reading the command line can see; expected argparse.ArgumentParser(..., "
            "allow_abbrev=False)"
        )

    return [
        NamedCheck(_SEAM_CHECK_NAME, check_wrapper_seam),
        NamedCheck(_EXACT_SPELLING_CHECK_NAME, check_exact_option_spelling),
    ]


def self_test_check(name: str, self_test: Callable[[], bool]) -> NamedCheck:
    """*self_test* (a module's own self-test, which prints its own lines and returns whether every one
    passed) as one check named *name*, failing when it returns False."""

    def check() -> None:
        assert self_test(), f"{name} reported a failure (see the lines above)"

    return NamedCheck(name, check)


def run_self_test(
    checks: Sequence[CheckFunc | NamedCheck],
    *,
    wrapper: str,
    module: str,
    parser: argparse.ArgumentParser,
    folder: Path = TEST_SCRIPTS_DIR,
) -> int:
    """Run *checks* and the ``seam_checks`` of ``<folder>/<wrapper>.ps1`` against *module*'s *parser*.

    Prints ``[OK]``/``[FAIL]`` per check and the verdict line; returns 0 when every check passed, else 1.
    """
    seam = seam_checks(wrapper=wrapper, module=module, parser=parser, folder=folder)
    passed = run_checks([*named_checks(checks), *seam])
    print()
    print("SELF-TEST PASSED" if passed else "SELF-TEST FAILED: see failures above.")
    return EXIT_PASS if passed else EXIT_VIOLATION
