import os
import warnings
from typing import Optional

import pyvo
from deprecated import deprecated

from .utils import get_pyvo_auth, get_service_url


@deprecated(reason='Please use get_tap_service("tap")')
def get_catalog() -> pyvo.dal.TAPService:
    return get_tap_service("tap")


@deprecated(reason='Please use get_tap_service("obstap")')
def get_obstap_service() -> pyvo.dal.TAPService:
    return get_tap_service("obstap")


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

    if database in ["tap", "obstap", "ssotap"]:
        tap_url = get_service_url(database)
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
        ts = pyvo.dal.TAPService(tap_url, get_pyvo_auth())
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
        atj = pyvo.dal.AsyncTAPJob(query_url, get_pyvo_auth())
    return atj
