import os
import warnings
from typing import Optional

import pyvo
import pyvo.auth.authsession
import requests
from deprecated import deprecated

from .utils import get_access_token


def _get_cutout_url() -> str:
    return os.getenv("EXTERNAL_INSTANCE_URL", "") + "/api/cutout"


def _get_datalink_url() -> str:
    return os.getenv("EXTERNAL_INSTANCE_URL", "") + "/api/datalink"


def _get_siav2_url() -> str:
    return os.getenv("EXTERNAL_INSTANCE_URL", "") + "/api/siav2"


def _get_tap_url(env_var: str, url: str) -> str:
    tapurl = os.getenv("EXTERNAL_" + env_var + "_URL")
    if not tapurl:
        tapurl = (os.getenv("EXTERNAL_INSTANCE_URL") or "") + (
            os.getenv(env_var + "_ROUTE") or "/api/" + url
        )
    return tapurl


def _get_auth() -> Optional[pyvo.auth.authsession.AuthSession]:
    tap_url = _get_tap_url("TAP", "tap")
    obstap_url = _get_tap_url("OBSTAP", "obstap")
    ssotap_url = _get_tap_url("SSOTAP", "ssotap")
    s = requests.Session()
    tok = get_access_token()
    if not tok:
        return None
    s.headers["Authorization"] = "Bearer " + tok
    auth = pyvo.auth.authsession.AuthSession()
    auth.credentials.set("lsst-token", s)
    auth.add_security_method_for_url(_get_cutout_url(), "lsst-token")
    auth.add_security_method_for_url(_get_datalink_url(), "lsst-token")
    auth.add_security_method_for_url(_get_siav2_url(), "lsst-token")
    auth.add_security_method_for_url(_get_siav2_url() + "/query", "lsst-token")
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


@deprecated(reason='Please use get_tap_service("tap")')
def get_catalog() -> pyvo.dal.TAPService:
    return get_tap_service("tap")


@deprecated(reason='Please use get_tap_service("obstap")')
def get_obstap_service() -> pyvo.dal.TAPService:
    return get_tap_service("obstap")


def get_siav2_service(*args: str) -> pyvo.dal.SIA2Service:
    return SIA2Service(_get_siav2_url(), _get_auth())


def get_tap_service(*args: str) -> pyvo.dal.TAPService:
    if len(args) == 0:
        warnings.warn(
            'get_tap_service() is deprecated, use get_tap_service("tap")',
            DeprecationWarning,
            stacklevel=2,
        )
        database = "tap"
    else:
        database = args[0]

    if database == "tap":
        tap_url = _get_tap_url("TAP", "tap")
    elif database == "obstap":
        tap_url = _get_tap_url("OBSTAP", "obstap")
    elif database == "ssotap":
        tap_url = _get_tap_url("SSOTAP", "ssotap")
    else:
        raise Exception(database + " is not a valid tap service")

    #
    # This is not ideal, but warning appears because require pyvo does
    # not register uws:Sync and uws:Async.  It's harmless.  The broadness
    # of the warning is unfortunately necessary since pyvo just uses
    # warnings.warn():
    # https://github.com/astropy/pyvo/blob/
    # 81a50d7fd24428f17104a075bc0e1ac661ed6ea0/pyvo/utils/xml/elements.py#L418
    #
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", category=UserWarning)
        ts = pyvo.dal.TAPService(tap_url, _get_auth())
    return ts


def retrieve_query(query_url: str) -> pyvo.dal.AsyncTAPJob:
    #
    # This is not ideal, but warning appears because require pyvo does
    # not register uws:Sync and uws:Async.  It's harmless.  The broadness
    # of the warning is unfortunately necessary since pyvo just uses
    # warnings.warn():
    # https://github.com/astropy/pyvo/blob/
    # 81a50d7fd24428f17104a075bc0e1ac661ed6ea0/pyvo/utils/xml/elements.py#L418
    #
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", category=UserWarning)
        atj = pyvo.dal.AsyncTAPJob(query_url, _get_auth())
    return atj
