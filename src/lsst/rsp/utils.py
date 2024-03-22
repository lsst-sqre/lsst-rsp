"""Utility functions for LSST JupyterLab notebook environment."""

import os
from contextlib import suppress
from pathlib import Path
from typing import Any
from urllib.parse import urljoin

import pyvo
import requests
from deprecated import deprecated


def format_bytes(n: int) -> str:
    """Format bytes as text.

    Taken from ``dask.distributed``, where it is not exported.

    Examples
    --------
    >>> format_bytes(1)
    '1 B'
    >>> format_bytes(1234)
    '1.23 kB'
    >>> format_bytes(12345678)
    '12.35 MB'
    >>> format_bytes(1234567890)
    '1.23 GB'
    >>> format_bytes(1234567890000)
    '1.23 TB'
    >>> format_bytes(1234567890000000)
    '1.23 PB'
    """
    if n > 1e15:
        return "%0.2f PB" % (n / 1e15)
    if n > 1e12:
        return "%0.2f TB" % (n / 1e12)
    if n > 1e9:
        return "%0.2f GB" % (n / 1e9)
    if n > 1e6:
        return "%0.2f MB" % (n / 1e6)
    if n > 1e3:
        return "%0.2f kB" % (n / 1000)
    return "%d B" % n


def get_hostname() -> str:
    """Return hostname or, failing that, ``localhost``."""
    return os.environ.get("HOSTNAME") or "localhost"


def get_service_url(name: str, env_name: str | None = None) -> str:
    """Get our best guess at the URL for the requested service."""
    if not env_name:
        env_name = name.upper()

    url = os.getenv(f"EXTERNAL_{env_name}_URL")
    if url:
        return url

    base = os.getenv("EXTERNAL_INSTANCE_URL") or ""
    path = os.getenv(f"{env_name}_ROUTE") or f"api/{name}"
    return urljoin(base, path)


def get_pyvo_auth() -> pyvo.auth.authsession.AuthSession | None:
    """Create a PyVO-compatible auth object."""
    tap_url = get_service_url("tap")
    obstap_url = get_service_url("obstap")
    ssotap_url = get_service_url("ssotap")
    siav2_url = get_service_url("siav2")
    s = requests.Session()
    tok = get_access_token()
    if not tok:
        return None
    s.headers["Authorization"] = "Bearer " + tok
    auth = pyvo.auth.authsession.AuthSession()
    auth.credentials.set("lsst-token", s)
    auth.add_security_method_for_url(get_service_url("cutout"), "lsst-token")
    auth.add_security_method_for_url(get_service_url("datalink"), "lsst-token")
    auth.add_security_method_for_url(siav2_url, "lsst-token")
    auth.add_security_method_for_url(siav2_url + "/query", "lsst-token")
    auth.add_security_method_for_url(tap_url, "lsst-token")
    auth.add_security_method_for_url(tap_url + "/sync", "lsst-token")
    auth.add_security_method_for_url(tap_url + "/async", "lsst-token")
    auth.add_security_method_for_url(tap_url + "/tables", "lsst-token")
    auth.add_security_method_for_url(obstap_url, "lsst-token")
    auth.add_security_method_for_url(obstap_url + "/sync", "lsst-token")
    auth.add_security_method_for_url(obstap_url + "/async", "lsst-token")
    auth.add_security_method_for_url(obstap_url + "/tables", "lsst-token")
    auth.add_security_method_for_url(ssotap_url, "lsst-token")
    auth.add_security_method_for_url(ssotap_url + "/sync", "lsst-token")
    auth.add_security_method_for_url(ssotap_url + "/async", "lsst-token")
    auth.add_security_method_for_url(ssotap_url + "/tables", "lsst-token")
    return auth


@deprecated(
    reason="get_pod() always returns None in RSPs running Nubladov3 or later"
)
def get_pod() -> None:
    """Get the name of the running pod (deprecated, not functional).

    No longer useful.  Formerly used to return the Kubernetes object for the
    pod in which this code was running.
    """
    return


def get_node() -> str:
    """Return the name of the current Kubernetes node.

    Returns
    -------
    str
        Name of the Kubernetes node on which this code is running, or the
        empty string if the node could not be determined.
    """
    return os.environ.get("KUBERNETES_NODE_NAME", "")


def get_digest() -> str:
    """Return the digest of the current Docker image.

    Returns
    -------
    str
        Digest of the Docker image this code is running inside, or the empty
        string if the digest could not be determined.
    """
    return os.environ.get("JUPYTER_IMAGE_SPEC", "")


def get_access_token(
    tokenfile: str | Path | None = None, log: Any | None = None
) -> str:
    """Get the Gafaelfawr access token for the user.

    Determine the access token from the mounted location (nublado 3/2) or
    environment (any).  Prefer the mounted version since it can be updated,
    while the environment variable stays at whatever it was when the process
    was started.  Return the empty string if the token cannot be determined.
    """
    if tokenfile:
        return Path(tokenfile).read_text()
    base_dir = Path("/opt/lsst/software/jupyterlab")
    for candidate in (
        base_dir / "secrets" / "token",
        base_dir / "environment" / "ACCESS_TOKEN",
    ):
        with suppress(FileNotFoundError):
            return candidate.read_text()

    # If we got here, we couldn't find a file. Return the environment variable
    # if set, otherwise the empty string.
    return os.environ.get("ACCESS_TOKEN", "")
