from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy.ext.asyncio import AsyncSession

from ecommerce_user_service.integrations._email_helpers import _email_send_smtp
from ecommerce_user_service.mq import producer as _mq_producer

if TYPE_CHECKING:
    from ecommerce_user_service.models.user_db.user import User


async def _user_db_user_after_create(
    target: User,
    db: AsyncSession,
    _commit: bool = True,
) -> None:
    """Execute afterCreate lifecycle hook for User."""
    _producer_instance = await _mq_producer.get_producer()
    await _producer_instance.publish_user_registered(
        target.id, target.email, target.full_name
    )
    await _email_send_smtp(
        {
            "to": target.email,
            "subject": "Verify your email",
            "template": "emailVerification",
            "data": {
                "token": target.email_verification_token,
                "fullName": target.full_name,
            },
        }
    )
