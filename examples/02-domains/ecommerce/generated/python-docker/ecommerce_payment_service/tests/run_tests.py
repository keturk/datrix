"""API endpoint tests for ecommerce.PaymentService (mocked dependencies).

Auto-generated test suite using FastAPI TestClient with dependency injection
overrides. Run with: pytest run_tests.py
"""

import uuid
from fastapi.testclient import TestClient

from ecommerce_payment_service.main import create_app

client = TestClient(create_app())


def test_payment_api_get_payment():
    """GET /api/v1/payments/00000000-0000-0000-0000-000000000001 returns 200"""
    response = client.get(
        "/api/v1/payments/00000000-0000-0000-0000-000000000001",
        headers={"Authorization": "Bearer test-token"},
    )
    assert response.status_code == 200


def test_payment_api_get():
    """GET /api/v1/payments/order/00000000-0000-0000-0000-000000000001 returns 200"""
    response = client.get(
        "/api/v1/payments/order/00000000-0000-0000-0000-000000000001",
        headers={"Authorization": "Bearer test-token"},
    )
    assert response.status_code == 200


def test_payment_api_get():
    """GET /api/v1/payments/my-payments returns 200"""
    response = client.get(
        "/api/v1/payments/my-payments",
        headers={"Authorization": "Bearer test-token"},
    )
    assert response.status_code == 200


def test_payment_api_post():
    """POST /api/v1/payments/process returns 201"""
    response = client.post(
        "/api/v1/payments/process",
        json={},
        headers={"Authorization": "Bearer test-token"},
    )
    assert response.status_code == 201


def test_payment_api_post():
    """POST /api/v1/payments/00000000-0000-0000-0000-000000000001/refund returns 201"""
    response = client.post(
        "/api/v1/payments/00000000-0000-0000-0000-000000000001/refund",
        json={},
        headers={"Authorization": "Bearer test-token"},
    )
    assert response.status_code == 201


def test_payment_api_post():
    """POST /api/v1/payments/webhook/stripe returns 201"""
    response = client.post(
        "/api/v1/payments/webhook/stripe",
        json={},
    )
    assert response.status_code == 201


# --- Authentication / Authorization Tests ---


class TestPaymentApiAuthAccess:
    """Test authentication and role-based access control for PaymentApi."""

    def test_payment_api_post_public_no_auth(self):
        """Public POST /api/v1/payments/webhook/stripe without auth returns 201"""
        response = client.post(
            "/api/v1/payments/webhook/stripe",
            json={},
        )
        assert response.status_code == 201

    def test_payment_api_get_payment_unauthenticated(self):
        """GET /api/v1/payments/00000000-0000-0000-0000-000000000001 without auth returns 401"""
        response = client.get(
            "/api/v1/payments/00000000-0000-0000-0000-000000000001",
        )
        assert response.status_code == 401

    def test_payment_api_get_unauthenticated(self):
        """GET /api/v1/payments/order/00000000-0000-0000-0000-000000000001 without auth returns 401"""
        response = client.get(
            "/api/v1/payments/order/00000000-0000-0000-0000-000000000001",
        )
        assert response.status_code == 401

    def test_payment_api_get_unauthenticated(self):
        """GET /api/v1/payments/my-payments without auth returns 401"""
        response = client.get(
            "/api/v1/payments/my-payments",
        )
        assert response.status_code == 401

    def test_payment_api_post_unauthenticated(self):
        """POST /api/v1/payments/process without auth returns 401"""
        response = client.post(
            "/api/v1/payments/process",
            json={},
        )
        assert response.status_code == 401

    def test_payment_api_post_unauthenticated(self):
        """POST /api/v1/payments/00000000-0000-0000-0000-000000000001/refund without auth returns 401"""
        response = client.post(
            "/api/v1/payments/00000000-0000-0000-0000-000000000001/refund",
            json={},
        )
        assert response.status_code == 401

    def test_payment_api_post_wrong_role(self):
        """POST /api/v1/payments/00000000-0000-0000-0000-000000000001/refund with wrong role returns 403"""
        response = client.post(
            "/api/v1/payments/00000000-0000-0000-0000-000000000001/refund",
            json={},
            headers={"Authorization": "Bearer wrong-role-token"},
        )
        assert response.status_code == 403
