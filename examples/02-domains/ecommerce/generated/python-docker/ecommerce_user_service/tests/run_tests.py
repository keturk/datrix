"""API endpoint tests for ecommerce.UserService (mocked dependencies).

Auto-generated test suite using FastAPI TestClient with dependency injection
overrides. Run with: pytest run_tests.py
"""

from fastapi.testclient import TestClient

from ecommerce_user_service.main import create_app

client = TestClient(create_app())


def test_user_api_list_users():
    """GET /api/v1/users returns 200"""
    response = client.get(
        "/api/v1/users",
        headers={"Authorization": "Bearer test-token"},
    )
    assert response.status_code == 200


def test_user_api_get_user():
    """GET /api/v1/users/00000000-0000-0000-0000-000000000001 returns 200"""
    response = client.get(
        "/api/v1/users/00000000-0000-0000-0000-000000000001",
        headers={"Authorization": "Bearer test-token"},
    )
    assert response.status_code == 200


def test_user_api_create_user():
    """POST /api/v1/users returns 201"""
    response = client.post(
        "/api/v1/users",
        json={},
        headers={"Authorization": "Bearer test-token"},
    )
    assert response.status_code == 201


def test_user_api_update_user():
    """PUT /api/v1/users/00000000-0000-0000-0000-000000000001 returns 200"""
    response = client.put(
        "/api/v1/users/00000000-0000-0000-0000-000000000001",
        json={},
        headers={"Authorization": "Bearer test-token"},
    )
    assert response.status_code == 200


def test_user_api_delete_user():
    """DELETE /api/v1/users/00000000-0000-0000-0000-000000000001 returns 204"""
    response = client.delete(
        "/api/v1/users/00000000-0000-0000-0000-000000000001",
        headers={"Authorization": "Bearer test-token"},
    )
    assert response.status_code == 204


def test_user_api_post():
    """POST /api/v1/register returns 201"""
    response = client.post(
        "/api/v1/register",
        json={},
    )
    assert response.status_code == 201


def test_user_api_post():
    """POST /api/v1/login returns 201"""
    response = client.post(
        "/api/v1/login",
        json={},
    )
    assert response.status_code == 201


def test_user_api_post():
    """POST /api/v1/logout returns 201"""
    response = client.post(
        "/api/v1/logout",
        json={},
        headers={"Authorization": "Bearer test-token"},
    )
    assert response.status_code == 201


def test_user_api_get():
    """GET /api/v1/me returns 200"""
    response = client.get(
        "/api/v1/me",
        headers={"Authorization": "Bearer test-token"},
    )
    assert response.status_code == 200


def test_user_api_put():
    """PUT /api/v1/me returns 200"""
    response = client.put(
        "/api/v1/me",
        json={},
        headers={"Authorization": "Bearer test-token"},
    )
    assert response.status_code == 200


def test_user_api_put():
    """PUT /api/v1/me/password returns 200"""
    response = client.put(
        "/api/v1/me/password",
        json={},
        headers={"Authorization": "Bearer test-token"},
    )
    assert response.status_code == 200


def test_user_api_post():
    """POST /api/v1/verify-email returns 201"""
    response = client.post(
        "/api/v1/verify-email",
        json={},
    )
    assert response.status_code == 201


def test_user_api_post():
    """POST /api/v1/forgot-password returns 201"""
    response = client.post(
        "/api/v1/forgot-password",
        json={},
    )
    assert response.status_code == 201


def test_user_api_post():
    """POST /api/v1/reset-password returns 201"""
    response = client.post(
        "/api/v1/reset-password",
        json={},
    )
    assert response.status_code == 201


def test_user_api_put():
    """PUT /api/v1/00000000-0000-0000-0000-000000000001/status returns 200"""
    response = client.put(
        "/api/v1/00000000-0000-0000-0000-000000000001/status",
        json={},
        headers={"Authorization": "Bearer test-token"},
    )
    assert response.status_code == 200


def test_user_api_get():
    """GET /api/v1/internal/00000000-0000-0000-0000-000000000001 returns 200"""
    response = client.get(
        "/api/v1/internal/00000000-0000-0000-0000-000000000001",
    )
    assert response.status_code == 200


def test_user_api_post():
    """POST /api/v1/internal/validate-session returns 201"""
    response = client.post(
        "/api/v1/internal/validate-session",
        json={},
    )
    assert response.status_code == 201


# --- Authentication / Authorization Tests ---


