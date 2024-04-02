"""Tests for utility functions."""

from __future__ import annotations

import pytest

from lsst.rsp import format_bytes
from lsst.rsp.utils import get_digest, get_service_url


def test_format_bytes() -> None:
    """Test human-readable names for numeric byte inputs."""
    assert format_bytes(1) == "1 B"
    assert format_bytes(1234) == "1.23 kB"
    assert format_bytes(12345678) == "12.35 MB"
    assert format_bytes(1234567890) == "1.23 GB"
    assert format_bytes(1234567890000) == "1.23 TB"
    assert format_bytes(1234567890000000) == "1.23 PB"


def test_get_digest(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("JUPYTER_IMAGE_SPEC", "sciplat-lab@sha256:abcde")
    digest = get_digest()
    assert digest == "abcde"


def test_get_digest_fail(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("JUPYTER_IMAGE_SPEC", "sciplat-lab:w_2024_01")
    digest = get_digest()
    assert digest == ""


def test_get_service_url(monkeypatch: pytest.MonkeyPatch) -> None:
    """Ensure there are no doubled slashes."""
    monkeypatch.setenv("EXTERNAL_INSTANCE_URL", "https://test.example.com/")
    monkeypatch.setenv("TAP_ROUTE", "/api/tap")
    assert get_service_url("tap") == "https://test.example.com/api/tap"
