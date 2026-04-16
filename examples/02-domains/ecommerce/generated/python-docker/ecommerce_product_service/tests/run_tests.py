"""API endpoint tests for ecommerce.ProductService (mocked dependencies).

Auto-generated test suite using FastAPI TestClient with dependency injection
overrides. Run with: pytest unit_tests.py
"""

import uuid
from fastapi.testclient import TestClient

from ecommerce_product_service.main import create_app

client = TestClient(create_app())


def test_product_api_list_products():
    """GET /api/v1/products/ returns 200"""
    response = client.get(
        "/api/v1/products/",
    )
    assert response.status_code == 200


def test_product_api_get_product():
    """GET /api/v1/products/00000000-0000-0000-0000-000000000001 returns 200"""
    response = client.get(
        "/api/v1/products/00000000-0000-0000-0000-000000000001",
    )
    assert response.status_code == 200


def test_product_api_create_product():
    """POST /api/v1/products/ returns 201"""
    response = client.post(
        "/api/v1/products/",
        json={},
        headers={"Authorization": "Bearer test-token"},
    )
    assert response.status_code == 201


def test_product_api_update_product():
    """PUT /api/v1/products/00000000-0000-0000-0000-000000000001 returns 200"""
    response = client.put(
        "/api/v1/products/00000000-0000-0000-0000-000000000001",
        json={},
        headers={"Authorization": "Bearer test-token"},
    )
    assert response.status_code == 200


def test_product_api_delete_product():
    """DELETE /api/v1/products/00000000-0000-0000-0000-000000000001 returns 204"""
    response = client.delete(
        "/api/v1/products/00000000-0000-0000-0000-000000000001",
        headers={"Authorization": "Bearer test-token"},
    )
    assert response.status_code == 204


def test_product_api_get():
    """GET /api/v1/products/slug/00000000-0000-0000-0000-000000000001 returns 200"""
    response = client.get(
        "/api/v1/products/slug/00000000-0000-0000-0000-000000000001",
    )
    assert response.status_code == 200


def test_product_api_get():
    """GET /api/v1/products/search returns 200"""
    response = client.get(
        "/api/v1/products/search",
    )
    assert response.status_code == 200


def test_product_api_get():
    """GET /api/v1/products/category/00000000-0000-0000-0000-000000000001 returns 200"""
    response = client.get(
        "/api/v1/products/category/00000000-0000-0000-0000-000000000001",
    )
    assert response.status_code == 200


def test_product_api_post():
    """POST /api/v1/products/ returns 201"""
    response = client.post(
        "/api/v1/products/",
        json={},
        headers={"Authorization": "Bearer test-token"},
    )
    assert response.status_code == 201


def test_product_api_put():
    """PUT /api/v1/products/00000000-0000-0000-0000-000000000001/inventory returns 200"""
    response = client.put(
        "/api/v1/products/00000000-0000-0000-0000-000000000001/inventory",
        json={},
        headers={"Authorization": "Bearer test-token"},
    )
    assert response.status_code == 200


def test_product_api_put():
    """PUT /api/v1/products/00000000-0000-0000-0000-000000000001/publish returns 200"""
    response = client.put(
        "/api/v1/products/00000000-0000-0000-0000-000000000001/publish",
        json={},
        headers={"Authorization": "Bearer test-token"},
    )
    assert response.status_code == 200


def test_product_api_post():
    """POST /api/v1/products/internal/check-availability returns 201"""
    response = client.post(
        "/api/v1/products/internal/check-availability",
        json={},
    )
    assert response.status_code == 201


def test_product_api_post():
    """POST /api/v1/products/internal/reserve-inventory returns 201"""
    response = client.post(
        "/api/v1/products/internal/reserve-inventory",
        json={},
    )
    assert response.status_code == 201


def test_product_api_post():
    """POST /api/v1/products/internal/confirm-reservation returns 201"""
    response = client.post(
        "/api/v1/products/internal/confirm-reservation",
        json={},
    )
    assert response.status_code == 201


def test_product_api_post():
    """POST /api/v1/products/internal/release-reservation returns 201"""
    response = client.post(
        "/api/v1/products/internal/release-reservation",
        json={},
    )
    assert response.status_code == 201


def test_product_api_get():
    """GET /api/v1/products/internal/00000000-0000-0000-0000-000000000001 returns 200"""
    response = client.get(
        "/api/v1/products/internal/00000000-0000-0000-0000-000000000001",
    )
    assert response.status_code == 200


def test_product_api_post():
    """POST /api/v1/products/internal/bulk returns 201"""
    response = client.post(
        "/api/v1/products/internal/bulk",
        json={},
    )
    assert response.status_code == 201


# --- Authentication / Authorization Tests ---


