"""
Collection of utilities, formerly in rsp_jupyter_utils.lab and
rsp_jupyter_utils.helper
"""
from importlib.metadata import PackageNotFoundError, version

from .catalog import get_catalog, get_tap_service, retrieve_query
from .forwarder import Forwarder
from .log import IPythonHandler, forward_lsst_log
from .utils import (
    format_bytes,
    get_access_token,
    get_digest,
    get_hostname,
    get_node,
    get_pod,
    show_with_bokeh_server,
)

__version__: str
"""The application version string of (PEP 440 / SemVer compatible)."""

try:
    __version__ = version(__name__)
except PackageNotFoundError:
    # package is not installed
    __version__ = "0.0.0"


__all__ = [
    "__version__",
    "Forwarder",
    "IPythonHandler",
    "format_bytes",
    "forward_lsst_log",
    "get_access_token",
    "get_catalog",
    "get_digest",
    "get_node",
    "get_pod",
    "get_tap_service",
    "retrieve_query",
    "get_hostname",
    "show_with_bokeh_server",
]
