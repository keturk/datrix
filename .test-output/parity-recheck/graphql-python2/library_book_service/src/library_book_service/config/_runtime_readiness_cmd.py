"""Readiness CLI command. Auto-generated. Do not edit.

Run with ``python -m library_book_service.config._runtime_readiness_cmd``.

Builds the SAME ``RemoteConfigClient`` the application builds (via
``config.remote_config.build_client``), runs the strict runtime readiness check,
prints one line per required item (names + statuses only -- never a resolved
value), and exits non-zero when any required item failed to resolve.
"""

from __future__ import annotations

import asyncio
import logging
import sys

from library_book_service.config._runtime_readiness import check_runtime_readiness
from library_book_service.config.remote_config import (
    build_client as build_config_client,
)

logger = logging.getLogger(__name__)

_EXIT_OK = 0
_EXIT_NOT_READY = 1


async def _run() -> int:
    """Build the config client, run the check, print results, return an exit code."""
    config_client = build_config_client()
    config_client.start()
    try:
        report = await check_runtime_readiness(config_client)
    finally:
        config_client.stop()
    for item in report.items:
        sys.stdout.write(
            f"{item.kind}\t{item.logical_name}\t{item.rendered_name}\t{item.status.value}\n"
        )
    return _EXIT_OK if report.ok else _EXIT_NOT_READY


def main() -> int:
    """Entry point: run the readiness check and return the process exit code."""
    return asyncio.run(_run())


if __name__ == "__main__":
    raise SystemExit(main())
