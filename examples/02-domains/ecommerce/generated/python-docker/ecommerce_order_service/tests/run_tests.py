"""API endpoint tests for ecommerce.OrderService (mocked dependencies).

Auto-generated test suite using FastAPI TestClient with dependency injection
overrides. Run with: pytest run_tests.py
"""

import uuid
from fastapi.testclient import TestClient

from ecommerce_order_service.main import create_app

client = TestClient(create_app())


def test_order_api_get():
    """GET /api/v1/orders/ returns 200"""
    response = client.get(
        "/api/v1/orders/",
        headers={"Authorization": "Bearer test-token"},
    )
    assert response.status_code == 200


def test_order_api_get():
    """GET /api/v1/orders/00000000-0000-0000-0000-000000000001 returns 200"""
    response = client.get(
        "/api/v1/orders/00000000-0000-0000-0000-000000000001",
        headers={"Authorization": "Bearer test-token"},
    )
    assert response.status_code == 200


def test_order_api_post():
    """POST /api/v1/orders/ returns 201"""
    response = client.post(
        "/api/v1/orders/",
        json={},
        headers={"Authorization": "Bearer test-token"},
    )
    assert response.status_code == 201


def test_order_api_put():
    """PUT /api/v1/orders/00000000-0000-0000-0000-000000000001/cancel returns 200"""
    response = client.put(
        "/api/v1/orders/00000000-0000-0000-0000-000000000001/cancel",
        json={},
        headers={"Authorization": "Bearer test-token"},
    )
    assert response.status_code == 200


def test_order_api_get():
    """GET /api/v1/orders/internal/00000000-0000-0000-0000-000000000001 returns 200"""
    response = client.get(
        "/api/v1/orders/internal/00000000-0000-0000-0000-000000000001",
    )
    assert response.status_code == 200


def test_order_api_post():
    """POST /api/v1/orders/00000000-0000-0000-0000-000000000001/confirm-payment returns 201"""
    response = client.post(
        "/api/v1/orders/00000000-0000-0000-0000-000000000001/confirm-payment",
        json={},
    )
    assert response.status_code == 201


def test_order_api_post():
    """POST /api/v1/orders/00000000-0000-0000-0000-000000000001/update-shipment returns 201"""
    response = client.post(
        "/api/v1/orders/00000000-0000-0000-0000-000000000001/update-shipment",
        json={},
    )
    assert response.status_code == 201


# --- Authentication / Authorization Tests ---


class TestOrderApiAuthAccess:
    """Test authentication and role-based access control for OrderApi."""

    def test_order_api_get_unauthenticated(self):
        """GET /api/v1/orders/ without auth returns 401"""
        response = client.get(
            "/api/v1/orders/",
        )
        assert response.status_code == 401

    def test_order_api_get_unauthenticated(self):
        """GET /api/v1/orders/00000000-0000-0000-0000-000000000001 without auth returns 401"""
        response = client.get(
            "/api/v1/orders/00000000-0000-0000-0000-000000000001",
        )
        assert response.status_code == 401

    def test_order_api_post_unauthenticated(self):
        """POST /api/v1/orders/ without auth returns 401"""
        response = client.post(
            "/api/v1/orders/",
            json={},
        )
        assert response.status_code == 401

    def test_order_api_put_unauthenticated(self):
        """PUT /api/v1/orders/00000000-0000-0000-0000-000000000001/cancel without auth returns 401"""
        response = client.put(
            "/api/v1/orders/00000000-0000-0000-0000-000000000001/cancel",
            json={},
        )
        assert response.status_code == 401
