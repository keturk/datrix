"""Author, migrate and check parity rows, behind ``gates/parity/parity-cases.ps1``: runs
``datrix_scripts.gates.parity.parity_cases_cli``.

A parity row is a case row whose stage is ``parity`` and whose observer is a conformance probe, read
on every registered target of the probe's axis by ``parity-cases-gate.ps1``. This module turns the
wrapper's ``-Command``, ``-Arguments`` and named fields into the CLI's line:

* ``new`` needs every field of the row (``-Id``, ``-Tags``, ``-CaseInput``, ``-Probe``, ``-Selector``,
  ``-Expectation``, ``-Reason``);
* ``migrate`` needs ``-Area`` and passes ``-Tags`` and ``-Replaces`` when given;
* ``observe``, ``accept`` and ``check`` take their arguments alone.

A missing field is a usage error (``Error: ...``, exit 2) before the CLI runs.
"""

from __future__ import annotations

import argparse
import sys
from collections.abc import Sequence
from typing import Final

from datrix_scripts.entrypoint import wrapper_flag
from datrix_scripts.test.wrappers import (
    PARITY_GATES_DIR,
    CommandUsageError,
    add_command_arguments,
    command_and_arguments,
    run_command_wrapper,
)

MODULE: Final = "datrix_scripts.gates.parity.parity_cases"
WRAPPER: Final = "parity-cases"
CLI_MODULE: Final = "datrix_scripts.gates.parity.parity_cases_cli"
COMMAND_NEW: Final = "new"
COMMAND_MIGRATE: Final = "migrate"
COMMANDS: Final = ("observe", COMMAND_NEW, COMMAND_MIGRATE, "accept", "check")
#: Each field ``new`` requires: the CLI's flag, the wrapper parameter, the parsed attribute.
NEW_FIELDS: Final = (
    ("--id", "Id", "id"),
    ("--tags", "Tags", "tags"),
    ("--input", "CaseInput", "case_input"),
    ("--probe", "Probe", "probe"),
    ("--selector", "Selector", "selector"),
    ("--expectation", "Expectation", "expectation"),
    ("--reason", "Reason", "reason"),
)
#: The fields ``migrate`` passes when given: the CLI's flag and the parsed attribute.
MIGRATE_OPTIONAL_FIELDS: Final = (("--tags", "tags"), ("--replaces", "replaces"))


def _new_line(args: argparse.Namespace, arguments: list[str]) -> list[str]:
    line = [COMMAND_NEW, *arguments]
    for cli_flag, parameter, attribute in NEW_FIELDS:
        value = getattr(args, attribute)
        if not value:
            raise CommandUsageError(f"new needs {wrapper_flag(parameter)}: every field of a row comes from you.")
        line.extend([cli_flag, value])
    return line


def _migrate_line(args: argparse.Namespace, arguments: list[str]) -> list[str]:
    if not args.area:
        raise CommandUsageError(
            f"migrate needs {wrapper_flag('Area')} <area>: the file the proposed rows belong to."
        )
    line = [COMMAND_MIGRATE, *arguments, "--area", args.area]
    for cli_flag, attribute in MIGRATE_OPTIONAL_FIELDS:
        value = getattr(args, attribute)
        if value:
            line.extend([cli_flag, value])
    return line


def parity_cases_cli_argv(args: argparse.Namespace, command: str, arguments: list[str]) -> list[str]:
    """The ``parity_cases_cli`` line for *command*.

    Raises:
        CommandUsageError: ``new`` without one of its fields, or ``migrate`` without ``-Area``.
    """
    if command == COMMAND_NEW:
        return _new_line(args, arguments)
    if command == COMMAND_MIGRATE:
        return _migrate_line(args, arguments)
    return [command, *arguments]


