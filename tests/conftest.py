"""Pytest configuration and fixtures."""

from collections.abc import Iterator
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

import pytest


@pytest.fixture
def rsp_env(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    with patch(
        "lsst.rsp.startup.constants.top_dir",
        (Path(__file__).parent / "support" / "stack_top" / "files"),
    ):
        with TemporaryDirectory() as homedir:
            monkeypatch.setenv("HOME", homedir)
            monkeypatch.setenv("USER", "hambone")
            yield
