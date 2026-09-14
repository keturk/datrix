"""Queue helper functions for generated Python code.

Uses aio-pika for async AMQP operations (RabbitMQ).

This module is the SINGLE shared credential-aware RabbitMQ connection helper for
the service. It holds the non-secret connection components (host/port/user/vhost)
from :class:`AppSettings` and the logical password handle, resolves the password
through the secrets resolver before opening or reusing a connection, reconnects
when the resolved value changes after TTL expiry (REBUILD_ON_REFRESH), and on a
DEFINITIVE AMQP auth failure (``ACCESS_REFUSED``) invalidates the handle,
reconnects, and retries the operation exactly once. No environment variables are
read at any point. The credential value is never logged.
"""

from __future__ import annotations

import json
import logging
from typing import Awaitable, Callable, Optional, TypeVar
from urllib.parse import quote

import aio_pika
from aio_pika.exceptions import AMQPException, ProbableAuthenticationError

from ecommerce_order_service.config._secrets_resolver import (
    get_secret,
    invalidate_secret,
)
from ecommerce_order_service.config.settings import get_settings

logger = logging.getLogger(__name__)

_DEFAULT_JOB_QUEUE_NAME = "datrix.jobs.ecommerce_order_service"

_JsonValue = dict[str, object] | list[object] | str | int | float | bool | None

_T = TypeVar("_T")

_connection: Optional[aio_pika.abc.AbstractRobustConnection] = None
# Last resolved password, kept ONLY to detect a rotation so the connection can be
# rebuilt. Never logged, never exposed through AppSettings.
_last_password: Optional[str] = None


def _compose_amqp_url(password: str) -> str:
    """Compose the AMQP URL from settings components and a resolved password.

    Credential parts are percent-encoded. The password is interpolated at call
    time and never persisted into a frozen setting.
    """
    settings = get_settings()
    user = quote(str(settings.QUEUE_USER), safe="")
    host = str(settings.QUEUE_HOST)
    port = int(settings.QUEUE_PORT)
    vhost = quote(str(settings.QUEUE_VHOST), safe="")
    return f"amqp://{user}:{quote(password, safe='')}@{host}:{port}/{vhost}"


def _is_definitive_amqp_auth_error(exc: BaseException) -> bool:
    """Return True only for a DEFINITIVE AMQP authentication failure.

    ``ACCESS_REFUSED`` (surfaced by aio-pika as ``ProbableAuthenticationError``)
    is a credential failure. Timeouts and connection-refused are transient and
    return False so the credential is NOT invalidated.
    """
    return isinstance(exc, ProbableAuthenticationError)


async def _open_connection() -> aio_pika.abc.AbstractRobustConnection:
    """Resolve the password handle and open a fresh robust AMQP connection."""
    global _last_password
    handle = str(get_settings().QUEUE_PASSWORD_HANDLE)
    password = await get_secret(handle)
    _last_password = password
    return await aio_pika.connect_robust(_compose_amqp_url(password))


async def _get_connection() -> aio_pika.abc.AbstractRobustConnection:
    """Get or create the AMQP connection, observing a rotated credential.

    Re-resolves the password handle through the secrets resolver (cached until
    TTL expiry). If the connection is closed, or the resolved password changed
    since the live connection was opened, a fresh connection is built so a
    rotated credential propagates after TTL expiry.
    """
    global _connection
    handle = str(get_settings().QUEUE_PASSWORD_HANDLE)
    resolved = await get_secret(handle)
    if _connection is None or _connection.is_closed or resolved != _last_password:
        if _connection is not None and not _connection.is_closed:
            await _connection.close()
        _connection = await _open_connection()
    return _connection


