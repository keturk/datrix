"""Event contract validation functions.

Auto-generated from ``ensure`` clauses in event declarations.
Each function validates preconditions before event publication.
"""

from __future__ import annotations

import decimal
import logging
import uuid

from prometheus_client import Counter

from ecommerce_product_service.errors import ContractViolationError

logger = logging.getLogger(__name__)

CONTRACT_VIOLATION_COUNTER = Counter(
    "mq_contract_violations_total",
    "Number of event contract violations",
    ["event", "clause"],
)


def _validate_product_created_contract(
    product_id: uuid.UUID,
    name: str,
    price: decimal.Decimal,
) -> None:
    """Validate contracts for ProductCreated event."""
    if not (len(name) > 0):
        logger.error(
            "contract_violation event=%r clause=%r name=%s",
            "ProductCreated",
            "name.length > 0",
            name,
        )
        CONTRACT_VIOLATION_COUNTER.labels(
            event="ProductCreated",
            clause="name.length > 0",
        ).inc()
        raise ContractViolationError(
            event="ProductCreated",
            clause="name.length > 0",
            actual={
                "name": name,
            },
        )
    if not (price > 0):
        logger.error(
            "contract_violation event=%r clause=%r price=%s",
            "ProductCreated",
            "price > 0",
            price,
        )
        CONTRACT_VIOLATION_COUNTER.labels(
            event="ProductCreated",
            clause="price > 0",
        ).inc()
        raise ContractViolationError(
            event="ProductCreated",
            clause="price > 0",
            actual={
                "price": price,
            },
        )


def _validate_inventory_updated_contract(
    product_id: uuid.UUID,
    old_quantity: int,
    new_quantity: int,
) -> None:
    """Validate contracts for InventoryUpdated event."""
    if not (new_quantity >= 0):
        logger.error(
            "contract_violation event=%r clause=%r newQuantity=%s",
            "InventoryUpdated",
            "newQuantity >= 0",
            new_quantity,
        )
        CONTRACT_VIOLATION_COUNTER.labels(
            event="InventoryUpdated",
            clause="newQuantity >= 0",
        ).inc()
        raise ContractViolationError(
            event="InventoryUpdated",
            clause="newQuantity >= 0",
            actual={
                "newQuantity": new_quantity,
            },
        )


def _validate_inventory_reserved_contract(
    reservation_id: uuid.UUID,
    product_ids: list[uuid.UUID],
) -> None:
    """Validate contracts for InventoryReserved event."""
    if not (len(product_ids) > 0):
        logger.error(
            "contract_violation event=%r clause=%r productIds=%s",
            "InventoryReserved",
            "productIds.length() > 0",
            product_ids,
        )
        CONTRACT_VIOLATION_COUNTER.labels(
            event="InventoryReserved",
            clause="productIds.length() > 0",
        ).inc()
        raise ContractViolationError(
            event="InventoryReserved",
            clause="productIds.length() > 0",
            actual={
                "productIds": product_ids,
            },
        )


def _validate_inventory_released_contract(
    reservation_id: uuid.UUID,
    reason: str,
) -> None:
    """Validate contracts for InventoryReleased event."""
    if not (len(reason) > 0):
        logger.error(
            "contract_violation event=%r clause=%r reason=%s",
            "InventoryReleased",
            "reason.length > 0",
            reason,
        )
        CONTRACT_VIOLATION_COUNTER.labels(
            event="InventoryReleased",
            clause="reason.length > 0",
        ).inc()
        raise ContractViolationError(
            event="InventoryReleased",
            clause="reason.length > 0",
            actual={
                "reason": reason,
            },
        )
