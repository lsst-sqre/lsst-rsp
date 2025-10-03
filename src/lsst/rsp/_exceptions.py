"""Exceptions raised by helper functions."""

from __future__ import annotations

from pathlib import Path

__all__ = [
    "DatasetNotSupportedError",
    "DiscoveryNotAvailableError",
    "InvalidDiscoveryError",
    "TokenNotAvailableError",
    "UnknownDatasetError",
    "UnknownInfluxDBError",
    "UnknownServiceError",
]


class DatasetNotSupportedError(Exception):
    """Requested service does not support the requested dataset."""

    def __init__(self, service: str, dataset: str) -> None:
        msg = f"Service {service} does not support dataset {dataset}"
        super().__init__(msg)


class DiscoveryNotAvailableError(Exception):
    """Service discovery information is not available."""

    def __init__(self, path: str | Path) -> None:
        msg = f"Service discovery information ({path!s}) not found"
        super().__init__(msg)


class InvalidDiscoveryError(Exception):
    """Discovery information is malformed."""

    def __init__(self, label: str, exc: Exception) -> None:
        error = f"{type(exc).__name__}: {exc!s}"
        msg = f"Invalid discovery information for {label}: {error}"
        super().__init__(msg)


class TokenNotAvailableError(Exception):
    """No Gafaelfawr token is available."""


class UnknownDatasetError(Exception):
    """Requested dataset is not present in this environment."""

    def __init__(self, dataset: str) -> None:
        msg = f"Dataset {dataset} is not present in this environment"
        super().__init__(msg)


class UnknownInfluxDBError(Exception):
    """Requested dataset is not present in this environment."""

    def __init__(self, label: str) -> None:
        msg = f"InfluxDB database {label} is not present in this environment"
        super().__init__(msg)


class UnknownServiceError(Exception):
    """Requested service is not present in this environment."""

    def __init__(self, service: str) -> None:
        msg = f"Service {service} is not present in this environment"
        super().__init__(msg)