async def _run_with_amqp_auth_retry(
    operation: Callable[[], Awaitable[_T]],
) -> _T:
    """Run an AMQP operation with one invalidate+reconnect+retry on auth failure.

    On a DEFINITIVE auth failure (``ACCESS_REFUSED``) the password handle is
    invalidated (throttled, no loop), the connection is rebuilt, and the
    operation is retried exactly once. A second failure propagates. Transient
    errors are not retried here and never invalidate the credential.
    """
    global _connection
    try:
        return await operation()
    except AMQPException as exc:
        if not _is_definitive_amqp_auth_error(exc):
            raise
        logger.warning(
            "rabbitmq_auth_failed_retrying handle=%s",
            str(get_settings().QUEUE_PASSWORD_HANDLE),
        )
        invalidate_secret(
            str(get_settings().QUEUE_PASSWORD_HANDLE), "rabbitmq_auth_failed"
        )
        if _connection is not None and not _connection.is_closed:
            await _connection.close()
        _connection = await _open_connection()
        return await operation()


async def _queue_publish(queue_name: str, message: _JsonValue) -> None:
    """Publish message to queue (with one auth-failure invalidate+retry)."""

    async def _op() -> None:
        conn = await _get_connection()
        async with conn.channel() as channel:
            await channel.default_exchange.publish(
                aio_pika.Message(body=json.dumps(message).encode()),
                routing_key=queue_name,
            )

    await _run_with_amqp_auth_retry(_op)


async def _queue_subscribe(queue_name: str, handler: Callable[..., object]) -> None:
    """Subscribe to queue with handler function."""
    conn = await _get_connection()
    channel = await conn.channel()
    queue = await channel.declare_queue(queue_name, durable=True)
    async with queue.iterator() as queue_iter:
        async for message in queue_iter:
            payload = json.loads(message.body.decode())
            result = handler(payload)
            if hasattr(result, "__await__"):
                await result


async def _queue_ack(message: aio_pika.abc.AbstractIncomingMessage) -> None:
    """Acknowledge message."""
    await message.ack()


async def _queue_nack(
    message: aio_pika.abc.AbstractIncomingMessage,
    requeue: bool = True,
) -> None:
    """Negative acknowledge message."""
    await message.nack(requeue=requeue)


async def _queue_purge(queue_name: str) -> int:
    """Purge all messages from queue."""
    conn = await _get_connection()
    async with conn.channel() as channel:
        queue = await channel.declare_queue(queue_name, durable=True)
        return await queue.purge()


async def _queue_length(queue_name: str) -> int:
    """Get queue length."""
    conn = await _get_connection()
    async with conn.channel() as channel:
        queue = await channel.declare_queue(queue_name, durable=True, passive=True)
        return queue.declaration_result.message_count


async def _queue_delay(
    queue_name: str, message: _JsonValue, delay_seconds: int
) -> None:
    """Publish message with delay using TTL + dead-letter exchange."""
    conn = await _get_connection()
    async with conn.channel() as channel:
        await channel.default_exchange.publish(
            aio_pika.Message(
                body=json.dumps(message).encode(),
                expiration=delay_seconds * 1000,
            ),
            routing_key=queue_name,
        )


async def _queue_enqueue_job(job_type: str, job_payload: _JsonValue) -> None:
    """Publish a background job request to this service's durable AMQP job queue.

    Message body: ``{"job": "<JobName>", "payload": <object>}``.

    Queue name defaults to ``datrix.jobs.<package>`` so API and queue-worker
    processes agree without extra configuration.
    """
    queue_name = _DEFAULT_JOB_QUEUE_NAME
    body: dict[str, object] = {"job": job_type, "payload": job_payload}

    async def _op() -> None:
        conn = await _get_connection()
        async with conn.channel() as channel:
            await channel.declare_queue(queue_name, durable=True)
            await channel.default_exchange.publish(
                aio_pika.Message(body=json.dumps(body).encode("utf-8")),
                routing_key=queue_name,
            )

    await _run_with_amqp_auth_retry(_op)
    logger.info("job_enqueued name=%s queue=%s", job_type, queue_name)
