"""API endpoint tests for taskmgmt.UserService (mocked dependencies).

Auto-generated test suite using FastAPI TestClient with dependency injection
overrides. Run with: pytest run_tests.py
"""

from fastapi.testclient import TestClient

from taskmgmt_user_service.main import create_app

client = TestClient(create_app())


def test_user_api_list_users():
    """GET /api/v1/users/ returns 200"""
    response = client.get(
        "/api/v1/users/",
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
    """POST /api/v1/users/ returns 201"""
    response = client.post(
        "/api/v1/users/",
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


# --- Authentication / Authorization Tests ---


class TestUserApiAuthAccess:
    """Test authentication and role-based access control for UserApi."""

    def test_user_api_list_users_unauthenticated(self):
        """GET /api/v1/users/ without auth returns 401"""
        response = client.get(
            "/api/v1/users/",
        )
        assert response.status_code == 401

    def test_user_api_get_user_unauthenticated(self):
        """GET /api/v1/users/00000000-0000-0000-0000-000000000001 without auth returns 401"""
        response = client.get(
            "/api/v1/users/00000000-0000-0000-0000-000000000001",
        )
        assert response.status_code == 401

    def test_user_api_create_user_unauthenticated(self):
        """POST /api/v1/users/ without auth returns 401"""
        response = client.post(
            "/api/v1/users/",
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
