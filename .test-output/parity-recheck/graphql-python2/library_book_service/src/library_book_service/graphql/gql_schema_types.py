"""Strawberry GraphQL object types for library_book_service."""

from __future__ import annotations

import uuid

import strawberry

from library_book_service.enums.book_status import BookStatus
from library_book_service.models.book_db.book import Book
from library_book_service.models.book_db.category import Category


@strawberry.type
class CategoryType:
    id: uuid.UUID
    name: str
    books: list[BookType]

    @classmethod
    def from_entity(cls, row: Category) -> CategoryType:
        return cls(
            id=row.id,
            name=row.name,
            books=[BookType.from_entity(_x) for _x in row.books],
        )


@strawberry.type
class BookType:
    id: uuid.UUID
    title: str
    author: str
    publication_year: int
    status: BookStatus

    @strawberry.field
    async def category(self, info: strawberry.Info) -> CategoryType:
        loader = info.context["category_loader"]
        _key = self.category_id
        return await loader.load(_key)

    @classmethod
    def from_entity(cls, row: Book) -> BookType:
        return cls(
            id=row.id,
            title=row.title,
            author=row.author,
            publication_year=row.publication_year,
            status=row.status,
        )
