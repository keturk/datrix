"""Tests for event contract validation.

Auto-generated. Verifies that contract violations are detected.
"""

from __future__ import annotations

import decimal
import uuid

import pytest

from ecommerce_payment_service.errors import ContractViolationError
from ecommerce_payment_service.mq.contracts import (
    _validate_payment_failed_contract,
    _validate_payment_processed_contract,
    _validate_payment_refunded_contract,
)


class TestPaymentProcessedContracts:
    """Contract tests for PaymentProcessed."""

    def test_valid_payload_passes(self) -> None:
        """Valid payload passes all contract checks."""
        _validate_payment_processed_contract(
            payment_id=uuid.UUID("550e8400-e29b-41d4-a716-446655440000"),
            order_id=uuid.UUID("550e8400-e29b-41d4-a716-446655440000"),
            amount=decimal.Decimal("19.99"),
        )

    def test_violating_clause_0(self) -> None:
        """Violating 'amount > 0' raises ContractViolationError."""
        with pytest.raises(ContractViolationError) as exc_info:
            _validate_payment_processed_contract(
                payment_id=uuid.UUID("550e8400-e29b-41d4-a716-446655440000"),
                order_id=uuid.UUID("550e8400-e29b-41d4-a716-446655440000"),
                amount=decimal.Decimal("-1"),
            )
        assert exc_info.value.event == "PaymentProcessed"
        assert exc_info.value.clause == "amount > 0"


class TestPaymentFailedContracts:
    """Contract tests for PaymentFailed."""

    def test_valid_payload_passes(self) -> None:
        """Valid payload passes all contract checks."""
        _validate_payment_failed_contract(
            payment_id=uuid.UUID("550e8400-e29b-41d4-a716-446655440000"),
            order_id=uuid.UUID("550e8400-e29b-41d4-a716-446655440000"),
            reason="x",
        )

    def test_violating_clause_0(self) -> None:
        """Violating 'reason.length > 0' raises ContractViolationError."""
        with pytest.raises(ContractViolationError) as exc_info:
            _validate_payment_failed_contract(
                payment_id=uuid.UUID("550e8400-e29b-41d4-a716-446655440000"),
                order_id=uuid.UUID("550e8400-e29b-41d4-a716-446655440000"),
                reason="",
            )
        assert exc_info.value.event == "PaymentFailed"
        assert exc_info.value.clause == "reason.length > 0"


class TestPaymentRefundedContracts:
    """Contract tests for PaymentRefunded."""

    def test_valid_payload_passes(self) -> None:
        """Valid payload passes all contract checks."""
        _validate_payment_refunded_contract(
            payment_id=uuid.UUID("550e8400-e29b-41d4-a716-446655440000"),
            order_id=uuid.UUID("550e8400-e29b-41d4-a716-446655440000"),
            amount=decimal.Decimal("19.99"),
        )

    def test_violating_clause_0(self) -> None:
        """Violating 'amount > 0' raises ContractViolationError."""
        with pytest.raises(ContractViolationError) as exc_info:
            _validate_payment_refunded_contract(
                payment_id=uuid.UUID("550e8400-e29b-41d4-a716-446655440000"),
                order_id=uuid.UUID("550e8400-e29b-41d4-a716-446655440000"),
                amount=decimal.Decimal("-1"),
            )
        assert exc_info.value.event == "PaymentRefunded"
        assert exc_info.value.clause == "amount > 0"
