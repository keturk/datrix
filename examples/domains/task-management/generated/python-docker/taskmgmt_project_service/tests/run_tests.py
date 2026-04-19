"""API endpoint tests for taskmgmt.ProjectService (mocked dependencies).

Auto-generated test suite using FastAPI TestClient with dependency injection
overrides. Run with: pytest unit_tests.py
"""

from fastapi.testclient import TestClient

from taskmgmt_project_service.main import create_app

client = TestClient(create_app())


def test_project_api_list_projects():
    """GET /api/v1/projects/ returns 200"""
    response = client.get(
        "/api/v1/projects/",
        headers={"Authorization": "Bearer test-token"},
    )
    assert response.status_code == 200


def test_project_api_get_project():
    """GET /api/v1/projects/00000000-0000-0000-0000-000000000001 returns 200"""
    response = client.get(
        "/api/v1/projects/00000000-0000-0000-0000-000000000001",
        headers={"Authorization": "Bearer test-token"},
    )
    assert response.status_code == 200


def test_project_api_create_project():
    """POST /api/v1/projects/ returns 201"""
    response = client.post(
        "/api/v1/projects/",
        json={},
        headers={"Authorization": "Bearer test-token"},
    )
    assert response.status_code == 201


def test_project_api_update_project():
    """PUT /api/v1/projects/00000000-0000-0000-0000-000000000001 returns 200"""
    response = client.put(
        "/api/v1/projects/00000000-0000-0000-0000-000000000001",
        json={},
        headers={"Authorization": "Bearer test-token"},
    )
    assert response.status_code == 200


def test_project_api_delete_project():
    """DELETE /api/v1/projects/00000000-0000-0000-0000-000000000001 returns 204"""
    response = client.delete(
        "/api/v1/projects/00000000-0000-0000-0000-000000000001",
        headers={"Authorization": "Bearer test-token"},
    )
    assert response.status_code == 204


# --- Authentication / Authorization Tests ---


class TestProjectApiAuthAccess:
    """Test authentication and role-based access control for ProjectApi."""

    def test_project_api_list_projects_unauthenticated(self):
        """GET /api/v1/projects/ without auth returns 401"""
        response = client.get(
            "/api/v1/projects/",
        )
        assert response.status_code == 401

    def test_project_api_get_project_unauthenticated(self):
        """GET /api/v1/projects/00000000-0000-0000-0000-000000000001 without auth returns 401"""
        response = client.get(
            "/api/v1/projects/00000000-0000-0000-0000-000000000001",
        )
        assert response.status_code == 401

    def test_project_api_create_project_unauthenticated(self):
        """POST /api/v1/projects/ without auth returns 401"""
        response = client.post(
            "/api/v1/projects/",
            json={},
        )
        assert response.status_code == 401

    def test_project_api_update_project_unauthenticated(self):
        """PUT /api/v1/projects/00000000-0000-0000-0000-000000000001 without auth returns 401"""
        response = client.put(
            "/api/v1/projects/00000000-0000-0000-0000-000000000001",
            json={},
        )
        assert response.status_code == 401

    def test_project_api_delete_project_unauthenticated(self):
        """DELETE /api/v1/projects/00000000-0000-0000-0000-000000000001 without auth returns 401"""
        response = client.delete(
            "/api/v1/projects/00000000-0000-0000-0000-000000000001",
        )
        assert response.status_code == 401
