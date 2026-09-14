"""API endpoint tests for ecommerce.ShippingService.

Auto-generated test suite that drives the API in-process through httpx
ASGITransport against a real database session (or a deployed service when
BASE_URL is set). Because these tests require a real database, they are
marked ``integration`` and are excluded from the database-free unit run.
Run with: pytest test_api.py -m integration
"""

import pytest


@pytest.mark.integration
async def test_shipping_api_get_shipment(client):
    """GET /api/v1/shipments/00000000-0000-0000-0000-000000000001 returns 404"""
    response = await client.get(
        "/api/v1/shipments/00000000-0000-0000-0000-000000000001",
    )
    assert response.status_code == 404


@pytest.mark.integration
async def test_shipping_api_get_order_by_order_id(client):
    """GET /api/v1/shipments/order/00000000-0000-0000-0000-000000000001 returns 404"""
    response = await client.get(
        "/api/v1/shipments/order/00000000-0000-0000-0000-000000000001",
    )
    assert response.status_code == 404


@pytest.mark.integration
async def test_shipping_api_get_track_by_tracking_number(client):
    """GET /api/v1/shipments/track/00000000-0000-0000-0000-000000000001 returns 404"""
    response = await client.get(
        "/api/v1/shipments/track/00000000-0000-0000-0000-000000000001",
    )
    assert response.status_code == 404


@pytest.mark.integration
async def test_shipping_api_put_by_id_status(client):
    """PUT /api/v1/shipments/00000000-0000-0000-0000-000000000001/status returns 422"""
    response = await client.put(
        "/api/v1/shipments/00000000-0000-0000-0000-000000000001/status",
        json={},
    )
    assert response.status_code in (422, 403)


@pytest.mark.integration
async def test_shipping_api_post_by_id_events(client):
    """POST /api/v1/shipments/00000000-0000-0000-0000-000000000001/events returns 422"""
    response = await client.post(
        "/api/v1/shipments/00000000-0000-0000-0000-000000000001/events",
        json={},
    )
    assert response.status_code in (422, 403)


@pytest.mark.integration
async def test_shipping_api_post_rates(client):
    """POST /api/v1/shipments/rates returns 422"""
    response = await client.post(
        "/api/v1/shipments/rates",
        json={},
    )
    assert response.status_code == 422


@pytest.mark.integration
async def test_shipping_api_post_webhook_fedex(client):
    """POST /api/v1/shipments/webhook/fedex returns 422"""
    response = await client.post(
        "/api/v1/shipments/webhook/fedex",
        json={},
    )
    assert response.status_code == 422


# --- Authentication / Authorization Tests ---


@pytest.mark.integration
class TestShippingApiAuthAccess:
    """Test authentication and role-based access control for ShippingApi."""

    async def test_shipping_api_get_track_by_tracking_number_public_no_auth(
        self, client
    ):
        """Public GET /api/v1/shipments/track/00000000-0000-0000-0000-000000000001 without auth returns 404"""
        response = await client.get(
            "/api/v1/shipments/track/00000000-0000-0000-0000-000000000001",
        )
        assert response.status_code == 404

    async def test_shipping_api_post_rates_public_no_auth(self, client):
        """Public POST /api/v1/shipments/rates without auth returns 422"""
        response = await client.post(
            "/api/v1/shipments/rates",
            json={},
        )
        assert response.status_code == 422

    async def test_shipping_api_get_shipment_unauthenticated(self, unauth_client):
        """GET /api/v1/shipments/00000000-0000-0000-0000-000000000001 without auth returns 401"""
        response = await unauth_client.get(
            "/api/v1/shipments/00000000-0000-0000-0000-000000000001",
        )
        assert response.status_code == 401

    async def test_shipping_api_get_order_by_order_id_unauthenticated(
        self, unauth_client
    ):
        """GET /api/v1/shipments/order/00000000-0000-0000-0000-000000000001 without auth returns 401"""
        response = await unauth_client.get(
            "/api/v1/shipments/order/00000000-0000-0000-0000-000000000001",
        )
        assert response.status_code == 401

    async def test_shipping_api_post_endpoint_unauthenticated(self, unauth_client):
        """POST /api/v1/shipments without auth returns 401"""
        response = await unauth_client.post(
            "/api/v1/shipments",
            json={},
        )
        assert response.status_code == 401

    async def test_shipping_api_put_by_id_status_unauthenticated(self, unauth_client):
        """PUT /api/v1/shipments/00000000-0000-0000-0000-000000000001/status without auth returns 401"""
        response = await unauth_client.put(
            "/api/v1/shipments/00000000-0000-0000-0000-000000000001/status",
            json={},
        )
        assert response.status_code == 401

    async def test_shipping_api_post_by_id_events_unauthenticated(self, unauth_client):
        """POST /api/v1/shipments/00000000-0000-0000-0000-000000000001/events without auth returns 401"""
        response = await unauth_client.post(
            "/api/v1/shipments/00000000-0000-0000-0000-000000000001/events",
            json={},
        )
        assert response.status_code == 401

    async def test_shipping_api_put_by_id_status_wrong_role(self, wrong_role_client):
        """PUT /api/v1/shipments/00000000-0000-0000-0000-000000000001/status with wrong role returns 403"""
        response = await wrong_role_client.put(
            "/api/v1/shipments/00000000-0000-0000-0000-000000000001/status",
            json={},
        )
        assert response.status_code == 403

    async def test_shipping_api_post_by_id_events_wrong_role(self, wrong_role_client):
        """POST /api/v1/shipments/00000000-0000-0000-0000-000000000001/events with wrong role returns 403"""
        response = await wrong_role_client.post(
            "/api/v1/shipments/00000000-0000-0000-0000-000000000001/events",
            json={},
        )
        assert response.status_code == 403

    async def test_shipping_api_post_endpoint_non_service_token(
        self, wrong_role_client
    ):
        """POST /api/v1/shipments with a non-service token returns 401"""
        response = await wrong_role_client.post(
            "/api/v1/shipments",
            json={},
        )
        assert response.status_code == 401
