from deprecated import deprecated

import lsst.rsp


@deprecated(reason="Please use lsst.rsp.get_tap_service()")
def get_catalog():
    return lsst.rsp.get_tap_service()


@deprecated(reason="Please use lsst.rsp.retrieve_query()")
def retrieve_query(query_url):
    return lsst.rsp.retrieve_query(query_url)
