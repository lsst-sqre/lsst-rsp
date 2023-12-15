"""Tests for utility functions."""

from __future__ import annotations

import os
from collections.abc import Iterator
from unittest.mock import patch

import pytest

from lsst.rsp import format_bytes
from lsst.rsp.utils import get_service_url


def test_format_bytes() -> None:
    """Test human-readable names for numeric byte inputs."""
    assert format_bytes(1) == "1 B"
    assert format_bytes(1234) == "1.23 kB"
    assert format_bytes(12345678) == "12.35 MB"
    assert format_bytes(1234567890) == "1.23 GB"
    assert format_bytes(1234567890000) == "1.23 TB"
    assert format_bytes(1234567890000000) == "1.23 PB"


@pytest.fixture
def url_env() -> Iterator[None]:
    """Set up some temporary environment variables for service URL tests."""
    env = {
        "EXTERNAL_INSTANCE_URL": "https://test.example.com/",
        "TAP_ROUTE": "/api/tap",
    }
    with patch.dict(os.environ, env):
        yield


def test_get_service_url(url_env: None) -> None:
    """Ensure there are no doubled slashes."""
    assert get_service_url("tap") == "https://test.example.com/api/tap"
