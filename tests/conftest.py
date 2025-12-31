"""Shared fixtures and pytest configuration for ai-jup test suite."""

import os

import pytest


def pytest_configure(config):
    """Register custom markers."""
    config.addinivalue_line("markers", "external: tests that call external APIs")
    config.addinivalue_line("markers", "slow: slow-running tests")
    config.addinivalue_line("markers", "e2e: end-to-end workflow tests")


@pytest.fixture
def haiku_enabled():
    """Check if Haiku tests are enabled.

    Returns True if RUN_HAIKU_TESTS=1 and ANTHROPIC_API_KEY is set.
    """
    return bool(
        os.environ.get("RUN_HAIKU_TESTS") and os.environ.get("ANTHROPIC_API_KEY")
    )


@pytest.fixture
def jupyter_base_url():
    """Base URL for Jupyter server API tests."""
    return os.environ.get("JUPYTER_BASE_URL", "http://localhost:8888")
