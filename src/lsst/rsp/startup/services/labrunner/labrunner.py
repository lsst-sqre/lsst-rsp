"""RSP Lab launcher."""

import configparser
import contextlib
import datetime
import hashlib
import json
import os
import pwd
import shutil
import sys
import time
from pathlib import Path
from typing import Any
from urllib.parse import parse_qsl, urlparse

import structlog

from .... import get_access_token, get_digest
from ....utils import get_jupyterlab_config_dir, get_runtime_mounts_dir
from ...constants import (
    APP_NAME,
    ETC_PATH,
    MAX_NUMBER_OUTPUTS,
    PREVIOUS_LOGGING_CHECKSUMS,
)
from ...exceptions import RSPErrorCode, RSPStartupError
from ...models.noninteractive import NonInteractiveExecutor
from ...storage.command import Command
from ...storage.logging import configure_logging

__all__ = ["LabRunner"]


class LabRunner:
    """Class to start JupyterLab using the environment supplied by
    JupyterHub and the Nublado controller.

    This environment is very Rubin-specific and opinionated, and will
    likely not work for anyone else's science platform.

    If that's you, use this for inspiration, but don't expect this to
    work out of the box.
    """

    def __init__(self) -> None:
        # We start with a copy of our own environment
        self._env = os.environ.copy()
        self._debug = bool(self._env.get("DEBUG", ""))
        configure_logging(debug=self._debug)
        self._logger = structlog.get_logger(APP_NAME)
        self._broken = False
        for req_env in ("JUPYTERHUB_BASE_URL", "HOME"):
            if req_env not in self._env:
                exc = RSPStartupError("EBADENV", None, req_env)
                self._set_abnormal_startup(exc)
        # If no home, use /tmp?  It won't work but at least if we create
        # stuff there it will be harmless, and the user will get a message
        # indicating what's wrong.
        self._home = Path(self._env.get("HOME", "/tmp"))
        self._cmd = Command(ignore_fail=True, logger=self._logger)

    def go(self) -> None:
        """Start the user lab."""
        # If the user somehow manages to screw up their local environment
        # so badly that Jupyterlab won't even start, we will have to
        # bail them out on the fileserver end.  Since Jupyter Lab is in
        # its own venv, which is not writeable by the user, this should
        # require quite a bit of creativity.
        try:
            self._relocate_user_environment_if_requested()
            self._configure_env()
        except OSError as exc:
            self._set_abnormal_startup(exc)

        # Clean up stale cache, check for writeability, try to free some
        # space if necessary.  This stage will manage its own abnormality,
        # since it tries to take some corrective action.
        self._tidy_homedir()

        # If everything seems OK so far, copy files into the user's home
        # space and set up git-lfs.

        if not self._broken:
            try:
                self._copy_files_to_user_homedir()
                self._setup_git()
            except OSError as exc:
                self._set_abnormal_startup(exc)

        # Decide between interactive and noninteractive start, do
        # things that change between those two, and launch the Lab
        self._launch()

    def _set_abnormal_startup(self, exc: OSError) -> None:
        """Take an OSError, convert it into an RSPStartupError if necessary,
        and then set the env variables that rsp-jupyter-extensions will use
        to report the error to the user at Lab startup.
        """
        self._broken = True
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

    def _clear_abnormal_startup(self) -> None:
        for e in ("", "_ERRNO", "_STRERROR", "_MESSAGE", "_ERRORCODE"):
            del self._env[f"ABNORMAL_STARTUP{e}"]
            self._broken = False
            self._logger.info("Cleared abnormal startup condition")

    def _relocate_user_environment_if_requested(self) -> None:
        if not self._env.get("RESET_USER_ENV", ""):
            return
        self._logger.debug("User environment relocation requested")
        now = datetime.datetime.now(datetime.UTC).strftime("%Y%m%d%H%M%S")
        reloc = self._home / f".user_env.{now}"
        for candidate in ("cache", "conda", "eups", "local", "jupyter"):
            c_path = self._home / f".{candidate}"
            if c_path.is_dir():
                if not reloc.is_dir():
                    reloc.mkdir()
                tgt = reloc / candidate
                self._logger.debug(f"Moving {c_path.name} to {tgt.name}")
                shutil.move(c_path, tgt)
        u_setups = self._home / "notebooks" / ".user_setups"
        if u_setups.is_file():
            tgt = reloc / "notebooks" / "user_setups"
            tgt.parent.mkdir()
            self._logger.debug(f"Moving {u_setups.name} to {tgt}")
            shutil.move(u_setups, tgt)

    #
    # Next up, a big block of setting up our subprocess environment.
    #
    def _configure_env(self) -> None:
        self._logger.debug("Configuring environment for JupyterLab process")
        self._set_user()
        self._set_tmpdir_if_scratch_available()
        self._set_butler_cache()
        self._set_cpu_variables()
        self._set_image_digest()
        self._expand_panda_tilde()
        self._set_firefly_variables()
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

    def _check_user_scratch_subdir(self, path: Path) -> Path | None:
        # This is very Rubin specific.  We generally have a large
        # world-writable filesystem in a scratch path.
        #
        # Given a path we will test that SCRATCH_PATH/user/path can be
        # created as a writable directory (or that it already exists
        # as a writable directory).  If it can be (or is), we return the
        # whole path, and if not, we return None.
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
        user_scratch_path = scratch_path / user / path
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
        return user_scratch_path

    def _set_tmpdir_if_scratch_available(self) -> None:
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
        temp_path = self._check_user_scratch_subdir(Path("tmp"))
        if temp_path:
            self._env["TMPDIR"] = str(temp_path)
            self._logger.debug(f"Set TMPDIR to {temp_path!s}")
        else:
            self._logger.debug("Did not set TMPDIR")

    def _set_butler_cache(self) -> None:
        # This is basically the same story as TMPDIR.
        env_v = "DAF_BUTLER_CACHE_DIRECTORY"
        dbcd = self._env.get(env_v, "")
        if dbcd:
            self._logger.debug(
                f"Not setting DAF_BUTLER_CACHE_DIRECTORY: already set to"
                f" {dbcd}"
            )
            return
        temp_path = self._check_user_scratch_subdir(Path("butler_cache"))
        if temp_path:
            self._env[env_v] = str(temp_path)
            self._logger.debug(
                f"Set DAF_BUTLER_CACHE_DIRECTORY to {temp_path!s}"
            )
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
        if cpu_limit < 1:
            cpu_limit = 1
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

    def _set_firefly_variables(self) -> None:
        self._logger.debug("Setting firefly variables")
        firefly_route = self._env.get("FIREFLY_ROUTE", "/firefly")
        ext_url = self._env.get(
            "EXTERNAL_INSTANCE_URL", "https://localhost:8888"
        )
        self._env["FIREFLY_URL"] = (
            f"{ext_url.strip('/')}/{firefly_route.lstrip('/')}"
        )
        self._logger.debug(f"Firefly URL -> '{self._env['FIREFLY_URL']}'")

    def _force_jupyter_prefer_env_path_false(self) -> None:
        # cf https://discourse.jupyter.org/t/jupyter-paths-priority-order/7771
        # and https://jupyter-core.readthedocs.io/en/latest/changelog.html#id63
        #
        # As long as we're running from the stack Python, we need to ensure
        # this is turned off.
        self._logger.debug("Forcing JUPYTER_PREFER_ENV_PATH to 'no'")
        self._env["JUPYTER_PREFER_ENV_PATH"] = "no"

    def _set_butler_credential_variables(self) -> None:
        # We split this up into environment manipulation and later
        # file substitution.  This is the environment part.
        self._logger.debug("Setting Butler credential variables")
        cred_dir = self._home / ".lsst"
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

    #
    # The second big block tries to tidy the home directory.
    #
    def _tidy_homedir(self) -> None:
        self._clean_astropy_cache()
        self._test_for_space()

    def _clean_astropy_cache(self) -> None:
        # This is extremely conservative.  We only find URLs with an
        # "Expires" parameter (in practice, s3 signed URLs), and remove
        # the key and contents if the expiration is in the past.
        cachedir = self._home / ".astropy" / "cache" / "download" / "url"
        if not cachedir.exists():
            return
        candidates = [x for x in cachedir.iterdir() if x.is_dir()]
        for c in candidates:
            urlfile = c / "url"
            if not urlfile.is_file():
                continue
            try:
                url = urlfile.read_text()
            except Exception:
                self._logger.exception("Could not read {urlfile!s}")
                continue
            qry = urlparse(url).query
            if not qry:
                continue
            for key, value in parse_qsl(qry):
                if key.lower() == "expires":
                    self._handle_expiry(c, value)

    def _handle_expiry(self, cachefile: Path, expiry: str) -> None:
        try:
            exptime = int(expiry)
        except ValueError:
            self._logger.exception("Could not parse Expires header")
            return
        if time.time() > exptime:
            self._logger.debug(f"Removing expired cache {cachefile!s}")
            try:
                self._remove_astropy_cachedir(cachefile)
            except OSError:
                self._logger.exception(f"Failed to remove cache {cachefile!s}")
                # Having found the parameter, we are done with this url.
                return

    def _remove_astropy_cachedir(self, cachedir: Path) -> None:
        (cachedir / "url").unlink()
        (cachedir / "contents").unlink()
        cachedir.rmdir()

    def _test_for_space(self) -> None:
        cachefile = self._home / ".cache" / "1mb.txt"
        try:
            self._write_a_megabyte(cachefile)
        except OSError as exc:
            self._logger.warning("Could not write 1MB of text")
            self._set_abnormal_startup(exc)
        if self._broken:
            self._try_emergency_cleanup()
            try:
                # Did that clear enough room?
                self._write_a_megabyte(cachefile)
                self._clear_abnormal_startup()
            except OSError:
                pass  # Nope, stay broken.

    def _write_a_megabyte(self, cachefile: Path) -> None:
        # Try to write a 1M block, which should be enough to start the lab.
        sixteen = "0123456789abcdef"
        mega = sixteen * 64 * 1024

        parent = cachefile.parent
        parent.mkdir(exist_ok=True)
        cachefile.write_text(mega)
        self._remove_cachefile(cachefile)

    def _remove_cachefile(self, cachefile: Path) -> None:
        if cachefile.is_file():
            cachefile.unlink()

    def _try_emergency_cleanup(self) -> None:
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

    #
    # The third big block is a bunch of file manipulation.
    #
    def _copy_files_to_user_homedir(self) -> None:
        self._logger.debug("Copying files to user home directory")
        self._copy_butler_credentials()
        self._copy_logging_profile()
        self._copy_dircolors()
        self._copy_etc_skel()

    def _copy_butler_credentials(self) -> None:
        if "AWS_SHARED_CREDENTIALS_FILE" in self._env:
            self._merge_aws_creds()
        if "PGPASSFILE" in self._env:
            self._merge_pgpass()

    def _merge_aws_creds(self) -> None:
        #
        # Merge the config in the original credentials file and the one
        # in our homedir.  For any given section, we assume that the
        # information in the container ("original credentials files")
        # is correct, but leave any other user config alone.
        #
        ascf = "AWS_SHARED_CREDENTIALS_FILE"
        for ev in (ascf, "ORIG_" + ascf):
            if ev not in self._env:
                raise RSPStartupError(RSPErrorCode.EBADENV, None, ev)
        hc_path = Path(self._env["AWS_SHARED_CREDENTIALS_FILE"])
        if not hc_path.parent.exists():
            hc_path.parent.mkdir(mode=0o700, parents=True)
        hc_path.touch(mode=0o600, exist_ok=True)
        home_config = configparser.ConfigParser()
        home_config.read(str(hc_path))
        ro_config = configparser.ConfigParser()
        ro_config.read(self._env["ORIG_AWS_SHARED_CREDENTIALS_FILE"])
        for sect in ro_config.sections():
            home_config[sect] = ro_config[sect]
        with hc_path.open("w") as f:
            home_config.write(f)

    def _merge_pgpass(self) -> None:
        #
        # Same as above, but for pgpass files.
        #
        config = {}
        # Get current config from homedir
        ppf = "PGPASSFILE"
        for ev in (ppf, "ORIG_" + ppf):
            if ev not in self._env:
                raise RSPStartupError(RSPErrorCode.EBADENV)
        home_pgpass = Path(self._env["PGPASSFILE"])
        if not home_pgpass.parent.exists():
            home_pgpass.parent.mkdir(mode=0o700, parents=True)
        home_pgpass.touch(mode=0o600, exist_ok=True)
        lines = home_pgpass.read_text().splitlines()
        for line in lines:
            if ":" not in line:
                continue
            connection, passwd = line.rsplit(":", maxsplit=1)
            config[connection] = passwd.rstrip()
        # Update config from container-supplied one
        ro_pgpass = Path(self._env["ORIG_PGPASSFILE"])
        lines = ro_pgpass.read_text().splitlines()
        for line in lines:
            if ":" not in line:
                continue
            connection, passwd = line.rsplit(":", maxsplit=1)
            config[connection] = passwd.rstrip()
        with home_pgpass.open("w") as f:
            for connection in config:
                f.write(f"{connection}:{config[connection]}\n")

    def _copy_logging_profile(self) -> None:
        self._logger.debug("Copying logging profile if needed")
        user_profile = (
            self._home
            / ".ipython"
            / "profile_default"
            / "startup"
            / "20-logging.py"
        )
        #
        # We have a list of previous supplied versions of 20-logging.py.
        #
        # If the one we have has a hash that matches any of those, then
        # there is a new container-supplied 20-logging.py that should replace
        # it.  However, if we have a 20-logging.py that does not match
        # any of those, then it has been locally modified, and we should
        # not replace it.  If we don't have one at all, we need to copy it
        # into place.
        #
        copy = False
        if not user_profile.is_file():
            copy = True  # It doesn't exist, so we need one.
        else:
            user_loghash = hashlib.sha256(
                user_profile.read_bytes()
            ).hexdigest()
            if user_loghash in PREVIOUS_LOGGING_CHECKSUMS:
                self._logger.debug(
                    f"User log profile '{user_loghash}' is"
                    " out-of-date; replacing with current version."
                )
                copy = True
        if copy:
            pdir = user_profile.parent
            if not pdir.is_dir():
                pdir.mkdir(parents=True)
            jl_path = get_jupyterlab_config_dir()
            srcfile = jl_path / "etc" / "20-logging.py"
            # Location changed with two-python container.  Try each.
            if not srcfile.is_file():
                srcfile = jl_path / "20-logging.py"
            if not srcfile.is_file():
                self._logger.warning("Could not find source user log profile.")
                return
            user_profile.write_bytes(srcfile.read_bytes())

    def _copy_dircolors(self) -> None:
        self._logger.debug("Copying dircolors if needed")
        if not (self._home / ".dir_colors").exists():
            self._logger.debug("Copying dircolors")
            dc = ETC_PATH / "dircolors.ansi-universal"
            dc_txt = dc.read_text()
            (self._home / ".dir_colors").write_text(dc_txt)
        else:
            self._logger.debug("Copying dircolors not needed")

    def _copy_etc_skel(self) -> None:
        self._logger.debug("Copying files from /etc/skel if they don't exist")
        etc_skel = ETC_PATH / "skel"
        contents = etc_skel.walk()
        #
        # We assume that if the file exists at all, we should leave it alone.
        # Users are allowed to modify these, after all.
        #
        for entry in contents:
            dirpath = entry[0]
            dirs = [Path(x) for x in entry[1]]
            files = [Path(x) for x in entry[2]]
            # Determine what the destination directory should be
            if dirpath == etc_skel:
                current_dir = self._home
            else:
                current_dir = (
                    self._home / str(dirpath)[(len(str(etc_skel)) + 1) :]
                )
            # For each directory in the tree at this level:
            # if we don't already have one in our directory, make it.
            for d_item in dirs:
                if not (current_dir / d_item).is_dir():
                    (current_dir / d_item).mkdir()
                    self._logger.debug(f"Creating {current_dir / d_item!s}")
            # For each file in the tree at this level:
            # if we don't already have one in our directory, copy the
            # contents.
            for f_item in files:
                if not (current_dir / f_item).exists():
                    src = Path(entry[0] / f_item)
                    self._logger.debug(f"Creating {current_dir / f_item!s}")
                    src_contents = src.read_bytes()
                    (current_dir / f_item).write_bytes(src_contents)

    #
    # Now that we're not checking out notebooks anymore, all we have to do
    # with Git is install git-lfs.
    #
    def _setup_git(self) -> None:
        # Set up Git LFS
        self._setup_gitlfs()

    def _setup_gitlfs(self) -> None:
        # Check for git-lfs
        self._logger.debug("Installing Git LFS if needed")
        if not self._check_for_git_lfs():
            self._cmd.run("git", "lfs", "install")
            self._logger.debug("Git LFS installed")

    def _check_for_git_lfs(self) -> bool:
        gitconfig = self._home / ".gitconfig"
        if gitconfig.is_file():
            gc = gitconfig.read_text().splitlines()
            for line in gc:
                line.strip()
                if line == '[filter "lfs"]':
                    return True
        return False

    #
    # Start the lab.
    #
    def _launch(self) -> None:
        # We're about to start the lab: set the flag saying we're running
        # inside the lab.  It's used by shell startup.
        self._env["RUNNING_INSIDE_JUPYTERLAB"] = "TRUE"
        if bool(self._env.get("NONINTERACTIVE", "")):
            self._start_noninteractive()
            # We exec a lab; control never returns here
        self._modify_interactive_settings()
        self._start()

    def _modify_interactive_settings(self) -> None:
        self._logger.debug("Modifying interactive settings if needed")
        self._manage_access_token()
        self._increase_log_limit()

    def _increase_log_limit(self) -> None:
        self._logger.debug("Increasing log limit if needed")
        settings: dict[str, Any] = {}
        settings_dir = (
            self._home
            / ".jupyter"
            / "lab"
            / "user-settings"
            / "@jupyterlab"
            / "notebook-extension"
        )
        settings_dir.mkdir(parents=True, exist_ok=True)
        settings_file = settings_dir / "tracker.jupyterlab.settings"
        if settings_file.is_file():
            with settings_file.open() as f:
                settings = json.load(f)
        current_limit = settings.get("maxNumberOutputs", 0)
        if current_limit < MAX_NUMBER_OUTPUTS:
            self._logger.warning(
                f"Changing maxNumberOutputs in {settings_file!s}"
                f" from {current_limit} to {MAX_NUMBER_OUTPUTS}"
            )
            settings["maxNumberOutputs"] = MAX_NUMBER_OUTPUTS
            with settings_file.open("w") as f:
                json.dump(settings, f, sort_keys=True, indent=4)
        else:
            self._logger.debug("Log limit increase not needed")

    def _manage_access_token(self) -> None:
        self._logger.debug("Updating access token")
        tokfile = self._home / ".access_token"
        tokfile.unlink(missing_ok=True)
        ctr_token = get_runtime_mounts_dir() / "secrets" / "token"
        if ctr_token.exists():
            self._logger.debug(f"Symlinking {tokfile!s}->{ctr_token!s}")
            tokfile.symlink_to(ctr_token)
            with contextlib.suppress(NotImplementedError):
                tokfile.chmod(0o600, follow_symlinks=False)
            return
        self._logger.debug("Did not find container token file")
        token = get_access_token()
        if token:
            tokfile.touch(mode=0o600)
            tokfile.write_text(token)
            self._logger.debug(f"Created {tokfile}")
        else:
            self._logger.debug("Could not determine access token")

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
        for setting in timeout_map:
            val = self._env.get(setting, "")
            if val:
                result.append(f"--{timeout_map[setting]}={val}")
        return result

    def _start(self) -> None:
        log_level = "DEBUG" if self._debug else "INFO"
        cmd = [
            "jupyterhub-singleuser",
            "--ip=0.0.0.0",
            "--port=8888",
            "--no-browser",
            f"--notebook-dir={self._home!s}",
            f"--log-level={log_level}",
            "--ContentsManager.allow_hidden=True",
            "--FileContentsManager.hide_globs=[]",
            "--KernelSpecManager.ensure_native_kernel=False",
            "--QtExporter.enabled=False",
            "--PDFExporter.enabled=False",
            "--WebPDFExporter.allow_chromium_download=True",
            "--MappingKernelManager.default_kernel_name=lsst",
            "--LabApp.check_for_updates_class=jupyterlab.NeverCheckForUpdate",
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
