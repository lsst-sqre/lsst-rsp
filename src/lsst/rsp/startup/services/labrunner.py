"""Control RSP startup."""

import datetime
import os
import sys
import tempfile
from pathlib import Path
from shlex import join

import structlog

from ..constants import app_name, profile_path, top_dir
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
        self.home = Path(os.environ["HOME"])  # If unset, it's OK to die.
        self._reset_user_env()
        self._ensure_environment()
        self._create_env()  # Sets self.env

    def _get_user(self) -> str:
        user = os.getenv("USER")
        if user:
            return user
        proc = run("id", "-u", "-n")
        if proc is None:
            raise ValueError("Could not determine user")
        return proc.stdout.strip()

    def _reset_user_env(self) -> None:
        if not str_bool(os.environ.get("RESET_USER_ENV", "")):
            return
        now = datetime.datetime.now(datetime.UTC).isoformat()
        reloc = self.home / f".user_env.{now}"
        moved = False
        for item in ("cache", "conda", "local", "jupyter"):
            dir_base = Path(f".{item}")
            dir_full = self.home / dir_base
            if dir_full.is_dir():
                dir_full.rename(reloc / dir_base)
                moved = True

        if not moved:
            reloc.rmdir()

    def _ensure_environment(self) -> None:
        """If we are not running from within the stack environment,
        restart from within it.
        """
        # Currently the JupyterLab machinery relies on the stack
        # Python to run.  While this is expected to change, it has not
        # yet, so...  we test for an environment variable that, unless
        # the user is extraordinarily perverse, will only be set in
        # the stack environment.
        #
        # It's ``RUBIN_EUPS_PATH``.
        #
        # If we don't find it, we create an executable shell file that
        # sets up the stack environment and then reruns the current
        # command with its arguments.  We know we have ``/bin/bash``
        # in the container, so we use that as the shell and use
        # ``loadLSST.bash`` to set up the environment.  We also add
        # some paths set up in the profile.  Then we use exec() in the
        # shell script to reinvoke the Python process exactly as it
        # was initially called.
        #
        # Finally we os.execl() that file, replacing this process with
        # that one, which will bring us right back here, but with the
        # stack initialized.  We do leave the file sitting around, but
        # since we're creating it as a temporary file, that's OK: it's
        # a few dozen bytes, and it will go away when the container
        # does.

        if os.environ.get("RUBIN_EUPS_PATH"):
            # All is well.
            return
        tf = tempfile.NamedTemporaryFile(mode="w", delete=False)
        tfp = Path(tf.name)
        tfp.write_text(
            "#!/bin/bash\n"
            f". {top_dir / 'stack' / 'loadLSST.bash'!s}\n"
            f". {profile_path!s}\n"
            f"exec {join(sys.argv)}\n"
        )
        # Make it executable
        tfp.chmod(0o700)
        # Run it
        os.execl(tf.name, tfp.name)

    def _create_env(self) -> None:
        self.env: dict[str, str] = {}
        self.env.update(os.environ)
        # Remove the SUDO env vars that give Conda fits.
        self._remove_sudo_env()

    def _remove_sudo_env(self) -> None:
        sudo_vars = ("SUDO_USER", "SUDO_UID", "SUDO_GID", "SUDO_COMMAND")
        for sv in sudo_vars:
            if os.environ.get(sv):
                del self.env[sv]

    def copy_butler_credentials(self) -> None:
        return
