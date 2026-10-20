"""Inspect and migrate schema-derived model contracts, behind ``test/model-contracts.ps1``: runs
``datrix_testing.model_contracts.cli``.

A package's model contract runner, ``tests/test_model_contracts.py``, derives each config model's
required fields, defaults, bounds, patterns and unknown-key refusal and proves them on the committed
``.dcfg`` fixtures that reach it; ``facts`` shows what it derives, ``inventory``/``migrate`` find the
hand tests it makes redundant, and ``accept`` deletes the ones an approved proposal names. The
wrapper's ``-Command`` and ``-Arguments`` are the CLI's line.
"""

from __future__ import annotations

import argparse
import sys
from collections.abc import Sequence
from typing import Final

from datrix_scripts.test.wrappers import add_command_arguments, run_command_wrapper

MODULE: Final = "datrix_scripts.test.model_contracts"
WRAPPER: Final = "model-contracts"
CLI_MODULE: Final = "datrix_testing.model_contracts.cli"
COMMANDS: Final = ("facts", "inventory", "migrate", "accept")


def build_parser() -> argparse.ArgumentParser:
    """The options ``test/model-contracts.ps1`` passes (each wrapper parameter as ``--kebab-name``)."""
    parser = argparse.ArgumentParser(
        prog="model-contracts",
        description=(
            "Inspect and migrate schema-derived model contracts: facts <package> [<model>] | "
            "inventory <package> | migrate <package> | accept <proposal>."
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
