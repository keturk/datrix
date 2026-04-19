"""Queue helper functions for generated Python code.

Uses aio-pika for async AMQP operations (RabbitMQ).
"""

from __future__ import annotations

import json
import os
from typing import Any, Callable, Optional

import aio_pika

_connection: Optional[aio_pika.abc.AbstractRobustConnection] = None


async def _get_connection() -> aio_pika.abc.AbstractRobustConnection:
    """Get or create the AMQP connection."""
    global _connection
    if _connection is None or _connection.is_closed:
        url = os.environ["AMQP_URL"]
        _connection = await aio_pika.connect_robust(url)
    return _connection


async def _queue_publish(queue_name: str, message: Any) -> None:
    """Publish message to queue."""
    conn = await _get_connection()
    async with conn.channel() as channel:
        await channel.default_exchange.publish(
            aio_pika.Message(body=json.dumps(message).encode()),
            routing_key=queue_name,
        )


async def _queue_subscribe(queue_name: str, handler: Callable[..., Any]) -> None:
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


async def _queue_delay(queue_name: str, message: Any, delay_seconds: int) -> None:
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
