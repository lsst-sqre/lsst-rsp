"""All of this stuff moved between JL2 and JL3.  Export these functions and
methods again, but with deprecated warnings so people know how to use them
correctly.
"""
from deprecated import deprecated

import lsst.rsp

from .utils import get_node


@deprecated(reason="Please use lsst.rsp.format_bytes()")
def format_bytes(n):
    return lsst.rsp.format_bytes(n)


@deprecated(reason="Please use lsst.rsp.get_tap_service()")
def get_catalog():
    return lsst.rsp.get_tap_service()


@deprecated(reason="Please use lsst.rsp.get_tap_service()")
def get_tap_service():
    return lsst.rsp.get_tap_service()


@deprecated(reason="Please use lsst.rsp.retrieve_query()")
def retrieve_query(query_url):
    return lsst.rsp.retrieve_query(query_url)


@deprecated(reason="Please use lsst.rsp.get_hostname()")
def get_hostname():
    return lsst.rsp.get_hostname()


@deprecated(reason="Please use lsst.rsp.show_with_bokeh_server()")
def show_with_bokeh_server(obj):
    return lsst.rsp.show_with_bokeh_server(obj)


@deprecated(reason="Please use lsst.rsp.Forwarder")
class Forwarder(lsst.rsp.Forwarder):
    def __init__(self, args, **kwargs):
        return super().__init__()


__all__ = [
    Forwarder,
    format_bytes,
    get_catalog,
    get_node,
    get_tap_service,
    retrieve_query,
    get_hostname,
    show_with_bokeh_server,
]
