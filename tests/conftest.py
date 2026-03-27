"""Pytest configuration and fixtures."""

from pathlib import Path

import pytest
from pyfakefs.fake_filesystem import FakeFilesystem
from safir.testing.data import Data

from lsst.rsp import RSPDiscovery


@pytest.fixture
def data(fs: FakeFilesystem) -> Data:
    fs.add_real_directory(Path(__file__).parent / "data")
    return Data(Path(__file__).parent / "data", fake_filesystem=fs)


@pytest.fixture
def discovery_path(data: Data, fs: FakeFilesystem) -> Path:
    """Set up a fake file system with discovery in the expected path."""
    path = data.path("discovery/v1.json")
    fs.add_real_file(path, target_path=RSPDiscovery._DISCOVERY_PATH)
    return path


@pytest.fixture
def discovery_v1_path() -> Path:
    """Delete once older functions and tests are retired."""
    return Path(__file__).parent / "data" / "discovery" / "v1.json"


@pytest.fixture
def token(monkeypatch: pytest.MonkeyPatch) -> str:
    monkeypatch.setenv("NUBLADO_TOKEN", "some-token")
    return "some-token"


@pytest.fixture
def _rsp_env(monkeypatch: pytest.MonkeyPatch) -> None:
    file_dir = Path(__file__).parent / "data" / "files"
    monkeypatch.setenv(
        "NUBLADO_RUNTIME_MOUNTS_DIR", str(file_dir / "etc" / "nublado")
    )
    monkeypatch.setenv("JUPYTERLAB_CONFIG_DIR", str(file_dir / "jupyterlab"))
