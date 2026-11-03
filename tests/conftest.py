"""Shared pytest configuration for the project test suite.

TODO: Add reusable fixtures for deterministic datasets and temporary artifacts.
"""

from collections.abc import Iterator

import pytest


@pytest.fixture
def test_environment() -> Iterator[str]:
    """Provide a placeholder environment fixture for future integration tests."""
    yield "test"
