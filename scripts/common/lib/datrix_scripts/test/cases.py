"""Author, migrate and check declarative test cases, behind ``test/cases.ps1``: runs ``datrix_testing.cases.cli``.

A case is one row of a package's ``tests/cases/<area>.cases.yaml``: a stage run on a committed input,
one observed value and an authored expectation, run by the package's ``tests/test_cases.py``. This
module turns the wrapper's ``-Command``, ``-Arguments`` and named fields into the CLI's line:

* ``observe`` needs ``-Package`` (and takes ``-At <file>:<line>``);
* ``new`` needs every field of the case (``-Id``, ``-Tags``, ``-CaseInput``, ``-Stage``,
  ``-Observer``, ``-Selector``, ``-Reason``) and passes ``-Expectation`` only when given, since an
  absent case takes none;
* ``migrate`` passes ``-Annotations``; ``accept`` and ``check`` take their arguments alone.

A missing field is a usage error (``Error: ...``, exit 2) before the CLI runs.
"""

from __future__ import annotations

import argparse
import sys
from collections.abc import Sequence
from typing import Final

from datrix_scripts.entrypoint import wrapper_flag
from datrix_scripts.test.wrappers import (
    CommandUsageError,
    add_command_arguments,
    command_and_arguments,
    run_command_wrapper,
)

MODULE: Final = "datrix_scripts.test.cases"
WRAPPER: Final = "cases"
CLI_MODULE: Final = "datrix_testing.cases.cli"
COMMAND_OBSERVE: Final = "observe"
COMMAND_NEW: Final = "new"
COMMAND_MIGRATE: Final = "migrate"
COMMANDS: Final = (COMMAND_OBSERVE, COMMAND_NEW, COMMAND_MIGRATE, "accept", "check")
#: Each field ``new`` requires: the CLI's flag, the wrapper parameter, the parsed attribute.
NEW_FIELDS: Final = (
    ("--id", "Id", "id"),
    ("--tags", "Tags", "tags"),
    ("--input", "CaseInput", "case_input"),
    ("--stage", "Stage", "stage"),
    ("--observer", "Observer", "observer"),
    ("--selector", "Selector", "selector"),
    ("--reason", "Reason", "reason"),
)


def _observe_line(args: argparse.Namespace, arguments: list[str]) -> list[str]:
    if not args.package:
        raise CommandUsageError(
            f"observe needs {wrapper_flag('Package')} <package>: the package whose inputs to load."
        )
    at = ["--at", args.at] if args.at else []
    return [COMMAND_OBSERVE, "--package", args.package, *at, *arguments]


def _new_line(args: argparse.Namespace, arguments: list[str]) -> list[str]:
    line = [COMMAND_NEW, *arguments]
    for cli_flag, parameter, attribute in NEW_FIELDS:
        value = getattr(args, attribute)
        if not value:
            raise CommandUsageError(f"new needs {wrapper_flag(parameter)}: every field of a case comes from you.")
        line.extend([cli_flag, value])
    if args.expectation is not None:
        line.extend(["--expectation", args.expectation])
    return line


def cases_cli_argv(args: argparse.Namespace, command: str, arguments: list[str]) -> list[str]:
    """The ``datrix_testing.cases.cli`` line for *command*.

    Raises:
        CommandUsageError: ``observe`` without ``-Package``, or ``new`` without one of its fields.
    """
    if command == COMMAND_OBSERVE:
        return _observe_line(args, arguments)
    if command == COMMAND_NEW:
        return _new_line(args, arguments)
    if command == COMMAND_MIGRATE and args.annotations:
        return [command, *arguments, "--annotations"]
    return [command, *arguments]


