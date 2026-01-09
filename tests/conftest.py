"""Pytest configuration and fixtures."""

from collections.abc import Iterator
from pathlib import Path
from tempfile import TemporaryDirectory

import pytest


@pytest.fixture
def discovery_v1_path() -> Path:
    return Path(__file__).parent / "data" / "discovery" / "v1.json"


# Things for startup


@pytest.fixture
def _rsp_env(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    with TemporaryDirectory() as fake_root:
        file_dir = Path(__file__).parent / "data" / "files"
        t_home = Path(fake_root) / "home" / "hambone"
        t_home.mkdir(parents=True)
        homedir = str(t_home)
        t_start = Path(fake_root) / "lab_startup"
        t_start.mkdir()
        monkeypatch.setenv(
            "NUBLADO_RUNTIME_MOUNTS_DIR", str(file_dir / "etc" / "nublado")
        )
        monkeypatch.setenv(
            "JUPYTERLAB_CONFIG_DIR", str(file_dir / "jupyterlab")
        )
        monkeypatch.setenv("RSP_STARTUP_PATH", f"{t_start!s}")
        monkeypatch.setenv("HOME", homedir)
        yield
