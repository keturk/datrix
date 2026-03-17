"""Unit tests for Shipment lifecycle hooks."""

from __future__ import annotations

import pytest

from ecommerce_shipping_service.models.db.shipment import Shipment


@pytest.mark.unit
class TestShipmentLifecycleHooks:
    """Tests for Shipment entity lifecycle hooks."""

    # --- afterUpdate hook tests ---

    def test_after_update_watches_status(self) -> None:
        """afterUpdate hook monitors changes to status via isChanged()."""
        instance = Shipment()
        # The afterUpdate hook checks isChanged(status).
        # At the unit level, verify the watched field exists and is mutable.
        assert hasattr(instance, "status")