class TestProductApiAuthAccess:
    """Test authentication and role-based access control for ProductApi."""

    def test_product_api_list_products_public_no_auth(self):
        """Public GET /api/v1/products/ without auth returns 200"""
        response = client.get(
            "/api/v1/products/",
        )
        assert response.status_code == 200

    def test_product_api_get_product_public_no_auth(self):
        """Public GET /api/v1/products/00000000-0000-0000-0000-000000000001 without auth returns 200"""
        response = client.get(
            "/api/v1/products/00000000-0000-0000-0000-000000000001",
        )
        assert response.status_code == 200

    def test_product_api_get_public_no_auth(self):
        """Public GET /api/v1/products/slug/00000000-0000-0000-0000-000000000001 without auth returns 200"""
        response = client.get(
            "/api/v1/products/slug/00000000-0000-0000-0000-000000000001",
        )
        assert response.status_code == 200

    def test_product_api_get_public_no_auth(self):
        """Public GET /api/v1/products/search without auth returns 200"""
        response = client.get(
            "/api/v1/products/search",
        )
        assert response.status_code == 200

    def test_product_api_get_public_no_auth(self):
        """Public GET /api/v1/products/category/00000000-0000-0000-0000-000000000001 without auth returns 200"""
        response = client.get(
            "/api/v1/products/category/00000000-0000-0000-0000-000000000001",
        )
        assert response.status_code == 200

    def test_product_api_create_product_unauthenticated(self):
        """POST /api/v1/products/ without auth returns 401"""
        response = client.post(
            "/api/v1/products/",
            json={},
        )
        assert response.status_code == 401

    def test_product_api_update_product_unauthenticated(self):
        """PUT /api/v1/products/00000000-0000-0000-0000-000000000001 without auth returns 401"""
        response = client.put(
            "/api/v1/products/00000000-0000-0000-0000-000000000001",
            json={},
        )
        assert response.status_code == 401

    def test_product_api_delete_product_unauthenticated(self):
        """DELETE /api/v1/products/00000000-0000-0000-0000-000000000001 without auth returns 401"""
        response = client.delete(
            "/api/v1/products/00000000-0000-0000-0000-000000000001",
        )
        assert response.status_code == 401

    def test_product_api_post_unauthenticated(self):
        """POST /api/v1/products/ without auth returns 401"""
        response = client.post(
            "/api/v1/products/",
            json={},
        )
        assert response.status_code == 401

    def test_product_api_put_unauthenticated(self):
        """PUT /api/v1/products/00000000-0000-0000-0000-000000000001/inventory without auth returns 401"""
        response = client.put(
            "/api/v1/products/00000000-0000-0000-0000-000000000001/inventory",
            json={},
        )
        assert response.status_code == 401

    def test_product_api_put_unauthenticated(self):
        """PUT /api/v1/products/00000000-0000-0000-0000-000000000001/publish without auth returns 401"""
        response = client.put(
            "/api/v1/products/00000000-0000-0000-0000-000000000001/publish",
            json={},
        )
        assert response.status_code == 401

    def test_product_api_create_product_wrong_role(self):
        """POST /api/v1/products/ with wrong role returns 403"""
        response = client.post(
            "/api/v1/products/",
            json={},
            headers={"Authorization": "Bearer wrong-role-token"},
        )
        assert response.status_code == 403

    def test_product_api_update_product_wrong_role(self):
        """PUT /api/v1/products/00000000-0000-0000-0000-000000000001 with wrong role returns 403"""
        response = client.put(
            "/api/v1/products/00000000-0000-0000-0000-000000000001",
            json={},
            headers={"Authorization": "Bearer wrong-role-token"},
        )
        assert response.status_code == 403

    def test_product_api_delete_product_wrong_role(self):
        """DELETE /api/v1/products/00000000-0000-0000-0000-000000000001 with wrong role returns 403"""
        response = client.delete(
            "/api/v1/products/00000000-0000-0000-0000-000000000001",
            headers={"Authorization": "Bearer wrong-role-token"},
        )
        assert response.status_code == 403

    def test_product_api_post_wrong_role(self):
        """POST /api/v1/products/ with wrong role returns 403"""
        response = client.post(
            "/api/v1/products/",
            json={},
            headers={"Authorization": "Bearer wrong-role-token"},
        )
        assert response.status_code == 403

    def test_product_api_put_wrong_role(self):
        """PUT /api/v1/products/00000000-0000-0000-0000-000000000001/inventory with wrong role returns 403"""
        response = client.put(
            "/api/v1/products/00000000-0000-0000-0000-000000000001/inventory",
            json={},
            headers={"Authorization": "Bearer wrong-role-token"},
        )
        assert response.status_code == 403

    def test_product_api_put_wrong_role(self):
        """PUT /api/v1/products/00000000-0000-0000-0000-000000000001/publish with wrong role returns 403"""
        response = client.put(
            "/api/v1/products/00000000-0000-0000-0000-000000000001/publish",
            json={},
            headers={"Authorization": "Bearer wrong-role-token"},
        )
        assert response.status_code == 403
