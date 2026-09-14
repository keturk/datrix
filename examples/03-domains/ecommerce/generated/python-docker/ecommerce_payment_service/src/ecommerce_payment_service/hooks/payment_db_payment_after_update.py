from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy.ext.asyncio import AsyncSession

from ecommerce_payment_service.enums.payment_status import PaymentStatus
from ecommerce_payment_service.mq import producer as _mq_producer
from ecommerce_payment_service.services._base import _field_changed

if TYPE_CHECKING:
    from ecommerce_payment_service.models.payment_db.payment import Payment


async def _payment_db_payment_after_update(
    target: Payment,
    db: AsyncSession,
    old_values: dict[str, object] | None = None,
    _commit: bool = True,
) -> None:
    """Execute afterUpdate lifecycle hook for Payment."""
    if _field_changed(target, "status", old_values):
        if target.status == PaymentStatus.completed:
            _producer_instance = await _mq_producer.get_producer()
            await _producer_instance.publish_payment_processed(
                target.id, target.order_id, target.amount
            )
        elif target.status == PaymentStatus.failed:
            _producer_instance = await _mq_producer.get_producer()
            await _producer_instance.publish_payment_failed(
                target.id,
                target.order_id,
                (
                    target.error_message
                    if target.error_message is not None
                    else "Payment failed"
                ),
            )
        elif target.status == PaymentStatus.refunded:
            _producer_instance = await _mq_producer.get_producer()
            await _producer_instance.publish_payment_refunded(
                target.id, target.order_id, target.amount
            )
