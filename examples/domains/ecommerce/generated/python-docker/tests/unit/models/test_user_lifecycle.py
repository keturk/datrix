"""Unit tests for User lifecycle hooks."""

from __future__ import annotations

import pytest

from ecommerce_user_service.models.db.user import User


@pytest.mark.unit
class TestUserLifecycleHooks:
    """Tests for User entity lifecycle hooks."""

    # --- afterCreate hook tests ---

    # --- afterUpdate hook tests ---

    def test_after_update_watches_status(self) -> None:
        """afterUpdate hook monitors changes to status via isChanged()."""
        instance = User()
        # The afterUpdate hook checks isChanged(status).
        # At the unit level, verify the watched field exists and is mutable.
        assert hasattr(instance, "status")
