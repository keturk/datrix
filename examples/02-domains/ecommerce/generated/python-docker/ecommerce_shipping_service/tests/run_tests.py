"""API endpoint tests for ecommerce.ShippingService (mocked dependencies).

Auto-generated test suite using FastAPI TestClient with dependency injection
overrides. Run with: pytest run_tests.py
"""

import uuid
from fastapi.testclient import TestClient

from ecommerce_shipping_service.main import create_app

client = TestClient(create_app())


def test_shipping_api_get_shipment():
    """GET /api/v1/shipments/00000000-0000-0000-0000-000000000001 returns 200"""
    response = client.get(
        "/api/v1/shipments/00000000-0000-0000-0000-000000000001",
        headers={"Authorization": "Bearer test-token"},
    )
    assert response.status_code == 200


def test_shipping_api_get():
    """GET /api/v1/shipments/order/00000000-0000-0000-0000-000000000001 returns 200"""
    response = client.get(
        "/api/v1/shipments/order/00000000-0000-0000-0000-000000000001",
        headers={"Authorization": "Bearer test-token"},
    )
    assert response.status_code == 200


def test_shipping_api_get():
    """GET /api/v1/shipments/track/00000000-0000-0000-0000-000000000001 returns 200"""
    response = client.get(
        "/api/v1/shipments/track/00000000-0000-0000-0000-000000000001",
    )
    assert response.status_code == 200


def test_shipping_api_post():
    """POST /api/v1/shipments/ returns 201"""
    response = client.post(
        "/api/v1/shipments/",
        json={},
    )
    assert response.status_code == 201


def test_shipping_api_put():
    """PUT /api/v1/shipments/00000000-0000-0000-0000-000000000001/status returns 200"""
    response = client.put(
        "/api/v1/shipments/00000000-0000-0000-0000-000000000001/status",
        json={},
        headers={"Authorization": "Bearer test-token"},
    )
    assert response.status_code == 200


def test_shipping_api_post():
    """POST /api/v1/shipments/00000000-0000-0000-0000-000000000001/events returns 201"""
    response = client.post(
        "/api/v1/shipments/00000000-0000-0000-0000-000000000001/events",
        json={},
        headers={"Authorization": "Bearer test-token"},
    )
    assert response.status_code == 201


def test_shipping_api_post():
    """POST /api/v1/shipments/rates returns 201"""
    response = client.post(
        "/api/v1/shipments/rates",
        json={},
    )
    assert response.status_code == 201


def test_shipping_api_post():
    """POST /api/v1/shipments/webhook/fedex returns 201"""
    response = client.post(
        "/api/v1/shipments/webhook/fedex",
        json={},
    )
    assert response.status_code == 201


# --- Authentication / Authorization Tests ---


class TestShippingApiAuthAccess:
    """Test authentication and role-based access control for ShippingApi."""

    def test_shipping_api_get_public_no_auth(self):
        """Public GET /api/v1/shipments/track/00000000-0000-0000-0000-000000000001 without auth returns 200"""
        response = client.get(
            "/api/v1/shipments/track/00000000-0000-0000-0000-000000000001",
        )
        assert response.status_code == 200

    def test_shipping_api_post_public_no_auth(self):
        """Public POST /api/v1/shipments/rates without auth returns 201"""
        response = client.post(
            "/api/v1/shipments/rates",
            json={},
        )
        assert response.status_code == 201

    def test_shipping_api_post_public_no_auth(self):
        """Public POST /api/v1/shipments/webhook/fedex without auth returns 201"""
        response = client.post(
            "/api/v1/shipments/webhook/fedex",
            json={},
        )
        assert response.status_code == 201

    def test_shipping_api_get_shipment_unauthenticated(self):
        """GET /api/v1/shipments/00000000-0000-0000-0000-000000000001 without auth returns 401"""
        response = client.get(
            "/api/v1/shipments/00000000-0000-0000-0000-000000000001",
        )
        assert response.status_code == 401

    def test_shipping_api_get_unauthenticated(self):
        """GET /api/v1/shipments/order/00000000-0000-0000-0000-000000000001 without auth returns 401"""
        response = client.get(
            "/api/v1/shipments/order/00000000-0000-0000-0000-000000000001",
        )
        assert response.status_code == 401

    def test_shipping_api_put_unauthenticated(self):
        """PUT /api/v1/shipments/00000000-0000-0000-0000-000000000001/status without auth returns 401"""
        response = client.put(
            "/api/v1/shipments/00000000-0000-0000-0000-000000000001/status",
            json={},
        )
        assert response.status_code == 401

    def test_shipping_api_post_unauthenticated(self):
        """POST /api/v1/shipments/00000000-0000-0000-0000-000000000001/events without auth returns 401"""
        response = client.post(
            "/api/v1/shipments/00000000-0000-0000-0000-000000000001/events",
            json={},
        )
        assert response.status_code == 401

    def test_shipping_api_put_wrong_role(self):
        """PUT /api/v1/shipments/00000000-0000-0000-0000-000000000001/status with wrong role returns 403"""
        response = client.put(
            "/api/v1/shipments/00000000-0000-0000-0000-000000000001/status",
            json={},
            headers={"Authorization": "Bearer wrong-role-token"},
        )
        assert response.status_code == 403

    def test_shipping_api_post_wrong_role(self):
        """POST /api/v1/shipments/00000000-0000-0000-0000-000000000001/events with wrong role returns 403"""
        response = client.post(
            "/api/v1/shipments/00000000-0000-0000-0000-000000000001/events",
            json={},
            headers={"Authorization": "Bearer wrong-role-token"},
        )
        assert response.status_code == 403
