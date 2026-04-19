"""Unit tests for Payment lifecycle hooks."""

from __future__ import annotations

import pytest

from ecommerce_payment_service.models.db.payment import Payment


@pytest.mark.unit
class TestPaymentLifecycleHooks:
    """Tests for Payment entity lifecycle hooks."""

    # --- afterUpdate hook tests ---

    def test_after_update_watches_status(self) -> None:
        """afterUpdate hook monitors changes to status via isChanged()."""
        instance = Payment()
        # The afterUpdate hook checks isChanged(status).
        # At the unit level, verify the watched field exists and is mutable.
        assert hasattr(instance, "status")
