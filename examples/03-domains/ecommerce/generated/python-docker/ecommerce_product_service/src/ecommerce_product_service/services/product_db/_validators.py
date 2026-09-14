"""Block-scoped DSL validation lowering (generated -- do not edit)."""

from __future__ import annotations

from ecommerce_product_service.models.product_db.inventory_reservation import (
    InventoryReservation,
)
from ecommerce_product_service.services._base import ValidationError


def validate_inventory_reservation(entity: InventoryReservation) -> None:
    """Validate InventoryReservation business rules (from DSL validate block)."""
    if entity.quantity <= 0:
        raise ValidationError(["Reservation quantity must be positive"])
