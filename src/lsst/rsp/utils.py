"""Utility functions for LSST JupyterLab notebook environment
"""
import os
import urllib
from pathlib import Path
from typing import Optional

import bokeh.io
from kubernetes import client, config


def format_bytes(n) -> str:
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


def show_with_bokeh_server(obj):
    """Method to wrap bokeh with proxy URL"""

    def jupyter_proxy_url(port):
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

    bokeh.io.show(obj, notebook_url=jupyter_proxy_url)


def get_pod():
    """Get pod record.  Throws an error if you're not running in a cluster."""
    config.load_incluster_config()
    api = client.CoreV1Api()
    namespace = "default"
    with open(
        "/var/run/secrets/kubernetes.io/serviceaccount/namespace", "r"
    ) as f:
        namespace = f.readlines()[0]
    pod = api.read_namespaced_pod(get_hostname(), namespace)
    return pod


def get_node() -> str:
    """Extract node name from pod."""
    return get_pod().spec.node_name


def get_digest() -> str:
    """Extract image digest from pod, if we can."""
    digest = ""
    try:
        img_id = get_pod().status.container_statuses[0].image_id
        # host/owner/repo@sha256:hash
        return (img_id.split("@")[-1]).split(":")[-1]
    except Exception:
        return ""  # We will just return the empty string
    return digest


def get_access_token(tokenfile=None, log=None) -> Optional[str]:
    """Determine the access token from the mounted configmap (nublado2),
    secret (nublado1), or environment (either).  Prefer the mounted version
    since it can be updated, while the environment variable stays at whatever
    it was when the process was started."""
    tok = None
    if tokenfile:
        # If a path was specified, trust it.
        tok = Path(tokenfile).read_text()
        tried_path = tokenfile
    else:
        # Try the default token paths, nublado2 first, then nublado1
        n2_tokenfile = "/opt/lsst/software/jupyterlab/environment/ACCESS_TOKEN"
        tried_path = n2_tokenfile
        token_path = Path(n2_tokenfile)
        try:
            tok = token_path.read_text()
        except Exception:
            # OK, it's not mounted.  Fall back to the environment.
            pass
    if not tok:
        tok = os.environ.get("ACCESS_TOKEN", None)
    if not tok:
        raise ValueError(
            f"Could not find token in env:ACCESS_TOKEN nor in {tried_path}"
        )
    return tok
