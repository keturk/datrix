"""Event contract validation functions.

Auto-generated from ``ensure`` clauses in event declarations.
Each function validates preconditions before event publication.
"""

from __future__ import annotations

import decimal
import logging
import uuid

from prometheus_client import Counter

from ecommerce_order_service.errors import ContractViolationError

logger = logging.getLogger(__name__)

CONTRACT_VIOLATION_COUNTER = Counter(
    "queue_contract_violations_total",
    "Number of event contract violations",
    ["event", "clause"],
)


def _validate_process_payment_contract(
    order_id: uuid.UUID,
    amount: decimal.Decimal,
    currency: str,
) -> None:
    """Validate contracts for ProcessPayment event."""
    if not (amount > 0):
        logger.error(
            "contract_violation event=%r clause=%r amount=%s",
            "ProcessPayment",
            "amount > 0",
            amount,
        )
        CONTRACT_VIOLATION_COUNTER.labels(
            event="ProcessPayment",
            clause="amount > 0",
        ).inc()
        raise ContractViolationError(
            event="ProcessPayment",
            clause="amount > 0",
            actual={
                "amount": amount,
            },
        )
    if not ("LENGTH" == 3):
        logger.error(
            "contract_violation event=%r clause=%r currency=%s",
            "ProcessPayment",
            "currency.length == 3",
            currency,
        )
        CONTRACT_VIOLATION_COUNTER.labels(
            event="ProcessPayment",
            clause="currency.length == 3",
        ).inc()
        raise ContractViolationError(
            event="ProcessPayment",
            clause="currency.length == 3",
            actual={
                "currency": currency,
            },
        )


def _validate_send_order_confirmation_contract(
    order_id: uuid.UUID,
    customer_email: str,
    order_number: str,
) -> None:
    """Validate contracts for SendOrderConfirmation event."""
    if not (len(customer_email) > 0):
        logger.error(
            "contract_violation event=%r clause=%r customerEmail=%s",
            "SendOrderConfirmation",
            "customerEmail.length > 0",
            customer_email,
        )
        CONTRACT_VIOLATION_COUNTER.labels(
            event="SendOrderConfirmation",
            clause="customerEmail.length > 0",
        ).inc()
        raise ContractViolationError(
            event="SendOrderConfirmation",
            clause="customerEmail.length > 0",
            actual={
                "customerEmail": customer_email,
            },
        )


def _validate_settle_payment_contract(
    payment_id: uuid.UUID,
    merchant_id: str,
    amount: decimal.Decimal,
) -> None:
    """Validate contracts for SettlePayment event."""
    if not (amount > 0):
        logger.error(
            "contract_violation event=%r clause=%r amount=%s",
            "SettlePayment",
            "amount > 0",
            amount,
        )
        CONTRACT_VIOLATION_COUNTER.labels(
            event="SettlePayment",
            clause="amount > 0",
        ).inc()
        raise ContractViolationError(
            event="SettlePayment",
            clause="amount > 0",
            actual={
                "amount": amount,
            },
        )
    if not (len(merchant_id) > 0):
        logger.error(
            "contract_violation event=%r clause=%r merchantId=%s",
            "SettlePayment",
            "merchantId.length > 0",
            merchant_id,
        )
        CONTRACT_VIOLATION_COUNTER.labels(
            event="SettlePayment",
            clause="merchantId.length > 0",
        ).inc()
        raise ContractViolationError(
            event="SettlePayment",
            clause="merchantId.length > 0",
            actual={
                "merchantId": merchant_id,
            },
        )
