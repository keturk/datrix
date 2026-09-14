from __future__ import annotations

import datetime
from typing import TYPE_CHECKING

from sqlalchemy.ext.asyncio import AsyncSession

from ecommerce_shipping_service.enums.shipment_status import ShipmentStatus
from ecommerce_shipping_service.mq import producer as _mq_producer
from ecommerce_shipping_service.schemas.shipping_db.shipment_event import (
    ShipmentEventCreate,
)
from ecommerce_shipping_service.services._base import _field_changed
from ecommerce_shipping_service.services.shipping_db.shipment_event_service import (
    ShipmentEventService,
)

if TYPE_CHECKING:
    from ecommerce_shipping_service.models.shipping_db.shipment import Shipment


async def _shipping_db_shipment_after_update(
    target: Shipment,
    db: AsyncSession,
    old_values: dict[str, object] | None = None,
    _commit: bool = True,
) -> None:
    """Execute afterUpdate lifecycle hook for Shipment."""
    if _field_changed(target, "status", old_values):
        _shipment_event_svc = ShipmentEventService(db)
        _entity = await _shipment_event_svc.create(
            ShipmentEventCreate(
                **{
                    "shipment_id": target.id,
                    "timestamp": datetime.datetime.now(datetime.timezone.utc),
                    "status": target.status,
                    "location": "System",
                    "description": f"Status updated to {target.status.value}",
                }
            ),
            _commit=_commit,
        )
        if target.status == ShipmentStatus.in_transit:
            _producer_instance = await _mq_producer.get_producer()
            await _producer_instance.publish_shipment_dispatched(
                target.id, target.order_id, target.tracking_number
            )
        elif target.status == ShipmentStatus.delivered:
            _producer_instance = await _mq_producer.get_producer()
            await _producer_instance.publish_shipment_delivered(
                target.id,
                target.order_id,
                (
                    target.actual_delivery
                    if target.actual_delivery is not None
                    else datetime.datetime.now(datetime.timezone.utc)
                ),
            )
        elif target.status == ShipmentStatus.failed:
            _producer_instance = await _mq_producer.get_producer()
            await _producer_instance.publish_shipment_failed(
                target.id,
                target.order_id,
                (
                    target.failure_reason
                    if target.failure_reason is not None
                    else "Delivery failed"
                ),
            )
