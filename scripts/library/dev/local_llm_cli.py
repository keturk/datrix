#!/usr/bin/env python3
"""Command line for the local model servers: status and usage (wrapped by dev/local-llm.ps1).

Usage:
    local_llm_cli.py status [--days N]   which servers answer, what they hold, usage over N days
    local_llm_cli.py usage [--days N]    the usage report alone (0 = everything logged)
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

_library_dir = Path(__file__).resolve().parent.parent
if str(_library_dir) not in sys.path:
    sys.path.insert(0, str(_library_dir))

from dev.local_llm_mcp import DEFAULT_USAGE_DAYS, mcp_settings, models_status  # noqa: E402
from shared.local_llm_usage import usage_report  # noqa: E402

DEFAULT_REPORT_DAYS = 7


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description="Local model servers: status and usage.")
    commands = parser.add_subparsers(dest="command", required=True)
    status = commands.add_parser("status", help="Which servers answer, what they hold, and recent usage.")
    status.add_argument("--days", type=int, default=DEFAULT_USAGE_DAYS, help="Usage days to cover.")
    usage = commands.add_parser("usage", help="The usage report: requests by caller and by server.")
    usage.add_argument("--days", type=int, default=DEFAULT_REPORT_DAYS, help="Days to cover; 0 = everything.")
    args = parser.parse_args(argv)
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
