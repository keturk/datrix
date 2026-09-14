"""API endpoint tests for ecommerce.PaymentService.

Auto-generated test suite that drives the API in-process through httpx
ASGITransport against a real database session (or a deployed service when
BASE_URL is set). Because these tests require a real database, they are
marked ``integration`` and are excluded from the database-free unit run.
Run with: pytest test_api.py -m integration
"""

import pytest


@pytest.mark.integration
async def test_payment_api_get_payment(client):
    """GET /api/v1/payments/00000000-0000-0000-0000-000000000001 returns 404"""
    response = await client.get(
        "/api/v1/payments/00000000-0000-0000-0000-000000000001",
    )
    assert response.status_code == 404


@pytest.mark.integration
async def test_payment_api_get_order_by_order_id(client):
    """GET /api/v1/payments/order/00000000-0000-0000-0000-000000000001 returns 404"""
    response = await client.get(
        "/api/v1/payments/order/00000000-0000-0000-0000-000000000001",
    )
    assert response.status_code == 404


@pytest.mark.integration
async def test_payment_api_get_my_payments(client):
    """GET /api/v1/payments/my-payments returns 200"""
    response = await client.get(
        "/api/v1/payments/my-payments",
    )
    assert response.status_code == 200


@pytest.mark.integration
async def test_payment_api_post_process(client):
    """POST /api/v1/payments/process returns 422"""
    response = await client.post(
        "/api/v1/payments/process",
        json={},
    )
    assert response.status_code == 422


@pytest.mark.integration
async def test_payment_api_post_by_id_refund(client):
    """POST /api/v1/payments/00000000-0000-0000-0000-000000000001/refund returns 422"""
    response = await client.post(
        "/api/v1/payments/00000000-0000-0000-0000-000000000001/refund",
        json={},
    )
    assert response.status_code in (422, 403)


@pytest.mark.integration
async def test_payment_api_post_webhook_stripe(client):
    """POST /api/v1/payments/webhook/stripe returns 422"""
    response = await client.post(
        "/api/v1/payments/webhook/stripe",
        json={},
    )
    assert response.status_code == 422


# --- Authentication / Authorization Tests ---


@pytest.mark.integration
class TestPaymentApiAuthAccess:
    """Test authentication and role-based access control for PaymentApi."""

    async def test_payment_api_get_payment_unauthenticated(self, unauth_client):
        """GET /api/v1/payments/00000000-0000-0000-0000-000000000001 without auth returns 401"""
        response = await unauth_client.get(
            "/api/v1/payments/00000000-0000-0000-0000-000000000001",
        )
        assert response.status_code == 401

    async def test_payment_api_get_order_by_order_id_unauthenticated(
        self, unauth_client
    ):
        """GET /api/v1/payments/order/00000000-0000-0000-0000-000000000001 without auth returns 401"""
        response = await unauth_client.get(
            "/api/v1/payments/order/00000000-0000-0000-0000-000000000001",
        )
        assert response.status_code == 401

    async def test_payment_api_get_my_payments_unauthenticated(self, unauth_client):
        """GET /api/v1/payments/my-payments without auth returns 401"""
        response = await unauth_client.get(
            "/api/v1/payments/my-payments",
        )
        assert response.status_code == 401

    async def test_payment_api_post_process_unauthenticated(self, unauth_client):
        """POST /api/v1/payments/process without auth returns 401"""
        response = await unauth_client.post(
            "/api/v1/payments/process",
            json={},
        )
        assert response.status_code == 401

    async def test_payment_api_post_by_id_refund_unauthenticated(self, unauth_client):
        """POST /api/v1/payments/00000000-0000-0000-0000-000000000001/refund without auth returns 401"""
        response = await unauth_client.post(
            "/api/v1/payments/00000000-0000-0000-0000-000000000001/refund",
            json={},
        )
        assert response.status_code == 401

    async def test_payment_api_post_by_id_refund_wrong_role(self, wrong_role_client):
        """POST /api/v1/payments/00000000-0000-0000-0000-000000000001/refund with wrong role returns 403"""
        response = await wrong_role_client.post(
            "/api/v1/payments/00000000-0000-0000-0000-000000000001/refund",
            json={},
        )
        assert response.status_code == 403
