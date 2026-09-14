"""Specification tests for ecommerce.PaymentService.

Auto-generated from DSL test blocks. Run with:
    pytest tests/spec/ -v -m spec
"""

from __future__ import annotations

import uuid
from decimal import Decimal

import pytest

from ecommerce_payment_service.enums.payment_method import PaymentMethod
from ecommerce_payment_service.enums.payment_status import PaymentStatus
from ecommerce_payment_service.schemas.payment_db.payment import (
    PaymentCreate,
    PaymentUpdate,
)
from ecommerce_payment_service.services.payment_db.payment_service import PaymentService


@pytest.mark.spec
async def test_computed_is_successful_reflects_completed_status(db_session, event_spy):
    """computed isSuccessful reflects Completed status"""
    _payment_svc = PaymentService(db_session)
    payment = await _payment_svc.create(
        PaymentCreate(
            **{
                "order_id": uuid.uuid4(),
                "customer_id": uuid.uuid4(),
                "amount": Decimal(str(99.99)),
                "method": PaymentMethod.credit_card,
                "transaction_id": "TXN-SPEC-001",
                "status": PaymentStatus.completed,
            }
        )
    )
    await db_session.refresh(payment)
    assert payment.is_successful == True


@pytest.mark.spec
async def test_computed_can_refund_requires_completed_status(db_session, event_spy):
    """computed canRefund requires Completed status"""
    _payment_svc = PaymentService(db_session)
    payment = await _payment_svc.create(
        PaymentCreate(
            **{
                "order_id": uuid.uuid4(),
                "customer_id": uuid.uuid4(),
                "amount": Decimal(str(49.99)),
                "method": PaymentMethod.pay_pal,
                "transaction_id": "TXN-SPEC-002",
                "status": PaymentStatus.completed,
            }
        )
    )
    await db_session.refresh(payment)
    assert payment.can_refund == True


@pytest.mark.spec
async def test_after_update_emits_payment_processed_when_status_is_completed(
    db_session, event_spy
):
    """afterUpdate emits PaymentProcessed when status is Completed"""
    _payment_svc = PaymentService(db_session)
    payment = await _payment_svc.create(
        PaymentCreate(
            **{
                "order_id": uuid.uuid4(),
                "customer_id": uuid.uuid4(),
                "amount": Decimal(str(175.5)),
                "method": PaymentMethod.credit_card,
                "transaction_id": "TXN-SPEC-003",
                "status": PaymentStatus.processing,
            }
        )
    )
    await db_session.refresh(payment)

    _payment_svc = PaymentService(db_session)
    payment = await _payment_svc.update(
        payment.id, PaymentUpdate(**{"status": PaymentStatus.completed})
    )
    assert event_spy.has(
        "PaymentProcessed",
        payment_id=payment.id,
        order_id=payment.order_id,
        amount=payment.amount,
    )


@pytest.mark.spec
async def test_after_update_emits_payment_failed_when_status_is_failed(
    db_session, event_spy
):
    """afterUpdate emits PaymentFailed when status is Failed"""
    _payment_svc = PaymentService(db_session)
    payment = await _payment_svc.create(
        PaymentCreate(
            **{
                "order_id": uuid.uuid4(),
                "customer_id": uuid.uuid4(),
                "amount": Decimal(str(220.0)),
                "method": PaymentMethod.debit_card,
                "transaction_id": "TXN-SPEC-004",
                "status": PaymentStatus.processing,
                "error_message": "Insufficient funds",
            }
        )
    )
    await db_session.refresh(payment)

    _payment_svc = PaymentService(db_session)
    payment = await _payment_svc.update(
        payment.id, PaymentUpdate(**{"status": PaymentStatus.failed})
    )
    assert event_spy.has(
        "PaymentFailed",
        payment_id=payment.id,
        order_id=payment.order_id,
        reason="Insufficient funds",
    )


@pytest.mark.spec
async def test_after_update_emits_payment_refunded_when_status_is_refunded(
    db_session, event_spy
):
    """afterUpdate emits PaymentRefunded when status is Refunded"""
    _payment_svc = PaymentService(db_session)
    payment = await _payment_svc.create(
        PaymentCreate(
            **{
                "order_id": uuid.uuid4(),
                "customer_id": uuid.uuid4(),
                "amount": Decimal(str(89.99)),
                "method": PaymentMethod.pay_pal,
                "transaction_id": "TXN-SPEC-005",
                "status": PaymentStatus.completed,
            }
        )
    )
    await db_session.refresh(payment)

    _payment_svc = PaymentService(db_session)
    payment = await _payment_svc.update(
        payment.id, PaymentUpdate(**{"status": PaymentStatus.refunded})
    )
    assert event_spy.has(
        "PaymentRefunded",
        payment_id=payment.id,
        order_id=payment.order_id,
        amount=payment.amount,
    )
