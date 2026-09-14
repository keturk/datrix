"""API endpoint tests for ecommerce.ProductService.

Auto-generated test suite that drives the API in-process through httpx
ASGITransport against a real database session (or a deployed service when
BASE_URL is set). Because these tests require a real database, they are
marked ``integration`` and are excluded from the database-free unit run.
Run with: pytest test_api.py -m integration
"""

import pytest


@pytest.mark.integration
async def test_product_api_list_products(client):
    """GET /api/v1/products returns 200"""
    response = await client.get(
        "/api/v1/products",
    )
    assert response.status_code == 200


@pytest.mark.integration
async def test_product_api_get_product(client):
    """GET /api/v1/products/00000000-0000-0000-0000-000000000001 returns 404"""
    response = await client.get(
        "/api/v1/products/00000000-0000-0000-0000-000000000001",
    )
    assert response.status_code == 404


@pytest.mark.integration
async def test_product_api_update_product(client):
    """PUT /api/v1/products/00000000-0000-0000-0000-000000000001 returns 404"""
    response = await client.put(
        "/api/v1/products/00000000-0000-0000-0000-000000000001",
        json={},
    )
    assert response.status_code == 404


@pytest.mark.integration
async def test_product_api_delete_product(client):
    """DELETE /api/v1/products/00000000-0000-0000-0000-000000000001 returns 404"""
    response = await client.delete(
        "/api/v1/products/00000000-0000-0000-0000-000000000001",
    )
    assert response.status_code == 404


@pytest.mark.integration
async def test_product_api_get_slug_by_slug(client):
    """GET /api/v1/products/slug/00000000-0000-0000-0000-000000000001 returns 404"""
    response = await client.get(
        "/api/v1/products/slug/00000000-0000-0000-0000-000000000001",
    )
    assert response.status_code == 404


@pytest.mark.integration
async def test_product_api_get_search(client):
    """GET /api/v1/products/search returns 422"""
    response = await client.get(
        "/api/v1/products/search",
    )
    assert response.status_code == 422


@pytest.mark.integration
async def test_product_api_get_category_by_category_id(client):
    """GET /api/v1/products/category/00000000-0000-0000-0000-000000000001 returns 200"""
    response = await client.get(
        "/api/v1/products/category/00000000-0000-0000-0000-000000000001",
    )
    assert response.status_code == 200


@pytest.mark.integration
async def test_product_api_post_endpoint(client):
    """POST /api/v1/products returns 422"""
    response = await client.post(
        "/api/v1/products",
        json={},
    )
    assert response.status_code in (422, 403)


@pytest.mark.integration
async def test_product_api_put_by_id_inventory(client):
    """PUT /api/v1/products/00000000-0000-0000-0000-000000000001/inventory returns 422"""
    response = await client.put(
        "/api/v1/products/00000000-0000-0000-0000-000000000001/inventory",
        json={},
    )
    assert response.status_code in (422, 403)


@pytest.mark.integration
async def test_product_api_put_by_id_publish(client):
    """PUT /api/v1/products/00000000-0000-0000-0000-000000000001/publish returns 404"""
    response = await client.put(
        "/api/v1/products/00000000-0000-0000-0000-000000000001/publish",
        json={},
    )
    assert response.status_code == 404


# --- Authentication / Authorization Tests ---


