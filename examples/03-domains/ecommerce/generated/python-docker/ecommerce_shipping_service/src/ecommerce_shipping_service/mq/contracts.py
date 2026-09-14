"""Event contract validation functions.

Auto-generated from ``ensure`` clauses in event declarations.
Each function validates preconditions before event publication.
"""

from __future__ import annotations

import logging
import uuid

from prometheus_client import Counter

from ecommerce_shipping_service.errors import ContractViolationError

logger = logging.getLogger(__name__)

CONTRACT_VIOLATION_COUNTER = Counter(
    "mq_contract_violations_total",
    "Number of event contract violations",
    ["event", "clause"],
)


def _validate_shipment_dispatched_contract(
    shipment_id: uuid.UUID,
    order_id: uuid.UUID,
    tracking_number: str,
) -> None:
    """Validate contracts for ShipmentDispatched event."""
    if not (len(tracking_number) > 0):
        logger.error(
            "contract_violation event=%r clause=%r trackingNumber=%s",
            "ShipmentDispatched",
            "trackingNumber.length > 0",
            tracking_number,
        )
        CONTRACT_VIOLATION_COUNTER.labels(
            event="ShipmentDispatched",
            clause="trackingNumber.length > 0",
        ).inc()
        raise ContractViolationError(
            event="ShipmentDispatched",
            clause="trackingNumber.length > 0",
            actual={
                "trackingNumber": tracking_number,
            },
        )


def _validate_shipment_failed_contract(
    shipment_id: uuid.UUID,
    order_id: uuid.UUID,
    reason: str,
) -> None:
    """Validate contracts for ShipmentFailed event."""
    if not (len(reason) > 0):
        logger.error(
            "contract_violation event=%r clause=%r reason=%s",
            "ShipmentFailed",
            "reason.length > 0",
            reason,
        )
        CONTRACT_VIOLATION_COUNTER.labels(
            event="ShipmentFailed",
            clause="reason.length > 0",
        ).inc()
        raise ContractViolationError(
            event="ShipmentFailed",
            clause="reason.length > 0",
            actual={
                "reason": reason,
            },
        )
