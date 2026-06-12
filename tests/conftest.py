"""Shared pytest configuration for the repo-level ``datrix`` test package.

Registers the real tree-sitter parser so ``parse_fixture*`` helpers work for
the cross-package integration tests that live here (e.g. byte-identical
regeneration and the identity multi-target suite).
"""

from __future__ import annotations

import pytest

from datrix_language.registration import register_all

register_all()


def pytest_configure(config: pytest.Config) -> None:
    """Register custom markers used by the repo-level integration tests."""
    config.addinivalue_line(
        "markers",
        "integration: Integration tests (slower, exercise the real pipeline).",
    )
    config.addinivalue_line(
        "markers",
        "e2e: End-to-end tests (full pipeline, real I/O, no mocking).",
    )
