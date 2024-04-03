"""Control RSP startup."""

import datetime
import os
import sys
import tempfile
from pathlib import Path
from shlex import join
from urllib.parse import urlparse

import structlog

from ... import get_digest
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
        # We start with a copy of our own environment
        self._env: dict[str, str] = {}
        self._env.update(os.environ)
        self._debug = str_bool(self._env.get("DEBUG", ""))
        configure_logging(self._debug)
        self._logger = structlog.get_logger(app_name)
        self._user = self._get_user()
        self._home = Path(self._env["HOME"])  # If unset, it's OK to die.

    def go(self) -> None:
        """Start the user lab."""
        # Reset the environment first.  This should maybe even be left in
        # shell and tested and run first, in case the user has somehow
        # messed up their environment so badly that Python itself won't
        # run, or at least loading lsst.rsp breaks because some dependency
        # is badly broken.
        #
        # If we do this, we need to restart after doing it so we get a
        # (hopefully cleaner) Python environment.
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
        user = self._env.get("USER", "")
        if not user:
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
            self._logger.debug("Restarting with cleaned-up filespace")
            # We're about to re-exec: we don't want to keep looping.
            del self._env["RESET_USER_ENV"]
            self._ensure_loadrspstack()
            # We cheat a bit here.  Sourcing the stack setup twice is
            # (I believe) harmless, and this is a fast way to re-exec
            # thus ensuring a cleaner Python environment
            if "LSST_CONDA_ENV_NAME" in self._env:
                del self._env["LSST_CONDA_ENV_NAME"]
            # This will re-exec so we get a new Python process
            self._ensure_environment()
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
        # It's ``LSST_CONDA_ENV_NAME``.
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

        if os.environ.get("LSST_CONDA_ENV_NAME"):
            self._logger.debug(
                "LSST_CONDA_ENV_NAME is set: stack Python assumed"
            )
            # All is well.
            return
        self._logger.debug(
            "LSST_CONDA_ENV_NAME not set; must re-exec with stack Python"
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
        # Ensure it's flushed to disk
        os.sync()
        # Run it
        self._logger.debug(f"About to re-exec: running {tfp!s}")
        os.execl(tf.name, tfp.name)

    #
    # This leads off a big block of setting up our subprocess environment
    #
    def _configure_env(self) -> None:
        self._logger.debug("Configuring environment for JupyterLab process")
        # Start with a copy of our own environment
        self._env.update(os.environ)
        # Remove the SUDO env vars that give Conda fits.
        self._remove_sudo_env()
        # Set a whole bunch of threading guideline variables
        self._set_cpu_variables()
        # Extract image digest
        self._set_image_digest()
        # Expand tilde in PANDA_CONFIG_ROOT, if needed
        self._expand_panda_tilde()
        # We no longer need to rebuild the lab, so we no longer
        # need to set NODE_OPTIONS --max-old-space-size
        # Set any missing timeout variables
        self._set_timeout_variables()
        # Set up launch parameters
        self._set_launch_params()
        # Set up Firefly variables
        self._set_firefly_variables()
        # Unset JUPYTER_PREFER_ENV_PATH
        self._unset_jupyter_prefer_env_path()
        # Set up variables for butler credential copy
        self._set_butler_credential_variables()
        #
        # That should do it.
        #
        self._logger.debug("Lab process environment", env=self._env)

    def _remove_sudo_env(self) -> None:
        self._logger.debug("Removing SUDO_ environment variables")
        sudo_vars = ("SUDO_USER", "SUDO_UID", "SUDO_GID", "SUDO_COMMAND")
        for sv in sudo_vars:
            if sv in self._env:
                self._logger.debug(f"Removed environment variable '{sv}'")
                del self._env[sv]

    def _set_cpu_variables(self) -> None:
        self._logger.debug("Setting CPU threading variables")
        lim = self._env.get("CPU_LIMIT", "1")
        lim_n: int = 0
        if lim:
            # It should be a string representing a number, and we're
            # going to coerce it to an integer.  If that fails, we
            # force it to 1
            try:
                lim_n = int(float(lim))
            except ValueError:
                lim_n = 1
        if lim_n < 1:
            lim_n = 1
        # Now it has an integral value at least 1.  Re-convert it back to
        # a string, and stuff it into a bunch of variables.
        lim = str(lim_n)
        for vname in (
            "CPU_LIMIT",
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
            self._logger.debug(f"Set env var {vname} to {lim}")

    def _set_image_digest(self) -> None:
        self._logger.debug("Setting image digest if available")
        # get_digest() is already a helper function in our parent package.
        digest = get_digest()
        if digest:
            self._logger.debug(f"Set image digest to '{digest}'")
            self._env["IMAGE_DIGEST"] = digest
        else:
            self._logger.debug("Could not get image digest")

    def _expand_panda_tilde(self) -> None:
        self._logger.debug("Expanding tilde in PANDA_CONFIG_ROOT, if needed")
        if "PANDA_CONFIG_ROOT" in self._env:
            pcr = self._env["PANDA_CONFIG_ROOT"]
            if pcr.find("~") == 0:
                # The tilde has to be at the start of the path.
                #
                # We don't have multiple users in the RSP, so "~" and "~<user>"
                # mean the same thing, and ~<anything-else> doesn't exist.
                t_user = pcr
                rest = ""
                if pcr.find("/") > 0:
                    # Does it have a directory in it?
                    t_user, rest = pcr.split("/")
                if t_user in ("~", f"~{self._user}"):
                    if rest:
                        newpcr = str(self._home / rest)
                    else:
                        newpcr = str(self._home)
                    self._logger.debug(
                        f"Replacing PANDA_CONFIG_ROOT '{pcr}' with '{newpcr}'"
                    )
                    self._env["PANDA_CONFIG_ROOT"] = newpcr
                else:
                    self._logger.warning(f"Cannot expand tilde in '{pcr}'")

    def _set_timeout_variables(self) -> None:
        self._logger.debug("Setting new timeout variables if needed.")
        defaults = {
            "NO_ACTIVITY_TIMEOUT": "120000",
            "CULL_KERNEL_IDLE_TIMEOUT": "43200",
            "CULL_KERNEL_CONNECTED": "True",
            "CULL_KERNEL_INTERVAL": "300",
            "CULL_TERMINAL_INACTIVE_TIMEOUT": "120000",
            "CULL_TERMINAL_INTERVAL": "300",
        }
        for k in defaults:
            v = defaults[k]
            if k not in self._env:
                self._logger.debug(f"Setting '{k}' to '{v}'")
                self._env[k] = v

    def _set_launch_params(self) -> None:
        # We're getting rid of the complicated stuff based on
        # HUB_SERVICE_HOST, since that was pre-version-3 nublado.
        self._logger.debug("Setting launch parameters")
        base_url = self._env.get("JUPYTERHUB_BASE_URL", "")
        jh_path = f"{base_url}hub"
        ext_url = self._env.get("EXTERNAL_INSTANCE_URL", "")
        ext_parsed = urlparse(ext_url)
        host = ext_parsed.hostname or ""
        # These don't actually need to be exposed as environment
        # variables, but we need them to launch the lab, and it's
        # as convenient a place as anywhere to stash them
        self._env["JUPYTERHUB_PATH"] = jh_path
        self._env["EXTERNAL_HOST"] = host
        self._logger.debug(
            f"Set host to '{host}', and Hub path to '{jh_path}'"
        )

    def _set_firefly_variables(self) -> None:
        self._logger.debug("Setting firefly variables")
        fr = self._env.get("FIREFLY_ROUTE", "")
        if not fr:
            self._env["FIREFLY_ROUTE"] = "/firefly/"
        ext_f_url = self._env.get("EXTERNAL_FIREFLY_URL", "")
        if ext_f_url:
            self._env["FIREFLY_URL"] = ext_f_url
        else:
            ext_i_url = self._env.get("EXTERNAL_INSTANCE_URL", "")
            self._env["FIREFLY_URL"] = (
                f"{ext_i_url}{self._env['FIREFLY_ROUTE']}"
            )
        self._env["FIREFLY_HTML"] = "slate.html"
        self._logger.debug(f"Firefly URL -> '{self._env['FIREFLY_URL']}'")

    def _unset_jupyter_prefer_env_path(self) -> None:
        self._logger.debug("Unsetting JUPYTER_PREFER_ENV_PATH")
        self._env["JUPYTER_PREFER_ENV_PATH"] = "no"

    def _set_butler_credential_variables(self) -> None:
        # We split this up into environment manipulation and later
        # file substitution.  This is the environment part.
        self._logger.debug("Setting Butler credential variables")
        cred_dir = self._home / ".lsst"
        # As with the launch parameters, we'll need it later.
        self._env["USER_CREDENTIALS_DIR"] = str(cred_dir)
        if "AWS_SHARED_CREDENTIALS_FILE" in self._env:
            awsname = Path(self._env["AWS_SHARED_CREDENTIALS_FILE"]).name
            self._env["ORIG_AWS_SHARED_CREDENTIALS_FILE"] = self._env[
                "AWS_SHARED_CREDENTIALS_FILE"
            ]
            newaws = str(cred_dir / awsname)
            self._env["AWS_SHARED_CREDENTIALS_FILE"] = newaws
            self._logger.debug(
                f"Set 'AWS_SHARED_CREDENTIALS_FILE' -> '{newaws}'"
            )
        if "PGPASSFILE" in self._env:
            pgpname = Path(self._env["PGPASSFILE"]).name
            newpg = str(cred_dir / pgpname)
            self._env["ORIG_PGPASSFILE"] = self._env["PGPASSFILE"]
            self._env["PGPASSFILE"] = newpg
            self._logger.debug(f"Set 'PGPASSFILE' -> '{newpg}'")
