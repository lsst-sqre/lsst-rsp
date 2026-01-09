"""Launcher for the user's JupyterLab."""

import contextlib
import errno
import json
import logging
import os
import sys
from pathlib import Path

__all__ = ["Launcher", "launch_lab"]


class Launcher:
    """Convenience class to hold Lab launcher."""

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
            f"Launcher initialized: HOME={self._home}; "
            " expecting environment and command files in"
            f"{self._startup_path}"
        )

    def load(self) -> None:
        try:
            env = json.loads((self._startup_path / "env.json").read_text())
            self._env.update(env)
            self._env_loaded = True
        except Exception as exc:
            self._logger.exception("Could not load environment file")
            self._set_broken(exc, old_controller=True)

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
                self._set_broken(exc, old_controller=True)

    def launch(self) -> None:
        if not self._command or not self._env:
            # Try to load command and environment
            self.load()
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

        We can retire this once all RSP sites are running a sufficiently
        new Nublado controller.
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
        if self._env.get("ABNORMAL_STARTUP") == "TRUE":
            # We're already broken; go with the earlier problem.
            return
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
                " required to launch this lab"
            )
            return
        self._env["ABNORMAL_STARTUP_MESSAGE"] = str(error)
        if isinstance(error, OSError):
            self._env["ABNORMAL_STARTUP_ERRNO"] = str(error.errno) or "201"
            self._env["ABNORMAL_STARTUP_STRERROR"] = errno.errorcode.get(
                error.errno or 201, "EUNKNOWN"
            )
            return
        self._env["ABNORMAL_STARTUP_ERRNO"] = "201"
        self._env["ABNORMAL_STARTUP_STRERROR"] = "EUNKNOWN"
        return


def launch_lab() -> None:
    """Read startup files and start the Lab (or noninteractive equivalent)."""
    launcher = Launcher()
    launcher.launch()
