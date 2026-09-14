"""Durable AMQP consumer that runs generated job wrappers for ``Queue.enqueue``.

The AMQP connection is opened through the shared credential-aware queue helper,
which composes the URL from non-secret settings plus the password resolved by
handle and rebuilds on rotation. No environment variables are read at any point.
"""

from __future__ import annotations

import asyncio
import json
import logging

import ecommerce_order_service.config._secrets_resolver as _secrets_resolver
from ecommerce_order_service._queue_helpers import _get_connection
from ecommerce_order_service.config.remote_config import (
    build_client as _build_config_client,
)
from ecommerce_order_service.config.settings import assemble_settings, get_settings
from ecommerce_order_service.jobs.runner import (
    _wrapped_cleanup_expired_idempotency_keys,
)

logger = logging.getLogger(__name__)

_JOB_HANDLERS: dict[str, object] = {
    "CleanupExpiredIdempotencyKeys": _wrapped_cleanup_expired_idempotency_keys,
}

_DEFAULT_JOB_QUEUE_NAME = "datrix.jobs.ecommerce_order_service"


async def run_job_queue_consumer() -> None:
    """Consume ``{"job": "<Name>", "payload": ...}`` messages and execute the wrapper.

    The connection is opened through the shared credential-aware queue helper
    (rotation-aware). Requires :class:`AppSettings` to have been assembled.
    """
    queue_name = _DEFAULT_JOB_QUEUE_NAME
    connection = await _get_connection()
    channel = await connection.channel()
    queue = await channel.declare_queue(queue_name, durable=True)
    logger.info("job_queue_consumer_started queue=%s", queue_name)
    async with queue.iterator() as queue_iter:
        async for message in queue_iter:
            try:
                body = json.loads(message.body.decode("utf-8"))
                job = body.get("job")
                if not isinstance(job, str) or job not in _JOB_HANDLERS:
                    available = sorted(_JOB_HANDLERS.keys())
                    logger.error(
                        "unknown_job name=%s available=%s",
                        job,
                        available,
                    )
                    await message.nack(requeue=False)
                    continue
                handler = _JOB_HANDLERS[job]
                await handler()
                await message.ack()
            except json.JSONDecodeError:
                logger.exception("job_queue_invalid_json")
                await message.nack(requeue=False)
            except Exception:
                logger.exception("job_queue_message_failed")
                await message.nack(requeue=False)


async def _main_async() -> None:
    """Assemble settings (so the shared queue helper can read them) then consume."""
    try:
        get_settings()
    except RuntimeError:
        config_client = _build_config_client()
        config_client.start()
        await assemble_settings(config_client, _secrets_resolver)
    await run_job_queue_consumer()


def main() -> None:
    asyncio.run(_main_async())


if __name__ == "__main__":
    main()
