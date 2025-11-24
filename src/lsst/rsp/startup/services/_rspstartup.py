"""Base class for both the init container and the lab runner class.
Has common setup and methods we want to use in each.
"""

import os
import shutil
from abc import ABC, abstractmethod
from pathlib import Path

import structlog

from ...constants import APP_NAME
from ...storage.command import Command
from ...storage.logging import configure_logging


class _RSPStartup(ABC):
    """Common elements for the startup in init container and Lab runner."""

    def __init__(self) -> None:
        # We start with a copy of our own environment
        self._env = os.environ.copy()
        self._debug = bool(self._env.get("DEBUG", ""))
        configure_logging(debug=self._debug)
        self._logger = structlog.get_logger(APP_NAME)
        self._broken = False
        # If no home, use /tmp?  It won't work but at least if we create
        # stuff there it will be harmless, and the user will get a message
        # indicating what's wrong.
        #
        # This should be a very difficult error to produce if the Lab is
        # started by the Nublado controller.
        self._home = Path(self._env.get("HOME", "/tmp"))
        self._cmd = Command(ignore_fail=True, logger=self._logger)

    @abstractmethod
    async def go(self) -> None:
        """Execute whatever startup tasks there are."""
        ...

    async def _test_for_space(self) -> None:
        cachefile = self._home / ".cache" / "1mb.txt"
        try:
            await self._write_a_megabyte(cachefile)
        except OSError as exc:
            await self._set_abnormal_startup(exc)
            self._logger.warning("Could not write 1MB of text")
            await self._try_emergency_cleanup()
            try:
                # Did that clear enough room?  If so, reset self._broken.
                await self._write_a_megabyte(cachefile)
                await self._clear_abnormal_startup()
            except OSError:
                pass  # Nope, stay broken.

    async def _write_a_megabyte(self, cachefile: Path) -> None:
        # Try to write a 1M block, which should be enough to start the lab.
        sixteen = "0123456789abcdef"
        mega = sixteen * 64 * 1024

        parent = cachefile.parent
        parent.mkdir(exist_ok=True)
        cachefile.write_text(mega)
        await self._remove_cachefile(cachefile)

    async def _remove_cachefile(self, cachefile: Path) -> None:
        if cachefile.is_file():
            cachefile.unlink()

    async def _try_emergency_cleanup(self) -> None:
        # We have either critically low space, or there's something else
        # wrong with the home directory.
        #
        # Try to reclaim the space by removing .cache and .astropy/cache.
        #
        # If we fail here, don't bother with recovery--we will be starting
        # in a degraded mode, and offering the user an explanation, anyway.
        self._logger.warning(
            "Attempting emergency cleanup of .cache and .astropy/cache"
        )
        try:
            for cdir in (
                (self._home / ".cache"),
                (self._home / ".astropy" / "cache"),
            ):
                shutil.rmtree(cdir, ignore_errors=True)
                cdir.mkdir(exist_ok=True)
        except Exception:
            self._logger.exception("Emergency cleanup failed")

    async def _set_abnormal_startup(self, exc: OSError) -> None:
        # This and _clear_abnormal_startup() are async because these
        # are likely methods to override in the caller, and the
        # overridden methods may want to do I/O.
        self._broken = True

    async def _clear_abnormal_startup(self) -> None:
        self._broken = False
