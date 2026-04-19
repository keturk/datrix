"""Unit tests for ShippingAPI API functions."""

from __future__ import annotations

import inspect

import pytest

from ecommerce_shipping_service.routes.shipping_api import (
    calculate_rate,
    map_fed_ex_status,
)


@pytest.mark.unit
class TestShippingAPIFunctions:
    """Tests for ShippingAPI API-level function declarations."""

    def test_calculate_rate_exists(self) -> None:
        """calculateRate function exists and is callable."""
        assert callable(calculate_rate)

    def test_calculate_rate_is_async(self) -> None:
        """calculateRate is an async function."""
        assert inspect.iscoroutinefunction(calculate_rate)

    def test_calculate_rate_parameter_count(self) -> None:
        """calculateRate accepts 3 parameter(s)."""
        sig = inspect.signature(calculate_rate)
        params = [p for p in sig.parameters.values() if p.name != "self"]
        # API functions may also receive injected dependencies (db, etc.)
        # so assert at least the declared parameter count.
        assert len(params) >= 3

    def test_calculate_rate_has_carrier_param(self) -> None:
        """calculateRate accepts 'carrier' parameter."""
        sig = inspect.signature(calculate_rate)
        param_names = list(sig.parameters.keys())
        assert "carrier" in param_names

    def test_calculate_rate_has_destination_param(self) -> None:
        """calculateRate accepts 'destination' parameter."""
        sig = inspect.signature(calculate_rate)
        param_names = list(sig.parameters.keys())
        assert "destination" in param_names

    def test_calculate_rate_has_weight_param(self) -> None:
        """calculateRate accepts 'weight' parameter."""
        sig = inspect.signature(calculate_rate)
        param_names = list(sig.parameters.keys())
        assert "weight" in param_names

    def test_map_fed_ex_status_exists(self) -> None:
        """mapFedExStatus function exists and is callable."""
        assert callable(map_fed_ex_status)

    def test_map_fed_ex_status_is_async(self) -> None:
        """mapFedExStatus is an async function."""
        assert inspect.iscoroutinefunction(map_fed_ex_status)

    def test_map_fed_ex_status_parameter_count(self) -> None:
        """mapFedExStatus accepts 1 parameter(s)."""
        sig = inspect.signature(map_fed_ex_status)
        params = [p for p in sig.parameters.values() if p.name != "self"]
        # API functions may also receive injected dependencies (db, etc.)
        # so assert at least the declared parameter count.
        assert len(params) >= 1

    def test_map_fed_ex_status_has_event_type_param(self) -> None:
        """mapFedExStatus accepts 'event_type' parameter."""
        sig = inspect.signature(map_fed_ex_status)
        param_names = list(sig.parameters.keys())
        assert "event_type" in param_names
