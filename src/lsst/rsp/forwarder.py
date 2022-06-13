import logging
from typing import Any, List, Optional

import maproxy.iomanager
import maproxy.proxyserver
import tornado.netutil


class Forwarder(maproxy.proxyserver.ProxyServer):
    """This creates a TCP proxy server running on a randomly-assigned
    dynamic local port.  Pass it the target host and port to construct it.
    """

    _ioloop = None
    _thread = None
    _logger = None
    _bind_addresses: List[Any] = []  # Fix this when we correct typing.

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        self._logger = logging.getLogger(__name__)
        self._logger.debug("Creating TCP Forwarder")
        sockets = tornado.netutil.bind_sockets(0, "")
        ioloop = None
        save_ioloop = None
        if "ioloop" in kwargs:
            self._logger.debug("IOLoop specified; saving current")
            ioloop = kwargs["ioloop"]
            save_ioloop = tornado.ioloop.IOLoop.current()
            if ioloop != save_ioloop:
                self._logger.debug("Switching IOLoop")
                ioloop.make_current()
            del kwargs["ioloop"]
        super().__init__(*args, **kwargs)
        self.add_sockets(sockets)
        self.bind_addresses = [x.getsockname()[:2] for x in sockets]
        self._ioloop = tornado.ioloop.IOLoop.current()
        if save_ioloop and save_ioloop != self._ioloop:
            self._logger.debug("Restoring IOLoop")
            save_ioloop.make_current()
        self._logger.debug("TCP Forwarder created")

    def get_ports(self) -> List[Any]:
        """Returns a list of the ports the Forwarder is listening to."""
        return list(set(x[1] for x in self.bind_addresses))

    def get_port(self) -> Optional[int]:
        """Returns the first port the Forwarder is listening to, or None."""
        rval = self.get_ports()
        if rval and len(rval) > 0:
            return rval[0]
        return None
