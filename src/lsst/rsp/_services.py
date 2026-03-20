"""Service discovery and authentication for RSP clients."""

import json
from pathlib import Path
from typing import ClassVar

from ._exceptions import (
    DiscoveryNotAvailableError,
    InvalidDiscoveryError,
    TokenNotAvailableError,
    UnknownDatasetError,
    UnknownServiceError,
)
from .utils import get_access_token

__all__ = ["RSPServices"]


class RSPServices:
    """Look up Rubin Science Platform services and construct clients.

    Provides an API to discovery the URLs of services, build clients that send
    appropriate authentication credentials to service requests, and build PyVO
    clients for services where appropriate.

    This class may be used either inside Nublado notebooks, in which case
    service discovery and authentication is automatic, or outside of the Rubin
    Science Platform. In the latter case, the caller will have to provide
    service discovery and authentication credentials for the RSP instance they
    wish to access.

    Parameters
    ----------
    dataset
        Label for the dataset that will be accessed. Create a separate
        instance of `RSPServices` for each dataset you wish to use.
    discovery_v1_path
        Path to discovery information. This is intended for testing and should
        normally not be provided. The default is the expected path to
        discovery information within a Nublado notebook.
    token
        Authentication token to use. This parameter can and should be omitted
        when called from inside a Nublado notebook.

    Raises
    ------
    DiscoveryNotAvailableError
        Raised if no service discovery information is available.
    InvalidDiscoveryError
        Raised if the discovery information has an invalid syntax.
    TokenNotAvailableError
        Raised if there is no Gafaelfawr token available.
    UnknownDatasetError
        Raised if this dataset is not present in the environment.
    """

    _DISCOVERY_PATH: ClassVar[Path] = Path("/etc/nublado/discovery/v1.json")
    """Path to static service discovery information in a Nublado notebook."""

    def __init__(
        self,
        dataset: str,
        *,
        discovery_v1_path: Path | None = None,
        token: str | None = None,
    ) -> None:
        self._dataset = dataset
        self._token = token or get_access_token()
        if not self._token:
            raise TokenNotAvailableError("No access token available")

        # Load discovery information for the specified dataset.
        path = discovery_v1_path or self._DISCOVERY_PATH
        try:
            discovery = json.loads(path.read_text())
        except FileNotFoundError as e:
            raise DiscoveryNotAvailableError(path) from e
        except json.JSONDecodeError as e:
            raise InvalidDiscoveryError(e) from e
        dataset_info = discovery.get("datasets", {}).get(dataset)
        if not dataset_info:
            raise UnknownDatasetError(dataset)
        self._discovery = dataset_info

    def get_service_url(self, service: str) -> str:
        """Get the API URL for a service.

        Parameters
        ----------
        service
            Name of the service.

        Returns
        -------
        str
            Base URL for the service API.

        Raises
        ------
        UnknownServiceError
            Raised if this service is not provided for this dataset.
        """
        url = self._discovery.get("services", {}).get(service, {}).get("url")
        if not url:
            raise UnknownServiceError(service, self._dataset)
        return url
