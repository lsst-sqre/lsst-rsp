"""Tests for the `~lsst.rsp.RSPService` class."""

import json
from pathlib import Path
from unittest.mock import patch

import pytest
from pyvo.dal import SIA2Service, TAPService
from requests_mock import Mocker
from safir.testing.data import Data

from lsst.rsp import (
    DiscoveryNotAvailableError,
    InvalidDiscoveryError,
    RSPServices,
    TokenNotAvailableError,
    UnknownDatasetError,
    UnknownServiceError,
)


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


def test_get_tap_client(
    *, data: Data, discovery_v1_path: Path, token: str, requests_mock: Mocker
) -> None:
    dp1_services = RSPServices("dp1", discovery_v1_path=discovery_v1_path)
    efd_services = RSPServices("efd", discovery_v1_path=discovery_v1_path)

    # PyVO immediately makes a request for the capabilities endpoint, which
    # needs to be mocked out. This can also be used to test whether the token
    # is correctly sent.
    url = dp1_services.get_service_url("tap")
    requests_mock.get(
        url + "/capabilities",
        request_headers={"Authorization": f"Bearer {token}"},
        text=data.read_text("responses/tap-capabilities.xml"),
        headers={"Content-Type": "text/xml"},
    )
    client = dp1_services.get_tap_client()
    assert isinstance(client, TAPService)

    with pytest.raises(UnknownServiceError):
        efd_services.get_tap_client()


def test_get_sia2_client(
    *, data: Data, discovery_v1_path: Path, token: str, requests_mock: Mocker
) -> None:
    dp03_services = RSPServices("dp03", discovery_v1_path=discovery_v1_path)
    dp1_services = RSPServices("dp1", discovery_v1_path=discovery_v1_path)

    # PyVO immediately makes a request for the capabilities endpoint, which
    # needs to be mocked out. This can also be used to test whether the token
    # is correctly sent.
    url = dp1_services.get_service_url("sia")
    requests_mock.get(
        url + "/capabilities",
        request_headers={"Authorization": f"Bearer {token}"},
        text=data.read_text("responses/sia-capabilities.xml"),
        headers={"Content-Type": "text/xml"},
    )
    client = dp1_services.get_sia2_client()
    assert isinstance(client, SIA2Service)

    with pytest.raises(UnknownServiceError):
        dp03_services.get_sia2_client()


@pytest.mark.usefixtures("token")
def test_missing_discovery() -> None:
    with pytest.raises(DiscoveryNotAvailableError):
        RSPServices("dp1", discovery_v1_path=Path("/bogus"))
    with patch.object(RSPServices, "_DISCOVERY_PATH", new=Path("/bogus")):
        with pytest.raises(DiscoveryNotAvailableError):
            RSPServices("dp1")


def test_missing_token(discovery_v1_path: Path) -> None:
    with pytest.raises(TokenNotAvailableError):
        RSPServices("dp1", discovery_v1_path=discovery_v1_path)


@pytest.mark.usefixtures("token")
def test_invalid_discovery(data: Data) -> None:
    invalid_path = data.path("discovery/syntax.json")
    with pytest.raises(InvalidDiscoveryError):
        RSPServices("dp1", discovery_v1_path=invalid_path)


@pytest.mark.usefixtures("token")
def test_missing_url(data: Data) -> None:
    invalid_path = data.path("discovery/v1-invalid.json")
    services = RSPServices("dp02", discovery_v1_path=invalid_path)
    with pytest.raises(UnknownServiceError):
        services.get_service_url("cutout")


@pytest.mark.usefixtures("token")
def test_empty(data: Data) -> None:
    empty_path = data.path("discovery/empty.json")
    with pytest.raises(UnknownDatasetError):
        RSPServices("dp1", discovery_v1_path=empty_path)
