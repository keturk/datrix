from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy.ext.asyncio import AsyncSession

from ecommerce_product_service._cache_helpers import _get_redis
from ecommerce_product_service.mq import producer as _mq_producer
from ecommerce_product_service.services._base import _field_changed, _field_old_value

if TYPE_CHECKING:
    from ecommerce_product_service.models.product_db.product import Product


async def _product_db_product_after_update(
    target: Product,
    db: AsyncSession,
    old_values: dict[str, object] | None = None,
    _commit: bool = True,
) -> None:
    """Execute afterUpdate lifecycle hook for Product."""
    if _field_changed(target, "inventory", old_values):
        _producer_instance = await _mq_producer.get_producer()
        await _producer_instance.publish_inventory_updated(
            target.id,
            _field_old_value(target, "inventory", old_values),
            target.inventory,
        )
    if _field_changed(target, "status", old_values):
        await _get_redis().delete(("product:" + f":{str(f'product:{target.id}')}"))
        await _get_redis().delete(
            ("product:" + f":{str(f'product:slug:{target.slug}')}")
        )