def build_parser() -> argparse.ArgumentParser:
    """The options ``test/cases.ps1`` passes (each wrapper parameter as ``--kebab-name``)."""
    parser = argparse.ArgumentParser(
        prog="cases",
        description=(
            "Author, migrate and check declarative test cases: observe | new | migrate | accept | check "
            "(see Get-Help test\\cases.ps1 for each command's arguments)."
        ),
        allow_abbrev=False,
    )
    add_command_arguments(parser, COMMANDS)
    parser.add_argument("--package", help="observe: the package whose named inputs and registrations to load")
    parser.add_argument("--at", help="observe: a fixture line, <file>:<line>, in place of the four positionals")
    parser.add_argument("--annotations", action="store_true",
                        help="migrate: propose fixture annotations and per-code fixtures instead of case rows")
    parser.add_argument("--id", help="new: the case id, <area>.<slug>")
    parser.add_argument("--tags", help="new: the feature tags, comma-separated")
    parser.add_argument("--case-input", help="new: the named input")
    parser.add_argument("--stage", help="new: the stage (generate, analyze, or one the package registers)")
    parser.add_argument("--observer", help="new: the observer kind")
    parser.add_argument("--selector", help="new: the selector, a YAML flow mapping")
    parser.add_argument("--expectation", default=None, help="new: the expectation, a YAML flow value; omit for an absent case")
    parser.add_argument("--reason", help="new: one sentence naming the decision the case protects")
    parser.add_argument("--dbg", action="store_true", help="print the interpreter and the CLI arguments first")
    parser.add_argument("--self-test", action="store_true", help="run this module's self-test")
    return parser


_PLANTED_FIELDS: Final = (
    "--id=compose.basic.api.port", "--tags=compose", "--case-input=basic", "--stage=generate",
    "--observer=surface", "--selector={path: docker-compose.yml}", "--reason=The API is published.",
)


def _line(argv: list[str]) -> list[str]:
    parser = build_parser()
    args = parser.parse_intermixed_args(argv)
    return cases_cli_argv(args, *command_and_arguments(parser, args))


def _refusal(argv: list[str]) -> str:
    try:
        _line(argv)
    except CommandUsageError as exc:
        return str(exc)
    return ""


def _check_cli_lines() -> None:
    cases = (
        (["observe", "basic", "generate", "--package=datrix-x", "--at=f.dtrx:3"],
         ["observe", "--package", "datrix-x", "--at", "f.dtrx:3", "basic", "generate"]),
        (["--command=migrate", "--arguments=datrix-x", "--arguments=m.py", "--annotations"],
         ["migrate", "datrix-x", "m.py", "--annotations"]),
        (["accept", "p.json", "--annotations"], ["accept", "p.json"]),
        (["new", "datrix-x", "compose", *_PLANTED_FIELDS, "--expectation="],
         ["new", "datrix-x", "compose", "--id", "compose.basic.api.port", "--tags", "compose", "--input", "basic",
          "--stage", "generate", "--observer", "surface", "--selector", "{path: docker-compose.yml}",
          "--reason", "The API is published.", "--expectation", ""]),
    )
    for argv, expected in cases:
        line = _line(argv)
        assert line == expected, f"{argv} built {line}, expected {expected}"


def _check_usage_refusals() -> None:
    observe = _refusal(["observe", "basic"])
    assert observe.startswith(f"observe needs {wrapper_flag('Package')} "), f"observe without a package: {observe!r}"
    without_tags = [field for field in _PLANTED_FIELDS if not field.startswith("--tags")]
    new = _refusal(["new", "datrix-x", "compose", *without_tags])
    assert new == f"new needs {wrapper_flag('Tags')}: every field of a case comes from you.", f"new without tags: {new!r}"
    assert _line(["new", "datrix-x", "compose", *_PLANTED_FIELDS])[-2:] != ["--expectation", ""], (
        "an absent case was given an expectation"
    )


def main(argv: Sequence[str] | None = None) -> int:
    return run_command_wrapper(
        build_parser(), argv, commands=COMMANDS, wrapper=WRAPPER, module=MODULE, cli_module=CLI_MODULE,
        cli_argv=cases_cli_argv, checks=(_check_cli_lines, _check_usage_refusals),
    )


if __name__ == "__main__":
    sys.exit(main())
