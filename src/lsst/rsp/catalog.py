import functools
import os
import warnings

import pyvo
import pyvo.auth.authsession
import requests

from .utils import get_access_token
from typing import Optional


def deprecated(new_name=""):
    def deprecated(func):
        """This is a decorator which can be used to mark functions
        as deprecated. It will result in a warning being emitted
        when the function is used."""

        @functools.wraps(func)
        def new_func(*args, **kwargs):
            warnings.simplefilter(
                "always", DeprecationWarning
            )  # turn off filter
            if new_name:
                warnings.warn(
                    f"Call to deprecated function {func.__name__}.  "
                    + "This function may be removed at any point "
                    + "in the future.  "
                    + f"Please use {new_name} instead.",
                    category=DeprecationWarning,
                    stacklevel=2,
                )
            else:
                warnings.warn(
                    f"Call to deprecated function {func.__name__}.  "
                    + "This function may be removed at any point "
                    + "in the future.",
                    category=DeprecationWarning,
                    stacklevel=2,
                )
            warnings.simplefilter(
                "default", DeprecationWarning
            )  # reset filter
            return func(*args, **kwargs)

        return new_func

    return deprecated


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


@deprecated(new_name="get_tap_service")
def get_catalog() -> pyvo.dal.TAPService:
    return get_tap_service()


def retrieve_query(query_url) -> pyvo.dal.AsyncTAPJob:
    return pyvo.dal.AsyncTAPJob(query_url, _get_auth())
