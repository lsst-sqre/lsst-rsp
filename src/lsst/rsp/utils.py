"""Utility functions for LSST JupyterLab notebook environment."""

import os
import urllib
from pathlib import Path
from typing import Any, Optional, Union

import bokeh.io

_NO_K8S = False

try:
    from kubernetes import client, config
    from kubernetes.client.rest import ApiException
    from kubernetes.config.config_exception import ConfigException
except ImportError:
    _NO_K8S = True


def format_bytes(n: int) -> str:
    """Format bytes as text

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

    (taken from dask.distributed, where it is not exported)
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
    """Utility function to return hostname or, failing that, "localhost"."""
    return os.environ.get("HOSTNAME") or "localhost"


def show_with_bokeh_server(obj: Any) -> None:
    """Method to wrap bokeh with proxy URL"""

    def jupyter_proxy_url(port: Optional[int] = None) -> str:
        """
        Callable to configure Bokeh's show method when a proxy must be
        configured.

        If port is None we're asking about the URL
        for the origin header.

        https://docs.bokeh.org/en/latest/docs/user_guide/jupyter.html
        """
        base_url = os.environ["EXTERNAL_INSTANCE_URL"]
        host = urllib.parse.urlparse(base_url).netloc

        # If port is None we're asking for the URL origin
        # so return the public hostname.
        if port is None:
            return host

        service_url_path = os.environ["JUPYTERHUB_SERVICE_PREFIX"]
        proxy_url_path = "proxy/%d" % port

        user_url = urllib.parse.urljoin(base_url, service_url_path)
        full_url = urllib.parse.urljoin(user_url, proxy_url_path)
        return full_url

    # The type: ignore is needed because the alternate form of notebook_url
    # (https://docs.bokeh.org/en/latest/docs/reference/io.html#bokeh.io.show)
    # isn't in bokeh's type hints.
    bokeh.io.show(obj=obj, notebook_url=jupyter_proxy_url)  # type:ignore


def get_pod() -> Optional[client.V1Pod]:
    """Get the Kubernetes object for the pod in which this is running.

    Returns
    -------
    kubernetes.client.V1Pod or None
        Kubernetes object for the pod in which this code is running, or `None`
        if not running inside Kubernetes or running without access to the
        Kubernetes API (the normal case for Nublado v3 and later).
    """
    if _NO_K8S:
        return None
    try:
        config.load_incluster_config()
    except ConfigException:
        # We have the K8S libraries, but we don't have in-cluster config.
        return None
    api = client.CoreV1Api()
    namespace = "default"
    try:
        with open(
            "/var/run/secrets/kubernetes.io/serviceaccount/namespace", "r"
        ) as f:
            namespace = f.readlines()[0]
    except FileNotFoundError:
        pass  # use 'default' as namespace
    try:
        pod = api.read_namespaced_pod(get_hostname(), namespace)
    except ApiException:
        # Well, that didn't work.
        return None
    return pod


def get_node() -> str:
    """Return the name of the current Kubernetes node.

    Returns
    -------
    str
        Name of the Kubernetes node on which this code is running, or the
        empty string if the node could not be determined.
    """
    node = os.environ.get("KUBERNETES_NODE_NAME")
    if node:
        return node

    # Fallback for Nublado v2, which got this information from the Kubernetes
    # API (and therefore had to have access to the Kubernetes API).
    pod = get_pod()
    if pod is not None:
        return pod.spec.node_name
    else:
        return ""


def get_digest() -> str:
    """Return the digest of the current Docker image.

    Returns
    -------
    str
        Digest of the Docker image this code is running inside, or the empty
        string if the digest could not be determined.
    """
    reference = os.environ.get("JUPYTER_IMAGE_SPEC", "")

    # Fallback for Nublado v2, which got this information from the Kubernetes
    # API (and therefore had to have access to the Kubernetes API).
    if not reference:
        pod = get_pod()
        if pod:
            try:
                reference = pod.status.container_statuses[0].image_id
            except Exception:
                pass

    try:
        # Reference looks like host/[project/]owner/repo@sha256:hash
        return (reference.split("@")[-1]).split(":")[-1]
    except Exception:
        return ""


def get_access_token(
    tokenfile: Optional[Union[str, Path]] = None, log: Optional[Any] = None
) -> str:
    """Determine the access token from the mounted location (nublado
    3/2) or environment (any).  Prefer the mounted version since it
    can be updated, while the environment variable stays at whatever
    it was when the process was started.  Return the empty string if
    the token cannot be determined.
    """
    tok = ""
    if tokenfile:
        # If a path was specified, trust it.
        tok = Path(tokenfile).read_text()
    else:
        jldir = "/opt/lsst/software/jupyterlab"
        # Try the default token paths: nublado3, then nublado2, then fall
        # back to the environment.
        tokenfiles = [
            f"{jldir}/secrets/token",
            f"{jldir}/environment/ACCESS_TOKEN",
        ]
        for tf in tokenfiles:
            token_path = Path(tf)
            try:
                tok = token_path.read_text()
                break
            except FileNotFoundError:
                pass
        if not tok:
            tok = os.environ.get("ACCESS_TOKEN", "")
    return tok
