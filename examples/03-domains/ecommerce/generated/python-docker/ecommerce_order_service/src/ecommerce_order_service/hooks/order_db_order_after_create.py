from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy.ext.asyncio import AsyncSession

from ecommerce_order_service._json_helpers import _json_index
from ecommerce_order_service.clients.user_service_client import get_user_service_client
from ecommerce_order_service.clients.user_service_responses import (
    UserServiceUserResponse,
    decode_user_service_user_response,
)
from ecommerce_order_service.mq import producer as _mq_producer
from ecommerce_order_service.queue import client as _datrix_queue_client

if TYPE_CHECKING:
    from ecommerce_order_service.models.order_db.order import Order


async def _order_db_order_after_create(
    target: Order,
    db: AsyncSession,
    _commit: bool = True,
) -> None:
    """Execute afterCreate lifecycle hook for Order."""
    _producer_instance = await _mq_producer.get_producer()
    await _producer_instance.publish_order_created(
        target.id,
        target.order_number,
        target.customer_id,
        target.total,
        target.inventory_reservation_id,
    )
    _queue_client_instance = await _datrix_queue_client.get_queue_client()
    await _queue_client_instance.dispatch_process_payment(
        target.id, target.total, "usd"
    )
    u: UserServiceUserResponse = decode_user_service_user_response(
        await get_user_service_client().get_json(
            f"/api/v1/service/{target.customer_id}", idempotent=True
        )
    )
    _queue_client_instance = await _datrix_queue_client.get_queue_client()
    await _queue_client_instance.dispatch_send_order_confirmation(
        target.id, _json_index(u, "email"), target.order_number
    )
