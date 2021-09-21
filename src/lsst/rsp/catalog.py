import os
from typing import Optional

import pyvo
import pyvo.auth.authsession
import requests
from deprecated import deprecated

from .utils import get_access_token


def _get_tap_url() -> str:
    tapurl = os.getenv("EXTERNAL_TAP_URL")
    if not tapurl:
        tapurl = (os.getenv("EXTERNAL_INSTANCE_URL") or "") + (
            os.getenv("TAP_ROUTE") or "/api/tap"
        )
    return tapurl


def _get_auth() -> Optional[pyvo.auth.authsession.AuthSession]:
    tap_url = _get_tap_url()
    s = requests.Session()
    tok = get_access_token()
    if not tok:
        return None
    s.headers["Authorization"] = "Bearer " + tok
    auth = pyvo.auth.authsession.AuthSession()
    auth.credentials.set("lsst-token", s)
    auth.add_security_method_for_url(tap_url, "lsst-token")
    auth.add_security_method_for_url(tap_url + "/sync", "lsst-token")
    auth.add_security_method_for_url(tap_url + "/async", "lsst-token")
    auth.add_security_method_for_url(tap_url + "/tables", "lsst-token")
    return auth


def get_tap_service() -> pyvo.dal.TAPService:
    return pyvo.dal.TAPService(_get_tap_url(), _get_auth())


@deprecated(reason="Please use get_tap_service()")
def get_catalog() -> pyvo.dal.TAPService:
    return get_tap_service()


def retrieve_query(query_url) -> pyvo.dal.AsyncTAPJob:
    return pyvo.dal.AsyncTAPJob(query_url, _get_auth())
