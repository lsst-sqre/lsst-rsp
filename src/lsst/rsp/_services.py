"""Service discovery and authentication for RSP clients."""

import json
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path
from typing import Any, ClassVar, override

import requests
from pyvo.auth import AuthSession
from pyvo.dal import AsyncTAPJob, ObsCoreRecord, SIA2Service, TAPService
from pyvo.dal.adhoc import DatalinkResults
from pyvo.utils.http import create_session
from requests import PreparedRequest, RequestException
from requests.auth import AuthBase
from requests.exceptions import InvalidJSONError

try:
    _lsst_rsp_version = version("lsst-rsp")
except PackageNotFoundError:
    _lsst_rsp_version = "unknown"

from ._exceptions import (
    DiscoveryNotAvailableError,
    InvalidDiscoveryError,
    TokenNotAvailableError,
    UnknownDatasetError,
    UnknownServiceError,
)
from .utils import get_access_token

__all__ = ["RSPDiscovery"]


class _RSPAuth(AuthBase):
    """Python requests authentication class for the RSP.

    Send the Gafaelfawr bearer token only to URLs matching or beneath the list
    of URLs passed to the constructor of the authentication class.

    Parameters
    ----------
    token
        Gafaelfawr token to send.
    urls
        Set of URLs to which authentication should be sent.
    """

    def __init__(self, token: str, urls: set[str]) -> None:
        self._token = token
        self._urls = urls
        self._prefixes = tuple(u.rstrip("/") + "/" for u in urls)

    @override
    def __call__(self, request: PreparedRequest) -> PreparedRequest:
        if not request.url:
            return request
        if request.url in self._urls or request.url.startswith(self._prefixes):
            request.headers["Authorization"] = f"Bearer {self._token}"
        return request


