"""Utility functions for IVOA clients."""

from pyvo.dal import SIA2Service
from pyvo.dal.adhoc import DatalinkResults
from pyvo.dal.sia2 import ObsCoreRecord

from .utils import get_pyvo_auth, get_service_url


def get_datalink_result(result: ObsCoreRecord) -> DatalinkResults:
    """Return the datalink part of a result."""
    return DatalinkResults.from_result_url(
        result.getdataurl(), session=get_pyvo_auth()
    )


def get_siav2_service(label: str) -> SIA2Service:
    """Construct an `SIA2Service` client."""
    # No matter what, we've only got one sia server per environment
    # so for now just do some checking.

    # However we may have multiple different endpoints
    # for different releases being served from the same server.
    # The label parameter here corresponds to the data release

    sia_url = get_service_url(f"sia/{label}")
    session = get_pyvo_auth()
    if session:
        session.add_security_method_for_url(sia_url + "/query", "lsst-token")

    return SIA2Service(sia_url, session=session)
