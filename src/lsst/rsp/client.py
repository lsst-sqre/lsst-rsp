"""Client for other services running in the same RSP instance."""

import logging
from urllib.parse import ParseResult, urlparse, urlunparse

import httpx

from .utils import get_access_token, get_runtime_mounts_dir


class RSPClient(httpx.AsyncClient):
    """Configured client for other services in the RSP.

    It uses knowledge present in the Lab instance it's running in to
    configure token authentication and a base URL.
    """

    def __init__(
        self, service_endpoint: str, token: str | None = None
    ) -> None:
        # Accept a passed token.  This can be useful, in conjunction with
        # forcing service_endpoint to be somewhere in some other RSP, for
        # making cross-RSP calls.
        if token is None:
            token = get_access_token()
        jupyterlab_dir = get_runtime_mounts_dir()
        instance_url = (
            (jupyterlab_dir / "environment" / "EXTERNAL_INSTANCE_URL")
            .read_text()
            .strip()
        )
        parsed_endpoint = urlparse(service_endpoint)
        parsed_instance = urlparse(instance_url)
        if parsed_endpoint.scheme:
            # We expect people to be feeding this a client based on the
            # results of Repertoire discovery, which will yield a full URL.
            # That will have both a scheme and a netloc (in urlparse() terms).
            #
            # If the netloc doesn't match (possibly with an "nb" in
            # front of it, which is true for Nublado with user domains
            # enabled) then warn the user but keep going.  Likewise
            # for the scheme, which must match exactly.  It's possible they
            # are intentionally making a call to a different RSP instance.
            if parsed_endpoint.scheme != parsed_instance.scheme or (
                parsed_endpoint.netloc != parsed_instance.netloc
                and f"nb.{parsed_endpoint.netloc}" != parsed_instance.netloc
            ):
                logger = logging.getLogger(__name__)
                logger.warning(
                    f"'{service_endpoint}' does not match '{instance_url}'"
                )
        else:
            # This is how the client was traditionally constructed, with just
            # a path.
            parsed_endpoint = ParseResult(
                scheme=parsed_instance.scheme,
                netloc=parsed_instance.netloc,
                path=parsed_endpoint.path,
                params=parsed_endpoint.params,
                query=parsed_endpoint.query,
                fragment=parsed_endpoint.fragment,
            )
        # Turn it back into a string, with scheme and netloc prepended if
        # necessary.
        service_root = urlunparse(parsed_endpoint)
        http_headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        }
        super().__init__(
            base_url=service_root, follow_redirects=True, headers=http_headers
        )
