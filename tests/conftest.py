"""Pytest configuration and fixtures."""

from pathlib import Path

import pytest


@pytest.fixture
def discovery_v1_path() -> Path:
    return Path(__file__).parent / "data" / "discovery" / "v1.json"


@pytest.fixture
def _rsp_env(monkeypatch: pytest.MonkeyPatch) -> None:
    file_dir = Path(__file__).parent / "data" / "files"
    monkeypatch.setenv(
        "NUBLADO_RUNTIME_MOUNTS_DIR", str(file_dir / "etc" / "nublado")
    )
    monkeypatch.setenv("JUPYTERLAB_CONFIG_DIR", str(file_dir / "jupyterlab"))
