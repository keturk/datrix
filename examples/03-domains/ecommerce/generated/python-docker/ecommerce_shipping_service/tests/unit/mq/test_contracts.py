"""Tests for event contract validation.

Auto-generated. Verifies that contract violations are detected.
"""

from __future__ import annotations

import uuid

import pytest

from ecommerce_shipping_service.errors import ContractViolationError
from ecommerce_shipping_service.mq.contracts import (
    _validate_shipment_dispatched_contract,
    _validate_shipment_failed_contract,
)


class TestShipmentDispatchedContracts:
    """Contract tests for ShipmentDispatched."""

    def test_valid_payload_passes(self) -> None:
        """Valid payload passes all contract checks."""
        _validate_shipment_dispatched_contract(
            shipment_id=uuid.UUID("550e8400-e29b-41d4-a716-446655440000"),
            order_id=uuid.UUID("550e8400-e29b-41d4-a716-446655440000"),
            tracking_number="x",
        )

    def test_violating_clause_0(self) -> None:
        """Violating 'trackingNumber.length > 0' raises ContractViolationError."""
        with pytest.raises(ContractViolationError) as exc_info:
            _validate_shipment_dispatched_contract(
                shipment_id=uuid.UUID("550e8400-e29b-41d4-a716-446655440000"),
                order_id=uuid.UUID("550e8400-e29b-41d4-a716-446655440000"),
                tracking_number="",
            )
        assert exc_info.value.event == "ShipmentDispatched"
        assert exc_info.value.clause == "trackingNumber.length > 0"


class TestShipmentFailedContracts:
    """Contract tests for ShipmentFailed."""

    def test_valid_payload_passes(self) -> None:
        """Valid payload passes all contract checks."""
        _validate_shipment_failed_contract(
            shipment_id=uuid.UUID("550e8400-e29b-41d4-a716-446655440000"),
            order_id=uuid.UUID("550e8400-e29b-41d4-a716-446655440000"),
            reason="x",
        )

    def test_violating_clause_0(self) -> None:
        """Violating 'reason.length > 0' raises ContractViolationError."""
        with pytest.raises(ContractViolationError) as exc_info:
            _validate_shipment_failed_contract(
                shipment_id=uuid.UUID("550e8400-e29b-41d4-a716-446655440000"),
                order_id=uuid.UUID("550e8400-e29b-41d4-a716-446655440000"),
                reason="",
            )
        assert exc_info.value.event == "ShipmentFailed"
        assert exc_info.value.clause == "reason.length > 0"