class TestUserApiAuthAccess:
    """Test authentication and role-based access control for UserApi."""

    def test_user_api_post_public_no_auth(self):
        """Public POST /api/v1/register without auth returns 201"""
        response = client.post(
            "/api/v1/register",
            json={},
        )
        assert response.status_code == 201

    def test_user_api_post_public_no_auth(self):
        """Public POST /api/v1/login without auth returns 201"""
        response = client.post(
            "/api/v1/login",
            json={},
        )
        assert response.status_code == 201

    def test_user_api_post_public_no_auth(self):
        """Public POST /api/v1/verify-email without auth returns 201"""
        response = client.post(
            "/api/v1/verify-email",
            json={},
        )
        assert response.status_code == 201

    def test_user_api_post_public_no_auth(self):
        """Public POST /api/v1/forgot-password without auth returns 201"""
        response = client.post(
            "/api/v1/forgot-password",
            json={},
        )
        assert response.status_code == 201

    def test_user_api_post_public_no_auth(self):
        """Public POST /api/v1/reset-password without auth returns 201"""
        response = client.post(
            "/api/v1/reset-password",
            json={},
        )
        assert response.status_code == 201

    def test_user_api_list_users_unauthenticated(self):
        """GET /api/v1/users without auth returns 401"""
        response = client.get(
            "/api/v1/users",
        )
        assert response.status_code == 401

    def test_user_api_get_user_unauthenticated(self):
        """GET /api/v1/users/00000000-0000-0000-0000-000000000001 without auth returns 401"""
        response = client.get(
            "/api/v1/users/00000000-0000-0000-0000-000000000001",
        )
        assert response.status_code == 401

    def test_user_api_create_user_unauthenticated(self):
        """POST /api/v1/users without auth returns 401"""
        response = client.post(
            "/api/v1/users",
            json={},
        )
        assert response.status_code == 401

    def test_user_api_update_user_unauthenticated(self):
        """PUT /api/v1/users/00000000-0000-0000-0000-000000000001 without auth returns 401"""
        response = client.put(
            "/api/v1/users/00000000-0000-0000-0000-000000000001",
            json={},
        )
        assert response.status_code == 401

    def test_user_api_delete_user_unauthenticated(self):
        """DELETE /api/v1/users/00000000-0000-0000-0000-000000000001 without auth returns 401"""
        response = client.delete(
            "/api/v1/users/00000000-0000-0000-0000-000000000001",
        )
        assert response.status_code == 401

    def test_user_api_post_unauthenticated(self):
        """POST /api/v1/logout without auth returns 401"""
        response = client.post(
            "/api/v1/logout",
            json={},
        )
        assert response.status_code == 401

    def test_user_api_get_unauthenticated(self):
        """GET /api/v1/me without auth returns 401"""
        response = client.get(
            "/api/v1/me",
        )
        assert response.status_code == 401

    def test_user_api_put_unauthenticated(self):
        """PUT /api/v1/me without auth returns 401"""
        response = client.put(
            "/api/v1/me",
            json={},
        )
        assert response.status_code == 401

    def test_user_api_put_unauthenticated(self):
        """PUT /api/v1/me/password without auth returns 401"""
        response = client.put(
            "/api/v1/me/password",
            json={},
        )
        assert response.status_code == 401

    def test_user_api_put_unauthenticated(self):
        """PUT /api/v1/00000000-0000-0000-0000-000000000001/status without auth returns 401"""
        response = client.put(
            "/api/v1/00000000-0000-0000-0000-000000000001/status",
            json={},
        )
        assert response.status_code == 401

    def test_user_api_list_users_wrong_role(self):
        """GET /api/v1/users with wrong role returns 403"""
        response = client.get(
            "/api/v1/users",
            headers={"Authorization": "Bearer wrong-role-token"},
        )
        assert response.status_code == 403

    def test_user_api_get_user_wrong_role(self):
        """GET /api/v1/users/00000000-0000-0000-0000-000000000001 with wrong role returns 403"""
        response = client.get(
            "/api/v1/users/00000000-0000-0000-0000-000000000001",
            headers={"Authorization": "Bearer wrong-role-token"},
        )
        assert response.status_code == 403

    def test_user_api_create_user_wrong_role(self):
        """POST /api/v1/users with wrong role returns 403"""
        response = client.post(
            "/api/v1/users",
            json={},
            headers={"Authorization": "Bearer wrong-role-token"},
        )
        assert response.status_code == 403

    def test_user_api_update_user_wrong_role(self):
        """PUT /api/v1/users/00000000-0000-0000-0000-000000000001 with wrong role returns 403"""
        response = client.put(
            "/api/v1/users/00000000-0000-0000-0000-000000000001",
            json={},
            headers={"Authorization": "Bearer wrong-role-token"},
        )
        assert response.status_code == 403

    def test_user_api_delete_user_wrong_role(self):
        """DELETE /api/v1/users/00000000-0000-0000-0000-000000000001 with wrong role returns 403"""
        response = client.delete(
            "/api/v1/users/00000000-0000-0000-0000-000000000001",
            headers={"Authorization": "Bearer wrong-role-token"},
        )
        assert response.status_code == 403

    def test_user_api_put_wrong_role(self):
        """PUT /api/v1/00000000-0000-0000-0000-000000000001/status with wrong role returns 403"""
        response = client.put(
            "/api/v1/00000000-0000-0000-0000-000000000001/status",
            json={},
            headers={"Authorization": "Bearer wrong-role-token"},
        )
        assert response.status_code == 403
