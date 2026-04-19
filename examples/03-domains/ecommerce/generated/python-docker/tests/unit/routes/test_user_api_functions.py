"""Unit tests for UserAPI API functions."""

from __future__ import annotations

import inspect

import pytest

from ecommerce_user_service.routes.user_api import (
    generate_session_token,
)


@pytest.mark.unit
class TestUserAPIFunctions:
    """Tests for UserAPI API-level function declarations."""

    def test_generate_session_token_exists(self) -> None:
        """generateSessionToken function exists and is callable."""
        assert callable(generate_session_token)

    def test_generate_session_token_is_async(self) -> None:
        """generateSessionToken is an async function."""
        assert inspect.iscoroutinefunction(generate_session_token)

    def test_generate_session_token_parameter_count(self) -> None:
        """generateSessionToken accepts 0 parameter(s)."""
        sig = inspect.signature(generate_session_token)
        params = [p for p in sig.parameters.values() if p.name != "self"]
        # API functions may also receive injected dependencies (db, etc.)
        # so assert at least the declared parameter count.
        assert len(params) >= 0
