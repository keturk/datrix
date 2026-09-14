from __future__ import annotations

import datetime
from typing import TYPE_CHECKING

from sqlalchemy.ext.asyncio import AsyncSession

if TYPE_CHECKING:
    from ecommerce_user_service.models.user_db.user import User


async def _user_db_user_before_update(
    target: User,
    db: AsyncSession,
    old_values: dict[str, object] | None = None,
    _commit: bool = True,
) -> None:
    """Execute beforeUpdate lifecycle hook for User."""
    target.updated_at = datetime.datetime.now(datetime.timezone.utc)
