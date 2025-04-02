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
    tok = get_access_token()
    if not tok:
        return None

    s = requests.Session()
    s.headers["Authorization"] = f"Bearer {tok}"

    auth = pyvo.auth.authsession.AuthSession()
    auth.credentials.set("lsst-token", s)

    service_endpoints = {
        "tap": get_service_url("tap"),
        "obstap": get_service_url("obstap"),
        "ssotap": get_service_url("ssotap"),
        "consdbtap": get_service_url("consdbtap"),
        "live": get_service_url("live"),
        "sia": get_service_url("sia"),
        "cutout": get_service_url("cutout"),
        "datalink": get_service_url("datalink"),
    }

    for name, url in service_endpoints.items():
        auth.add_security_method_for_url(url, "lsst-token")

        # Add standard subpaths for TAP services
        if name in ["tap", "obstap", "ssotap", "consdbtap", "live"]:
            for subpath in ["/sync", "/async", "/tables"]:
                auth.add_security_method_for_url(url + subpath, "lsst-token")

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
    spec = os.environ.get("JUPYTER_IMAGE_SPEC", "")
    hash_marker = "@sha256:"
    hash_pos = spec.find(hash_marker)
    if hash_pos == -1:
        return ""
    return spec[hash_pos + len(hash_marker) :]


def get_jupyterlab_config_dir() -> Path:
    """Return the directory where Jupyterlab configuration is stored.
    For single-python images, this will be `/opt/lsst/software/jupyterlab`.

    For images with split stack and Jupyterlab Pythons, it will be the
    value of `JUPYTERLAB_CONFIG_DIR`.

    Returns
    -------
    pathlib.Path
        Location where Jupyterlab configuration is stored.
    """
    return Path(
        os.environ.get(
            "JUPYTERLAB_CONFIG_DIR", "/opt/lsst/software/jupyterlab"
        )
    )


def get_runtime_mounts_dir() -> Path:
    """Return the directory where Nublado runtime info is mounted.  For
    single-python images, this will be `/opt/lsst/software/jupyterlab`.

    For images with split stack and Jupyterlab Pythons, it will be the
    value of `NUBLADO_RUNTIME_MOUNTS_DIR`.

    Returns
    -------
    pathlib.Path
        Location where the Nublado runtime information is mounted.
    """
    return Path(
        os.environ.get(
            "NUBLADO_RUNTIME_MOUNTS_DIR", "/opt/lsst/software/jupyterlab"
        )
    )


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
        return Path(tokenfile).read_text().strip()
    base_dir = get_runtime_mounts_dir()
    for candidate in (
        base_dir / "secrets" / "token",
        base_dir / "environment" / "ACCESS_TOKEN",
    ):
        with suppress(FileNotFoundError):
            return candidate.read_text().strip()

    # If we got here, we couldn't find a file. Return the environment variable
    # if set, otherwise the empty string.
    return os.environ.get("ACCESS_TOKEN", "")
