"""Event contract validation functions.

Auto-generated from ``ensure`` clauses in event declarations.
Each function validates preconditions before event publication.
"""

from __future__ import annotations

import logging
import uuid

from prometheus_client import Counter

from ecommerce_user_service.enums.user_status import UserStatus
from ecommerce_user_service.errors import ContractViolationError

logger = logging.getLogger(__name__)

CONTRACT_VIOLATION_COUNTER = Counter(
    "mq_contract_violations_total",
    "Number of event contract violations",
    ["event", "clause"],
)


def _validate_user_registered_contract(
    user_id: uuid.UUID,
    email: str,
    full_name: str,
) -> None:
    """Validate contracts for UserRegistered event."""
    if not (len(full_name) > 0):
        logger.error(
            "contract_violation event=%r clause=%r fullName=%s",
            "UserRegistered",
            "fullName.length > 0",
            full_name,
        )
        CONTRACT_VIOLATION_COUNTER.labels(
            event="UserRegistered",
            clause="fullName.length > 0",
        ).inc()
        raise ContractViolationError(
            event="UserRegistered",
            clause="fullName.length > 0",
            actual={
                "fullName": full_name,
            },
        )


def _validate_user_status_changed_contract(
    user_id: uuid.UUID,
    old_status: UserStatus,
    new_status: UserStatus,
) -> None:
    """Validate contracts for UserStatusChanged event."""
    if not (old_status != new_status):
        logger.error(
            "contract_violation event=%r clause=%r newStatus=%s oldStatus=%s",
            "UserStatusChanged",
            "oldStatus != newStatus",
            new_status,
            old_status,
        )
        CONTRACT_VIOLATION_COUNTER.labels(
            event="UserStatusChanged",
            clause="oldStatus != newStatus",
        ).inc()
        raise ContractViolationError(
            event="UserStatusChanged",
            clause="oldStatus != newStatus",
            actual={
                "newStatus": new_status,
                "oldStatus": old_status,
            },
        )
