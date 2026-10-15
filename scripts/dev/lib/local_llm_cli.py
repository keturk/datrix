#!/usr/bin/env python3
"""Command line for the local model servers: status, usage and model residency (wrapped by dev/local-llm.ps1).

Usage:
    local_llm_cli.py status [--days N]   which servers answer, what they hold, usage over N days
    local_llm_cli.py usage [--days N]    the usage report alone (0 = everything logged)
    local_llm_cli.py pin                 keep the first preferred installed model resident on every machine
    local_llm_cli.py unpin               unload every indefinitely resident model on every machine
"""

from __future__ import annotations

import argparse
import sys
from datetime import UTC, datetime

from datrix_scripts.local_llm import LocalLlmSettings, pin_models, unpin_models
from datrix_scripts.local_llm_usage import usage_report
from local_llm_mcp import DEFAULT_USAGE_DAYS, mcp_settings, models_status

DEFAULT_REPORT_DAYS = 7


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description="Local model servers: status, usage and model residency.")
    commands = parser.add_subparsers(dest="command", required=True)
    status = commands.add_parser("status", help="Which servers answer, what they hold, and recent usage.")
    status.add_argument("--days", type=int, default=DEFAULT_USAGE_DAYS, help="Usage days to cover.")
    usage = commands.add_parser("usage", help="The usage report: requests by caller and by server.")
    usage.add_argument("--days", type=int, default=DEFAULT_REPORT_DAYS, help="Days to cover; 0 = everything.")
    # A pin loads a model, so it runs with the default settings (loads allowed, the long load timeout).
    commands.add_parser("pin", help="Keep the first preferred installed model resident on every machine.")
    commands.add_parser("unpin", help="Unload every indefinitely resident model on every machine.")
    args = parser.parse_args(argv)
    if args.command == "pin":
        print("\n".join(pin_models(LocalLlmSettings())))
        return 0
    if args.command == "unpin":
        print("\n".join(unpin_models(LocalLlmSettings(), datetime.now(UTC))))
        return 0
    if args.days < 0:
        parser.error(f"--days must be 0 (everything) or a positive number of days; got {args.days}.")
    settings = mcp_settings()
    if args.command == "status":
        print(models_status(settings, args.days))
    else:
        print(usage_report(settings.usage_log, args.days).render())
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
