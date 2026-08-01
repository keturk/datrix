"""GraphQL mutation resolvers for library_book_service."""

from __future__ import annotations

import uuid

import strawberry
from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from library_book_service.enums.book_status import BookStatus
from library_book_service.graphql.gql_schema_types import BookType
from library_book_service.graphql.inputs import CreateBookInput, UpdateBookInput
from library_book_service.models.book_db.book import Book
from library_book_service.mq import producer as _mq_producer
from library_book_service.services.book_db.book_service import BookService


@strawberry.type
class Mutation:
    @strawberry.mutation
    async def create_book(
        self, input: CreateBookInput, info: strawberry.Info
    ) -> BookType:
        db: AsyncSession = info.context["db"]
        book = Book(
            **{
                "title": input.title,
                "author": input.author,
                "publication_year": input.publication_year,
                "category_id": input.category_id,
                "status": BookStatus.available,
            }
        )
        db.add(book)
        await db.flush()
        await db.refresh(book)
        db.add(book)
        await db.commit()
        await db.refresh(book)
        _producer_instance = _mq_producer.producer_instance
        if _producer_instance is not None:
            await _producer_instance.publish_book_added(book.id, book.title)
        return book

    @strawberry.mutation
    async def update_book(
        self, id: uuid.UUID, input: UpdateBookInput, info: strawberry.Info
    ) -> BookType:
        db: AsyncSession = info.context["db"]
        service = BookService(db)
        book = await service.get(id)
        if book is None:
            raise HTTPException(status_code=404, detail="Not found")
        if input.title is not None:
            book.title = input.title
        if input.author is not None:
            book.author = input.author
        if input.status is not None:
            old_status: BookStatus = book.status
            book.status = input.status
            _producer_instance = _mq_producer.producer_instance
            if _producer_instance is not None:
                await _producer_instance.publish_book_status_changed(
                    id, old_status, input.status
                )
        db.add(book)
        await db.commit()
        await db.refresh(book)
        return book

    @strawberry.mutation
    async def delete_book(self, id: uuid.UUID, info: strawberry.Info) -> bool:
        db: AsyncSession = info.context["db"]
        service = BookService(db)
        book = await service.get(id)
        if book is None:
            raise HTTPException(status_code=404, detail="Not found")
        await db.delete(book)
        await db.commit()
        return True
