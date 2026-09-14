"""API endpoint tests for ecommerce.OrderService.

Auto-generated test suite that drives the API in-process through httpx
ASGITransport against a real database session (or a deployed service when
BASE_URL is set). Because these tests require a real database, they are
marked ``integration`` and are excluded from the database-free unit run.
Run with: pytest test_api.py -m integration
"""

import pytest


@pytest.mark.integration
async def test_order_api_get_endpoint(client):
    """GET /api/v1/orders returns 200"""
    response = await client.get(
        "/api/v1/orders",
    )
    assert response.status_code == 200


@pytest.mark.integration
async def test_order_api_get_by_id(client):
    """GET /api/v1/orders/00000000-0000-0000-0000-000000000001 returns 404"""
    response = await client.get(
        "/api/v1/orders/00000000-0000-0000-0000-000000000001",
    )
    assert response.status_code == 404


@pytest.mark.integration
async def test_order_api_post_endpoint(client):
    """POST /api/v1/orders returns 422"""
    response = await client.post(
        "/api/v1/orders",
        json={},
    )
    assert response.status_code == 422


@pytest.mark.integration
async def test_order_api_put_by_id_cancel(client):
    """PUT /api/v1/orders/00000000-0000-0000-0000-000000000001/cancel returns 404"""
    response = await client.put(
        "/api/v1/orders/00000000-0000-0000-0000-000000000001/cancel",
        json={},
    )
    assert response.status_code == 404


# --- Authentication / Authorization Tests ---


@pytest.mark.integration
class TestOrderApiAuthAccess:
    """Test authentication and role-based access control for OrderApi."""

    async def test_order_api_get_endpoint_unauthenticated(self, unauth_client):
        """GET /api/v1/orders without auth returns 401"""
        response = await unauth_client.get(
            "/api/v1/orders",
        )
        assert response.status_code == 401

    async def test_order_api_get_by_id_unauthenticated(self, unauth_client):
        """GET /api/v1/orders/00000000-0000-0000-0000-000000000001 without auth returns 401"""
        response = await unauth_client.get(
            "/api/v1/orders/00000000-0000-0000-0000-000000000001",
        )
        assert response.status_code == 401

    async def test_order_api_post_endpoint_unauthenticated(self, unauth_client):
        """POST /api/v1/orders without auth returns 401"""
        response = await unauth_client.post(
            "/api/v1/orders",
            json={},
        )
        assert response.status_code == 401

    async def test_order_api_put_by_id_cancel_unauthenticated(self, unauth_client):
        """PUT /api/v1/orders/00000000-0000-0000-0000-000000000001/cancel without auth returns 401"""
        response = await unauth_client.put(
            "/api/v1/orders/00000000-0000-0000-0000-000000000001/cancel",
            json={},
        )
        assert response.status_code == 401

    async def test_order_api_get_service_by_id_unauthenticated(self, unauth_client):
        """GET /api/v1/orders/service/00000000-0000-0000-0000-000000000001 without auth returns 401"""
        response = await unauth_client.get(
            "/api/v1/orders/service/00000000-0000-0000-0000-000000000001",
        )
        assert response.status_code == 401

    async def test_order_api_post_by_id_confirm_payment_unauthenticated(
        self, unauth_client
    ):
        """POST /api/v1/orders/00000000-0000-0000-0000-000000000001/confirm-payment without auth returns 401"""
        response = await unauth_client.post(
            "/api/v1/orders/00000000-0000-0000-0000-000000000001/confirm-payment",
            json={},
        )
        assert response.status_code == 401

    async def test_order_api_post_by_id_update_shipment_unauthenticated(
        self, unauth_client
    ):
        """POST /api/v1/orders/00000000-0000-0000-0000-000000000001/update-shipment without auth returns 401"""
        response = await unauth_client.post(
            "/api/v1/orders/00000000-0000-0000-0000-000000000001/update-shipment",
            json={},
        )
        assert response.status_code == 401

    async def test_order_api_get_service_by_id_non_service_token(
        self, wrong_role_client
    ):
        """GET /api/v1/orders/service/00000000-0000-0000-0000-000000000001 with a non-service token returns 401"""
        response = await wrong_role_client.get(
            "/api/v1/orders/service/00000000-0000-0000-0000-000000000001",
        )
        assert response.status_code == 401

    async def test_order_api_post_by_id_confirm_payment_non_service_token(
        self, wrong_role_client
    ):
        """POST /api/v1/orders/00000000-0000-0000-0000-000000000001/confirm-payment with a non-service token returns 401"""
        response = await wrong_role_client.post(
            "/api/v1/orders/00000000-0000-0000-0000-000000000001/confirm-payment",
            json={},
        )
        assert response.status_code == 401

    async def test_order_api_post_by_id_update_shipment_non_service_token(
        self, wrong_role_client
    ):
        """POST /api/v1/orders/00000000-0000-0000-0000-000000000001/update-shipment with a non-service token returns 401"""
        response = await wrong_role_client.post(
            "/api/v1/orders/00000000-0000-0000-0000-000000000001/update-shipment",
            json={},
        )
        assert response.status_code == 401
