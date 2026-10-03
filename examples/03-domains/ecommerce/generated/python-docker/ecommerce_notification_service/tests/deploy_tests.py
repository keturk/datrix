"""Deployment verification tests for ecommerce.NotificationService.

Auto-generated smoke tests that run against a live deployed endpoint.
Uses httpx async client for HTTP requests. Configure BASE_URL via environment variable.

Run with: BASE_URL=https://your-service.com pytest deploy_tests.py
"""


async def test_push_device_api_post_devices(client):
    """POST /push/devices returns 422"""
    response = await client.post(
        "/push/devices",
        json={},
    )
    assert response.status_code == 422


async def test_push_device_api_post_devices_unregister(client):
    """POST /push/devices/unregister returns 422"""
    response = await client.post(
        "/push/devices/unregister",
        json={},
    )
    assert response.status_code == 422


# --- Authentication / Authorization Tests ---


async def test_push_device_api_post_devices_unauthenticated(unauth_client):
    """POST /push/devices without auth returns 401"""
    response = await unauth_client.post(
        "/push/devices",
        json={},
    )
    assert response.status_code == 401


async def test_push_device_api_post_devices_unregister_unauthenticated(unauth_client):
    """POST /push/devices/unregister without auth returns 401"""
    response = await unauth_client.post(
        "/push/devices/unregister",
        json={},
    )
    assert response.status_code == 401
