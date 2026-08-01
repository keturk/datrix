"""Strawberry GraphQL input types for library_book_service."""

from __future__ import annotations

import uuid

import strawberry

from library_book_service.enums.book_status import BookStatus


@strawberry.input
class CreateBookInput:
    title: str
    author: str
    publication_year: int
    category_id: uuid.UUID


@strawberry.input
class UpdateBookInput:
    title: str | None
    author: str | None
    status: BookStatus | None
