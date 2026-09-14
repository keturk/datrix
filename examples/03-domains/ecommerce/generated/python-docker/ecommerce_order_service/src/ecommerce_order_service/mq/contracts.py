"""Event contract validation functions.

Auto-generated from ``ensure`` clauses in event declarations.
Each function validates preconditions before event publication.
"""

from __future__ import annotations

import decimal
import logging
import uuid

from prometheus_client import Counter
from pydantic import JsonValue

from ecommerce_order_service.enums.order_status import OrderStatus
from ecommerce_order_service.errors import ContractViolationError
from ecommerce_order_service.schemas.address import Address

logger = logging.getLogger(__name__)

CONTRACT_VIOLATION_COUNTER = Counter(
    "mq_contract_violations_total",
    "Number of event contract violations",
    ["event", "clause"],
)


def _validate_order_created_contract(
    order_id: uuid.UUID,
    order_number: str,
    customer_id: uuid.UUID,
    total: decimal.Decimal,
    reservation_id: uuid.UUID,
) -> None:
    """Validate contracts for OrderCreated event."""
    if not (len(order_number) > 0):
        logger.error(
            "contract_violation event=%r clause=%r orderNumber=%s",
            "OrderCreated",
            "orderNumber.length > 0",
            order_number,
        )
        CONTRACT_VIOLATION_COUNTER.labels(
            event="OrderCreated",
            clause="orderNumber.length > 0",
        ).inc()
        raise ContractViolationError(
            event="OrderCreated",
            clause="orderNumber.length > 0",
            actual={
                "orderNumber": order_number,
            },
        )
    if not (total > 0):
        logger.error(
            "contract_violation event=%r clause=%r total=%s",
            "OrderCreated",
            "total > 0",
            total,
        )
        CONTRACT_VIOLATION_COUNTER.labels(
            event="OrderCreated",
            clause="total > 0",
        ).inc()
        raise ContractViolationError(
            event="OrderCreated",
            clause="total > 0",
            actual={
                "total": total,
            },
        )


def _validate_order_confirmed_contract(
    order_id: uuid.UUID,
    payment_id: uuid.UUID | None,
    reservation_id: uuid.UUID,
    shipping_address: Address,
    items: list[JsonValue],
    estimated_weight: decimal.Decimal,
) -> None:
    """Validate contracts for OrderConfirmed event."""
    if not (len(items) > 0):
        logger.error(
            "contract_violation event=%r clause=%r items=%s",
            "OrderConfirmed",
            "items.length() > 0",
            items,
        )
        CONTRACT_VIOLATION_COUNTER.labels(
            event="OrderConfirmed",
            clause="items.length() > 0",
        ).inc()
        raise ContractViolationError(
            event="OrderConfirmed",
            clause="items.length() > 0",
            actual={
                "items": items,
            },
        )
    if not (estimated_weight > 0):
        logger.error(
            "contract_violation event=%r clause=%r estimatedWeight=%s",
            "OrderConfirmed",
            "estimatedWeight > 0",
            estimated_weight,
        )
        CONTRACT_VIOLATION_COUNTER.labels(
            event="OrderConfirmed",
            clause="estimatedWeight > 0",
        ).inc()
        raise ContractViolationError(
            event="OrderConfirmed",
            clause="estimatedWeight > 0",
            actual={
                "estimatedWeight": estimated_weight,
            },
        )


def _validate_order_cancelled_contract(
    order_id: uuid.UUID,
    reason: str,
    reservation_id: uuid.UUID,
) -> None:
    """Validate contracts for OrderCancelled event."""
    if not (len(reason) > 0):
        logger.error(
            "contract_violation event=%r clause=%r reason=%s",
            "OrderCancelled",
            "reason.length > 0",
            reason,
        )
        CONTRACT_VIOLATION_COUNTER.labels(
            event="OrderCancelled",
            clause="reason.length > 0",
        ).inc()
        raise ContractViolationError(
            event="OrderCancelled",
            clause="reason.length > 0",
            actual={
                "reason": reason,
            },
        )


def _validate_order_status_changed_contract(
    order_id: uuid.UUID,
    old_status: OrderStatus,
    new_status: OrderStatus,
) -> None:
    """Validate contracts for OrderStatusChanged event."""
    if not (old_status != new_status):
        logger.error(
            "contract_violation event=%r clause=%r newStatus=%s oldStatus=%s",
            "OrderStatusChanged",
            "oldStatus != newStatus",
            new_status,
            old_status,
        )
        CONTRACT_VIOLATION_COUNTER.labels(
            event="OrderStatusChanged",
            clause="oldStatus != newStatus",
        ).inc()
        raise ContractViolationError(
            event="OrderStatusChanged",
            clause="oldStatus != newStatus",
            actual={
                "newStatus": new_status,
                "oldStatus": old_status,
            },
        )
