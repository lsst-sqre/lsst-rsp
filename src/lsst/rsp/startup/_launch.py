"""Launcher for the user's JupyterLab."""

import contextlib
import errno
import json
import logging
import os
import sys
from pathlib import Path

from ._deprecated.services.labrunner import LabRunner

__all__ = ["Launcher", "launch_lab"]


class Launcher:
    """Convenience class to hold Lab launcher.

    Notes
    -----
    It expects to find a directory named /lab_startup, in which it will have
    an env.json file which will contain a dict of string to string, where the
    key is the environment variable name and the value is its value, e.g.
    { "PATH": "/bin:/usr/bin",
      "USER": "fbooth" }

    There will also be a file called either args.json or
    noninteractive.json, depending on whether the Lab container is to
    be run interactively or noninteractively. This will be a list of
    strings, where the first string is the command to be run and the
    following ones are arguments to that command, e.g.
    [ "jupyterhub-singleuser", "--ip=0.0.0.0", "--port=8888" ]

    These files will have been written into the directory by a startup
    init container provided by Nublado (v11.0.0+).

    If /lab_startup is not present, or is not a directory, or env.json
    does not exist, we assume that the underlying cause is that the
    Nublado controller is too old. The deprecated older startup code
    will be invoked, and ABNORMAL_STARTUP environment variables will
    be set to alert the user on Lab launch.

    If env.json or the command file fails to load correctly,
    ABNORMAL_STARTUP will be used as above, and a default command or
    environment will be used, although it will not be assumed that the
    controller is the problem.

    In both cases the idea is to get something in front of the user to
    explain the problem and suggest remedial action.
    """

    def __init__(self) -> None:
        self._env: dict[str, str] = {}
        self._env_loaded = False
        self._command: list[str] = []
        self._debug = bool(os.getenv("DEBUG"))
        self._logger = logging.getLogger(__name__)
        if self._debug:
            logging.basicConfig(level=logging.DEBUG)
        else:
            logging.basicConfig(level=logging.INFO)
        self._broken = False
        home_str = os.getenv("HOME", "")
        if not home_str:
            self._set_broken(
                error=RuntimeError("$HOME must be set; using /tmp instead")
            )
            home_str = "/tmp"
        self._home = Path(home_str)
        startup_path = os.getenv("RSP_STARTUP_PATH", "/lab_startup")
        self._startup_path = Path(startup_path)
        self._logger.debug(
            f"Launcher initialized: HOME={self._home};"
            " expecting environment and command files in"
            f"{self._startup_path}"
        )

    def load(self) -> None:
        """Load the environment and startup command for the user lab.

        Note
        ----
        If we think something seems wrong about the /lab_startup directory
        or the environment file that suggests we were launched from a
        Nublado controller prior to version 11, we fall back to attempting
        an older (now deprecated) launch of the lab, but we also set the
        startup environment such that the lab will warn the user that the
        Nublado controller needs to be upgraded.

        Other failures will display a similar warning but will attempt a
        new-style launch with default values for the environment or command
        or both.
        """
        env_file = self._startup_path / "env.json"
        if (
            not self._startup_path.exists()
            or not self._startup_path.is_dir()
            or not env_file.exists()
        ):
            try:
                # This will fail, but possibly in different ways, all,
                # however, in ways that throw an exception, which we can then
                # report.
                #
                # This is likely to be an old-controller error, since
                # either /lab_startup isn't there, or isn't a directory, or
                # no env.json file exists within it.
                env_file.read_text()
            except Exception as exc:
                self._set_broken(exc, old_controller=True)
                self._logger.exception("Problem loading startup files")
                self._logger.warning("Falling back to deprecated startup")
                # Set up abnormal startup in actual environment
                for e in ("", "_ERRNO", "_STRERROR", "_MESSAGE", "_ERRORCODE"):
                    key = f"ABNORMAL_STARTUP{e}"
                    os.environ[key] = self._env[key]
                LabRunner(broken=True).go()
                return  # never reached
        try:
            env = json.loads((self._startup_path / "env.json").read_text())
            self._env.update(env)
            self._env_loaded = True
        except Exception as exc:
            self._logger.exception("Could not load environment file")
            self._set_broken(exc)
        ni_cmd = self._startup_path / "noninteractive.json"
        if ni_cmd.exists():
            try:
                self._command = json.loads(
                    (self._startup_path / "noninteractive.json").read_text()
                )
            except Exception as exc:
                self._logger.exception(
                    "Could not load noninteractive command file"
                )
                self._set_broken(exc)
        else:
            try:
                self._command = json.loads(
                    (self._startup_path / "args.json").read_text()
                )
            except Exception as exc:
                self._logger.exception("Could not load command file")
                self._set_broken(exc)

    def launch(self) -> None:
        """Start the user Lab."""
        if not self._command or not self._env:
            # Try to load command and environment.
            self.load()
            # If we think it was a too-old-controller problem, we will
            # never reach here, as we will have fallen back to the old
            # launcher.  If we get here, we're pretty sure it's the
            # new-style launcher but something may still be wrong.
        if not self._command:
            self._logger.warning("No command given; using default")
            self._command = self._get_default_command()
        if not self._env_loaded:
            self._logger.warning("No environment given; using current")
            self._env.update(dict(os.environ))
        self._inject_path_if_needed()
        self._logger.debug(f"Command: {self._command}")
        self._logger.debug(f"Environment: {self._env}")
        with contextlib.chdir(self._home):
            # We use execvpe() here because we have a list of commands and an
            # environment to supply to it.
            sys.stdout.flush()
            sys.stderr.flush()
            os.execvpe(self._command[0], self._command, env=self._env)

    def _get_default_command(self) -> list[str]:
        """Return default command to launch a Lab.

        This a failsafe designed to get the Lab up and running so it
        can display a modal dialog to the user explaining the problem.
        """
        cmd = [
            "jupyterhub-singleuser",
            "--ip=0.0.0.0",
            "--port=8888",
            "--no-browser",
            "--ContentsManager.allow_hidden=True",
            "--FileContentsManager.hide_globs=[]",
            "--KernelSpecManager.ensure_native_kernel=False",
            "--LatexExporter.enabled=False",
            "--QtExporter.enabled=False",
            "--PDFExporter.enabled=False",
            "--WebPDFExporter.enabled=False",
            "--MappingKernelManager.default_kernel_name=lsst",
            "--LabApp.check_for_updates_class=jupyterlab.NeverCheckForUpdate",
        ]
        cmd.append(f"--notebook-dir={self._home!s}")
        ll = "DEBUG" if self._debug else "INFO"
        cmd.append(f"--log-level={ll}")
        return cmd

    def _inject_path_if_needed(self) -> None:
        envpath = self._env.get("PATH")
        curpath = os.getenv("PATH")
        if not envpath:
            if curpath:
                self._env["PATH"] = curpath
            else:
                def_path = "/usr/bin:/bin:/usr/local/bin"
                self._logger.warning(
                    "No $PATH in current or injected environment: using"
                    f" {def_path}"
                )
                self._env["PATH"] = def_path
                os.environ["PATH"] = def_path

    def _set_broken(
        self, error: Exception, *, old_controller: bool = False
    ) -> None:
        """Set the environment variables for the launched lab that will
        cause it to display a warning on startup.
        """
        if self._broken:
            # We're already broken; go with the earlier problem.
            return
        self._broken = True
        self._env["ABNORMAL_STARTUP"] = "TRUE"
        if old_controller:
            # We're guessing the reason we have a problem is that we
            # were started from a Nublado controller too old to write files
            # to a shared startup space.
            _min_nublado_ver = "11.0.0"
            self._env["ABNORMAL_STARTUP_ERRNO"] = "202"
            self._env["ABNORMAL_STARTUP_ERRORCODE"] = "EOLDNUB"
            self._env["ABNORMAL_STARTUP_STRERROR"] = (
                "Nublado controller too old"
            )
            self._env["ABNORMAL_STARTUP_MESSAGE"] = (
                f"Nublado controller {_min_nublado_ver} or greater"
                " required to launch this lab; falling back to older"
                " startup implementation"
            )
            return
        self._env["ABNORMAL_STARTUP_MESSAGE"] = str(error)
        if isinstance(error, OSError):
            eno = error.errno or 201
            self._env["ABNORMAL_STARTUP_ERRORCODE"] = errno.errorcode.get(
                eno, f"Unknown error {eno}"
            )
            self._env["ABNORMAL_STARTUP_ERRNO"] = str(eno)
            self._env["ABNORMAL_STARTUP_STRERROR"] = errno.errorcode.get(
                eno, "EUNKNOWN"
            )
            return
        self._env["ABNORMAL_STARTUP_ERRNO"] = "201"
        self._env["ABNORMAL_STARTUP_STRERROR"] = "EUNKNOWN"
        return


def launch_lab() -> None:
    """Read startup files and start the Lab (or noninteractive equivalent)."""
    launcher = Launcher()
    launcher.launch()
