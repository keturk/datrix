"""Tests for event contract validation.

Auto-generated. Verifies that contract violations are detected.
"""

from __future__ import annotations

import decimal
import uuid

import pytest

from ecommerce_order_service.enums.order_status import OrderStatus
from ecommerce_order_service.errors import ContractViolationError
from ecommerce_order_service.mq.contracts import (
    _validate_order_cancelled_contract,
    _validate_order_confirmed_contract,
    _validate_order_created_contract,
    _validate_order_status_changed_contract,
)


class TestOrderCreatedContracts:
    """Contract tests for OrderCreated."""

    def test_valid_payload_passes(self) -> None:
        """Valid payload passes all contract checks."""
        _validate_order_created_contract(
            order_id=uuid.UUID("550e8400-e29b-41d4-a716-446655440000"),
            order_number="x",
            customer_id=uuid.UUID("550e8400-e29b-41d4-a716-446655440000"),
            total=decimal.Decimal("19.99"),
            reservation_id=uuid.UUID("550e8400-e29b-41d4-a716-446655440000"),
        )

    def test_violating_clause_0(self) -> None:
        """Violating 'orderNumber.length > 0' raises ContractViolationError."""
        with pytest.raises(ContractViolationError) as exc_info:
            _validate_order_created_contract(
                order_id=uuid.UUID("550e8400-e29b-41d4-a716-446655440000"),
                order_number="",
                customer_id=uuid.UUID("550e8400-e29b-41d4-a716-446655440000"),
                total=decimal.Decimal("19.99"),
                reservation_id=uuid.UUID("550e8400-e29b-41d4-a716-446655440000"),
            )
        assert exc_info.value.event == "OrderCreated"
        assert exc_info.value.clause == "orderNumber.length > 0"

    def test_violating_clause_1(self) -> None:
        """Violating 'total > 0' raises ContractViolationError."""
        with pytest.raises(ContractViolationError) as exc_info:
            _validate_order_created_contract(
                order_id=uuid.UUID("550e8400-e29b-41d4-a716-446655440000"),
                order_number="x",
                customer_id=uuid.UUID("550e8400-e29b-41d4-a716-446655440000"),
                total=decimal.Decimal("-1"),
                reservation_id=uuid.UUID("550e8400-e29b-41d4-a716-446655440000"),
            )
        assert exc_info.value.event == "OrderCreated"
        assert exc_info.value.clause == "total > 0"


class TestOrderConfirmedContracts:
    """Contract tests for OrderConfirmed."""

    def test_valid_payload_passes(self) -> None:
        """Valid payload passes all contract checks."""
        _validate_order_confirmed_contract(
            order_id=uuid.UUID("550e8400-e29b-41d4-a716-446655440000"),
            payment_id=uuid.UUID("550e8400-e29b-41d4-a716-446655440000"),
            reservation_id=uuid.UUID("550e8400-e29b-41d4-a716-446655440000"),
            shipping_address={
                "street": "test",
                "city": "test",
                "state": "test",
                "zip_code": "test",
                "country": "US",
                "phone": "15551234567",
            },
            items=["test"],
            estimated_weight=decimal.Decimal("10.50"),
        )

    def test_violating_clause_0(self) -> None:
        """Violating 'items.length() > 0' raises ContractViolationError."""
        with pytest.raises(ContractViolationError) as exc_info:
            _validate_order_confirmed_contract(
                order_id=uuid.UUID("550e8400-e29b-41d4-a716-446655440000"),
                payment_id=uuid.UUID("550e8400-e29b-41d4-a716-446655440000"),
                reservation_id=uuid.UUID("550e8400-e29b-41d4-a716-446655440000"),
                shipping_address={
                    "street": "test",
                    "city": "test",
                    "state": "test",
                    "zip_code": "test",
                    "country": "US",
                    "phone": "15551234567",
                },
                items=[],
                estimated_weight=decimal.Decimal("10.50"),
            )
        assert exc_info.value.event == "OrderConfirmed"
        assert exc_info.value.clause == "items.length() > 0"

    def test_violating_clause_1(self) -> None:
        """Violating 'estimatedWeight > 0' raises ContractViolationError."""
        with pytest.raises(ContractViolationError) as exc_info:
            _validate_order_confirmed_contract(
                order_id=uuid.UUID("550e8400-e29b-41d4-a716-446655440000"),
                payment_id=uuid.UUID("550e8400-e29b-41d4-a716-446655440000"),
                reservation_id=uuid.UUID("550e8400-e29b-41d4-a716-446655440000"),
                shipping_address={
                    "street": "test",
                    "city": "test",
                    "state": "test",
                    "zip_code": "test",
                    "country": "US",
                    "phone": "15551234567",
                },
                items=["test"],
                estimated_weight=decimal.Decimal("-1"),
            )
        assert exc_info.value.event == "OrderConfirmed"
        assert exc_info.value.clause == "estimatedWeight > 0"


class TestOrderCancelledContracts:
    """Contract tests for OrderCancelled."""

    def test_valid_payload_passes(self) -> None:
        """Valid payload passes all contract checks."""
        _validate_order_cancelled_contract(
            order_id=uuid.UUID("550e8400-e29b-41d4-a716-446655440000"),
            reason="x",
            reservation_id=uuid.UUID("550e8400-e29b-41d4-a716-446655440000"),
        )

    def test_violating_clause_0(self) -> None:
        """Violating 'reason.length > 0' raises ContractViolationError."""
        with pytest.raises(ContractViolationError) as exc_info:
            _validate_order_cancelled_contract(
                order_id=uuid.UUID("550e8400-e29b-41d4-a716-446655440000"),
                reason="",
                reservation_id=uuid.UUID("550e8400-e29b-41d4-a716-446655440000"),
            )
        assert exc_info.value.event == "OrderCancelled"
        assert exc_info.value.clause == "reason.length > 0"


class TestOrderStatusChangedContracts:
    """Contract tests for OrderStatusChanged."""

    def test_valid_payload_passes(self) -> None:
        """Valid payload passes all contract checks."""
        _validate_order_status_changed_contract(
            order_id=uuid.UUID("550e8400-e29b-41d4-a716-446655440000"),
            old_status=OrderStatus.pending,
            new_status=OrderStatus.payment_pending,
        )

    def test_violating_clause_0(self) -> None:
        """Violating 'oldStatus != newStatus' raises ContractViolationError."""
        with pytest.raises(ContractViolationError) as exc_info:
            _validate_order_status_changed_contract(
                order_id=uuid.UUID("550e8400-e29b-41d4-a716-446655440000"),
                old_status=OrderStatus.pending,
                new_status=OrderStatus.pending,
            )
        assert exc_info.value.event == "OrderStatusChanged"
        assert exc_info.value.clause == "oldStatus != newStatus"
