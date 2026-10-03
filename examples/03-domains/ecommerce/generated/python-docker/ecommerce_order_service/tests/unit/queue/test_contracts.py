"""Tests for event contract validation.

Auto-generated. Verifies that contract violations are detected.
"""

from __future__ import annotations

import decimal
import uuid

import pytest

from ecommerce_order_service.errors import ContractViolationError
from ecommerce_order_service.queue.contracts import (
    _validate_process_payment_contract,
    _validate_send_order_confirmation_contract,
    _validate_settle_payment_contract,
)


class TestProcessPaymentContracts:
    """Contract tests for ProcessPayment."""

    def test_valid_payload_passes(self) -> None:
        """Valid payload passes all contract checks."""
        _validate_process_payment_contract(
            order_id=uuid.UUID("550e8400-e29b-41d4-a716-446655440000"),
            amount=decimal.Decimal("19.99"),
            currency="xxx",
        )

    def test_violating_clause_0(self) -> None:
        """Violating 'amount > 0' raises ContractViolationError."""
        with pytest.raises(ContractViolationError) as exc_info:
            _validate_process_payment_contract(
                order_id=uuid.UUID("550e8400-e29b-41d4-a716-446655440000"),
                amount=decimal.Decimal("-1"),
                currency="xxx",
            )
        assert exc_info.value.event == "ProcessPayment"
        assert exc_info.value.clause == "amount > 0"

    def test_violating_clause_1(self) -> None:
        """Violating 'currency.length == 3' raises ContractViolationError."""
        with pytest.raises(ContractViolationError) as exc_info:
            _validate_process_payment_contract(
                order_id=uuid.UUID("550e8400-e29b-41d4-a716-446655440000"),
                amount=decimal.Decimal("19.99"),
                currency="",
            )
        assert exc_info.value.event == "ProcessPayment"
        assert exc_info.value.clause == "currency.length == 3"


class TestSendOrderConfirmationContracts:
    """Contract tests for SendOrderConfirmation."""

    def test_valid_payload_passes(self) -> None:
        """Valid payload passes all contract checks."""
        _validate_send_order_confirmation_contract(
            order_id=uuid.UUID("550e8400-e29b-41d4-a716-446655440000"),
            customer_email="x",
            order_number="test_value",
        )

    def test_violating_clause_0(self) -> None:
        """Violating 'customerEmail.length > 0' raises ContractViolationError."""
        with pytest.raises(ContractViolationError) as exc_info:
            _validate_send_order_confirmation_contract(
                order_id=uuid.UUID("550e8400-e29b-41d4-a716-446655440000"),
                customer_email="",
                order_number="test_value",
            )
        assert exc_info.value.event == "SendOrderConfirmation"
        assert exc_info.value.clause == "customerEmail.length > 0"


class TestSettlePaymentContracts:
    """Contract tests for SettlePayment."""

    def test_valid_payload_passes(self) -> None:
        """Valid payload passes all contract checks."""
        _validate_settle_payment_contract(
            payment_id=uuid.UUID("550e8400-e29b-41d4-a716-446655440000"),
            merchant_id="x",
            amount=decimal.Decimal("10.50"),
        )

    def test_violating_clause_0(self) -> None:
        """Violating 'amount > 0' raises ContractViolationError."""
        with pytest.raises(ContractViolationError) as exc_info:
            _validate_settle_payment_contract(
                payment_id=uuid.UUID("550e8400-e29b-41d4-a716-446655440000"),
                merchant_id="x",
                amount=decimal.Decimal("-1"),
            )
        assert exc_info.value.event == "SettlePayment"
        assert exc_info.value.clause == "amount > 0"

    def test_violating_clause_1(self) -> None:
        """Violating 'merchantId.length > 0' raises ContractViolationError."""
        with pytest.raises(ContractViolationError) as exc_info:
            _validate_settle_payment_contract(
                payment_id=uuid.UUID("550e8400-e29b-41d4-a716-446655440000"),
                merchant_id="",
                amount=decimal.Decimal("10.50"),
            )
        assert exc_info.value.event == "SettlePayment"
        assert exc_info.value.clause == "merchantId.length > 0"
