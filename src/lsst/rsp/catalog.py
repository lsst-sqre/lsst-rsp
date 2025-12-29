"""Utility functions to get clients for TAP catalog search."""

import warnings
from pathlib import Path
from typing import Any

import httpx
import pyvo
import xmltodict
from deprecated import deprecated

from ._discovery import list_datasets
from .client import RSPClient
from .utils import get_pyvo_auth, get_service_url


@deprecated(reason='Please use get_tap_service("tap")')
def get_catalog() -> pyvo.dal.TAPService:
    """Call ``get_tap_service("tap")`` (deprecated alias)."""
    return get_tap_service("tap")


@deprecated(reason='Please use get_tap_service("live")')
def get_obstap_service() -> pyvo.dal.TAPService:
    """Call ``get_tap_service("live")`` (deprecated alias)."""
    return get_tap_service("live")


def get_tap_service(*args: str) -> pyvo.dal.TAPService:
    """Construct a TAP service instance for the requested TAP service.

    Parameters
    ----------
    args
        First arg is the name of the requested TAP service.  The rest are
        ignored.  If args is the empty list, "tap" is assumed.
    """
    if len(args) == 0:
        warnings.warn(
            'get_tap_service() is deprecated, use get_tap_service("tap")',
            DeprecationWarning,
            stacklevel=2,
        )
        database = "tap"
    else:
        database = args[0]

    # We renamed the name of the TAP service from obstap
    # to live
    if database == "obstap":
        database = "live"

    if database in ("live", "tap", "ssotap", "consdbtap"):
        tap_url = get_service_url(database)
    else:
        raise ValueError(f"{database} is not a valid tap service")

    # This is not ideal, but warning appears because require pyvo does
    # not register uws:Sync and uws:Async.  It's harmless.  The broadness
    # of the warning is unfortunately necessary since pyvo just uses
    # warnings.warn():
    #
    # https://github.com/astropy/pyvo/blob/
    # 81a50d7fd24428f17104a075bc0e1ac661ed6ea0/pyvo/utils/xml/elements.py#L418
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", category=UserWarning)
        return pyvo.dal.TAPService(tap_url, session=get_pyvo_auth())


def retrieve_query(query_url: str) -> pyvo.dal.AsyncTAPJob:
    """Retrieve job corresponding to a particular query URL.

    Parameters
    ----------
    query_url
        URL of endpoint for particular TAP service.
    """
    # This is not ideal, but warning appears because require pyvo does
    # not register uws:Sync and uws:Async.  It's harmless.  The broadness
    # of the warning is unfortunately necessary since pyvo just uses
    # warnings.warn():
    #
    # https://github.com/astropy/pyvo/blob/
    # 81a50d7fd24428f17104a075bc0e1ac661ed6ea0/pyvo/utils/xml/elements.py#L418
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", category=UserWarning)
        return pyvo.dal.AsyncTAPJob(query_url, session=get_pyvo_auth())


async def get_query_history(
    n: int | None = None, *, discovery_v1_path: Path | None = None
) -> list[str]:
    """Retrieve last n query jobref ids.  If n is not specified, or n<1,
    retrieve all query jobref ids.

    Parameters
    ----------
    n
        Maximum number of query IDs to return.  If n is not specified or n<1,
        return all query IDs.
    discovery_v1_path
        Path to discovery information. This is intended for testing and should
        normally not be provided. The default is the expected path to
        discovery information within a Nublado notebook.

    Returns
    -------
    list[str]
        A list of strings in the format dataset:query_id.

    Notes
    -----
    This formerly assumed "/api/tap"; it no longer does.  The way we're
    handling this, and the transition between the two, is that we will do the
    last n jobref ids across all datasets found in the discovery document.

    What we will return is a list of strings (still) where the string returned
    is dataset:query_id.  Then the caller must check whether there is a
    colon in the returned value, and use that to resolve the correct endpoint
    to send the query to.  If no colon exists, it's at "/api/tap".
    """
    datasets = list_datasets(discovery_v1_path=discovery_v1_path)
    # Some datasets share an endpoint.  In that case, we only want to get
    # the n most recent for a given endpoint, so we do some deduplication
    # here.  (So, for instance, if dp1 and dp02 share "/api/tap", what we
    # want is the n most recent from both of those put together, not the n
    # most recent from each.)
    #
    # It won't matter in that case whether we assign the query as having
    # belonged to dp1 or dp02, because it's the endpoint:query_id tuple
    # that is unique.
    client: dict[str, RSPClient] = {}
    seen_endpoints: set[str] = set()
    for ds in datasets:
        url = get_service_url("tap", ds)
        if url:
            if url not in seen_endpoints:
                seen_endpoints.add(url)
                client[ds] = RSPClient(url)

    params: dict[str, str] = {}
    params = {"last": f"{n}"} if n and n > 0 else {}
    resp: dict[str, httpx.Response] = {}
    history: dict[str, Any] = {}
    qlist: list[dict[str, Any]] = []
    for ds, ds_client in client.items():
        resp[ds] = await ds_client.get("async", params=params)
        history[ds] = xmltodict.parse(
            resp[ds].text, force_list=("uws:jobref",)
        )

    for ds, history_ds in history.items():
        if "uws:jobs" in history_ds:
            if "uws:jobref" in history_ds["uws:jobs"]:
                for entry in history_ds["uws:jobs"]["uws:jobref"]:
                    # Annotate with dataset name
                    entry["__uws:dataset"] = ds
                    qlist.append(entry)

    # It appears that uws:creationTime can be lexically sorted and will do
    # the right thing.
    qlist.sort(key=lambda x: x["uws:creationTime"], reverse=True)

    # Trim list to size, if requested
    last_n = qlist[:n] if n is not None and n > 0 else qlist

    # Return list of dataset:query_id
    return [f"{x['__uws:dataset']}:{x['@id']}" for x in last_n]
