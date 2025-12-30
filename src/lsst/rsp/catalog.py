"""Utility functions to get clients for TAP catalog search."""

import logging
import warnings
from pathlib import Path
from typing import Any

import pyvo
import xmltodict
from deprecated import deprecated

from ._discovery import get_service_url, list_datasets
from .client import RSPClient
from .utils import get_pyvo_auth, guess_service_url


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
        ignored.  If args is empty, defaults to "tap" (deprecated
        behavior).

    Notes
    -----
        This method will soon be deprecated in favor of ``get_service_url()``
    from ``_discovery``, which requires specifying a dataset as well as a
    service.
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
        tap_url = guess_service_url(database)
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
    limit: int | None = None, *, discovery_v1_path: Path | None = None
) -> list[str]:
    """Retrieve last ``limit`` query jobref ids.  If n is not specified,
    or limit<1, retrieve all query jobref ids.

    Parameters
    ----------
    limit
        Maximum number of query IDs to return.  If limit is not specified
        or limit<1, return all query IDs.
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
    datasets.reverse()
    # Some datasets share an endpoint.  In that case, we only want to get
    # the n most recent for a given endpoint, so we do some deduplication
    # here.  (So, for instance, if dp1 and dp02 share "/api/tap", what we
    # want is the n most recent from both of those put together, not the n
    # most recent from each.)
    #
    # It won't matter in that case whether we assign the query as having
    # belonged to dp1 or dp02, because it's the endpoint:query_id tuple
    # that is unique.
    #
    # The reverse() is on shaky grounds.  Thus far, in the service discovery
    # document, later datasets get added at the bottom.  Thus, we're going to
    # assume that for a duplicated endpoint, we want the *last* occurrence of
    # it because that is likely to be the most recent and therefore is likely
    # to be the one people probably are most likely to want to look at.
    client: dict[str, RSPClient] = {}
    seen_endpoints: set[str] = set()
    for ds in datasets:
        url = get_service_url("tap", ds, discovery_v1_path=discovery_v1_path)
        if url:
            if url not in seen_endpoints:
                seen_endpoints.add(url)
                client[ds] = RSPClient(url)

    params = {"last": f"{limit}"} if limit and limit > 0 else {}
    history: dict[str, Any] = {}
    jobs: list[dict[str, Any]] = []
    logging.basicConfig()
    logger = logging.getLogger(__name__)
    for ds, ds_client in client.items():
        resp = await ds_client.get("async", params=params)
        status = resp.status_code
        if status < 400:
            history[ds] = xmltodict.parse(
                resp.text, force_list=("uws:jobref",)
            )
        else:
            logger.warning(f"Job list request failed with status {status}")

    for ds, history_ds in history.items():
        if "uws:jobs" in history_ds:
            if "uws:jobref" in history_ds["uws:jobs"]:
                for entry in history_ds["uws:jobs"]["uws:jobref"]:
                    # Annotate with dataset name
                    entry["__dataset__"] = ds
                    jobs.append(entry)

    # It appears that uws:creationTime can be lexically sorted and will do
    # the right thing.  If it is somehow missing, we assign it the Unix
    # epoch (it should never be missing).
    jobs.sort(
        key=lambda x: x.get("uws:creationTime", "1970-01-01T00:00:00.000Z"),
        reverse=True,
    )

    # Trim list to size, if requested
    last_limit = jobs[:limit] if limit is not None and limit > 0 else jobs

    # Return list of dataset:query_id
    return [f"{x['__dataset__']}:{x['@id']}" for x in last_limit]
