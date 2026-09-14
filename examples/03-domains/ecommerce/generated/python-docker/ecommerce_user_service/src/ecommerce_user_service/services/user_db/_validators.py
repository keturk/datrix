"""Block-scoped DSL validation lowering (generated -- do not edit)."""

from __future__ import annotations

import re

import validators

from ecommerce_user_service.enums.user_status import UserStatus
from ecommerce_user_service.models.user_db.user import User
from ecommerce_user_service.models.user_db.user_session import UserSession
from ecommerce_user_service.services._base import ValidationError


def validate_user(entity: User) -> None:
    """Validate User business rules (from DSL validate block)."""
    if not bool(validators.email(entity.email)):
        raise ValidationError(["Invalid email format"])
    if entity.phone_number is not None and (
        not bool(re.match("^\\+?[1-9]\\d{1,14}$", entity.phone_number))
    ):
        raise ValidationError(["Invalid phone number"])
    if entity.status is not None and (
        entity.status == UserStatus.active and (not entity.is_verified)
    ):
        raise ValidationError(["Cannot activate unverified user"])


def validate_user_session(entity: UserSession) -> None:
    """Validate UserSession business rules (from DSL validate block)."""
    if entity.created_at is not None and entity.expires_at <= entity.created_at:
        raise ValidationError(["Expiry must be after creation"])
