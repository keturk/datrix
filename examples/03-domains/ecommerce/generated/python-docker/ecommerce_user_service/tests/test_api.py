"""API endpoint tests for ecommerce.UserService.

Auto-generated test suite that drives the API in-process through httpx
ASGITransport against a real database session (or a deployed service when
BASE_URL is set). Because these tests require a real database, they are
marked ``integration`` and are excluded from the database-free unit run.
Run with: pytest test_api.py -m integration
"""

import pytest


@pytest.mark.integration
async def test_user_api_list_users(client):
    """GET /api/v1/users returns 200"""
    response = await client.get(
        "/api/v1/users",
    )
    assert response.status_code == 200


@pytest.mark.integration
async def test_user_api_get_user(client):
    """GET /api/v1/users/00000000-0000-0000-0000-000000000001 returns 404"""
    response = await client.get(
        "/api/v1/users/00000000-0000-0000-0000-000000000001",
    )
    assert response.status_code == 404


@pytest.mark.integration
async def test_user_api_create_user(client):
    """POST /api/v1/users returns 422"""
    response = await client.post(
        "/api/v1/users",
        json={},
    )
    assert response.status_code in (422, 403)


@pytest.mark.integration
async def test_user_api_update_user(client):
    """PUT /api/v1/users/00000000-0000-0000-0000-000000000001 returns 404"""
    response = await client.put(
        "/api/v1/users/00000000-0000-0000-0000-000000000001",
        json={},
    )
    assert response.status_code == 404


@pytest.mark.integration
async def test_user_api_delete_user(client):
    """DELETE /api/v1/users/00000000-0000-0000-0000-000000000001 returns 404"""
    response = await client.delete(
        "/api/v1/users/00000000-0000-0000-0000-000000000001",
    )
    assert response.status_code == 404


@pytest.mark.integration
async def test_user_api_post_register(client):
    """POST /api/v1/register returns 422"""
    response = await client.post(
        "/api/v1/register",
        json={},
    )
    assert response.status_code == 422


@pytest.mark.integration
async def test_user_api_post_login(client):
    """POST /api/v1/login returns 422"""
    response = await client.post(
        "/api/v1/login",
        json={},
    )
    assert response.status_code == 422


@pytest.mark.integration
async def test_user_api_post_logout(client):
    """POST /api/v1/logout returns 200"""
    response = await client.post(
        "/api/v1/logout",
        json={},
    )
    assert response.status_code == 200


@pytest.mark.integration
async def test_user_api_get_me(client):
    """GET /api/v1/me returns 404"""
    response = await client.get(
        "/api/v1/me",
    )
    assert response.status_code == 404


@pytest.mark.integration
async def test_user_api_put_me(client):
    """PUT /api/v1/me returns 404"""
    response = await client.put(
        "/api/v1/me",
        json={},
    )
    assert response.status_code == 404


@pytest.mark.integration
async def test_user_api_put_me_password(client):
    """PUT /api/v1/me/password returns 422"""
    response = await client.put(
        "/api/v1/me/password",
        json={},
    )
    assert response.status_code == 422


@pytest.mark.integration
async def test_user_api_post_verify_email(client):
    """POST /api/v1/verify-email returns 422"""
    response = await client.post(
        "/api/v1/verify-email",
        json={},
    )
    assert response.status_code == 422


@pytest.mark.integration
async def test_user_api_post_forgot_password(client):
    """POST /api/v1/forgot-password returns 422"""
    response = await client.post(
        "/api/v1/forgot-password",
        json={},
    )
    assert response.status_code == 422


@pytest.mark.integration
async def test_user_api_post_reset_password(client):
    """POST /api/v1/reset-password returns 422"""
    response = await client.post(
        "/api/v1/reset-password",
        json={},
    )
    assert response.status_code == 422


@pytest.mark.integration
async def test_user_api_put_by_id_status(client):
    """PUT /api/v1/00000000-0000-0000-0000-000000000001/status returns 422"""
    response = await client.put(
        "/api/v1/00000000-0000-0000-0000-000000000001/status",
        json={},
    )
    assert response.status_code in (422, 403)


# --- Authentication / Authorization Tests ---


