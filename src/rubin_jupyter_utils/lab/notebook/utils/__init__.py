from deprecated import deprecated

import lsst.rsp


@deprecated(reason="Please use lsst.rsp.get_node()")
def get_node():
    return lsst.rsp.get_node()
