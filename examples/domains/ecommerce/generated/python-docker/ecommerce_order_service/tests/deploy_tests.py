"""Deployment verification tests for ecommerce.OrderService.

Auto-generated smoke tests that run against a live deployed endpoint.
Configure BASE_URL via environment variable.

Run with: BASE_URL=https://your-service.com pytest deploy_tests.py
"""

import os
import httpx
import pytest

BASE_URL = os.environ["BASE_URL"]


def test_order_api_get():
    """GET /api/v1/orders/ returns 200"""
    response = httpx.get(
        f"{BASE_URL}/api/v1/orders/",
        headers={"Authorization": "Bearer test-token"},
    )
    assert response.status_code == 200


def test_order_api_get():
    """GET /api/v1/orders/00000000-0000-0000-0000-000000000001 returns 200"""
    response = httpx.get(
        f"{BASE_URL}/api/v1/orders/00000000-0000-0000-0000-000000000001",
        headers={"Authorization": "Bearer test-token"},
    )
    assert response.status_code == 200


def test_order_api_post():
    """POST /api/v1/orders/ returns 201"""
    response = httpx.post(
        f"{BASE_URL}/api/v1/orders/",
        json={},
        headers={"Authorization": "Bearer test-token"},
    )
    assert response.status_code == 201


def test_order_api_put():
    """PUT /api/v1/orders/00000000-0000-0000-0000-000000000001/cancel returns 200"""
    response = httpx.put(
        f"{BASE_URL}/api/v1/orders/00000000-0000-0000-0000-000000000001/cancel",
        json={},
        headers={"Authorization": "Bearer test-token"},
    )
    assert response.status_code == 200


def test_order_api_get():
    """GET /api/v1/orders/internal/00000000-0000-0000-0000-000000000001 returns 200"""
    response = httpx.get(
        f"{BASE_URL}/api/v1/orders/internal/00000000-0000-0000-0000-000000000001",
    )
    assert response.status_code == 200


def test_order_api_post():
    """POST /api/v1/orders/00000000-0000-0000-0000-000000000001/confirm-payment returns 201"""
    response = httpx.post(
        f"{BASE_URL}/api/v1/orders/00000000-0000-0000-0000-000000000001/confirm-payment",
        json={},
    )
    assert response.status_code == 201


def test_order_api_post():
    """POST /api/v1/orders/00000000-0000-0000-0000-000000000001/update-shipment returns 201"""
    response = httpx.post(
        f"{BASE_URL}/api/v1/orders/00000000-0000-0000-0000-000000000001/update-shipment",
        json={},
    )
    assert response.status_code == 201


# --- Authentication / Authorization Tests ---


def test_order_api_get_unauthenticated():
    """GET /api/v1/orders/ without auth returns 401"""
    response = httpx.get(
        f"{BASE_URL}/api/v1/orders/",
    )
    assert response.status_code == 401


def test_order_api_get_unauthenticated():
    """GET /api/v1/orders/00000000-0000-0000-0000-000000000001 without auth returns 401"""
    response = httpx.get(
        f"{BASE_URL}/api/v1/orders/00000000-0000-0000-0000-000000000001",
    )
    assert response.status_code == 401


def test_order_api_post_unauthenticated():
    """POST /api/v1/orders/ without auth returns 401"""
    response = httpx.post(
        f"{BASE_URL}/api/v1/orders/",
        json={},
    )
    assert response.status_code == 401


def test_order_api_put_unauthenticated():
    """PUT /api/v1/orders/00000000-0000-0000-0000-000000000001/cancel without auth returns 401"""
    response = httpx.put(
        f"{BASE_URL}/api/v1/orders/00000000-0000-0000-0000-000000000001/cancel",
        json={},
    )
    assert response.status_code == 401
