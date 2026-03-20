"""Tests for the `~lsst.rsp.RSPService` class."""

import json
from pathlib import Path
from unittest.mock import patch

import pytest

from lsst.rsp import (
    DiscoveryNotAvailableError,
    InvalidDiscoveryError,
    RSPServices,
    UnknownDatasetError,
    UnknownServiceError,
)

from .support.data import data_path


@pytest.mark.usefixtures("token")
def test_get_service_url(discovery_v1_path: Path) -> None:
    dp02_services = RSPServices("dp02", discovery_v1_path=discovery_v1_path)
    dp03_services = RSPServices("dp03", discovery_v1_path=discovery_v1_path)
    dp1_services = RSPServices("dp1", discovery_v1_path=discovery_v1_path)
    discovery = json.loads(discovery_v1_path.read_text())

    expected = discovery["datasets"]["dp1"]["services"]["sia"]["url"]
    assert dp1_services.get_service_url("sia") == expected
    expected = discovery["datasets"]["dp02"]["services"]["cutout"]["url"]
    assert dp02_services.get_service_url("cutout") == expected

    with pytest.raises(UnknownServiceError):
        dp1_services.get_service_url("foo")

    with pytest.raises(UnknownServiceError):
        dp03_services.get_service_url("sia")

    with pytest.raises(UnknownDatasetError):
        RSPServices("unknown", discovery_v1_path=discovery_v1_path)


@pytest.mark.usefixtures("token")
def test_missing_discovery() -> None:
    with pytest.raises(DiscoveryNotAvailableError):
        RSPServices("dp1", discovery_v1_path=Path("/bogus"))
    with patch.object(RSPServices, "_DISCOVERY_PATH", new=Path("/bogus")):
        with pytest.raises(DiscoveryNotAvailableError):
            RSPServices("dp1")


@pytest.mark.usefixtures("token")
def test_invalid_discovery() -> None:
    invalid_path = data_path("discovery/syntax.json")
    with pytest.raises(InvalidDiscoveryError):
        RSPServices("dp1", discovery_v1_path=invalid_path)


@pytest.mark.usefixtures("token")
def test_empty() -> None:
    empty_path = data_path("discovery/empty.json")
    with pytest.raises(UnknownDatasetError):
        RSPServices("dp1", discovery_v1_path=empty_path)