def build_parser() -> argparse.ArgumentParser:
    """The options ``gates/parity/parity-cases.ps1`` passes (each wrapper parameter as ``--kebab-name``)."""
    parser = argparse.ArgumentParser(
        prog=WRAPPER,
        description=(
            "Author, migrate and check parity rows: observe | new | migrate | accept | check "
            "(see Get-Help gates\\parity\\parity-cases.ps1 for each command's arguments)."
        ),
        allow_abbrev=False,
    )
    add_command_arguments(parser, COMMANDS)
    parser.add_argument("--id", help="new: the row id, <area>.<slug>")
    parser.add_argument("--tags", help="new, migrate: the feature tags, comma-separated")
    parser.add_argument("--case-input", help="new: the fixture, a registered example or a header-set fixture")
    parser.add_argument("--probe", help="new: the conformance probe method the row observes")
    parser.add_argument("--selector", help="new: the selector, a YAML flow mapping")
    parser.add_argument("--expectation", help="new: the expectation, a YAML flow value")
    parser.add_argument("--reason", help="new: one sentence naming the decision the row protects")
    parser.add_argument("--area", help="migrate: the area of the proposed rows")
    parser.add_argument("--replaces", help="migrate: the probe-backed gate the rows replace, by wrapper name")
    parser.add_argument("--dbg", action="store_true", help="print the interpreter and the CLI arguments first")
    parser.add_argument("--self-test", action="store_true", help="run this module's self-test")
    return parser


_PLANTED_FIELDS: Final = (
    "--id=routes.books.get", "--tags=parity,rest-api", "--case-input=rest-api", "--probe=route_wire_contracts",
    "--selector={facet: route}", "--expectation={status: 200}", "--reason=The read route answers 200.",
)


def _line(argv: list[str]) -> list[str]:
    parser = build_parser()
    args = parser.parse_intermixed_args(argv)
    return parity_cases_cli_argv(args, *command_and_arguments(parser, args))


def _refusal(argv: list[str]) -> str:
    try:
        _line(argv)
    except CommandUsageError as exc:
        return str(exc)
    return ""


def _check_cli_lines() -> None:
    cases = (
        (["observe", "rest-api", "route_wire_contracts", "{facet: route}"],
         ["observe", "rest-api", "route_wire_contracts", "{facet: route}"]),
        (["--command=migrate", "--arguments=pubsub", "--arguments=event_envelopes", "--area=events", "--tags=pubsub"],
         ["migrate", "pubsub", "event_envelopes", "--area", "events", "--tags", "pubsub"]),
        (["migrate", "pubsub", "event_envelopes", "--area=events", "--replaces=x-gate"],
         ["migrate", "pubsub", "event_envelopes", "--area", "events", "--replaces", "x-gate"]),
        (["accept", "p.json", "--area=events"], ["accept", "p.json"]),
        (["new", "routes", *_PLANTED_FIELDS],
         ["new", "routes", "--id", "routes.books.get", "--tags", "parity,rest-api", "--input", "rest-api",
          "--probe", "route_wire_contracts", "--selector", "{facet: route}", "--expectation", "{status: 200}",
          "--reason", "The read route answers 200."]),
    )
    for argv, expected in cases:
        line = _line(argv)
        assert line == expected, f"{argv} built {line}, expected {expected}"


def _check_usage_refusals() -> None:
    without_expectation = [field for field in _PLANTED_FIELDS if not field.startswith("--expectation")]
    new = _refusal(["new", "routes", *without_expectation])
    expected_new = f"new needs {wrapper_flag('Expectation')}: every field of a row comes from you."
    assert new == expected_new, f"new without an expectation: {new!r}"
    migrate = _refusal(["migrate", "pubsub", "event_envelopes"])
    assert migrate.startswith(f"migrate needs {wrapper_flag('Area')} "), f"migrate without an area: {migrate!r}"


def main(argv: Sequence[str] | None = None) -> int:
    return run_command_wrapper(
        build_parser(), argv, commands=COMMANDS, wrapper=WRAPPER, module=MODULE, cli_module=CLI_MODULE,
        cli_argv=parity_cases_cli_argv, checks=(_check_cli_lines, _check_usage_refusals), folder=PARITY_GATES_DIR,
    )


if __name__ == "__main__":
    sys.exit(main())
