"""Specification tests for ecommerce.UserService.

Auto-generated from DSL test blocks. Run with:
    pytest tests/spec/ -v -m spec
"""

from __future__ import annotations

import datetime

import bcrypt
import pytest

from ecommerce_user_service.enums.user_status import UserStatus
from ecommerce_user_service.schemas.user_db.user import UserCreate, UserUpdate
from ecommerce_user_service.services._base import ValidationError
from ecommerce_user_service.services.user_db.user_service import UserService


@pytest.mark.spec
async def test_computed_full_name_concatenates_first_and_last_name(
    db_session, event_spy
):
    """computed fullName concatenates first and last name"""
    _user_svc = UserService(db_session)
    user = await _user_svc.create(
        UserCreate(
            **{
                "email": "spec.name@example.com",
                "password_hash": bcrypt.hashpw(
                    "Str0ng#TestP@ss9".encode(), bcrypt.gensalt()
                ).decode(),
                "first_name": "John",
                "last_name": "Doe",
            }
        )
    )
    await db_session.refresh(user)
    assert user.full_name == "John Doe"


@pytest.mark.spec
async def test_computed_can_login_requires_active_and_verified(db_session, event_spy):
    """computed canLogin requires active and verified"""
    _user_svc = UserService(db_session)
    user = await _user_svc.create(
        UserCreate(
            **{
                "email": "spec.login@example.com",
                "password_hash": bcrypt.hashpw(
                    "Str0ng#TestP@ss9".encode(), bcrypt.gensalt()
                ).decode(),
                "first_name": "Jane",
                "last_name": "Smith",
                "status": UserStatus.active,
                "email_verified_at": datetime.datetime.now(datetime.timezone.utc),
            }
        )
    )
    await db_session.refresh(user)
    assert user.can_login == True


@pytest.mark.spec
async def test_validation_rejects_activating_unverified_user(db_session, event_spy):
    """validation rejects activating unverified user"""
    with pytest.raises(ValidationError, match="Cannot activate unverified user"):
        _user_svc = UserService(db_session)
        _entity = await _user_svc.create(
            UserCreate(
                **{
                    "email": "spec.unverified@example.com",
                    "password_hash": bcrypt.hashpw(
                        "Str0ng#TestP@ss9".encode(), bcrypt.gensalt()
                    ).decode(),
                    "first_name": "Unverified",
                    "last_name": "User",
                    "status": UserStatus.active,
                }
            )
        )


@pytest.mark.spec
async def test_after_create_emits_user_registered_event(db_session, event_spy):
    """afterCreate emits UserRegistered event"""
    _user_svc = UserService(db_session)
    user = await _user_svc.create(
        UserCreate(
            **{
                "email": "spec.event@example.com",
                "password_hash": bcrypt.hashpw(
                    "Str0ng#TestP@ss9".encode(), bcrypt.gensalt()
                ).decode(),
                "first_name": "Alice",
                "last_name": "Johnson",
            }
        )
    )
    await db_session.refresh(user)
    assert event_spy.has(
        "UserRegistered", user_id=user.id, email=user.email, full_name=user.full_name
    )


@pytest.mark.spec
async def test_computed_is_active_reflects_active_status(db_session, event_spy):
    """computed isActive reflects Active status"""
    _user_svc = UserService(db_session)
    user = await _user_svc.create(
        UserCreate(
            **{
                "email": "spec.active@example.com",
                "password_hash": bcrypt.hashpw(
                    "Str0ng#TestP@ss9".encode(), bcrypt.gensalt()
                ).decode(),
                "first_name": "Marcus",
                "last_name": "Green",
                "status": UserStatus.active,
                "email_verified_at": datetime.datetime.now(datetime.timezone.utc),
            }
        )
    )
    await db_session.refresh(user)
    assert user.is_active == True


@pytest.mark.spec
async def test_computed_is_verified_when_email_verified_at_is_set(
    db_session, event_spy
):
    """computed isVerified when emailVerifiedAt is set"""
    _user_svc = UserService(db_session)
    user = await _user_svc.create(
        UserCreate(
            **{
                "email": "spec.verified@example.com",
                "password_hash": bcrypt.hashpw(
                    "Str0ng#TestP@ss9".encode(), bcrypt.gensalt()
                ).decode(),
                "first_name": "Elena",
                "last_name": "Martinez",
                "status": UserStatus.active,
                "email_verified_at": datetime.datetime.now(datetime.timezone.utc),
            }
        )
    )
    await db_session.refresh(user)
    assert user.is_verified == True


@pytest.mark.spec
async def test_after_update_emits_user_status_changed_on_status_change(
    db_session, event_spy
):
    """afterUpdate emits UserStatusChanged on status change"""
    _user_svc = UserService(db_session)
    user = await _user_svc.create(
        UserCreate(
            **{
                "email": "spec.statuschange@example.com",
                "password_hash": bcrypt.hashpw(
                    "Str0ng#TestP@ss9".encode(), bcrypt.gensalt()
                ).decode(),
                "first_name": "Robert",
                "last_name": "Chen",
                "status": UserStatus.pending,
            }
        )
    )
    await db_session.refresh(user)

    _user_svc = UserService(db_session)
    user = await _user_svc.update(
        user.id,
        UserUpdate(
            **{
                "email_verified_at": datetime.datetime.now(datetime.timezone.utc),
                "status": UserStatus.active,
            }
        ),
    )
    assert event_spy.has(
        "UserStatusChanged",
        user_id=user.id,
        old_status=UserStatus.pending,
        new_status=UserStatus.active,
    )
