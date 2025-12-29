"""Collection of utilities for Rubin Science Platform notebooks."""

from importlib.metadata import PackageNotFoundError, version

from ._discovery import (
    InfluxDBCredentials,
    InfluxDBLocation,
    get_influxdb_credentials,
    get_influxdb_location,
    get_service_url,
    list_datasets,
    list_influxdb_labels,
)
from ._exceptions import (
    DiscoveryNotAvailableError,
    InvalidDiscoveryError,
    TokenNotAvailableError,
    UnknownDatasetError,
    UnknownInfluxDBError,
    UnknownServiceError,
)
from .catalog import (
    get_catalog,
    get_obstap_service,
    get_query_history,
    get_tap_service,
    retrieve_query,
)
from .client import RSPClient
from .log import IPythonHandler, forward_lsst_log
from .service import get_datalink_result, get_siav2_service
from .utils import (
    format_bytes,
    get_access_token,
    get_digest,
    get_hostname,
    get_node,
    get_pod,
)

__version__: str
"""The application version string of (PEP 440 / SemVer compatible)."""

try:
    __version__ = version(__name__)
except PackageNotFoundError:
    # package is not installed
    __version__ = "0.0.0"


__all__ = [
    "DatasetNotSupportedError",
    "DiscoveryNotAvailableError",
    "IPythonHandler",
    "InfluxDBCredentials",
    "InfluxDBLocation",
    "InvalidDiscoveryError",
    "RSPClient",
    "TokenNotAvailableError",
    "UnknownDatasetError",
    "UnknownInfluxDBError",
    "UnknownServiceError",
    "__version__",
    "format_bytes",
    "forward_lsst_log",
    "get_access_token",
    "get_catalog",
    "get_datalink_result",
    "get_digest",
    "get_hostname",
    "get_influxdb_credentials",
    "get_influxdb_location",
    "get_node",
    "get_obstap_service",
    "get_pod",
    "get_query_history",
    "get_service_url",
    "get_siav2_service",
    "get_tap_service",
    "list_datasets",
    "list_influxdb_labels",
    "retrieve_query",
]
