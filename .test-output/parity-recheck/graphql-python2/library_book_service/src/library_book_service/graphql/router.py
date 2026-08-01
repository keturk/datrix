"""FastAPI GraphQL router for library_book_service."""

from __future__ import annotations

from typing import Annotated

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.requests import Request
from strawberry.fastapi import GraphQLRouter

from library_book_service.book_db.session import get_book_db_db

from .data_loaders import build_graphql_data_loaders
from .schema import schema


async def get_context(
    db: Annotated[AsyncSession, Depends(get_book_db_db)],
    request: Request,
) -> dict[str, object]:
    """Inject dependencies into Strawberry context for GraphQL resolvers."""
    loaders = build_graphql_data_loaders(db)
    ctx: dict[str, object] = {"db": db, "request": request}
    ctx.update(loaders)
    return ctx


graphql_router = GraphQLRouter(schema, path="/graphql", context_getter=get_context)
