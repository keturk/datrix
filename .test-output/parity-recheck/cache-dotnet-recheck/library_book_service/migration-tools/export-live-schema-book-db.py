"""Environment-side live-schema exporter for the postgres database.

GENERATED FILE — do not edit by hand. Rendered by datrix-codegen-sql for
rdbms_id be71df4e-831f-4cfb-be66-0dc89a523a60.

This tool runs WHERE THE DATABASE IS REACHABLE (the deployment/staging
environment), NOT on the Datrix workstation. It opens a READ-ONLY connection
using credentials taken from its runtime environment only, reflects the live
catalog into a canonical snapshot, wraps it in the portable
``live-schema-snapshot.json`` artifact, and writes that file. Datrix-side
``drift``/``reconcile`` commands import the artifact offline and never connect to
a database.

It emits NO hostnames, credentials, connection strings, ports, or environment
names into the artifact: the connection string is read from the environment,
used to open the connection, and never persisted or logged.
"""

from __future__ import annotations

import logging
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Mapping

from datrix_codegen_sql.dialects.reflector_registry import get_reflector
from datrix_common.migration.live_snapshot_export import (
    build_live_snapshot_artifact,
    serialize_live_snapshot_artifact,
)

logger = logging.getLogger(__name__)

# Identity stamped onto the reflected snapshot. A live catalog does not know which
# Datrix block it belongs to; these source-side values (NOT secrets) are baked in
# at generation time and carried on the rdbms_block handed to the reflector.
ENGINE = "postgres"
RDBMS_ID = "be71df4e-831f-4cfb-be66-0dc89a523a60"
SERVICE_NAME = "library.BookService"
SERVICE_VERSION = "1.0.0"
CONTAINER_NAME = "library.BookService"
CONTAINER_KIND = "service"
BLOCK_NAME = "bookDb"
LATEST_REVISION = None

# Environment variable holding the connection DSN. Read at runtime, used only to
# open the connection, never written to the artifact or logged.
DSN_ENV_VAR = "DATRIX_LIVE_DB_DSN"

# Output artifact filename (written to the current working directory).
OUTPUT_FILENAME = "live-schema-snapshot.json"


class _ReflectionIdentity:
    """Source-side identity the reflector stamps onto the live snapshot."""

    def __init__(self) -> None:
        self.rdbms_id = RDBMS_ID
        self.service_name = SERVICE_NAME
        self.service_version = SERVICE_VERSION
        self.container_name = CONTAINER_NAME
        self.container_kind = CONTAINER_KIND
        self.block_name = BLOCK_NAME
        self.latest_revision = LATEST_REVISION


class _RowFetcher:
    """Synchronous read-only ``RowFetcher`` over an asyncpg connection.

    Postgres reflector SQL uses positional ``$1``/``$2`` placeholders, which
    asyncpg consumes directly.
    """

    def __init__(self, conn: object) -> None:
        self._conn = conn

    def fetch_all(
        self, sql: str, params: tuple[object, ...]
    ) -> list[Mapping[str, object]]:
        import asyncio

        async def _run() -> list[Mapping[str, object]]:
            rows = await self._conn.fetch(sql, *params)  # type: ignore[attr-defined]
            return [dict(r) for r in rows]

        return asyncio.get_event_loop().run_until_complete(_run())


def _reflect(dsn: str) -> object:
    """Open a read-only asyncpg connection, reflect, and close it."""
    import asyncio

    import asyncpg

    async def _run() -> object:
        conn = await asyncpg.connect(dsn)
        try:
            # Read-only transaction: the reflector issues SELECTs only.
            async with conn.transaction(readonly=True):
                reflector = get_reflector(ENGINE)
                return reflector.reflect_snapshot(
                    _ReflectionIdentity(), _RowFetcher(conn)
                )
        finally:
            await conn.close()

    return asyncio.get_event_loop().run_until_complete(_run())


def _now_iso() -> str:
    """Current UTC export timestamp (ISO-8601)."""
    return datetime.now(timezone.utc).isoformat()


def main() -> int:
    """Reflect the live postgres catalog and write the snapshot artifact.

    Returns 0 on success, 1 on failure. The DSN is read from the environment and
    never logged or written to the artifact.
    """
    logging.basicConfig(level=logging.INFO)
    dsn = os.environ.get(DSN_ENV_VAR)
    if not dsn:
        logger.error(
            "missing_dsn env_var=%s hint=Set %s to the read-only connection DSN",
            DSN_ENV_VAR,
            DSN_ENV_VAR,
        )
        return 1

    logger.info("reflecting_live_schema engine=%s rdbms_id=%s", ENGINE, RDBMS_ID)
    snapshot = _reflect(dsn)
    artifact = build_live_snapshot_artifact(
        snapshot=snapshot,  # type: ignore[arg-type]
        engine=ENGINE,
        exported_at=_now_iso(),
    )
    output_path = Path(OUTPUT_FILENAME)
    output_path.write_text(serialize_live_snapshot_artifact(artifact), encoding="utf-8")
    logger.info("wrote_artifact path=%s rdbms_id=%s", output_path, RDBMS_ID)
    return 0


if __name__ == "__main__":
    sys.exit(main())