@pytest.mark.integration
class TestProductApiAuthAccess:
    """Test authentication and role-based access control for ProductApi."""

    async def test_product_api_list_products_public_no_auth(self, client):
        """Public GET /api/v1/products without auth returns 200"""
        response = await client.get(
            "/api/v1/products",
        )
        assert response.status_code == 200

    async def test_product_api_get_product_public_no_auth(self, client):
        """Public GET /api/v1/products/00000000-0000-0000-0000-000000000001 without auth returns 404"""
        response = await client.get(
            "/api/v1/products/00000000-0000-0000-0000-000000000001",
        )
        assert response.status_code == 404

    async def test_product_api_get_slug_by_slug_public_no_auth(self, client):
        """Public GET /api/v1/products/slug/00000000-0000-0000-0000-000000000001 without auth returns 404"""
        response = await client.get(
            "/api/v1/products/slug/00000000-0000-0000-0000-000000000001",
        )
        assert response.status_code == 404

    async def test_product_api_get_search_public_no_auth(self, client):
        """Public GET /api/v1/products/search without auth returns 422"""
        response = await client.get(
            "/api/v1/products/search",
        )
        assert response.status_code == 422

    async def test_product_api_get_category_by_category_id_public_no_auth(self, client):
        """Public GET /api/v1/products/category/00000000-0000-0000-0000-000000000001 without auth returns 200"""
        response = await client.get(
            "/api/v1/products/category/00000000-0000-0000-0000-000000000001",
        )
        assert response.status_code == 200

    async def test_product_api_update_product_unauthenticated(self, unauth_client):
        """PUT /api/v1/products/00000000-0000-0000-0000-000000000001 without auth returns 401"""
        response = await unauth_client.put(
            "/api/v1/products/00000000-0000-0000-0000-000000000001",
            json={},
        )
        assert response.status_code == 401

    async def test_product_api_delete_product_unauthenticated(self, unauth_client):
        """DELETE /api/v1/products/00000000-0000-0000-0000-000000000001 without auth returns 401"""
        response = await unauth_client.delete(
            "/api/v1/products/00000000-0000-0000-0000-000000000001",
        )
        assert response.status_code == 401

    async def test_product_api_post_endpoint_unauthenticated(self, unauth_client):
        """POST /api/v1/products without auth returns 401"""
        response = await unauth_client.post(
            "/api/v1/products",
            json={},
        )
        assert response.status_code == 401

    async def test_product_api_put_by_id_inventory_unauthenticated(self, unauth_client):
        """PUT /api/v1/products/00000000-0000-0000-0000-000000000001/inventory without auth returns 401"""
        response = await unauth_client.put(
            "/api/v1/products/00000000-0000-0000-0000-000000000001/inventory",
            json={},
        )
        assert response.status_code == 401

    async def test_product_api_put_by_id_publish_unauthenticated(self, unauth_client):
        """PUT /api/v1/products/00000000-0000-0000-0000-000000000001/publish without auth returns 401"""
        response = await unauth_client.put(
            "/api/v1/products/00000000-0000-0000-0000-000000000001/publish",
            json={},
        )
        assert response.status_code == 401

    async def test_product_api_post_service_check_availability_unauthenticated(
        self, unauth_client
    ):
        """POST /api/v1/products/service/check-availability without auth returns 401"""
        response = await unauth_client.post(
            "/api/v1/products/service/check-availability",
            json={},
        )
        assert response.status_code == 401

    async def test_product_api_post_service_reserve_inventory_unauthenticated(
        self, unauth_client
    ):
        """POST /api/v1/products/service/reserve-inventory without auth returns 401"""
        response = await unauth_client.post(
            "/api/v1/products/service/reserve-inventory",
            json={},
        )
        assert response.status_code == 401

    async def test_product_api_post_service_confirm_reservation_unauthenticated(
        self, unauth_client
    ):
        """POST /api/v1/products/service/confirm-reservation without auth returns 401"""
        response = await unauth_client.post(
            "/api/v1/products/service/confirm-reservation",
            json={},
        )
        assert response.status_code == 401

    async def test_product_api_post_service_release_reservation_unauthenticated(
        self, unauth_client
    ):
        """POST /api/v1/products/service/release-reservation without auth returns 401"""
        response = await unauth_client.post(
            "/api/v1/products/service/release-reservation",
            json={},
        )
        assert response.status_code == 401

    async def test_product_api_get_service_by_id_unauthenticated(self, unauth_client):
        """GET /api/v1/products/service/00000000-0000-0000-0000-000000000001 without auth returns 401"""
        response = await unauth_client.get(
            "/api/v1/products/service/00000000-0000-0000-0000-000000000001",
        )
        assert response.status_code == 401

    async def test_product_api_post_service_bulk_unauthenticated(self, unauth_client):
        """POST /api/v1/products/service/bulk without auth returns 401"""
        response = await unauth_client.post(
            "/api/v1/products/service/bulk",
            json={},
        )
        assert response.status_code == 401

    async def test_product_api_update_product_wrong_role(self, wrong_role_client):
        """PUT /api/v1/products/00000000-0000-0000-0000-000000000001 with wrong role returns 403"""
        response = await wrong_role_client.put(
            "/api/v1/products/00000000-0000-0000-0000-000000000001",
            json={},
        )
        assert response.status_code == 403

    async def test_product_api_delete_product_wrong_role(self, wrong_role_client):
        """DELETE /api/v1/products/00000000-0000-0000-0000-000000000001 with wrong role returns 403"""
        response = await wrong_role_client.delete(
            "/api/v1/products/00000000-0000-0000-0000-000000000001",
        )
        assert response.status_code == 403

    async def test_product_api_post_endpoint_wrong_role(self, wrong_role_client):
        """POST /api/v1/products with wrong role returns 403"""
        response = await wrong_role_client.post(
            "/api/v1/products",
            json={},
        )
        assert response.status_code == 403

    async def test_product_api_put_by_id_inventory_wrong_role(self, wrong_role_client):
        """PUT /api/v1/products/00000000-0000-0000-0000-000000000001/inventory with wrong role returns 403"""
        response = await wrong_role_client.put(
            "/api/v1/products/00000000-0000-0000-0000-000000000001/inventory",
            json={},
        )
        assert response.status_code == 403

    async def test_product_api_put_by_id_publish_wrong_role(self, wrong_role_client):
        """PUT /api/v1/products/00000000-0000-0000-0000-000000000001/publish with wrong role returns 403"""
        response = await wrong_role_client.put(
            "/api/v1/products/00000000-0000-0000-0000-000000000001/publish",
            json={},
        )
        assert response.status_code == 403

    async def test_product_api_post_service_check_availability_non_service_token(
        self, wrong_role_client
    ):
        """POST /api/v1/products/service/check-availability with a non-service token returns 401"""
        response = await wrong_role_client.post(
            "/api/v1/products/service/check-availability",
            json={},
        )
        assert response.status_code == 401

    async def test_product_api_post_service_reserve_inventory_non_service_token(
        self, wrong_role_client
    ):
        """POST /api/v1/products/service/reserve-inventory with a non-service token returns 401"""
        response = await wrong_role_client.post(
            "/api/v1/products/service/reserve-inventory",
            json={},
        )
        assert response.status_code == 401

    async def test_product_api_post_service_confirm_reservation_non_service_token(
        self, wrong_role_client
    ):
        """POST /api/v1/products/service/confirm-reservation with a non-service token returns 401"""
        response = await wrong_role_client.post(
            "/api/v1/products/service/confirm-reservation",
            json={},
        )
        assert response.status_code == 401

    async def test_product_api_post_service_release_reservation_non_service_token(
        self, wrong_role_client
    ):
        """POST /api/v1/products/service/release-reservation with a non-service token returns 401"""
        response = await wrong_role_client.post(
            "/api/v1/products/service/release-reservation",
            json={},
        )
        assert response.status_code == 401

    async def test_product_api_get_service_by_id_non_service_token(
        self, wrong_role_client
    ):
        """GET /api/v1/products/service/00000000-0000-0000-0000-000000000001 with a non-service token returns 401"""
        response = await wrong_role_client.get(
            "/api/v1/products/service/00000000-0000-0000-0000-000000000001",
        )
        assert response.status_code == 401

    async def test_product_api_post_service_bulk_non_service_token(
        self, wrong_role_client
    ):
        """POST /api/v1/products/service/bulk with a non-service token returns 401"""
        response = await wrong_role_client.post(
            "/api/v1/products/service/bulk",
            json={},
        )
        assert response.status_code == 401
