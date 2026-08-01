"""GraphQL query resolvers for library_book_service."""

from __future__ import annotations

import uuid

import strawberry
from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from library_book_service.graphql.gql_schema_types import BookType
from library_book_service.models.book_db.book import Book
from library_book_service.services.book_db.book_service import BookService


@strawberry.type
class Query:
    @strawberry.field
    async def get_book(self, id: uuid.UUID, info: strawberry.Info) -> BookType:
        db: AsyncSession = info.context["db"]
        service = BookService(db)
        book = await service.get(id)
        if book is None:
            raise HTTPException(status_code=404, detail="Not found")
        return book

    @strawberry.field
    async def list_books(self, info: strawberry.Info) -> list[BookType]:
        db: AsyncSession = info.context["db"]
        all_books: list[Book] = list((await db.execute(select(Book))).scalars().all())
        return all_books

    @strawberry.field
    async def search_books(self, query: str, info: strawberry.Info) -> list[BookType]:
        db: AsyncSession = info.context["db"]
        return list(
            (await db.execute(select(Book).where(Book.title == query))).scalars().all()
        )
