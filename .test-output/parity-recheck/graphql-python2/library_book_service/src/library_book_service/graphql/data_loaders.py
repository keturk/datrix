"""Strawberry DataLoaders for library_book_service (request-scoped, SQLAlchemy batching)."""

from __future__ import annotations

import logging
import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from strawberry.dataloader import DataLoader

from library_book_service.graphql.gql_schema_types import CategoryType
from library_book_service.models.book_db.category import Category

logger = logging.getLogger(__name__)


def build_graphql_data_loaders(db: AsyncSession) -> dict[str, DataLoader]:
    """Create DataLoader instances bound to *db* for one GraphQL request.

    Args:
        db: Async SQLAlchemy session from GraphQL context.

    Returns:
        Mapping of context keys (e.g. ``books_by_category_loader``) to DataLoader.
    """
    loaders: dict[str, DataLoader] = {}

    async def _batch_load_category_loader(
        keys: list[uuid.UUID],
    ) -> list[CategoryType | None]:
        if not keys:
            return []
        stmt = select(Category).where(getattr(Category, "id").in_(keys))
        result = await db.execute(stmt)
        rows = list(result.scalars().all())
        by_id: dict[uuid.UUID, CategoryType] = {}
        for row in rows:
            rid = getattr(row, "id")
            by_id[rid] = CategoryType.from_entity(row)
        ordered = [by_id.get(k) for k in keys]
        logger.info(
            "graphql_dataloader_batch mode=pk_batch loader=category_loader keys=%d rows=%d",
            len(keys),
            len(rows),
        )
        return ordered

    loaders["category_loader"] = DataLoader(
        load_fn=_batch_load_category_loader,
        max_batch_size=100,
    )
    return loaders
