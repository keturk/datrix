#!/usr/bin/env python3
"""Set up the line-edit MCP server (``datrix-edit``) that agents read and edit files through by line.

The module behind ``dev/line-edit.ps1`` (and its ``.sh`` twin). The server
(``datrix_scripts.dev.line_edit_mcp``, logic in ``datrix_scripts.line_edits``) gives agents
``read_lines``, which shows every line numbered and hashed, and ``edit_lines``, which replaces or
inserts line ranges, many at once across files, naming the old lines by number and hash instead of
re-sending their text. ``--setup`` registers it in the workspace's ``.mcp.json``.

Exit codes: 0 done, 1 the request could not be carried out (the message says why).
"""

from __future__ import annotations

import argparse
import importlib.util
import sys
from collections.abc import Sequence
from typing import Final

from datrix_scripts.dev.mcp_setup import SELF_TEST_CHECKS as SETUP_CHECKS
from datrix_scripts.dev.mcp_setup import run_setup
from datrix_scripts.paths import WORKSPACE_DIR
from datrix_scripts.test.wrappers import DEV_SCRIPTS_DIR, module_main, run_self_test

MODULE: Final = "datrix_scripts.dev.line_edit"
WRAPPER: Final = "line-edit"
MCP_SERVER_NAME: Final = "datrix-edit"
MCP_SERVER_MODULE: Final = "datrix_scripts.dev.line_edit_mcp"
SETUP_COMMAND: Final = "line-edit.ps1 -Setup"

EXIT_REFUSED: Final = 1
NO_ACTION_MESSAGE: Final = (
    "Pass -Setup to register the datrix-edit MCP server on this machine (Get-Help .\\line-edit.ps1 -Full)."
)


def build_parser() -> argparse.ArgumentParser:
    """The options of ``dev/line-edit.ps1``: one per wrapper parameter, spelled exactly."""
    parser = argparse.ArgumentParser(allow_abbrev=False, description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--setup", action="store_true",
                        help="Register the datrix-edit MCP server for this machine in .mcp.json.")
    parser.add_argument("--self-test", action="store_true",
                        help="Run only the self-test: -Setup is required, the server module it registers exists, "
                             "and the setup writes its two files in a temporary workspace.")
    parser.set_defaults(debug=False)
    return parser


def _check_setup_is_required() -> None:
    parser = build_parser()
    assert not parser.parse_args([]).setup
    assert parser.parse_args(["--setup"]).setup


def _check_the_registered_server_module_exists() -> None:
    # .mcp.json starts the server as `python -m MCP_SERVER_MODULE`: a module that does not resolve
    # would register a server that cannot start.
    assert importlib.util.find_spec(MCP_SERVER_MODULE) is not None, (
        f"{MCP_SERVER_MODULE} does not resolve on this interpreter's path; -Setup would register a server "
        "that cannot start"
    )


def main(argv: Sequence[str] | None = None) -> int:
    """Entry point."""
    return module_main(build_parser(), _run, argv)


def _run(args: argparse.Namespace) -> int:
    if args.self_test:
        # The setup -Setup runs, in a temporary workspace: the two files it writes, an invalid file refused.
        checks = [_check_setup_is_required, _check_the_registered_server_module_exists, *SETUP_CHECKS]
        return run_self_test(checks, wrapper=WRAPPER, module=MODULE, parser=build_parser(), folder=DEV_SCRIPTS_DIR)
    if not args.setup:
        print(NO_ACTION_MESSAGE, file=sys.stderr)
        return EXIT_REFUSED
    return run_setup(name=MCP_SERVER_NAME, module=MCP_SERVER_MODULE, workspace=WORKSPACE_DIR,
                     setup_command=SETUP_COMMAND)


if __name__ == "__main__":
    sys.exit(main())
