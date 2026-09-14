"""Block-scoped DSL validation lowering (generated -- do not edit)."""

from __future__ import annotations

from sqlalchemy.orm.attributes import instance_state

from ecommerce_order_service.models.order_db.idempotency_key import IdempotencyKey
from ecommerce_order_service.models.order_db.order import Order
from ecommerce_order_service.models.order_db.order_item import OrderItem
from ecommerce_order_service.services._base import ValidationError


def validate_order(entity: Order) -> None:
    """Validate Order business rules (from DSL validate block)."""
    _rel_state = instance_state(entity).dict
    if "items" in _rel_state:
        if entity.items is not None and len(entity.items) == 0:
            raise ValidationError(["Order must have at least one item"])
    if "items" in _rel_state:
        if entity.items is not None and len(entity.items) > 50:
            raise ValidationError(["Order cannot have more than 50 items"])


def validate_order_item(entity: OrderItem) -> None:
    """Validate OrderItem business rules (from DSL validate block)."""
    if entity.quantity <= 0:
        raise ValidationError(["Quantity must be greater than 0"])
    if entity.quantity > 100:
        raise ValidationError(["Quantity cannot exceed 100 per item"])
    if entity.unit_price < 0:
        raise ValidationError(["Unit price cannot be negative"])


def validate_idempotency_key(entity: IdempotencyKey) -> None:
    """Validate IdempotencyKey business rules (from DSL validate block)."""
    if len(entity.key.strip()) == 0:
        raise ValidationError(["Idempotency key cannot be empty"])
