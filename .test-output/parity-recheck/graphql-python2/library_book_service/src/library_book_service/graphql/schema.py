"""Assembled Strawberry schema (lazy import so resolver modules may load first)."""

from __future__ import annotations

import strawberry


def build_schema() -> strawberry.Schema:
    """Import root types after all graphql modules exist, then build schema."""
    from .mutations import Mutation
    from .queries import Query
    from .subscriptions import Subscription

    return strawberry.Schema(
        query=Query,
        mutation=Mutation,
        subscription=Subscription,
    )


schema = build_schema()
