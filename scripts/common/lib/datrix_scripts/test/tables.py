"""Inspect and migrate table contracts, behind ``test/tables.ps1``: runs ``datrix_testing.tables.cli``.

A package's runner module, ``tests/test_tables.py``, proves every row of every table its
``tests/conftest.py`` registered as one pytest item per row; ``rows`` shows those items,
``inventory``/``migrate`` find the per-row hand tests they make redundant, and ``accept`` deletes the
ones an approved proposal names. The wrapper's ``-Command`` and ``-Arguments`` are the CLI's line.
"""

from __future__ import annotations

import argparse
import sys
from collections.abc import Sequence
from typing import Final

from datrix_scripts.test.wrappers import add_command_arguments, run_command_wrapper

MODULE: Final = "datrix_scripts.test.tables"
WRAPPER: Final = "tables"
CLI_MODULE: Final = "datrix_testing.tables.cli"
COMMANDS: Final = ("rows", "inventory", "migrate", "accept")


def build_parser() -> argparse.ArgumentParser:
    """The options ``test/tables.ps1`` passes (each wrapper parameter as ``--kebab-name``)."""
    parser = argparse.ArgumentParser(
        prog="tables",
        description=(
            "Inspect and migrate table contracts: rows <package> [<table>] | inventory <package> | "
            "migrate <package> | accept <proposal>."
        ),
        allow_abbrev=False,
    )
    add_command_arguments(parser, COMMANDS)
    parser.add_argument("--dbg", action="store_true", help="print the interpreter and the CLI arguments first")
    parser.add_argument("--self-test", action="store_true", help="run this module's self-test")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    return run_command_wrapper(
        build_parser(), argv, commands=COMMANDS, wrapper=WRAPPER, module=MODULE, cli_module=CLI_MODULE
    )


if __name__ == "__main__":
    sys.exit(main())
