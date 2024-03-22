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
    if label != "staff":
        raise ValueError(label + " data not available at your location")

    # No matter what, we've only got one sia server per environment
    # so for now just do some checking.
    return SIA2Service(get_service_url("siav2"), get_pyvo_auth())
