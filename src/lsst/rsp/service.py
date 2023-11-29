import pyvo
from pyvo.dal import SIA2Service

from .utils import get_pyvo_auth, get_service_url

def get_siav2_service(*args: str) -> pyvo.dal.SIA2Service:
    if len(args) == 0:
        ds = "dp0.2"
    elif args == "latiss":
        ds = "latiss"

    return SIA2Service(get_service_url("siav2"), get_pyvo_auth())
