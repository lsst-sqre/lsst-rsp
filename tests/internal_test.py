"""Tests for the `~lsst.rsp.RSPInternalDiscovery` class."""

import json
from pathlib import Path
from typing import Any
from unittest.mock import patch

import pytest
from pyfakefs.fake_filesystem import FakeFilesystem
from requests_mock import Mocker
from safir.testing.data import Data

from lsst.rsp import (
    DiscoveryNotAvailableError,
    InvalidDiscoveryError,
    RSPDiscovery,
    RSPInternalDiscovery,
    TokenNotAvailableError,
    UnknownServiceError,
)


@pytest.mark.usefixtures("token")
def test_get_service_url(discovery_path: Path) -> None:
    services = RSPInternalDiscovery()
    discovery = json.loads(discovery_path.read_text())

    expected = discovery["services"]["internal"]["gafaelfawr"]["url"]
    assert services.get_internal_service_url("gafaelfawr") == expected

    # Test requesting a specific version.
    gafaelfawr = discovery["services"]["internal"]["gafaelfawr"]
    expected = gafaelfawr["versions"]["v1"]["url"]
    seen = services.get_internal_service_url("gafaelfawr", version="v1")
    assert seen == expected

    # Unknown service.
    with pytest.raises(UnknownServiceError):
        services.get_internal_service_url("foo")

    # Unknown service version.
    with pytest.raises(UnknownServiceError):
        services.get_internal_service_url("gafaelfawr", version="v5")


def _has_lsst_rsp_user_agent(request: Any) -> bool:
    ua = request.headers.get("User-Agent", "")
    return "lsst-rsp/" in ua


@pytest.mark.usefixtures("discovery_path")
def test_get_session(token: str, requests_mock: Mocker) -> None:
    services = RSPInternalDiscovery()
    session = services.get_session()

    # Register a mock under one of the URLs for a service and ensure that the
    # token is correctly sent.
    url = services.get_internal_service_url("gafaelfawr")
    requests_mock.get(
        url,
        additional_matcher=_has_lsst_rsp_user_agent,
        request_headers={"Authorization": f"Bearer {token}"},
        text="okay",
    )
    r = session.get(url)
    assert r.status_code == 200
    assert r.text == "okay"

    # Check the same for a URL under one of the versions. The test discovery
    # data puts these versions under a different URL prefix as the base URL
    # for the service so that this test can verify that version URLs are
    # registered separately.
    url = services.get_internal_service_url("gafaelfawr", version="v1")
    requests_mock.get(
        url,
        additional_matcher=_has_lsst_rsp_user_agent,
        request_headers={"Authorization": f"Bearer {token}"},
        text="okay",
    )
    r = session.get(url)
    assert r.status_code == 200
    assert r.text == "okay"

    def no_token(request: Any) -> bool:
        return "Authorization" not in request.headers

    # Register a mock under some URL that isn't beneath any of the service
    # URLs and use that callback to check that the token was not sent. Check
    # both an unrelated URL and one that starts with a valid URL but isn't
    # properly nested.
    for external in ("https://data.example.com/api/other", url + "foo"):
        requests_mock.get(external, additional_matcher=no_token, text="okay")
        r = session.get(external)
        assert r.status_code == 200
        assert r.text == "okay"


def test_outside_nublado(data: Data, requests_mock: Mocker) -> None:
    """Test retrieval of service discovery from outside Nublado."""
    discovery = data.read_json("discovery/full")
    repertoire_url = "https://data.example.com/repertoire"

    # Mock out the retrieval of the discovery information.
    requests_mock.get(
        repertoire_url + "/discovery",
        additional_matcher=_has_lsst_rsp_user_agent,
        json=discovery,
        headers={"Content-Type": "application/json"},
    )

    # Create the RSPInternalDiscovery object, which retrieves discovery
    # information, and then check on discovery results.
    services = RSPInternalDiscovery(discovery_url=repertoire_url, token="blah")
    expected = discovery["services"]["internal"]["gafaelfawr"]["url"]
    assert services.get_internal_service_url("gafaelfawr") == expected

    # Check that the provided token is used correctly when constructing
    # authenticated requests to services.
    requests_mock.get(
        expected,
        additional_matcher=_has_lsst_rsp_user_agent,
        request_headers={"Authorization": "Bearer blah"},
        text="okay",
    )
    session = services.get_session()
    r = session.get(expected)
    assert r.status_code == 200
    assert r.text == "okay"


@pytest.mark.usefixtures("discovery_path", "token")
def test_missing_discovery() -> None:
    with patch.object(RSPDiscovery, "_DISCOVERY_PATH", new=Path("/bogus")):
        with pytest.raises(DiscoveryNotAvailableError):
            RSPInternalDiscovery()


@pytest.mark.usefixtures("discovery_path")
def test_missing_token() -> None:
    with pytest.raises(TokenNotAvailableError):
        RSPInternalDiscovery()


@pytest.mark.usefixtures("token")
def test_invalid_discovery(data: Data, fs: FakeFilesystem) -> None:
    path = data.path("discovery/syntax.json")
    fs.add_real_file(path, target_path=RSPDiscovery._DISCOVERY_PATH)
    with pytest.raises(InvalidDiscoveryError):
        RSPInternalDiscovery()


@pytest.mark.usefixtures("token")
def test_missing_url(data: Data, fs: FakeFilesystem) -> None:
    path = data.path("discovery/v1-invalid.json")
    fs.add_real_file(path, target_path=RSPDiscovery._DISCOVERY_PATH)
    services = RSPInternalDiscovery()

    # This discovery information contains an entry for the Gafaelfawr service
    # with no URL. This should be treated the same as no entry.
    with pytest.raises(UnknownServiceError):
        services.get_internal_service_url("gafaelfawr")


@pytest.mark.usefixtures("token")
def test_empty(data: Data, fs: FakeFilesystem) -> None:
    path = data.path("discovery/empty.json")
    fs.add_real_file(path, target_path=RSPDiscovery._DISCOVERY_PATH)
    services = RSPInternalDiscovery()

    with pytest.raises(UnknownServiceError):
        services.get_internal_service_url("gafaelfawr")
