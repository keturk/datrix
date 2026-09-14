from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy.ext.asyncio import AsyncSession

from ecommerce_user_service.enums.user_status import UserStatus
from ecommerce_user_service.mq import producer as _mq_producer
from ecommerce_user_service.services._base import _field_changed, _field_old_value

if TYPE_CHECKING:
    from ecommerce_user_service.models.user_db.user import User


async def _user_db_user_after_update(
    target: User,
    db: AsyncSession,
    old_values: dict[str, object] | None = None,
    _commit: bool = True,
) -> None:
    """Execute afterUpdate lifecycle hook for User."""
    if _field_changed(target, "status", old_values):
        _producer_instance = await _mq_producer.get_producer()
        await _producer_instance.publish_user_status_changed(
            target.id, _field_old_value(target, "status", old_values), target.status
        )
        if (target.status == UserStatus.active) and target.is_verified:
            _producer_instance = await _mq_producer.get_producer()
            await _producer_instance.publish_user_verified(target.id, target.email)
