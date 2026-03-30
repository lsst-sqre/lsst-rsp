"""Version number for :py:mod`lsst.rsp`.

This is broken into a separate internal module because it's also used in
service discovery to add to ``User-Agent``.
"""

from importlib.metadata import PackageNotFoundError, version

__version__: str
"""The application version string of (PEP 440 / SemVer compatible)."""

try:
    __version__ = version("lsst.rsp")
except PackageNotFoundError:
    # package is not installed
    __version__ = "0.0.0"
