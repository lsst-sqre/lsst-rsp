from deprecated import deprecated

import lsst.rsp


@deprecated(reason="Please use lsst.rsp.show_with_bokeh_server()")
def show_with_bokeh_server(obj):
    return lsst.rsp.show_with_bokeh_server(obj)
