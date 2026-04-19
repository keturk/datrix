"""API endpoint tests for taskmgmt.TaskService (mocked dependencies).

Auto-generated test suite using FastAPI TestClient with dependency injection
overrides. Run with: pytest unit_tests.py
"""

from fastapi.testclient import TestClient

from taskmgmt_task_service.main import create_app

client = TestClient(create_app())


def test_task_api_list_tasks():
    """GET /api/v1/tasks/ returns 200"""
    response = client.get(
        "/api/v1/tasks/",
        headers={"Authorization": "Bearer test-token"},
    )
    assert response.status_code == 200


def test_task_api_get_task():
    """GET /api/v1/tasks/00000000-0000-0000-0000-000000000001 returns 200"""
    response = client.get(
        "/api/v1/tasks/00000000-0000-0000-0000-000000000001",
        headers={"Authorization": "Bearer test-token"},
    )
    assert response.status_code == 200


def test_task_api_create_task():
    """POST /api/v1/tasks/ returns 201"""
    response = client.post(
        "/api/v1/tasks/",
        json={},
        headers={"Authorization": "Bearer test-token"},
    )
    assert response.status_code == 201


def test_task_api_update_task():
    """PUT /api/v1/tasks/00000000-0000-0000-0000-000000000001 returns 200"""
    response = client.put(
        "/api/v1/tasks/00000000-0000-0000-0000-000000000001",
        json={},
        headers={"Authorization": "Bearer test-token"},
    )
    assert response.status_code == 200


def test_task_api_delete_task():
    """DELETE /api/v1/tasks/00000000-0000-0000-0000-000000000001 returns 204"""
    response = client.delete(
        "/api/v1/tasks/00000000-0000-0000-0000-000000000001",
        headers={"Authorization": "Bearer test-token"},
    )
    assert response.status_code == 204


# --- Authentication / Authorization Tests ---


class TestTaskApiAuthAccess:
    """Test authentication and role-based access control for TaskApi."""

    def test_task_api_list_tasks_unauthenticated(self):
        """GET /api/v1/tasks/ without auth returns 401"""
        response = client.get(
            "/api/v1/tasks/",
        )
        assert response.status_code == 401

    def test_task_api_get_task_unauthenticated(self):
        """GET /api/v1/tasks/00000000-0000-0000-0000-000000000001 without auth returns 401"""
        response = client.get(
            "/api/v1/tasks/00000000-0000-0000-0000-000000000001",
        )
        assert response.status_code == 401

    def test_task_api_create_task_unauthenticated(self):
        """POST /api/v1/tasks/ without auth returns 401"""
        response = client.post(
            "/api/v1/tasks/",
            json={},
        )
        assert response.status_code == 401

    def test_task_api_update_task_unauthenticated(self):
        """PUT /api/v1/tasks/00000000-0000-0000-0000-000000000001 without auth returns 401"""
        response = client.put(
            "/api/v1/tasks/00000000-0000-0000-0000-000000000001",
            json={},
        )
        assert response.status_code == 401

    def test_task_api_delete_task_unauthenticated(self):
        """DELETE /api/v1/tasks/00000000-0000-0000-0000-000000000001 without auth returns 401"""
        response = client.delete(
            "/api/v1/tasks/00000000-0000-0000-0000-000000000001",
        )
        assert response.status_code == 401
