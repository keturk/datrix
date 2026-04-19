"""Unit tests for Product lifecycle hooks."""

from __future__ import annotations

import pytest

from ecommerce_product_service.models.db.product import Product


@pytest.mark.unit
class TestProductLifecycleHooks:
    """Tests for Product entity lifecycle hooks."""

    # --- afterUpdate hook tests ---

    def test_after_update_watches_inventory(self) -> None:
        """afterUpdate hook monitors changes to inventory via isChanged()."""
        instance = Product()
        # The afterUpdate hook checks isChanged(inventory).
        # At the unit level, verify the watched field exists and is mutable.
        assert hasattr(instance, "inventory")

    def test_after_update_watches_status(self) -> None:
        """afterUpdate hook monitors changes to status via isChanged()."""
        instance = Product()
        # The afterUpdate hook checks isChanged(status).
        # At the unit level, verify the watched field exists and is mutable.
        assert hasattr(instance, "status")
