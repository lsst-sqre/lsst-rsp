"""Pytest configuration and fixtures."""

from collections.abc import Iterator

import pytest


@pytest.fixture
def startup_mock(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    monkeypatch.setenv("RUBIN_EUPS_PATH", "/opt/lsst/software/stack/foo")
    return None
