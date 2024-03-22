"""Tests for utility functions."""

from __future__ import annotations

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


def test_get_service_url(monkeypatch: pytest.MonkeyPatch) -> None:
    """Ensure there are no doubled slashes."""
    monkeypatch.setenv("EXTERNAL_INSTANCE_URL", "https://test.example.com/")
    monkeypatch.setenv("TAP_ROUTE", "/api/tap")
    assert get_service_url("tap") == "https://test.example.com/api/tap"
