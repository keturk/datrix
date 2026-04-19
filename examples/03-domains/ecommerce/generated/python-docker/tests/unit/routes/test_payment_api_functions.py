"""Unit tests for PaymentAPI API functions."""

from __future__ import annotations

import inspect

import pytest

from ecommerce_payment_service.routes.payment_api import (
    process_refund_via_gateway,
)


@pytest.mark.unit
class TestPaymentAPIFunctions:
    """Tests for PaymentAPI API-level function declarations."""

    def test_process_refund_via_gateway_exists(self) -> None:
        """processRefundViaGateway function exists and is callable."""
        assert callable(process_refund_via_gateway)

    def test_process_refund_via_gateway_is_async(self) -> None:
        """processRefundViaGateway is an async function."""
        assert inspect.iscoroutinefunction(process_refund_via_gateway)

    def test_process_refund_via_gateway_parameter_count(self) -> None:
        """processRefundViaGateway accepts 2 parameter(s)."""
        sig = inspect.signature(process_refund_via_gateway)
        params = [p for p in sig.parameters.values() if p.name != "self"]
        # API functions may also receive injected dependencies (db, etc.)
        # so assert at least the declared parameter count.
        assert len(params) >= 2

    def test_process_refund_via_gateway_has_payment_param(self) -> None:
        """processRefundViaGateway accepts 'payment' parameter."""
        sig = inspect.signature(process_refund_via_gateway)
        param_names = list(sig.parameters.keys())
        assert "payment" in param_names

    def test_process_refund_via_gateway_has_refund_param(self) -> None:
        """processRefundViaGateway accepts 'refund' parameter."""
        sig = inspect.signature(process_refund_via_gateway)
        param_names = list(sig.parameters.keys())
        assert "refund" in param_names
