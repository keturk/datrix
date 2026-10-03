"""API endpoint tests for ecommerce.NotificationService.

Auto-generated test suite that drives the API in-process through httpx
ASGITransport against a real database session (or a deployed service when
BASE_URL is set). Because these tests require a real database, they are
marked ``integration`` and are excluded from the database-free unit run.
Run with: pytest test_api.py -m integration
"""

import pytest


@pytest.mark.integration
async def test_push_device_api_post_devices(client):
    """POST /push/devices returns 422"""
    response = await client.post(
        "/push/devices",
        json={},
    )
    assert response.status_code == 422


@pytest.mark.integration
async def test_push_device_api_post_devices_unregister(client):
    """POST /push/devices/unregister returns 422"""
    response = await client.post(
        "/push/devices/unregister",
        json={},
    )
    assert response.status_code == 422


# --- Authentication / Authorization Tests ---


@pytest.mark.integration
class TestPushDeviceApiAuthAccess:
    """Test authentication and role-based access control for PushDeviceApi."""

    async def test_push_device_api_post_devices_unauthenticated(self, unauth_client):
        """POST /push/devices without auth returns 401"""
        response = await unauth_client.post(
            "/push/devices",
            json={},
        )
        assert response.status_code == 401

    async def test_push_device_api_post_devices_unregister_unauthenticated(
        self, unauth_client
    ):
        """POST /push/devices/unregister without auth returns 401"""
        response = await unauth_client.post(
            "/push/devices/unregister",
            json={},
        )
        assert response.status_code == 401
