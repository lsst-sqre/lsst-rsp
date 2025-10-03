"""Tests for service discovery inside Nublado notebooks."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

import pytest
import respx
from httpx import Request, Response

from lsst.rsp import (
    DatasetNotSupportedError,
    DiscoveryNotAvailableError,
    InvalidDiscoveryError,
    TokenNotAvailableError,
    UnknownDatasetError,
    UnknownInfluxDBError,
    UnknownServiceError,
    _discovery,
    get_influxdb_credentials,
    get_influxdb_location,
    get_service_url,
    list_influxdb_labels,
)

from .support.data import data_path, read_test_json


def test_get_service_url(discovery_path_v1: Path) -> None:
    discovery = json.loads(discovery_path_v1.read_text())

    expected = discovery["services"]["data"]["sia"]["dp1"]["url"]
    assert get_service_url("sia", "dp1") == expected
    expected = discovery["services"]["data"]["cutout"]["dp02"]["url"]
    assert get_service_url("cutout", "dp02") == expected

    with pytest.raises(DatasetNotSupportedError):
        get_service_url("sia", "dp03")

    with pytest.raises(UnknownDatasetError):
        get_service_url("cutout", "unknown")

    with pytest.raises(UnknownServiceError):
        get_service_url("foo", "dp1")


def test_get_influxdb_location(discovery_path_v1: Path) -> None:
    discovery = json.loads(discovery_path_v1.read_text())

    expected = discovery["influxdb_databases"]["idfdev_efd"]
    location = get_influxdb_location("idfdev_efd")
    assert location.url == expected["url"]
    assert location.database == expected["database"]
    assert location.schema_registry == expected["schema_registry"]

    with pytest.raises(UnknownInfluxDBError):
        get_influxdb_location("unknown")


def test_get_influxdb_credentials(
    discovery_path_v1: Path,
    respx_mock: respx.Router,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    discovery = json.loads(discovery_path_v1.read_text())
    data = discovery["influxdb_databases"]["idfdev_efd"]
    credentials_url = data["credentials_url"]

    def handler(request: Request) -> Response:
        assert request.headers["Authorization"] == "Bearer some-token"
        return Response(200, json=read_test_json("discovery/idfdev_efd"))

    respx_mock.get(credentials_url).mock(side_effect=handler)

    with pytest.raises(TokenNotAvailableError):
        get_influxdb_credentials("idfdev_efd")

    credentials = get_influxdb_credentials("idfdev_efd", "some-token")
    expected = read_test_json("discovery/idfdev_efd")
    assert credentials.url == expected["url"]
    assert credentials.database == expected["database"]
    assert credentials.schema_registry == expected["schema_registry"]
    assert credentials.username == expected["username"]
    assert credentials.password == expected["password"]

    monkeypatch.setenv("ACCESS_TOKEN", "some-token")
    assert get_influxdb_credentials("idfdev_efd") == credentials

    with pytest.raises(UnknownInfluxDBError):
        get_influxdb_location("unknown")


def test_list_influxdb_labels(discovery_path_v1: Path) -> None:
    discovery = json.loads(discovery_path_v1.read_text())
    labels = sorted(discovery["influxdb_databases"].keys())

    assert list_influxdb_labels() == labels


def test_missing_discovery() -> None:
    with patch.object(_discovery, "_DISCOVERY_PATH", new=Path("/nonexistent")):
        with pytest.raises(DiscoveryNotAvailableError):
            get_service_url("sia", "dp1")
        with pytest.raises(DiscoveryNotAvailableError):
            get_influxdb_location("idfdev_efd")
        with pytest.raises(DiscoveryNotAvailableError):
            get_influxdb_credentials("idfdev_efd")
        with pytest.raises(DiscoveryNotAvailableError):
            list_influxdb_labels()


def test_invalid_discovery(
    respx_mock: respx.Router, monkeypatch: pytest.MonkeyPatch
) -> None:
    invalid_path = data_path("discovery/v1-invalid.json")
    monkeypatch.setenv("ACCESS_TOKEN", "some-token")

    def handler(request: Request) -> Response:
        assert request.headers["Authorization"] == "Bearer some-token"
        credentials = read_test_json("discovery/idfdev_efd-invalid")
        return Response(200, json=credentials)

    discovery = json.loads(invalid_path.read_text())
    data = discovery["influxdb_databases"]["idfdev_efd"]
    credentials_url = data["credentials_url"]
    respx_mock.get(credentials_url).mock(side_effect=handler)

    with patch.object(_discovery, "_DISCOVERY_PATH", invalid_path):
        with pytest.raises(DatasetNotSupportedError):
            get_service_url("cutout", "dp02")
        with pytest.raises(InvalidDiscoveryError):
            get_influxdb_location("idfdev_efd")
        with pytest.raises(InvalidDiscoveryError):
            get_influxdb_credentials("idfdev_efd")


def test_empty() -> None:
    empty_path = data_path("discovery/empty.json")
    with patch.object(_discovery, "_DISCOVERY_PATH", new=empty_path):
        assert list_influxdb_labels() == []
        with pytest.raises(UnknownServiceError):
            get_service_url("sia", "dp1")
            with pytest.raises(UnknownInfluxDBError):
                get_influxdb_location("idfdev_efd")
            with pytest.raises(UnknownInfluxDBError):
                get_influxdb_credentials("idfdev_efd")
