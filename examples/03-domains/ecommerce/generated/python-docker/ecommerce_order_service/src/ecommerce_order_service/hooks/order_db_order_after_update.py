from __future__ import annotations

from typing import TYPE_CHECKING

from pydantic import JsonValue
from sqlalchemy.ext.asyncio import AsyncSession

from ecommerce_order_service.enums.order_status import OrderStatus
from ecommerce_order_service.mq import producer as _mq_producer
from ecommerce_order_service.services._base import _field_changed, _field_old_value

if TYPE_CHECKING:
    from ecommerce_order_service.models.order_db.order import Order


async def _order_db_order_after_update(
    target: Order,
    db: AsyncSession,
    old_values: dict[str, object] | None = None,
    _commit: bool = True,
) -> None:
    """Execute afterUpdate lifecycle hook for Order."""
    if _field_changed(target, "status", old_values):
        _producer_instance = await _mq_producer.get_producer()
        await _producer_instance.publish_order_status_changed(
            target.id, _field_old_value(target, "status", old_values), target.status
        )
        if target.status == OrderStatus.confirmed:
            order_items: list[JsonValue] = [
                {"productId": i.product_id, "quantity": i.quantity}
                for i in target.items
            ]
            estimated_weight: float = len(target.items) * 1.0
            _producer_instance = await _mq_producer.get_producer()
            await _producer_instance.publish_order_confirmed(
                target.id,
                target.payment_id,
                target.inventory_reservation_id,
                target.shipping_address,
                order_items,
                estimated_weight,
            )
        elif target.status == OrderStatus.cancelled:
            _producer_instance = await _mq_producer.get_producer()
            await _producer_instance.publish_order_cancelled(
                target.id,
                (
                    target.cancellation_reason
                    if target.cancellation_reason is not None
                    else "Cancelled"
                ),
                target.inventory_reservation_id,
            )
