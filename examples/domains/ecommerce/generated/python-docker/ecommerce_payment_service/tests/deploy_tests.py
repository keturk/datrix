"""Deployment verification tests for ecommerce.PaymentService.

Auto-generated smoke tests that run against a live deployed endpoint.
Configure BASE_URL via environment variable.

Run with: BASE_URL=https://your-service.com pytest deploy_tests.py
"""

import os
import httpx
import pytest

BASE_URL = os.environ["BASE_URL"]


def test_payment_api_get_payment():
    """GET /api/v1/payments/00000000-0000-0000-0000-000000000001 returns 200"""
    response = httpx.get(
        f"{BASE_URL}/api/v1/payments/00000000-0000-0000-0000-000000000001",
        headers={"Authorization": "Bearer test-token"},
    )
    assert response.status_code == 200


def test_payment_api_get():
    """GET /api/v1/payments/order/00000000-0000-0000-0000-000000000001 returns 200"""
    response = httpx.get(
        f"{BASE_URL}/api/v1/payments/order/00000000-0000-0000-0000-000000000001",
        headers={"Authorization": "Bearer test-token"},
    )
    assert response.status_code == 200


def test_payment_api_get():
    """GET /api/v1/payments/my-payments returns 200"""
    response = httpx.get(
        f"{BASE_URL}/api/v1/payments/my-payments",
        headers={"Authorization": "Bearer test-token"},
    )
    assert response.status_code == 200


def test_payment_api_post():
    """POST /api/v1/payments/process returns 201"""
    response = httpx.post(
        f"{BASE_URL}/api/v1/payments/process",
        json={},
        headers={"Authorization": "Bearer test-token"},
    )
    assert response.status_code == 201


def test_payment_api_post():
    """POST /api/v1/payments/00000000-0000-0000-0000-000000000001/refund returns 201"""
    response = httpx.post(
        f"{BASE_URL}/api/v1/payments/00000000-0000-0000-0000-000000000001/refund",
        json={},
        headers={"Authorization": "Bearer test-token"},
    )
    assert response.status_code == 201


def test_payment_api_post():
    """POST /api/v1/payments/webhook/stripe returns 201"""
    response = httpx.post(
        f"{BASE_URL}/api/v1/payments/webhook/stripe",
        json={},
    )
    assert response.status_code == 201


# --- Authentication / Authorization Tests ---


def test_payment_api_post_public_no_auth():
    """Public POST /api/v1/payments/webhook/stripe without auth returns 201"""
    response = httpx.post(
        f"{BASE_URL}/api/v1/payments/webhook/stripe",
        json={},
    )
    assert response.status_code == 201


def test_payment_api_get_payment_unauthenticated():
    """GET /api/v1/payments/00000000-0000-0000-0000-000000000001 without auth returns 401"""
    response = httpx.get(
        f"{BASE_URL}/api/v1/payments/00000000-0000-0000-0000-000000000001",
    )
    assert response.status_code == 401


def test_payment_api_get_unauthenticated():
    """GET /api/v1/payments/order/00000000-0000-0000-0000-000000000001 without auth returns 401"""
    response = httpx.get(
        f"{BASE_URL}/api/v1/payments/order/00000000-0000-0000-0000-000000000001",
    )
    assert response.status_code == 401


def test_payment_api_get_unauthenticated():
    """GET /api/v1/payments/my-payments without auth returns 401"""
    response = httpx.get(
        f"{BASE_URL}/api/v1/payments/my-payments",
    )
    assert response.status_code == 401


def test_payment_api_post_unauthenticated():
    """POST /api/v1/payments/process without auth returns 401"""
    response = httpx.post(
        f"{BASE_URL}/api/v1/payments/process",
        json={},
    )
    assert response.status_code == 401


def test_payment_api_post_unauthenticated():
    """POST /api/v1/payments/00000000-0000-0000-0000-000000000001/refund without auth returns 401"""
    response = httpx.post(
        f"{BASE_URL}/api/v1/payments/00000000-0000-0000-0000-000000000001/refund",
        json={},
    )
    assert response.status_code == 401


def test_payment_api_post_wrong_role():
    """POST /api/v1/payments/00000000-0000-0000-0000-000000000001/refund with wrong role returns 403"""
    response = httpx.post(
        f"{BASE_URL}/api/v1/payments/00000000-0000-0000-0000-000000000001/refund",
        json={},
        headers={"Authorization": "Bearer wrong-role-token"},
    )
    assert response.status_code == 403
