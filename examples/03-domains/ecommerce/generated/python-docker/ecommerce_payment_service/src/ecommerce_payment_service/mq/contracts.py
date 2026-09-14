"""Event contract validation functions.

Auto-generated from ``ensure`` clauses in event declarations.
Each function validates preconditions before event publication.
"""

from __future__ import annotations

import decimal
import logging
import uuid

from prometheus_client import Counter

from ecommerce_payment_service.errors import ContractViolationError

logger = logging.getLogger(__name__)

CONTRACT_VIOLATION_COUNTER = Counter(
    "mq_contract_violations_total",
    "Number of event contract violations",
    ["event", "clause"],
)


def _validate_payment_processed_contract(
    payment_id: uuid.UUID,
    order_id: uuid.UUID,
    amount: decimal.Decimal,
) -> None:
    """Validate contracts for PaymentProcessed event."""
    if not (amount > 0):
        logger.error(
            "contract_violation event=%r clause=%r amount=%s",
            "PaymentProcessed",
            "amount > 0",
            amount,
        )
        CONTRACT_VIOLATION_COUNTER.labels(
            event="PaymentProcessed",
            clause="amount > 0",
        ).inc()
        raise ContractViolationError(
            event="PaymentProcessed",
            clause="amount > 0",
            actual={
                "amount": amount,
            },
        )


def _validate_payment_failed_contract(
    payment_id: uuid.UUID,
    order_id: uuid.UUID,
    reason: str,
) -> None:
    """Validate contracts for PaymentFailed event."""
    if not (len(reason) > 0):
        logger.error(
            "contract_violation event=%r clause=%r reason=%s",
            "PaymentFailed",
            "reason.length > 0",
            reason,
        )
        CONTRACT_VIOLATION_COUNTER.labels(
            event="PaymentFailed",
            clause="reason.length > 0",
        ).inc()
        raise ContractViolationError(
            event="PaymentFailed",
            clause="reason.length > 0",
            actual={
                "reason": reason,
            },
        )


def _validate_payment_refunded_contract(
    payment_id: uuid.UUID,
    order_id: uuid.UUID,
    amount: decimal.Decimal,
) -> None:
    """Validate contracts for PaymentRefunded event."""
    if not (amount > 0):
        logger.error(
            "contract_violation event=%r clause=%r amount=%s",
            "PaymentRefunded",
            "amount > 0",
            amount,
        )
        CONTRACT_VIOLATION_COUNTER.labels(
            event="PaymentRefunded",
            clause="amount > 0",
        ).inc()
        raise ContractViolationError(
            event="PaymentRefunded",
            clause="amount > 0",
            actual={
                "amount": amount,
            },
        )
