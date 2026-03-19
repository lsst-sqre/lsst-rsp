"""Utility functions to get clients for TAP catalog search."""

import logging
from pathlib import Path
from typing import Any

import xmltodict
from httpx import AsyncClient

from ._discovery import get_service_url, list_datasets
from .utils import get_access_token


async def get_query_history(
    limit: int | None = None,
    *,
    discovery_v1_path: Path | None = None,
    token: str | None = None,
) -> list[str]:
    """Retrieve the UWS IDs of the user's most recent TAP queries.

    Parameters
    ----------
    limit
        Maximum number of query IDs to return.  If limit is not specified
        or limit<1, return all query IDs.
    discovery_v1_path
        Path to discovery information. This is intended for testing and should
        normally not be provided. The default is the expected path to
        discovery information within a Nublado notebook.
    token
        Authentication token. If not given, the authentication token will be
        obtained from the Nublado environment.

    Returns
    -------
    list of str
        A list of strings in the format :samp:`{dataset}:{query_id}`. For
        backwards compatibility, the caller should check if the return values
        contain a colon and, if not, assume they are just query IDs with the
        default TAP server.

    Notes
    -----
    Multiple datasets may share the same TAP service, which makes it
    impossible to determine which dataset a query is associated with. In this
    case, the queries will be returned multiple times, one for each dataset
    that shares that TAP service.
    """
    logging.basicConfig()
    logger = logging.getLogger(__name__)

    # Create a shared HTTP client used for the queries.
    if not token:
        token = get_access_token()
    client = AsyncClient(
        follow_redirects=True, headers={"Authorization": f"Bearer {token}"}
    )

    # Get the list of available datasets.
    discovery_args = {"discovery_v1_path": discovery_v1_path}
    datasets = list_datasets(**discovery_args)

    # For each dataset, retrieve the list of jobs.
    params = {"last": str(limit)} if limit and limit > 0 else {}
    jobs: list[tuple[str, dict[str, Any]]] = []
    for dataset in datasets:
        url = get_service_url("tap", dataset, **discovery_args)
        if not url:
            continue
        r = await client.get(url + "/async", params=params)
        if r.status_code >= 300:
            msg = f"Status {r.status_code} from {url}/async, skipping"
            logger.warning(msg)
            continue
        history = xmltodict.parse(r.text, force_list=("uws:jobref",))
        if jobrefs := history.get("uws:jobs", {}).get("uws:jobref"):
            jobs.extend((dataset, r) for r in jobrefs)

    # Collapse the jobs to a list, sorted by timestamp across all of the
    # datasets.
    epoch = "1970-01-01T00:00:00.000Z"
    job_ids = [
        f"{dataset}:{jobref['@id']}"
        for dataset, jobref in sorted(
            jobs,
            key=lambda e: (e[1].get("uws:creationTime", epoch), e[0]),
            reverse=True,
        )
    ]

    # Trim list to size, if requested, and return it.
    if limit and limit > 0:
        job_ids = job_ids[:limit]
    return job_ids
