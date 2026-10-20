#!/usr/bin/env python3
"""The local model servers: setup, status, usage and model residency.

The module behind ``dev/local-llm.ps1`` (and its ``.sh`` twin): exactly one action per run.
``--setup`` registers the agents' MCP server (``datrix_scripts.dev.local_llm_mcp``) in the
workspace's ``.mcp.json``; ``--status`` shows which servers answer and what they hold;
``--usage`` reports requests by caller and by server; ``--pin``/``--unpin`` keep a model
resident on every machine, or release it.

Exit codes: 0 done, 1 the request could not be carried out (the message says why).
"""

from __future__ import annotations

import argparse
import sys
from collections.abc import Sequence
from datetime import UTC, datetime
from typing import Final

from datrix_scripts.dev.local_llm_mcp import DEFAULT_USAGE_DAYS, mcp_settings, models_status
from datrix_scripts.dev.mcp_setup import run_setup
from datrix_scripts.gate_harness import install_sigint_handler
from datrix_scripts.local_llm import LocalLlmSettings, pin_models, unpin_models
from datrix_scripts.local_llm_usage import usage_report
from datrix_scripts.paths import WORKSPACE_DIR
from datrix_scripts.test.wrappers import DEV_SCRIPTS_DIR, module_main, run_self_test

MODULE: Final = "datrix_scripts.dev.local_llm"
WRAPPER: Final = "local-llm"
MCP_SERVER_NAME: Final = "datrix-local-llm"
MCP_SERVER_MODULE: Final = "datrix_scripts.dev.local_llm_mcp"
SETUP_COMMAND: Final = "local-llm.ps1 -Setup"

EXIT_OK: Final = 0
EXIT_REFUSED: Final = 1
DEFAULT_REPORT_DAYS: Final = 7
#: -Days's "not given": -Status and -Usage keep their own defaults.
DAYS_NOT_GIVEN: Final = -1
#: The actions, in the order the usage message names them: (wrapper parameter, option dest).
ACTIONS: Final = (
    ("-Setup", "setup"),
    ("-Status", "status"),
    ("-Usage", "usage"),
    ("-Pin", "pin"),
    ("-Unpin", "unpin"),
)
_DAYS_ACTIONS: Final = frozenset({"status", "usage"})


def build_parser() -> argparse.ArgumentParser:
    """The options of ``dev/local-llm.ps1``: one per wrapper parameter, spelled exactly."""
    parser = argparse.ArgumentParser(allow_abbrev=False, description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--setup", action="store_true", help="Register the local-model MCP server for this machine.")
    parser.add_argument("--status", action="store_true", help="Which servers answer, what they hold, and recent usage.")
    parser.add_argument("--usage", action="store_true", help="The usage report: requests by caller and by server.")
    # A pin loads a model, so it runs with the default settings (loads allowed, the long load timeout).
    parser.add_argument("--pin", action="store_true",
                        help="Keep the first preferred installed model resident on every machine.")
    parser.add_argument("--unpin", action="store_true", help="Unload every indefinitely resident model on every machine.")
    parser.add_argument("--days", type=int, default=DAYS_NOT_GIVEN,
                        help=f"With --status (default {DEFAULT_USAGE_DAYS}) or --usage (default {DEFAULT_REPORT_DAYS}): "
                             "days to cover; 0 = everything logged.")
    parser.add_argument("--self-test", action="store_true",
                        help="Run only the self-test: exactly one action is required, and --days only with "
                             "--status or --usage.")
    parser.set_defaults(debug=False)
    return parser


def refusal(args: argparse.Namespace) -> str:
    """Why *args* cannot run (no action, several, or --days with an action that takes none), or ``""``."""
    chosen = [(flag, dest) for flag, dest in ACTIONS if getattr(args, dest)]
    if len(chosen) != 1:
        given = ", ".join(flag for flag, _ in chosen) or "none"
        listed = ", ".join(flag for flag, _ in ACTIONS[:-1])
        return (f"Pass exactly one action: {listed} or {ACTIONS[-1][0]} (given: {given}). "
                "Get-Help .\\local-llm.ps1 -Full lists them.")
    flag, dest = chosen[0]
    if args.days >= 0 and dest not in _DAYS_ACTIONS:
        return f"-Days applies to -Status and -Usage only; {flag} takes no other parameter."
    return ""


def report_days(args: argparse.Namespace) -> int:
    """The days -Status or -Usage covers: --days when given, else the action's own default."""
    if args.days >= 0:
        return int(args.days)
    return DEFAULT_USAGE_DAYS if args.status else DEFAULT_REPORT_DAYS


def _check_exactly_one_action_is_required() -> None:
    parser = build_parser()
    assert refusal(parser.parse_args([])) == (
        "Pass exactly one action: -Setup, -Status, -Usage, -Pin or -Unpin (given: none). "
        "Get-Help .\\local-llm.ps1 -Full lists them."
    ), refusal(parser.parse_args([]))
    assert "(given: -Status, -Pin)" in refusal(parser.parse_args(["--pin", "--status"]))
    assert refusal(parser.parse_args(["--unpin"])) == ""


def _check_days_only_with_status_or_usage() -> None:
    parser = build_parser()
    assert refusal(parser.parse_args(["--pin", "--days=1"])) == (
        "-Days applies to -Status and -Usage only; -Pin takes no other parameter."
    )
    assert refusal(parser.parse_args(["--usage", "--days=0"])) == ""
    assert report_days(parser.parse_args(["--status"])) == DEFAULT_USAGE_DAYS
    assert report_days(parser.parse_args(["--usage"])) == DEFAULT_REPORT_DAYS
    assert report_days(parser.parse_args(["--usage", "--days=0"])) == 0


def main(argv: Sequence[str] | None = None) -> int:
    """Entry point."""
    install_sigint_handler()
    return module_main(build_parser(), _run, argv)


def _run(args: argparse.Namespace) -> int:
    if args.self_test:
        checks = [_check_exactly_one_action_is_required, _check_days_only_with_status_or_usage]
        return run_self_test(checks, wrapper=WRAPPER, module=MODULE, parser=build_parser(), folder=DEV_SCRIPTS_DIR)
    problem = refusal(args)
    if problem:
        print(problem)
        return EXIT_REFUSED
    if args.setup:
        return run_setup(name=MCP_SERVER_NAME, module=MCP_SERVER_MODULE, workspace=WORKSPACE_DIR,
                         setup_command=SETUP_COMMAND)
    if args.pin:
        print("\n".join(pin_models(LocalLlmSettings())))
        return EXIT_OK
    if args.unpin:
        print("\n".join(unpin_models(LocalLlmSettings(), datetime.now(UTC))))
        return EXIT_OK
    settings = mcp_settings()
    if args.status:
        print(models_status(settings, report_days(args)))
    else:
        print(usage_report(settings.usage_log, report_days(args)).render())
    return EXIT_OK


if __name__ == "__main__":
    sys.exit(main())
