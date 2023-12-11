from pyvo.dal import SIA2Service

from .utils import get_pyvo_auth, get_service_url


def get_siav2_service(label: str) -> SIA2Service:
    """Return a configured SIA2Service object that is ready to use."""
    if label != "staff":
        raise Exception(label + " data not available at your location")

    # No matter what, we've only got one sia server per environment
    # so for now just do some checking.
    return SIA2Service(get_service_url("siav2"), get_pyvo_auth())
