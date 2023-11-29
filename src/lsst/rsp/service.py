import os

import pyvo
from pyvo.dal import SIA2Service

from .utils import get_pyvo_auth, get_service_url


LSST_CLOUD = [
    "https://data.lsst.cloud",
    "https://data-int.lsst.cloud", 
    "https://data-dev.lsst.cloud"
]

USDF = [
    "https://usdf-rsp.slac.stanford.edu/",
    "https://usdf-rsp-dev.slac.stanford.edu/"
]


def get_siav2_service(*args: str) -> SIA2Service:
    """Return a configured SIA2Service object that is ready to use."""
    fqdn = os.environ["EXTERNAL_INSTANCE_URL"]

    if len(args) == 0:
        # Use the default for each environment
        if fqdn in LSST_CLOUD:
            label = "dp0.2"
        elif fqdn in USDF:
            label = "latiss"
        else:
            raise Exception("Unknown environment" + fqdn)
    else:
        label = args[0]

    # If a label is passed, check that.
    if label not in ["dp0.2", "latiss"]:
        raise Exception(label + " is not a valid siav2 label")

    if label == "latiss" and fqdn not in USDF:
        raise Exception(label + " data not available at your location")
    if label == "dp0.2" and fqdn not in LSST_CLOUD:
        raise Exception(label + " data not available at your location")

    # No matter what, we've only got one sia server per environment
    # so for now just do some checking.
    return SIA2Service(get_service_url("siav2"), get_pyvo_auth())
