"""Deployment verification tests for taskmgmt.TaskService.

Auto-generated smoke tests that run against a live deployed endpoint.
Configure BASE_URL via environment variable.

Run with: BASE_URL=https://your-service.com pytest deploy_tests.py
"""

import os
import httpx

BASE_URL = os.environ["BASE_URL"]


def test_task_api_list_tasks():
    """GET /api/v1/tasks/ returns 200"""
    response = httpx.get(
        f"{BASE_URL}/api/v1/tasks/",
        headers={"Authorization": "Bearer test-token"},
    )
    assert response.status_code == 200


def test_task_api_get_task():
    """GET /api/v1/tasks/00000000-0000-0000-0000-000000000001 returns 200"""
    response = httpx.get(
        f"{BASE_URL}/api/v1/tasks/00000000-0000-0000-0000-000000000001",
        headers={"Authorization": "Bearer test-token"},
    )
    assert response.status_code == 200


def test_task_api_create_task():
    """POST /api/v1/tasks/ returns 201"""
    response = httpx.post(
        f"{BASE_URL}/api/v1/tasks/",
        json={},
        headers={"Authorization": "Bearer test-token"},
    )
    assert response.status_code == 201


def test_task_api_update_task():
    """PUT /api/v1/tasks/00000000-0000-0000-0000-000000000001 returns 200"""
    response = httpx.put(
        f"{BASE_URL}/api/v1/tasks/00000000-0000-0000-0000-000000000001",
        json={},
        headers={"Authorization": "Bearer test-token"},
    )
    assert response.status_code == 200


def test_task_api_delete_task():
    """DELETE /api/v1/tasks/00000000-0000-0000-0000-000000000001 returns 204"""
    response = httpx.delete(
        f"{BASE_URL}/api/v1/tasks/00000000-0000-0000-0000-000000000001",
        headers={"Authorization": "Bearer test-token"},
    )
    assert response.status_code == 204


# --- Authentication / Authorization Tests ---


def test_task_api_list_tasks_unauthenticated():
    """GET /api/v1/tasks/ without auth returns 401"""
    response = httpx.get(
        f"{BASE_URL}/api/v1/tasks/",
    )
    assert response.status_code == 401


def test_task_api_get_task_unauthenticated():
    """GET /api/v1/tasks/00000000-0000-0000-0000-000000000001 without auth returns 401"""
    response = httpx.get(
        f"{BASE_URL}/api/v1/tasks/00000000-0000-0000-0000-000000000001",
    )
    assert response.status_code == 401


def test_task_api_create_task_unauthenticated():
    """POST /api/v1/tasks/ without auth returns 401"""
    response = httpx.post(
        f"{BASE_URL}/api/v1/tasks/",
        json={},
    )
    assert response.status_code == 401


def test_task_api_update_task_unauthenticated():
    """PUT /api/v1/tasks/00000000-0000-0000-0000-000000000001 without auth returns 401"""
    response = httpx.put(
        f"{BASE_URL}/api/v1/tasks/00000000-0000-0000-0000-000000000001",
        json={},
    )
    assert response.status_code == 401


def test_task_api_delete_task_unauthenticated():
    """DELETE /api/v1/tasks/00000000-0000-0000-0000-000000000001 without auth returns 401"""
    response = httpx.delete(
        f"{BASE_URL}/api/v1/tasks/00000000-0000-0000-0000-000000000001",
    )
    assert response.status_code == 401
