"""Tests for RSPStartupErrror."""

import errno
import os

from lsst.rsp.startup.exceptions import RSPStartupError


def test_bad_environment() -> None:
    assert "NONEXISTENT_ENV_VAR" not in os.environ
    exc = RSPStartupError(200, None, "NONEXISTENT_ENV_VAR")
    assert exc.errno == 200
    assert exc.strerror == "Missing environment variable"
    assert exc.filename == "NONEXISTENT_ENV_VAR"
    assert exc.errorcode == "EBADENV"


def test_from_oserror() -> None:
    osexc = OSError(errno.EDQUOT, None, "/fake/huge-file")
    exc = RSPStartupError.from_os_error(osexc)
    assert exc.errno == errno.EDQUOT
    assert exc.strerror == os.strerror(errno.EDQUOT)
    assert exc.filename == "/fake/huge-file"
    assert exc.errorcode == "EDQUOT"
