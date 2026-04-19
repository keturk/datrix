"""Unit tests for OrderAPI API functions."""

from __future__ import annotations

import inspect

import pytest

from ecommerce_order_service.routes.order_api import (
    check_idempotency,
    store_idempotency,
)


@pytest.mark.unit
class TestOrderAPIFunctions:
    """Tests for OrderAPI API-level function declarations."""

    def test_check_idempotency_exists(self) -> None:
        """checkIdempotency function exists and is callable."""
        assert callable(check_idempotency)

    def test_check_idempotency_is_async(self) -> None:
        """checkIdempotency is an async function."""
        assert inspect.iscoroutinefunction(check_idempotency)

    def test_check_idempotency_parameter_count(self) -> None:
        """checkIdempotency accepts 2 parameter(s)."""
        sig = inspect.signature(check_idempotency)
        params = [p for p in sig.parameters.values() if p.name != "self"]
        # API functions may also receive injected dependencies (db, etc.)
        # so assert at least the declared parameter count.
        assert len(params) >= 2

    def test_check_idempotency_has_idempotency_key_param(self) -> None:
        """checkIdempotency accepts 'idempotency_key' parameter."""
        sig = inspect.signature(check_idempotency)
        param_names = list(sig.parameters.keys())
        assert "idempotency_key" in param_names

    def test_check_idempotency_has_operation_param(self) -> None:
        """checkIdempotency accepts 'operation' parameter."""
        sig = inspect.signature(check_idempotency)
        param_names = list(sig.parameters.keys())
        assert "operation" in param_names

    def test_store_idempotency_exists(self) -> None:
        """storeIdempotency function exists and is callable."""
        assert callable(store_idempotency)

    def test_store_idempotency_is_async(self) -> None:
        """storeIdempotency is an async function."""
        assert inspect.iscoroutinefunction(store_idempotency)

    def test_store_idempotency_parameter_count(self) -> None:
        """storeIdempotency accepts 4 parameter(s)."""
        sig = inspect.signature(store_idempotency)
        params = [p for p in sig.parameters.values() if p.name != "self"]
        # API functions may also receive injected dependencies (db, etc.)
        # so assert at least the declared parameter count.
        assert len(params) >= 4

    def test_store_idempotency_has_idempotency_key_param(self) -> None:
        """storeIdempotency accepts 'idempotency_key' parameter."""
        sig = inspect.signature(store_idempotency)
        param_names = list(sig.parameters.keys())
        assert "idempotency_key" in param_names

    def test_store_idempotency_has_operation_param(self) -> None:
        """storeIdempotency accepts 'operation' parameter."""
        sig = inspect.signature(store_idempotency)
        param_names = list(sig.parameters.keys())
        assert "operation" in param_names

    def test_store_idempotency_has_resource_id_param(self) -> None:
        """storeIdempotency accepts 'resource_id' parameter."""
        sig = inspect.signature(store_idempotency)
        param_names = list(sig.parameters.keys())
        assert "resource_id" in param_names

    def test_store_idempotency_has_response_param(self) -> None:
        """storeIdempotency accepts 'response' parameter."""
        sig = inspect.signature(store_idempotency)
        param_names = list(sig.parameters.keys())
        assert "response" in param_names
