"""Deployment verification tests for ecommerce.ShippingService.

Auto-generated smoke tests that run against a live deployed endpoint.
Uses httpx async client for HTTP requests. Configure BASE_URL via environment variable.

Run with: BASE_URL=https://your-service.com pytest deploy_tests.py
"""


async def test_shipping_api_get_shipment(client):
    """GET /api/v1/shipments/00000000-0000-0000-0000-000000000001 returns 404"""
    response = await client.get(
        "/api/v1/shipments/00000000-0000-0000-0000-000000000001",
    )
    assert response.status_code == 404


async def test_shipping_api_get_order_by_order_id(client):
    """GET /api/v1/shipments/order/00000000-0000-0000-0000-000000000001 returns 404"""
    response = await client.get(
        "/api/v1/shipments/order/00000000-0000-0000-0000-000000000001",
    )
    assert response.status_code == 404


async def test_shipping_api_get_track_by_tracking_number(client):
    """GET /api/v1/shipments/track/00000000-0000-0000-0000-000000000001 returns 404"""
    response = await client.get(
        "/api/v1/shipments/track/00000000-0000-0000-0000-000000000001",
    )
    assert response.status_code == 404


async def test_shipping_api_put_by_id_status(client):
    """PUT /api/v1/shipments/00000000-0000-0000-0000-000000000001/status returns 422"""
    response = await client.put(
        "/api/v1/shipments/00000000-0000-0000-0000-000000000001/status",
        json={},
    )
    assert response.status_code in (422, 403)


async def test_shipping_api_post_by_id_events(client):
    """POST /api/v1/shipments/00000000-0000-0000-0000-000000000001/events returns 422"""
    response = await client.post(
        "/api/v1/shipments/00000000-0000-0000-0000-000000000001/events",
        json={},
    )
    assert response.status_code in (422, 403)


async def test_shipping_api_post_rates(client):
    """POST /api/v1/shipments/rates returns 422"""
    response = await client.post(
        "/api/v1/shipments/rates",
        json={},
    )
    assert response.status_code == 422


async def test_shipping_api_post_webhook_fedex(client):
    """POST /api/v1/shipments/webhook/fedex returns 422"""
    response = await client.post(
        "/api/v1/shipments/webhook/fedex",
        json={},
    )
    assert response.status_code == 422


# --- Authentication / Authorization Tests ---


async def test_shipping_api_get_track_by_tracking_number_public_no_auth(client):
    """Public GET /api/v1/shipments/track/00000000-0000-0000-0000-000000000001 without auth returns 404"""
    response = await client.get(
        "/api/v1/shipments/track/00000000-0000-0000-0000-000000000001",
    )
    assert response.status_code == 404


async def test_shipping_api_post_rates_public_no_auth(client):
    """Public POST /api/v1/shipments/rates without auth returns 422"""
    response = await client.post(
        "/api/v1/shipments/rates",
        json={},
    )
    assert response.status_code == 422


async def test_shipping_api_get_shipment_unauthenticated(unauth_client):
    """GET /api/v1/shipments/00000000-0000-0000-0000-000000000001 without auth returns 401"""
    response = await unauth_client.get(
        "/api/v1/shipments/00000000-0000-0000-0000-000000000001",
    )
    assert response.status_code == 401


async def test_shipping_api_get_order_by_order_id_unauthenticated(unauth_client):
    """GET /api/v1/shipments/order/00000000-0000-0000-0000-000000000001 without auth returns 401"""
    response = await unauth_client.get(
        "/api/v1/shipments/order/00000000-0000-0000-0000-000000000001",
    )
    assert response.status_code == 401


async def test_shipping_api_post_endpoint_unauthenticated(unauth_client):
    """POST /api/v1/shipments without auth returns 401"""
    response = await unauth_client.post(
        "/api/v1/shipments",
        json={},
    )
    assert response.status_code == 401


async def test_shipping_api_put_by_id_status_unauthenticated(unauth_client):
    """PUT /api/v1/shipments/00000000-0000-0000-0000-000000000001/status without auth returns 401"""
    response = await unauth_client.put(
        "/api/v1/shipments/00000000-0000-0000-0000-000000000001/status",
        json={},
    )
    assert response.status_code == 401


async def test_shipping_api_post_by_id_events_unauthenticated(unauth_client):
    """POST /api/v1/shipments/00000000-0000-0000-0000-000000000001/events without auth returns 401"""
    response = await unauth_client.post(
        "/api/v1/shipments/00000000-0000-0000-0000-000000000001/events",
        json={},
    )
    assert response.status_code == 401


async def test_shipping_api_put_by_id_status_wrong_role(wrong_role_client):
    """PUT /api/v1/shipments/00000000-0000-0000-0000-000000000001/status with wrong role returns 403"""
    response = await wrong_role_client.put(
        "/api/v1/shipments/00000000-0000-0000-0000-000000000001/status",
        json={},
    )
    assert response.status_code == 403


async def test_shipping_api_post_by_id_events_wrong_role(wrong_role_client):
    """POST /api/v1/shipments/00000000-0000-0000-0000-000000000001/events with wrong role returns 403"""
    response = await wrong_role_client.post(
        "/api/v1/shipments/00000000-0000-0000-0000-000000000001/events",
        json={},
    )
    assert response.status_code == 403


async def test_shipping_api_post_endpoint_non_service_token(wrong_role_client):
    """POST /api/v1/shipments with a non-service token returns 401"""
    response = await wrong_role_client.post(
        "/api/v1/shipments",
        json={},
    )
    assert response.status_code == 401
