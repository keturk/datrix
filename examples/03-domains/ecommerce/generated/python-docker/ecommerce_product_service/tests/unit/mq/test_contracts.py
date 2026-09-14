"""Tests for event contract validation.

Auto-generated. Verifies that contract violations are detected.
"""

from __future__ import annotations

import decimal
import uuid

import pytest

from ecommerce_product_service.errors import ContractViolationError
from ecommerce_product_service.mq.contracts import (
    _validate_inventory_released_contract,
    _validate_inventory_reserved_contract,
    _validate_inventory_updated_contract,
    _validate_product_created_contract,
)


class TestProductCreatedContracts:
    """Contract tests for ProductCreated."""

    def test_valid_payload_passes(self) -> None:
        """Valid payload passes all contract checks."""
        _validate_product_created_contract(
            product_id=uuid.UUID("550e8400-e29b-41d4-a716-446655440000"),
            name="x",
            price=decimal.Decimal("19.99"),
        )

    def test_violating_clause_0(self) -> None:
        """Violating 'name.length > 0' raises ContractViolationError."""
        with pytest.raises(ContractViolationError) as exc_info:
            _validate_product_created_contract(
                product_id=uuid.UUID("550e8400-e29b-41d4-a716-446655440000"),
                name="",
                price=decimal.Decimal("19.99"),
            )
        assert exc_info.value.event == "ProductCreated"
        assert exc_info.value.clause == "name.length > 0"

    def test_violating_clause_1(self) -> None:
        """Violating 'price > 0' raises ContractViolationError."""
        with pytest.raises(ContractViolationError) as exc_info:
            _validate_product_created_contract(
                product_id=uuid.UUID("550e8400-e29b-41d4-a716-446655440000"),
                name="x",
                price=decimal.Decimal("-1"),
            )
        assert exc_info.value.event == "ProductCreated"
        assert exc_info.value.clause == "price > 0"


class TestInventoryUpdatedContracts:
    """Contract tests for InventoryUpdated."""

    def test_valid_payload_passes(self) -> None:
        """Valid payload passes all contract checks."""
        _validate_inventory_updated_contract(
            product_id=uuid.UUID("550e8400-e29b-41d4-a716-446655440000"),
            old_quantity=1,
            new_quantity=1,
        )

    def test_violating_clause_0(self) -> None:
        """Violating 'newQuantity >= 0' raises ContractViolationError."""
        with pytest.raises(ContractViolationError) as exc_info:
            _validate_inventory_updated_contract(
                product_id=uuid.UUID("550e8400-e29b-41d4-a716-446655440000"),
                old_quantity=1,
                new_quantity=-1,
            )
        assert exc_info.value.event == "InventoryUpdated"
        assert exc_info.value.clause == "newQuantity >= 0"


class TestInventoryReservedContracts:
    """Contract tests for InventoryReserved."""

    def test_valid_payload_passes(self) -> None:
        """Valid payload passes all contract checks."""
        _validate_inventory_reserved_contract(
            reservation_id=uuid.UUID("550e8400-e29b-41d4-a716-446655440000"),
            product_ids=[uuid.UUID(int=0)],
        )

    def test_violating_clause_0(self) -> None:
        """Violating 'productIds.length() > 0' raises ContractViolationError."""
        with pytest.raises(ContractViolationError) as exc_info:
            _validate_inventory_reserved_contract(
                reservation_id=uuid.UUID("550e8400-e29b-41d4-a716-446655440000"),
                product_ids=[],
            )
        assert exc_info.value.event == "InventoryReserved"
        assert exc_info.value.clause == "productIds.length() > 0"


class TestInventoryReleasedContracts:
    """Contract tests for InventoryReleased."""

    def test_valid_payload_passes(self) -> None:
        """Valid payload passes all contract checks."""
        _validate_inventory_released_contract(
            reservation_id=uuid.UUID("550e8400-e29b-41d4-a716-446655440000"),
            reason="x",
        )

    def test_violating_clause_0(self) -> None:
        """Violating 'reason.length > 0' raises ContractViolationError."""
        with pytest.raises(ContractViolationError) as exc_info:
            _validate_inventory_released_contract(
                reservation_id=uuid.UUID("550e8400-e29b-41d4-a716-446655440000"),
                reason="",
            )
        assert exc_info.value.event == "InventoryReleased"
        assert exc_info.value.clause == "reason.length > 0"
