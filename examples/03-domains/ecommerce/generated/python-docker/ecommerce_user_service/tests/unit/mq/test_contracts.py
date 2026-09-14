"""Tests for event contract validation.

Auto-generated. Verifies that contract violations are detected.
"""

from __future__ import annotations

import uuid

import pytest

from ecommerce_user_service.enums.user_status import UserStatus
from ecommerce_user_service.errors import ContractViolationError
from ecommerce_user_service.mq.contracts import (
    _validate_user_registered_contract,
    _validate_user_status_changed_contract,
)


class TestUserRegisteredContracts:
    """Contract tests for UserRegistered."""

    def test_valid_payload_passes(self) -> None:
        """Valid payload passes all contract checks."""
        _validate_user_registered_contract(
            user_id=uuid.UUID("550e8400-e29b-41d4-a716-446655440000"),
            email="user@example.com",
            full_name="x",
        )

    def test_violating_clause_0(self) -> None:
        """Violating 'fullName.length > 0' raises ContractViolationError."""
        with pytest.raises(ContractViolationError) as exc_info:
            _validate_user_registered_contract(
                user_id=uuid.UUID("550e8400-e29b-41d4-a716-446655440000"),
                email="user@example.com",
                full_name="",
            )
        assert exc_info.value.event == "UserRegistered"
        assert exc_info.value.clause == "fullName.length > 0"


class TestUserStatusChangedContracts:
    """Contract tests for UserStatusChanged."""

    def test_valid_payload_passes(self) -> None:
        """Valid payload passes all contract checks."""
        _validate_user_status_changed_contract(
            user_id=uuid.UUID("550e8400-e29b-41d4-a716-446655440000"),
            old_status=UserStatus.active,
            new_status=UserStatus.inactive,
        )

    def test_violating_clause_0(self) -> None:
        """Violating 'oldStatus != newStatus' raises ContractViolationError."""
        with pytest.raises(ContractViolationError) as exc_info:
            _validate_user_status_changed_contract(
                user_id=uuid.UUID("550e8400-e29b-41d4-a716-446655440000"),
                old_status=UserStatus.active,
                new_status=UserStatus.active,
            )
        assert exc_info.value.event == "UserStatusChanged"
        assert exc_info.value.clause == "oldStatus != newStatus"
