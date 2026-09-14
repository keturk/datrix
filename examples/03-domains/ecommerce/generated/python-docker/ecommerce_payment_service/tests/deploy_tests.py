"""Deployment verification tests for ecommerce.PaymentService.

Auto-generated smoke tests that run against a live deployed endpoint.
Uses httpx async client for HTTP requests. Configure BASE_URL via environment variable.

Run with: BASE_URL=https://your-service.com pytest deploy_tests.py
"""


async def test_payment_api_get_payment(client):
    """GET /api/v1/payments/00000000-0000-0000-0000-000000000001 returns 404"""
    response = await client.get(
        "/api/v1/payments/00000000-0000-0000-0000-000000000001",
    )
    assert response.status_code == 404


async def test_payment_api_get_order_by_order_id(client):
    """GET /api/v1/payments/order/00000000-0000-0000-0000-000000000001 returns 404"""
    response = await client.get(
        "/api/v1/payments/order/00000000-0000-0000-0000-000000000001",
    )
    assert response.status_code == 404


async def test_payment_api_get_my_payments(client):
    """GET /api/v1/payments/my-payments returns 200"""
    response = await client.get(
        "/api/v1/payments/my-payments",
    )
    assert response.status_code == 200


async def test_payment_api_post_process(client):
    """POST /api/v1/payments/process returns 422"""
    response = await client.post(
        "/api/v1/payments/process",
        json={},
    )
    assert response.status_code == 422


async def test_payment_api_post_by_id_refund(client):
    """POST /api/v1/payments/00000000-0000-0000-0000-000000000001/refund returns 422"""
    response = await client.post(
        "/api/v1/payments/00000000-0000-0000-0000-000000000001/refund",
        json={},
    )
    assert response.status_code in (422, 403)


async def test_payment_api_post_webhook_stripe(client):
    """POST /api/v1/payments/webhook/stripe returns 422"""
    response = await client.post(
        "/api/v1/payments/webhook/stripe",
        json={},
    )
    assert response.status_code == 422


# --- Authentication / Authorization Tests ---


async def test_payment_api_get_payment_unauthenticated(unauth_client):
    """GET /api/v1/payments/00000000-0000-0000-0000-000000000001 without auth returns 401"""
    response = await unauth_client.get(
        "/api/v1/payments/00000000-0000-0000-0000-000000000001",
    )
    assert response.status_code == 401


async def test_payment_api_get_order_by_order_id_unauthenticated(unauth_client):
    """GET /api/v1/payments/order/00000000-0000-0000-0000-000000000001 without auth returns 401"""
    response = await unauth_client.get(
        "/api/v1/payments/order/00000000-0000-0000-0000-000000000001",
    )
    assert response.status_code == 401


async def test_payment_api_get_my_payments_unauthenticated(unauth_client):
    """GET /api/v1/payments/my-payments without auth returns 401"""
    response = await unauth_client.get(
        "/api/v1/payments/my-payments",
    )
    assert response.status_code == 401


async def test_payment_api_post_process_unauthenticated(unauth_client):
    """POST /api/v1/payments/process without auth returns 401"""
    response = await unauth_client.post(
        "/api/v1/payments/process",
        json={},
    )
    assert response.status_code == 401


async def test_payment_api_post_by_id_refund_unauthenticated(unauth_client):
    """POST /api/v1/payments/00000000-0000-0000-0000-000000000001/refund without auth returns 401"""
    response = await unauth_client.post(
        "/api/v1/payments/00000000-0000-0000-0000-000000000001/refund",
        json={},
    )
    assert response.status_code == 401


async def test_payment_api_post_by_id_refund_wrong_role(wrong_role_client):
    """POST /api/v1/payments/00000000-0000-0000-0000-000000000001/refund with wrong role returns 403"""
    response = await wrong_role_client.post(
        "/api/v1/payments/00000000-0000-0000-0000-000000000001/refund",
        json={},
    )
    assert response.status_code == 403
