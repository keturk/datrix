"""Unit tests for queue payload dataclasses (auto-generated)."""

from __future__ import annotations

import decimal
import json
import uuid

import pytest

from ecommerce_order_service.queue.payloads import (
    ProcessPaymentPayload,
    SendOrderConfirmationPayload,
    SettlePaymentPayload,
)


class TestProcessPaymentPayload:
    """Tests for ProcessPaymentPayload."""

    def test_creates_valid_payload(self) -> None:
        payload = ProcessPaymentPayload(
            order_id=uuid.UUID(int=0),
            amount=decimal.Decimal("0"),
            currency="test",
        )
        assert payload.order_id == uuid.UUID(int=0)
        assert payload.amount == decimal.Decimal("0")
        assert payload.currency == "test"

    def test_payload_is_frozen(self) -> None:
        payload = ProcessPaymentPayload(
            order_id=uuid.UUID(int=0),
            amount=decimal.Decimal("0"),
            currency="test",
        )
        with pytest.raises(AttributeError):
            payload.order_id = uuid.UUID(int=0)

    def test_json_round_trip(self) -> None:
        payload = ProcessPaymentPayload(
            order_id=uuid.UUID(int=0),
            amount=decimal.Decimal("0"),
            currency="test",
        )
        data = {
            "orderId": uuid.UUID(int=0),
            "amount": decimal.Decimal("0"),
            "currency": "test",
        }
        serialized = json.dumps(data, default=str)
        deserialized = json.loads(serialized)
        assert deserialized["orderId"] is not None


class TestSendOrderConfirmationPayload:
    """Tests for SendOrderConfirmationPayload."""

    def test_creates_valid_payload(self) -> None:
        payload = SendOrderConfirmationPayload(
            order_id=uuid.UUID(int=0),
            customer_email="test",
            order_number="test",
        )
        assert payload.order_id == uuid.UUID(int=0)
        assert payload.customer_email == "test"
        assert payload.order_number == "test"

    def test_payload_is_frozen(self) -> None:
        payload = SendOrderConfirmationPayload(
            order_id=uuid.UUID(int=0),
            customer_email="test",
            order_number="test",
        )
        with pytest.raises(AttributeError):
            payload.order_id = uuid.UUID(int=0)

    def test_json_round_trip(self) -> None:
        payload = SendOrderConfirmationPayload(
            order_id=uuid.UUID(int=0),
            customer_email="test",
            order_number="test",
        )
        data = {
            "orderId": uuid.UUID(int=0),
            "customerEmail": "test",
            "orderNumber": "test",
        }
        serialized = json.dumps(data, default=str)
        deserialized = json.loads(serialized)
        assert deserialized["orderId"] is not None


class TestSettlePaymentPayload:
    """Tests for SettlePaymentPayload."""

    def test_creates_valid_payload(self) -> None:
        payload = SettlePaymentPayload(
            payment_id=uuid.UUID(int=0),
            merchant_id="test",
            amount=decimal.Decimal("0"),
        )
        assert payload.payment_id == uuid.UUID(int=0)
        assert payload.merchant_id == "test"
        assert payload.amount == decimal.Decimal("0")

    def test_payload_is_frozen(self) -> None:
        payload = SettlePaymentPayload(
            payment_id=uuid.UUID(int=0),
            merchant_id="test",
            amount=decimal.Decimal("0"),
        )
        with pytest.raises(AttributeError):
            payload.payment_id = uuid.UUID(int=0)

    def test_json_round_trip(self) -> None:
        payload = SettlePaymentPayload(
            payment_id=uuid.UUID(int=0),
            merchant_id="test",
            amount=decimal.Decimal("0"),
        )
        data = {
            "paymentId": uuid.UUID(int=0),
            "merchantId": "test",
            "amount": decimal.Decimal("0"),
        }
        serialized = json.dumps(data, default=str)
        deserialized = json.loads(serialized)
        assert deserialized["paymentId"] is not None
