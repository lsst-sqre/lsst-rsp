"""Control RSP startup."""

import os

import structlog

from ..constants import app_name
from ..storage.logging import configure_logging
from ..storage.process import run
from ..util import str_bool

__all__ = ["LabRunner"]


class LabRunner:
    """Class to start JupyterLab using the environment supplied by
    JupyterHub and the Nublado controller.  This environment is very
    Rubin-specific and opinionated, and will likely not work for anyone
    else's science platform.

    If that's you, use this for inspiration, but don't expect this to
    work out of the box.
    """

    def __init__(self) -> None:
        self.debug = str_bool(os.getenv("DEBUG", ""))
        configure_logging(self.debug)
        self.logger = structlog.get_logger(app_name)
        self.user = self._get_user()
        self.env = self._create_env()

    def _get_user(self) -> str:
        user = os.getenv("USER")
        if user:
            return user
        proc = run("id", "-u", "-n")
        if proc is None:
            raise ValueError("Could not determine user")
        return proc.stdout.strip()

    def _create_env(self) -> dict[str, str]:
        return {}

    def copy_butler_credentials(self) -> None:
        return
