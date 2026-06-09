"""Service discovery within Nublado notebooks.

These functions use a service discovery JSON file created by the Nublado
controller when the user's lab was created for everything except obtaining
InfluxDB credentials. This avoids a dependency on the Rubin Repertoire client,
which may require a newer Python version than is available in the execution
environment using lsst.rsp.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import httpx

from ._exceptions import (
    DiscoveryNotAvailableError,
    InvalidDiscoveryError,
    TokenNotAvailableError,
    UnknownDatasetError,
    UnknownInfluxDBError,
    UnknownServiceError,
)
from .utils import get_access_token

_DISCOVERY_PATH = Path("/etc/nublado/discovery/v1.json")
"""Path to static service discovery information."""

__all__ = [
    "InfluxDBCredentials",
    "InfluxDBLocation",
    "get_influxdb_credentials",
    "get_influxdb_location",
    "get_service_url",
    "list_datasets",
    "list_influxdb_labels",
]


@dataclass
class InfluxDBLocation:
    """Location information for an InfluxDB database."""

    url: str
    """URL to the InfluxDB database."""

    database: str
    """Name of the InfluxDB database."""

    schema_registry: str
    """URL to the Schema Registry corresponding to that database."""


@dataclass
class InfluxDBCredentials(InfluxDBLocation):
    """InfluxDB database location information and credentials."""

    username: str
    """Username to use for authentication."""

    password: str
    """Password to use for authentication."""


def _get_discovery() -> dict[str, Any]:
    """Get the data and service discovery information.

    Returns
    -------
    dict
        Parsed service discovery information.

    Raises
    ------
    DiscoveryNotAvailableError
        Raised if no service discovery information is available.
    """
    try:
        return json.loads(_DISCOVERY_PATH.read_text())
    except FileNotFoundError as e:
        raise DiscoveryNotAvailableError(e) from e


def get_influxdb_credentials(
    label: str,
    token: str | None = None,
) -> InfluxDBCredentials:
    """Get the credentials for an InfluxDB database.

    Parameters
    ----------
    label
        Human label for the InfluxDB database.
    token
        If given, use this Gafaelfawr token instead of the local notebook
        token.

    Returns
    -------
    InfluxDBLocation
        Location and credentials for the InfluxDB database.

    Raises
    ------
    DiscoveryNotAvailableError
        Raised if no service discovery information is available.
    InvalidDiscoveryError
        Raised if the discovery information has an invalid syntax.
    TokenNotAvailableError
        Raised if there is no Gafaelfawr token available.
    UnknownInfluxDBError
        Raised if the InfluxDB database is not known.
    """
    discovery = _get_discovery()
    influxdb = discovery.get("influxdb_databases", {}).get(label)
    if not influxdb:
        raise UnknownInfluxDBError(label)
    url = influxdb.get("credentials_url")
    if not url:
        raise UnknownInfluxDBError(label)

    # Determine the authentication token to use.
    if not token:
        token = get_access_token()
    if not token:
        raise TokenNotAvailableError("No access token available")

    # Make an authenticated request to Repertoire to get the InfluxDB
    # connection information with username and password.
    r = httpx.get(url, headers={"Authorization": f"Bearer {token}"})
    r.raise_for_status()
    info = r.json()

    # Construct the return value.
    try:
        return InfluxDBCredentials(
            url=info["url"],
            database=info["database"],
            schema_registry=info["schema_registry"],
            username=info["username"],
            password=info["password"],
        )
    except KeyError as e:
        raise InvalidDiscoveryError(e, f"InfluxDB creds for {label}") from e


def get_influxdb_location(label: str) -> InfluxDBLocation:
    """Get the location information for an InfluxDB database.

    Parameters
    ----------
    label
        Human label for the InfluxDB database.

    Returns
    -------
    InfluxDBLocation
        Location information for the InfluxDB database.

    Raises
    ------
    DiscoveryNotAvailableError
        Raised if no service discovery information is available.
    InvalidDiscoveryError
        Raised if the discovery information has an invalid syntax.
    UnknownInfluxDBError
        Raised if the InfluxDB database is not known.
    """
    discovery = _get_discovery()
    influxdb = discovery.get("influxdb_databases", {}).get(label)
    if not influxdb:
        raise UnknownInfluxDBError(label)
    try:
        return InfluxDBLocation(
            url=influxdb["url"],
            database=influxdb["database"],
            schema_registry=influxdb["schema_registry"],
        )
    except KeyError as e:
        raise InvalidDiscoveryError(e, f"InfluxDB database {label}") from e


def get_service_url(service: str, dataset: str) -> str:
    """Get the API URL for a service and dataset combination.

    Parameters
    ----------
    service
        Name of the service.
    dataset
        Name of the dataset.

    Returns
    -------
    str
        Base URL for the service API.

    Raises
    ------
    DiscoveryNotAvailableError
        Raised if no service discovery information is available.
    UnknownDatasetError
        Raised if this dataset is not present in the environment.
    UnknownServiceError
        Raised if this service is not present in the environment for this
        dataset.
    """
    discovery = _get_discovery()
    dataset_info = discovery.get("datasets", {}).get(dataset)
    if not dataset_info:
        raise UnknownDatasetError(dataset)
    url = dataset_info.get("services", {}).get(service, {}).get("url")
    if not url:
        raise UnknownServiceError(service, dataset)
    return url


def list_datasets() -> list[str]:
    """List the available datasets in this environment.

    Returns
    -------
    list of str
        Names of datasets in this environment.

    Raises
    ------
    DiscoveryNotAvailableError
        Raised if no service discovery information is available.
    """
    discovery = _get_discovery()
    return sorted(discovery.get("datasets", {}).keys())


def list_influxdb_labels(*, local: bool | None = None) -> list[str]:
    """List the available InfluxDB labels in this environment.

    Parameters
    ----------
    local
        If set to `True`, return only InfluxDB databases hosted in the local
        Phalanx environment (the one whose service discovery service is being
        queried). If set to `False`, return only InfluxDB databases that are
        hosted outside this Phalanx environment. The default, `None`, lists
        all accessible databases, local or not. This parameter is primarily
        for testing and should normally not be provided.

    Returns
    -------
    list of str
        Labels for InfluxDB databases suitable for passing to
        `get_influxdb_location` or `get_influxdb_credentials`.

    Raises
    ------
    DiscoveryNotAvailableError
        Raised if no service discovery information is available.
    """
    discovery = _get_discovery()
    if local is None:
        return sorted(discovery.get("influxdb_databases", {}).keys())
    else:
        databases = discovery.get("influxdb_databases", {}).items()
        if local:
            return sorted(k for k, v in databases if v.get("local"))
        else:
            return sorted(k for k, v in databases if not v.get("local"))