class RSPDiscovery:
    """Look up Rubin Science Platform services and construct clients.

    Provides an API to discover the URLs of services, build clients that send
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
    discovery_url
        Base URL to discovery services. This should not be provided when
        running inside Nublado. It allows the class to be used outside of
        Nublado and pointed to a particular instance of the Rubin Science
        Platform. If given, the URL should be the base URL for the Repertoire
        service.
    discovery_v1_path
        Path to discovery information. This is intended for testing and should
        normally not be provided. The default is the expected path to
        discovery information within a Nublado notebook. If ``discovery_url``
        is given, this parameter is ignored.
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
        discovery_url: str | None = None,
        discovery_v1_path: Path | None = None,
        token: str | None = None,
    ) -> None:
        self._dataset = dataset
        self._token = token or get_access_token()
        if not self._token:
            raise TokenNotAvailableError("No access token available")
        self._pyvo_auth: AuthSession | None = None

        # Get the discovery information for the given dataset.
        if discovery_url:
            discovery = self._fetch_discovery(discovery_url)
        else:
            path = discovery_v1_path or self._DISCOVERY_PATH
            discovery = self._read_discovery(path)
        dataset_info = discovery.get("datasets", {}).get(dataset)
        if dataset_info is None:
            raise UnknownDatasetError(dataset)
        self._discovery = dataset_info

    def get_datalink_results(self, result: ObsCoreRecord) -> DatalinkResults:
        """Return the DataLink part of an ObsCore record.

        This is the record returned by, for example, an SIAv2 query. The
        resulting object can be used to follow DataLink pointers.

        Parameters
        ----------
        result
            Result record.

        Returns
        -------
        DatalinkResults
            Results object that can be used to follow DataLink pointers.
        """
        return DatalinkResults.from_result_url(
            result.getdataurl(), session=self._get_pyvo_auth()
        )

    def get_service_url(
        self, service: str, *, version: str | None = None
    ) -> str:
        """Get the API URL for a service.

        Parameters
        ----------
        service
            Name of the service.
        version
            Optional API version. If given, get the specific base URL of that
            version of the API instead of the base URL of the service as a
            whole.

        Returns
        -------
        str
            Base URL for the service API.

        Raises
        ------
        UnknownServiceError
            Raised if this service is not provided for this dataset.
        """
        data = self._discovery.get("services", {}).get(service, {})
        if version:
            url = data.get("versions", {}).get(version, {}).get("url")
        else:
            url = data.get("url")
        if not url:
            raise UnknownServiceError(service, self._dataset)
        return url

    def get_session(self) -> requests.Session:
        """Get a requests session that sends a token only to service URLs.

        The resulting requests session can be used to make any HTTP requests,
        and will include the bearer token in the ``Authorization`` header only
        if the request goes to a URL under one of the base service URLs.

        Returns
        -------
        requests.Session
            Requests session configured to send an authentication token if
            the request is to an RSP service.
        """
        session = requests.Session()
        session.headers["User-Agent"] = self._build_user_agent(session)
        session.auth = _RSPAuth(self._token, self._get_all_service_urls())
        return session

    def get_sia_client(self) -> SIA2Service:
        """Get a configured PyVO SIAv2 client for this dataset.

        Returns
        -------
        SIA2Service
            PyVO SIAv2 client configured with an appropriate base URL and
            authentication credentials.

        Raises
        ------
        UnknownServiceError
            Raised if there is no SIA2 service for this dataset.
        """
        url = self.get_service_url("sia")
        return SIA2Service(url, session=self._get_pyvo_auth())

    def get_tap_client(self) -> TAPService:
        """Get a configured PyVO TAP client for this dataset's TAP service.

        Returns
        -------
        TAPService
            PyVO TAP client configured with an appropriate base URL and
            authentication credentials.

        Raises
        ------
        UnknownServiceError
            Raised if there is no TAP service for this dataset.
        """
        url = self.get_service_url("tap")
        return TAPService(url, session=self._get_pyvo_auth())

    def get_tap_job(self, url: str) -> AsyncTAPJob:
        """Retrieve a TAP UWS job with appropriate authentication.

        This can be used to retrieve the results of a previous TAP query if
        one has the URL to the UWS job in the TAP server.

        Parameters
        ----------
        url
            URL of the TAP job. In PyVO, this is the value of ``job.url``
            after successfully submitting an async TAP job using the
            ``submit_job`` method.

        Returns
        -------
        AsyncTAPJob
            Object representing the underlying job, which can be used to
            retrieve its results or other metadata.
        """
        return AsyncTAPJob(url, session=self._get_pyvo_auth())

    def _build_user_agent(self, session: requests.Session) -> str:
        """Construct a ``User-Agent`` header.

        Start from the ``User-Agent`` header in the session, if any, and
        prepend the version of the lsst.rsp module.

        Parameters
        ----------
        session
            The requests session.

        Returns
        -------
        str
            ``User-Agent`` string to use.
        """
        user_agent = session.headers.get("User-Agent", "")
        if isinstance(user_agent, bytes):
            user_agent = user_agent.decode()
        return f"lsst-rsp/{_lsst_rsp_version} {user_agent}".strip()

    def _get_all_service_urls(self) -> set[str]:
        """Return all service URLs for the configured dataset."""
        urls = set()
        for service in self._discovery.get("services", {}).values():
            if url := service.get("url"):
                urls.add(url)
        return urls

    def _get_pyvo_auth(self) -> AuthSession:
        """Construct a PyVO authentication session.

        This can be passed into PyVO objects to configure subsequent requests
        to send the Gafaelfawr token as a bearer token.

        Returns
        -------
        AuthSession
            PyVO authentication session.
        """
        if self._pyvo_auth:
            return self._pyvo_auth

        # We haven't built a PyVO auth session yet, so do so.
        session = create_session()
        session.headers["Authorization"] = f"Bearer {self._token}"
        session.headers["User-Agent"] = self._build_user_agent(session)
        auth = AuthSession()
        auth.credentials.set("lsst-token", session)

        # Configure PyVO to use these credentials for every URL found in the
        # discovery information for the dataset. This assumes all URLs can be
        # treated as URL prefixes and it's safe to send credentials to any
        # URLs below that prefix.
        for url in self._get_all_service_urls():
            auth.add_security_method_for_url(url, "lsst-token")

        # Return the configured authentication session.
        self._pyvo_auth = auth
        return auth

    def _fetch_discovery(self, url: str) -> dict[str, Any]:
        """Fetch discovery information from Repertoire.

        Parameters
        ----------
        url
            Base URL of the Repertoire service.

        Returns
        -------
        dict
            Discovery information as a nested dictionary.
        """
        try:
            with requests.Session() as session:
                session.headers["User-Agent"] = self._build_user_agent(session)
                r = session.get(url.rstrip("/") + "/discovery", timeout=10)
                r.raise_for_status()
                return r.json()
        except InvalidJSONError as e:
            raise InvalidDiscoveryError(e) from e
        except RequestException as e:
            raise DiscoveryNotAvailableError(e) from e

    def _read_discovery(self, path: Path) -> dict[str, Any]:
        """Read discovery information from an on-disk path.

        Parameters
        ----------
        path
            Path to the discovery information.

        Returns
        -------
        dict
            Discovery information as a nested dictionary.
        """
        try:
            return json.loads(path.read_text())
        except FileNotFoundError as e:
            raise DiscoveryNotAvailableError(e) from e
        except json.JSONDecodeError as e:
            raise InvalidDiscoveryError(e) from e
