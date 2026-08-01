"""GraphQL subscription resolvers for library_book_service."""

from __future__ import annotations

import uuid
from collections.abc import AsyncGenerator

import strawberry
from sqlalchemy.ext.asyncio import AsyncSession

from library_book_service.enums.book_status import BookStatus
from library_book_service.graphql.gql_schema_types import BookType
from library_book_service.models.book_db.book import Book


@strawberry.type
class Subscription:
    @strawberry.subscription
    async def on_book_added(
        self, book_id: uuid.UUID, title: str, info: strawberry.Info
    ) -> AsyncGenerator[BookType, None]:
        db: AsyncSession = info.context["db"]
        book: Book = await db.get(Book, book_id)
        return book

    @strawberry.subscription
    async def on_book_status_changed(
        self,
        book_id: uuid.UUID,
        old_status: BookStatus,
        new_status: BookStatus,
        info: strawberry.Info,
    ) -> AsyncGenerator[BookType, None]:
        db: AsyncSession = info.context["db"]
        book: Book = await db.get(Book, book_id)
        return book
