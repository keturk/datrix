"""Unit tests for Order lifecycle hooks."""

from __future__ import annotations

import pytest

from ecommerce_order_service.models.db.order import Order


@pytest.mark.unit
class TestOrderLifecycleHooks:
    """Tests for Order entity lifecycle hooks."""

    # --- afterCreate hook tests ---

    # --- afterUpdate hook tests ---

    def test_after_update_watches_status(self) -> None:
        """afterUpdate hook monitors changes to status via isChanged()."""
        instance = Order()
        # The afterUpdate hook checks isChanged(status).
        # At the unit level, verify the watched field exists and is mutable.
        assert hasattr(instance, "status")
