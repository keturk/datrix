"""Deployment verification tests for taskmgmt.ProjectService.

Auto-generated smoke tests that run against a live deployed endpoint.
Configure BASE_URL via environment variable.

Run with: BASE_URL=https://your-service.com pytest deploy_tests.py
"""

import os
import httpx

BASE_URL = os.environ["BASE_URL"]


def test_project_api_list_projects():
    """GET /api/v1/projects/ returns 200"""
    response = httpx.get(
        f"{BASE_URL}/api/v1/projects/",
        headers={"Authorization": "Bearer test-token"},
    )
    assert response.status_code == 200


def test_project_api_get_project():
    """GET /api/v1/projects/00000000-0000-0000-0000-000000000001 returns 200"""
    response = httpx.get(
        f"{BASE_URL}/api/v1/projects/00000000-0000-0000-0000-000000000001",
        headers={"Authorization": "Bearer test-token"},
    )
    assert response.status_code == 200


def test_project_api_create_project():
    """POST /api/v1/projects/ returns 201"""
    response = httpx.post(
        f"{BASE_URL}/api/v1/projects/",
        json={},
        headers={"Authorization": "Bearer test-token"},
    )
    assert response.status_code == 201


def test_project_api_update_project():
    """PUT /api/v1/projects/00000000-0000-0000-0000-000000000001 returns 200"""
    response = httpx.put(
        f"{BASE_URL}/api/v1/projects/00000000-0000-0000-0000-000000000001",
        json={},
        headers={"Authorization": "Bearer test-token"},
    )
    assert response.status_code == 200


def test_project_api_delete_project():
    """DELETE /api/v1/projects/00000000-0000-0000-0000-000000000001 returns 204"""
    response = httpx.delete(
        f"{BASE_URL}/api/v1/projects/00000000-0000-0000-0000-000000000001",
        headers={"Authorization": "Bearer test-token"},
    )
    assert response.status_code == 204


# --- Authentication / Authorization Tests ---


def test_project_api_list_projects_unauthenticated():
    """GET /api/v1/projects/ without auth returns 401"""
    response = httpx.get(
        f"{BASE_URL}/api/v1/projects/",
    )
    assert response.status_code == 401


def test_project_api_get_project_unauthenticated():
    """GET /api/v1/projects/00000000-0000-0000-0000-000000000001 without auth returns 401"""
    response = httpx.get(
        f"{BASE_URL}/api/v1/projects/00000000-0000-0000-0000-000000000001",
    )
    assert response.status_code == 401


def test_project_api_create_project_unauthenticated():
    """POST /api/v1/projects/ without auth returns 401"""
    response = httpx.post(
        f"{BASE_URL}/api/v1/projects/",
        json={},
    )
    assert response.status_code == 401


def test_project_api_update_project_unauthenticated():
    """PUT /api/v1/projects/00000000-0000-0000-0000-000000000001 without auth returns 401"""
    response = httpx.put(
        f"{BASE_URL}/api/v1/projects/00000000-0000-0000-0000-000000000001",
        json={},
    )
    assert response.status_code == 401


def test_project_api_delete_project_unauthenticated():
    """DELETE /api/v1/projects/00000000-0000-0000-0000-000000000001 without auth returns 401"""
    response = httpx.delete(
        f"{BASE_URL}/api/v1/projects/00000000-0000-0000-0000-000000000001",
    )
    assert response.status_code == 401
