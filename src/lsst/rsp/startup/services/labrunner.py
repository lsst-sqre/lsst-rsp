"""RSP Lab launcher."""

import json
import os
import pwd
import sys
from pathlib import Path
from textwrap import dedent

from rubin.repertoire import DiscoveryClient

from ... import get_digest
from ...utils import get_runtime_mounts_dir
from ..exceptions import RSPErrorCode, RSPStartupError
from ..models.noninteractive import NonInteractiveExecutor
from ._rspstartup import _RSPStartup

__all__ = ["LabRunner"]


class LabRunner(_RSPStartup):
    """Class to start JupyterLab using the environment supplied by
    JupyterHub and the Nublado controller.

    This environment is very Rubin-specific and opinionated, and will
    likely not work for anyone else's science platform.

    If that's you, use this for inspiration, but don't expect this to
    work out of the box.
    """

    def __init__(self) -> None:
        super().__init__()
        rep_url = os.getenv("REPERTOIRE_BASE_URL") or (
            f"{self._env.get('EXTERNAL_INSTANCE_URL')}/repertoire"
        )
        self._discovery = DiscoveryClient(base_url=rep_url)

    async def go(self) -> None:
        """Start the user lab."""
        # First, look to see if the init container left us a file indicating
        # it had a problem.

        startup_errs = list(self._home.glob("ABNORMAL_STARTUP_*"))
        if startup_errs:
            # We know, conventionally, that we're going to put a Unix
            # datestamp into the startup file name and that will be lexically
            # sorted, so it's the last one that should generate the
            # exception we show as the error.  If we get here there's at
            # least one element in the list, so taking the last one is fine.
            #
            # Don't remove them: the next attempted lab spawn will do that
            # in the init container.
            displayed = startup_errs[-1]
            exc = RSPStartupError(json.loads(displayed.read_text()))
            await self._set_abnormal_startup(exc)
        try:
            # We need to do this here as well, because if we were fatally
            # out of space, the init container did not write anything that
            # we could read, so we don't know yet.
            await self._test_for_space()
            await self._configure_env()
        except OSError as exc:
            await self._set_abnormal_startup(exc)

        # Decide between interactive and noninteractive start, do
        # things that change between those two, and launch the Lab.
        #
        # The await is a lie: the process is replaced with JupyterLab at
        # launch time, but then there's nothing to await the method's
        # exit either.
        await self._launch()

    async def _set_abnormal_startup(self, exc: OSError) -> None:
        """Take an OSError, convert it into an RSPStartupError if necessary,
        and then set the env variables that rsp-jupyter-extensions will use
        to report the error to the user at Lab startup.
        """
        await super()._set_abnormal_startup(exc)
        if not isinstance(exc, RSPStartupError):
            # This will also catch the EUNKNOWN case
            new_exc = RSPStartupError.from_os_error(exc)
        else:
            new_exc = exc

        self._env["ABNORMAL_STARTUP"] = "TRUE"
        self._env["ABNORMAL_STARTUP_ERRNO"] = str(new_exc.errno)
        self._env["ABNORMAL_STARTUP_STRERROR"] = (
            # Mypy didn't know the above caught the EUNKNOWN case.
            new_exc.strerror
            or os.strerror(int(new_exc.errno or RSPErrorCode.EUNKNOWN.value))
            or f"Unknown error {new_exc.errno}"
        )
        self._env["ABNORMAL_STARTUP_ERRORCODE"] = new_exc.errorcode
        self._env["ABNORMAL_STARTUP_MESSAGE"] = str(new_exc)
        msg = f"Abnormal RSP startup set with exception {new_exc!s}"
        self._logger.error(msg)

    # Set up the environment for the Lab.  There's a lot of it.
    # In general, if a method does I/O, it's async.  Otherwise it's not.

    async def _configure_env(self) -> None:
        self._logger.debug("Configuring environment for JupyterLab process")
        self._set_user()
        await self._set_tmpdir_if_scratch_available()
        await self._set_butler_cache()
        self._set_cpu_variables()
        self._set_image_digest()
        self._expand_panda_tilde()
        await self._set_firefly_variables()
        self._force_jupyter_prefer_env_path_false()
        self._set_butler_credential_variables()
        self._logger.debug("Lab process environment", env=self._env)

    def _set_user(self) -> None:
        self._logger.debug("Determining user name")
        user = self._env.get("USER", "")
        if not user:
            user = pwd.getpwuid(os.getuid()).pw_name
            if not user:
                raise RSPStartupError(RSPErrorCode.EBADENV, None, "USER")
            self._env["USER"] = user

    async def _check_user_scratch_subdir(self, path: Path) -> Path | None:
        # This is very Rubin specific.  We generally have a large
        # world-writable filesystem in a scratch path.
        #
        # Given a path we will test that ${SCRATCH_PATH}/user/path can be
        # created as a writable directory (or that it already exists
        # as a writable directory).  If it can be (or is), we return the
        # whole path, and if not, we return None.  If we can set it,
        # we also set the SCRATCH_DIR environment variable to point to it.
        #
        # This will only be readable by the user; they can chmod() it if
        # they want to share, but for TMPDIR and DAF_BUTLER_CACHE_DIRECTORY
        # they probably should not.  The mode will not be reset if the
        # directory already exists and is writeable

        scratch_path = Path(os.getenv("SCRATCH_PATH") or "/scratch")

        if not scratch_path.is_dir():
            self._logger.debug(
                # Debug only: not having /scratch is reasonable.
                f"{scratch_path} is not a directory."
            )
            return None
        user = self._env.get("USER", "")
        if not user:
            self._logger.warning("Could not determine user from environment")
            return None
        schema = self._env.get("HOMEDIR_SCHEMA", "username")
        user_scratch_dir = scratch_path / user
        # This is pretty ad-hoc, but USDF uses the first letter in the
        # username for both home and scratch
        if schema == "initialThenUsername":
            user_scratch_dir = scratch_path / user[0] / user
        user_scratch_path = user_scratch_dir / path
        try:
            user_scratch_path.mkdir(parents=True, exist_ok=True, mode=0o700)
        except OSError as exc:
            self._logger.warning(
                f"Could not create directory at {user_scratch_path!s}: {exc}"
            )
            return None
        if not os.access(user_scratch_path, os.W_OK):
            self._logger.warning(f"Unable to write to {user_scratch_path!s}")
            return None
        self._logger.debug(f"Using user scratch path {user_scratch_path!s}")
        # Set user-specific top dir as SCRATCH_DIR
        self._env["SCRATCH_DIR"] = f"{user_scratch_dir!s}"
        return user_scratch_path

    async def _set_tmpdir_if_scratch_available(self) -> None:
        # Assuming that TMPDIR is not already set (e.g. by the spawner),
        # we will try to create <scratch_path>/<user>/tmp and ensure it is a
        # writeable directory, and if it is, TMPDIR will be repointed to it.
        # This will then reduce our ephemeral storage issues, which have
        # caused mass pod eviction and destruction of the prepull cache.
        #
        # In our tests at the IDF, on a 2CPU/8GiB "Medium", TMPDIR on
        # /scratch (NFS) is about 15% slower than on local ephemeral storage.
        self._logger.debug("Resetting TMPDIR if scratch storage available")
        tmpdir = self._env.get("TMPDIR", "")
        if tmpdir:
            self._logger.debug(f"Not setting TMPDIR: already set to {tmpdir}")
            return
        temp_path = await self._check_user_scratch_subdir(Path("tmp"))
        if temp_path:
            self._env["TMPDIR"] = str(temp_path)
            self._logger.debug(f"Set TMPDIR to {temp_path!s}")
        else:
            self._logger.debug("Did not set TMPDIR")

    async def _set_butler_cache(self) -> None:
        # This is basically the same story as TMPDIR.
        env_v = "DAF_BUTLER_CACHE_DIRECTORY"
        dbcd = self._env.get(env_v, "")
        if dbcd:
            self._logger.debug(f"Not setting {env_v}: already set to {dbcd}")
            return
        temp_path = await self._check_user_scratch_subdir(Path("butler_cache"))
        if temp_path:
            self._env[env_v] = str(temp_path)
            self._logger.debug(f"Set {env_v} to {temp_path!s}")
            return
        # In any sane RSP environment, /tmp will not be shared (it will
        # be either tmpfs or on ephemeral storage, and in any case not
        # visible beyond its own pod), so we are not actually using a risky
        # shared directory.
        self._env[env_v] = "/tmp/butler_cache"

    def _set_cpu_variables(self) -> None:
        self._logger.debug("Setting CPU threading variables")
        try:
            cpu_limit = int(float(self._env.get("CPU_LIMIT", "1")))
        except ValueError:
            cpu_limit = 1
        cpu_limit = max(cpu_limit, 1)
        cpu_limit_str = str(cpu_limit)
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
            self._env[vname] = cpu_limit_str
            self._logger.debug(f"Set '{vname}' -> '{cpu_limit_str}'")

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
        # Using Path.expanduser(), while probably more feature-complete,
        # makes this method very hard to test, and you just end up
        # monkeypatching Path.expanduser() with something a lot like this
        # logic.
        self._logger.debug("Expanding tilde in PANDA_CONFIG_ROOT, if needed")
        if "PANDA_CONFIG_ROOT" in self._env:
            # We've already been through set_user(), so USER must be set.
            username = self._env["USER"]
            path = Path(self._env["PANDA_CONFIG_ROOT"])
            path_parts = path.parts
            if path_parts[0] in ("~", f"~{username}"):
                new_path = Path(self._home, *path_parts[1:])
                self._logger.debug(
                    f"Replacing PANDA_CONFIG_ROOT '{path!s}'"
                    f"with '{new_path!s}'"
                )
                self._env["PANDA_CONFIG_ROOT"] = str(new_path)
            elif path_parts[0].startswith("~"):
                self._logger.warning(f"Cannot expand tilde in '{path!s}'")

    async def _set_firefly_variables(self) -> None:
        self._logger.debug("Setting firefly variables")
        url = await self._discovery.url_for_ui("portal")
        if url:
            self._env["FIREFLY_URL"] = url
            self._logger.debug(f"Firefly URL -> '{url}'")

    def _force_jupyter_prefer_env_path_false(self) -> None:
        # cf https://discourse.jupyter.org/t/jupyter-paths-priority-order/7771
        # and https://jupyter-core.readthedocs.io/en/latest/changelog.html#id63
        #
        # As long as we're running from the stack Python, we need to ensure
        # this is turned off.
        self._logger.debug("Forcing JUPYTER_PREFER_ENV_PATH to 'no'")
        self._env["JUPYTER_PREFER_ENV_PATH"] = "no"

    async def _launch(self) -> None:
        # We're about to start the lab: set the flag saying we're running
        # inside the lab.  It's used by shell startup.
        self._env["RUNNING_INSIDE_JUPYTERLAB"] = "TRUE"
        # Close our discovery client (not that it matters; our process is
        # about to be os.execve()'d away.
        await self._discovery.aclose()
        if bool(self._env.get("NONINTERACTIVE", "")):
            self._start_noninteractive()
            # We exec a lab; control never returns here
        await self._start()

    def _start_noninteractive(self) -> None:
        config_path = (
            get_runtime_mounts_dir()
            / "noninteractive"
            / "command"
            / "command.json"
        )
        launcher = NonInteractiveExecutor.from_config(config_path)
        launcher.execute(env=self._env)

    def _set_timeout_variables(self) -> list[str]:
        timeout_map = {
            "NO_ACTIVITY_TIMEOUT": "ServerApp.shutdown_no_activity_timeout",
            "CULL_KERNEL_IDLE_TIMEOUT": (
                "MappingKernelManager.cull_idle_timeout"
            ),
            "CULL_KERNEL_CONNECTED": "MappingKernelManager.cull_connected",
            "CULL_KERNEL_INTERVAL": "MappingKernelManager.cull_interval",
            "CULL_TERMINAL_INACTIVE_TIMEOUT": (
                "TerminalManager.cull_inactive_timeout"
            ),
            "CULL_TERMINAL_INTERVAL": "TerminalManager.cull_interval",
        }
        result: list[str] = []
        for envvar, setting in timeout_map.items():
            val = self._env.get(envvar, "")
            if val:
                result.append(f"--{setting}={val}")
        return result

    async def _make_abnormal_startup_environment(self) -> None:
        # What we're doing is writing (we hope) someplace safe, be that
        # an empty, ephemeral filesystem (such as /tmp in any sanely-configured
        # K8s-based RSP) or in scratch space somewhere.
        #
        # Performance is irrelevant.  As we explain to the user, they should
        # not be using this lab for anything other than immediate problem
        # amelioration.

        # Try a sanity check and ensure that we are in fact in a broken state.
        if not self._broken:
            return

        txt = self._make_abnormal_landing_markdown()
        s_obj = {"defaultViewers": {"markdown": "Markdown Preview"}}
        s_txt = json.dumps(s_obj)

        try:
            temphome = self._env.get("SCRATCH_DIR", "/tmp")
            welcome = Path(temphome) / "notebooks" / "tutorials" / "welcome.md"
            welcome.parent.mkdir(exist_ok=True, parents=True)
            welcome.write_text(txt)
            settings = (
                Path(temphome)
                / ".jupyter"
                / "lab"
                / "user-settings"
                / "@jupyterlab"
                / "docmanager-extension"
                / "plugin.jupyterlab-settings"
            )
            settings.parent.mkdir(exist_ok=True, parents=True)
            settings.write_text(s_txt)
        except Exception:
            self._logger.exception(
                "Writing files to report abnormal startup failed"
            )

    def _make_abnormal_landing_markdown(self) -> str:
        user = self._env["USER"]
        home = self._env.get(
            "NUBLADO_HOME",
            self._env.get(
                "HOME",
                f"/home/{user}",  # Guess, albeit a good one.
            ),
        )

        errmsg = self._env.get("ABNORMAL_STARTUP_MESSAGE", "<no message>")
        errcode = self._env.get("ABNORMAL_STARTUP_ERRORCODE", "EUNKNOWN")

        self._logger.error(
            f"Abnormal startup: errorcode {errcode}; message {errmsg}"
        )

        open_an_issue = dedent(
            f"""

            Please open an issue with your RSP site administrator with the
            following information: `{errmsg}`
            """
        )

        # Start with generic error text.  It's very simple markdown, with a
        # heading and literal text only.

        txt = dedent("""
        # Abnormal startup

        Your Lab container did not start normally.

        Do not trust this lab for work you want to keep.

        """)

        # Now add error-specific advice.
        match errcode:
            case "EDQUOT":
                txt += dedent(
                    f"""
                    You have exceeded your quota.  Try using the terminal to
                    remove unneeded files in `{home}`.  You can use the
                    `quota` command to check your usage.

                    After that, shut down and restart the lab.  If that does
                    not result in a working lab:
                    """
                )
            case "ENOSPC":
                txt += dedent(
                    f"""
                    You have run out of filesystem space.  Try using the
                    terminal to remove unneeded files in `{home}`.  Since the
                    filesystem is full, this may not be something you can
                    correct.

                    After you have trimmed whatever possible, shut down and
                    restart the lab.

                    If that does not result in a working lab:
                    """
                )
            case "EROFS" | "EACCES":
                txt += dedent(
                    """
                    You do not have permission to write.  Ask your RSP
                    administrator to check ownership and permissions on your
                    directories.
                    """
                )
            case "EBADENV":
                txt += dedent(
                    """
                    You are missing environment variables necessary for RSP
                    operation.
                    """
                )
            case _:
                pass
        txt += dedent(open_an_issue)
        return txt

    async def _start(self) -> None:
        log_level = "DEBUG" if self._debug else "INFO"
        notebook_dir = f"{self._home!s}"
        if self._broken:
            self._logger.warning(
                f"Abnormal startup: {self._env['ABNORMAL_STARTUP_MESSAGE']}"
            )
            await self._make_abnormal_startup_environment()
            #
            # We will check to see if we got SCRATCH_DIR set before we broke,
            # and if so, use that, which would be a user-specific path on a
            # scratch filesystem.  If we didn't, we just use "/tmp" and hope
            # for the best.  Any reasonably-configured RSP running under K8s
            # will not have a shared "/tmp".
            #
            temphome = self._env.get("SCRATCH_DIR", "/tmp")
            self._logger.warning(f"Launching with homedir='{temphome}'")
            self._env["HOME"] = temphome
            os.environ["HOME"] = temphome
            notebook_dir = temphome

        cmd = [
            "jupyterhub-singleuser",
            "--ip=0.0.0.0",
            "--port=8888",
            "--no-browser",
            f"--log-level={log_level}",
            "--ContentsManager.allow_hidden=True",
            "--ContentsManager.hide_globs=[]",
            f"--ContentsManager.preferred_dir={notebook_dir}",
            f"--ContentsManager.root_dir={notebook_dir}",
            "--KernelSpecManager.ensure_native_kernel=False",
            "--LabApp.check_for_updates_class=jupyterlab.NeverCheckForUpdate",
            "--MappingKernelManager.default_kernel_name=lsst",
            "--QtExporter.enabled=False",
            "--PDFExporter.enabled=True",
            f"--Serverapp.root_dir={notebook_dir}",
            "--WebPDFExporter.enabled=False",
        ]
        cmd.extend(self._set_timeout_variables())
        self._logger.debug("Command to run:", command=cmd)
        # Flush open files before exec()
        sys.stdout.flush()
        sys.stderr.flush()
        # exec the Jupyter process directly.  We use os.execvpe()
        # because we have a list of arguments we just created and we
        # want to pass the environment we built up.
        os.execvpe(cmd[0], cmd, env=self._env)