@pytest.mark.integration
class TestUserApiAuthAccess:
    """Test authentication and role-based access control for UserApi."""

    async def test_user_api_post_register_public_no_auth(self, client):
        """Public POST /api/v1/register without auth returns 422"""
        response = await client.post(
            "/api/v1/register",
            json={},
        )
        assert response.status_code == 422

    async def test_user_api_post_login_public_no_auth(self, client):
        """Public POST /api/v1/login without auth returns 422"""
        response = await client.post(
            "/api/v1/login",
            json={},
        )
        assert response.status_code == 422

    async def test_user_api_post_verify_email_public_no_auth(self, client):
        """Public POST /api/v1/verify-email without auth returns 422"""
        response = await client.post(
            "/api/v1/verify-email",
            json={},
        )
        assert response.status_code == 422

    async def test_user_api_post_forgot_password_public_no_auth(self, client):
        """Public POST /api/v1/forgot-password without auth returns 422"""
        response = await client.post(
            "/api/v1/forgot-password",
            json={},
        )
        assert response.status_code == 422

    async def test_user_api_post_reset_password_public_no_auth(self, client):
        """Public POST /api/v1/reset-password without auth returns 422"""
        response = await client.post(
            "/api/v1/reset-password",
            json={},
        )
        assert response.status_code == 422

    async def test_user_api_list_users_unauthenticated(self, unauth_client):
        """GET /api/v1/users without auth returns 401"""
        response = await unauth_client.get(
            "/api/v1/users",
        )
        assert response.status_code == 401

    async def test_user_api_get_user_unauthenticated(self, unauth_client):
        """GET /api/v1/users/00000000-0000-0000-0000-000000000001 without auth returns 401"""
        response = await unauth_client.get(
            "/api/v1/users/00000000-0000-0000-0000-000000000001",
        )
        assert response.status_code == 401

    async def test_user_api_create_user_unauthenticated(self, unauth_client):
        """POST /api/v1/users without auth returns 401"""
        response = await unauth_client.post(
            "/api/v1/users",
            json={},
        )
        assert response.status_code == 401

    async def test_user_api_update_user_unauthenticated(self, unauth_client):
        """PUT /api/v1/users/00000000-0000-0000-0000-000000000001 without auth returns 401"""
        response = await unauth_client.put(
            "/api/v1/users/00000000-0000-0000-0000-000000000001",
            json={},
        )
        assert response.status_code == 401

    async def test_user_api_delete_user_unauthenticated(self, unauth_client):
        """DELETE /api/v1/users/00000000-0000-0000-0000-000000000001 without auth returns 401"""
        response = await unauth_client.delete(
            "/api/v1/users/00000000-0000-0000-0000-000000000001",
        )
        assert response.status_code == 401

    async def test_user_api_post_logout_unauthenticated(self, unauth_client):
        """POST /api/v1/logout without auth returns 401"""
        response = await unauth_client.post(
            "/api/v1/logout",
            json={},
        )
        assert response.status_code == 401

    async def test_user_api_get_me_unauthenticated(self, unauth_client):
        """GET /api/v1/me without auth returns 401"""
        response = await unauth_client.get(
            "/api/v1/me",
        )
        assert response.status_code == 401

    async def test_user_api_put_me_unauthenticated(self, unauth_client):
        """PUT /api/v1/me without auth returns 401"""
        response = await unauth_client.put(
            "/api/v1/me",
            json={},
        )
        assert response.status_code == 401

    async def test_user_api_put_me_password_unauthenticated(self, unauth_client):
        """PUT /api/v1/me/password without auth returns 401"""
        response = await unauth_client.put(
            "/api/v1/me/password",
            json={},
        )
        assert response.status_code == 401

    async def test_user_api_put_by_id_status_unauthenticated(self, unauth_client):
        """PUT /api/v1/00000000-0000-0000-0000-000000000001/status without auth returns 401"""
        response = await unauth_client.put(
            "/api/v1/00000000-0000-0000-0000-000000000001/status",
            json={},
        )
        assert response.status_code == 401

    async def test_user_api_get_service_by_id_unauthenticated(self, unauth_client):
        """GET /api/v1/service/00000000-0000-0000-0000-000000000001 without auth returns 401"""
        response = await unauth_client.get(
            "/api/v1/service/00000000-0000-0000-0000-000000000001",
        )
        assert response.status_code == 401

    async def test_user_api_post_service_validate_session_unauthenticated(
        self, unauth_client
    ):
        """POST /api/v1/service/validate-session without auth returns 401"""
        response = await unauth_client.post(
            "/api/v1/service/validate-session",
            json={},
        )
        assert response.status_code == 401

    async def test_user_api_list_users_wrong_role(self, wrong_role_client):
        """GET /api/v1/users with wrong role returns 403"""
        response = await wrong_role_client.get(
            "/api/v1/users",
        )
        assert response.status_code == 403

    async def test_user_api_get_user_wrong_role(self, wrong_role_client):
        """GET /api/v1/users/00000000-0000-0000-0000-000000000001 with wrong role returns 403"""
        response = await wrong_role_client.get(
            "/api/v1/users/00000000-0000-0000-0000-000000000001",
        )
        assert response.status_code == 403

    async def test_user_api_create_user_wrong_role(self, wrong_role_client):
        """POST /api/v1/users with wrong role returns 403"""
        response = await wrong_role_client.post(
            "/api/v1/users",
            json={},
        )
        assert response.status_code == 403

    async def test_user_api_update_user_wrong_role(self, wrong_role_client):
        """PUT /api/v1/users/00000000-0000-0000-0000-000000000001 with wrong role returns 403"""
        response = await wrong_role_client.put(
            "/api/v1/users/00000000-0000-0000-0000-000000000001",
            json={},
        )
        assert response.status_code == 403

    async def test_user_api_delete_user_wrong_role(self, wrong_role_client):
        """DELETE /api/v1/users/00000000-0000-0000-0000-000000000001 with wrong role returns 403"""
        response = await wrong_role_client.delete(
            "/api/v1/users/00000000-0000-0000-0000-000000000001",
        )
        assert response.status_code == 403

    async def test_user_api_put_by_id_status_wrong_role(self, wrong_role_client):
        """PUT /api/v1/00000000-0000-0000-0000-000000000001/status with wrong role returns 403"""
        response = await wrong_role_client.put(
            "/api/v1/00000000-0000-0000-0000-000000000001/status",
            json={},
        )
        assert response.status_code == 403

    async def test_user_api_get_service_by_id_non_service_token(
        self, wrong_role_client
    ):
        """GET /api/v1/service/00000000-0000-0000-0000-000000000001 with a non-service token returns 401"""
        response = await wrong_role_client.get(
            "/api/v1/service/00000000-0000-0000-0000-000000000001",
        )
        assert response.status_code == 401

    async def test_user_api_post_service_validate_session_non_service_token(
        self, wrong_role_client
    ):
        """POST /api/v1/service/validate-session with a non-service token returns 401"""
        response = await wrong_role_client.post(
            "/api/v1/service/validate-session",
            json={},
        )
        assert response.status_code == 401
