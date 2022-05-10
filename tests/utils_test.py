"""Tests for utility functions."""

from __future__ import annotations

from lsst.rsp import format_bytes


def test_format_bytes() -> None:
    assert format_bytes(1) == "1 B"
    assert format_bytes(1234) == "1.23 kB"
    assert format_bytes(12345678) == "12.35 MB"
    assert format_bytes(1234567890) == "1.23 GB"
    assert format_bytes(1234567890000) == "1.23 TB"
    assert format_bytes(1234567890000000) == "1.23 PB"
