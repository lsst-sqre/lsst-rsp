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
        self._debug = str_bool(os.getenv("DEBUG", ""))
        configure_logging(self._debug)
        self._logger = structlog.get_logger(app_name)
        self._user = self._get_user()
        self._home = Path(os.environ["HOME"])  # If unset, it's OK to die.
        # We start with a copy of our own environment
        self._env: dict[str, str] = {}
        self._env.update(os.environ)

    def go(self) -> None:
        """Start the user lab."""
        # Reset the environment first.  This should maybe even be left in
        # shell and tested and run first, in case the user has somehow
        # messed up their environment so badly that Python itself won't
        # run, or at least loading lsst.rsp breaks because some dependency
        # is badly broken.
        #
        # So far we haven't seen breakage this bad: it's usually
        # user-installed Jupyter-related packages that keep the Lab-Hub
        # communication from working.
        self._reset_user_env()

        # Check to see whether LOADRSPSTACK is set and force it if it is
        # not.  We need this to source the correct file in the next step.
        self._ensure_loadrspstack()

        # Check to see whether we are running within the stack, and do a
        # complicated re-exec dance if we are not.  Modular so we can rip
        # this out when we are no longer using the stack Python.
        self._ensure_environment()

        # Set up the (complicated) environment for the JupyterLab process
        self._configure_env()

    def _get_user(self) -> str:
        self._logger.debug("Determining user name")
        user = os.getenv("USER")
        if user:
            return user
        proc = run("id", "-u", "-n")
        if proc is None:
            raise ValueError("Could not determine user")
        user = proc.stdout.strip()
        self._logger.debug(f"User name -> '{user}'")
        return user

    def _reset_user_env(self) -> None:
        if not str_bool(os.environ.get("RESET_USER_ENV", "")):
            self._logger.debug("User environment reset not requested")
            return
        self._logger.debug("User environment reset requested")
        now = datetime.datetime.now(datetime.UTC).isoformat()
        reloc = self._home / f".user_env.{now}"
        reloc.mkdir()  # Fail it it already exists--that would be weird
        moved = False
        # Top-level (relative to $HOME) dirs
        for item in ("cache", "conda", "local", "jupyter"):
            dir_base = Path(f".{item}")
            dir_full = self._home / dir_base
            if dir_full.is_dir():
                dir_full.rename(reloc / dir_base)
                moved = True
        # Files, not necessarily at top level
        u_setups = self._home / "notebooks" / ".user_setups"
        if u_setups.is_file():
            (reloc / "notebooks").mkdir()
            u_setups.rename(reloc / "notebooks" / "user_setups")
            moved = True
        if moved:
            self._logger.debug(f"Relocated files to {reloc!s}")
        else:
            self._logger.debug("No user files needed relocation")
            # Nothing was actually moved, so throw away the directory.
            reloc.rmdir()

    def _ensure_loadrspstack(self) -> None:
        self._logger.debug("Ensuring that LOADRSPSTACK is set")
        if "LOADRSPSTACK" in self._env:
            self._logger.debug(
                f"LOADRSPSTACK was set to '{self._env["LOADRSPSTACK"]}'"
            )
            return
        rspstack = top_dir / "rspstack" / "loadrspstack.bash"
        if not rspstack.is_file():
            rspstack = top_dir / "stack" / "loadLSST.bash"
        self._env["LOADRSPSTACK"] = str(rspstack)
        self._logger.debug(f"Newly set LOADRSPSTACK to {rspstack!s}")

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
            self._logger.debug("RUBIN_EUPS_PATH is set: stack Python assumed")
            # All is well.
            return
        self._logger.debug(
            "RUBIN_EUPS_PATH not set; must re-exec with stack Python"
        )
        tf = tempfile.NamedTemporaryFile(mode="w", delete=False)
        tfp = Path(tf.name)
        tfp.write_text(
            "#!/bin/bash\n"
            f". {self._env['LOADRSPSTACK']}\n"
            f". {profile_path!s}\n"
            f"exec {join(sys.argv)}\n"
        )
        # Make it executable
        tfp.chmod(0o700)
        # Run it
        self._logger.debug(f"About to re-exec: running {tfp!s}")
        os.execl(tf.name, tfp.name)

    def _configure_env(self) -> None:
        self._logger.debug("Configuring environment for JupyterLab process")
        # Start with a copy of our own environment
        self._env.update(os.environ)
        # Remove the SUDO env vars that give Conda fits.
        self._remove_sudo_env()
        # Set a whole bunch of threading guideline variables
        self._set_cpu_variables()
        self._logger.debug("Lab process environment", env=self._env)

    def _remove_sudo_env(self) -> None:
        self._logger.debug("Removing SUDO_ environment variables")
        sudo_vars = ("SUDO_USER", "SUDO_UID", "SUDO_GID", "SUDO_COMMAND")
        for sv in sudo_vars:
            if sv in self._env:
                self._logger.debug(f"Removed environment variable '{sv}'")
                del self._env[sv]

    def _set_cpu_variables(self) -> None:
        lim = self._env.get("CPU_LIMIT", "1")
        lim_n: int = 0
        if lim:
            # It should be a string representing a number, and we're
            # going to coerce it to an integer.  If that fails, we
            # force it to 1
            try:
                lim_n = int(lim)
            except ValueError:
                lim_n = 1
        if lim_n < 1:
            lim_n = 1
        # Now it has an integral value at least 1.  Re-convert it back to
        # a string, and stuff it into a bunch of variables.
        lim = str(lim_n)
        for vname in (
            "CPU_COUNT",
            "GOTO_NUM_THREADS",
            "MKL_DOMAIN_NUM_THREADS",
            "MPI_NUM_THREADS",
            "NUMEXPR_NUM_THREADS",
            "NUMEXPR_MAX_THREADS",
            "OMP_NUM_THREADS",
            "OPENBLAS_NUM_THREADS",
            "RAYON_NUM_THREADS",
        ):
            self._env[vname] = lim

    def copy_butler_credentials(self) -> None:
        return
