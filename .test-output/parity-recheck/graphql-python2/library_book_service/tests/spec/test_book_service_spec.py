"""Specification tests for library.BookService.

Auto-generated from DSL test blocks. Run with:
    pytest tests/spec/ -v -m spec
"""

from __future__ import annotations

import pytest

from library_book_service.enums.book_status import BookStatus
from library_book_service.schemas.book_db.book import BookCreate
from library_book_service.schemas.book_db.category import CategoryCreate
from library_book_service.services.book_db.book_service import BookService
from library_book_service.services.book_db.category_service import CategoryService


@pytest.mark.spec
async def test_book_is_created_with_available_status_by_default(db_session, event_spy):
    """book is created with Available status by default"""
    _category_svc = CategoryService(db_session)
    cat = await _category_svc.create(CategoryCreate(**{"name": "SpecCatGql"}))
    await db_session.refresh(cat)
    _book_svc = BookService(db_session)
    book = await _book_svc.create(
        BookCreate(
            **{
                "title": "GraphQL Guide",
                "author": "Test Author",
                "publication_year": 2023,
                "status": BookStatus.available,
                "category_id": cat.id,
            }
        )
    )
    await db_session.refresh(book)
    assert book.status == BookStatus.available
