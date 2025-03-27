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


def get_siav2_service(label: str, data_release: str) -> SIA2Service:
    """Construct an `SIA2Service` client."""
    # data_release determines the Data release, as we may have different
    # releases being served from the same server.
    # The label parameter here corresponds to RSP "kind" (i.e. "telescope",
    # "science", "staff")

    if label == "telescope":
        raise ValueError(label + " data not available at your location")

    sia_url = get_service_url(f"sia/{data_release}")
    session = get_pyvo_auth()
    if session:
        session.add_security_method_for_url(sia_url + "/query", "lsst-token")

    return SIA2Service(sia_url, session=session)
