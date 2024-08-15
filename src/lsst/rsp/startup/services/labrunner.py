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
from pathlib import Path
from subprocess import SubprocessError
from time import sleep
from typing import Any
from urllib.parse import urlparse

import structlog
import symbolicmode

from ... import get_access_token, get_digest
from ...utils import get_jupyterlab_config_dir, get_runtime_mounts_dir
from ..constants import (
    APP_NAME,
    ETC_PATH,
    MAX_NUMBER_OUTPUTS,
    PREVIOUS_LOGGING_CHECKSUMS,
    SCRATCH_PATH,
)
from ..models.noninteractive import NonInteractiveExecutor
from ..storage.command import Command
from ..storage.logging import configure_logging

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
        self._home = Path(self._env["HOME"])  # If unset, it's OK to die.
        if "JUPYTERHUB_BASE_URL" not in self._env:
            raise ValueError("'JUPYTERHUB_BASE_URL' must be set")
        self._user = ""
        self._stash: dict[str, str] = {}  # Used for settings we don't expose.
        self._cmd = Command(ignore_fail=True, logger=self._logger)

    def go(self) -> None:
        """Start the user lab."""
        # If the user somehow manages to screw up their local environment
        # so badly that Jupyterlab won't even start, we will have to
        # bail them out on the fileserver end.  Since Jupyter Lab is in
        # its own venv, which is not writeable by the user, this should
        # require quite a bit of creativity.

        self._relocate_user_environment_if_requested()

        # Set up environment variables that we'll need either to launch the
        # Lab or for the user's terminal environment
        self._configure_env()

        # Copy files into the user's home space.  If $HOME is not mounted
        # and writeable, things will go wrong here.
        self._copy_files_to_user_homedir()

        # Check out notebooks, and set up git-lfs
        self._setup_git()

        # Decide between interactive and noninteractive start, do
        # things that change between those two, and launch the Lab
        self._launch()

    def _externalize(self, setting: str) -> str:
        # We build multiple settings by concatenating `EXTERNAL_INSTANCE_URL`
        # with some other string.  Make this robust by accepting either
        # a slash or no slash on the end of `EXTERNAL_INSTANCE_URL` and
        # returning a string with exactly one slash as a separator between
        # the external URL and the setting.
        ext_url = self._env["EXTERNAL_INSTANCE_URL"]
        return f"{ext_url.strip('/')}/{setting.lstrip('/')}"

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
        self._set_launch_params()
        self._set_firefly_variables()
        self._force_jupyter_prefer_env_path_false()
        self._set_butler_credential_variables()
        self._logger.debug("Lab process environment", env=self._env)

    def _set_user(self) -> None:
        self._logger.debug("Determining user name")
        user = self._env.get("USER", "")
        if not user:
            self._env["USER"] = pwd.getpwuid(os.getuid()).pw_name

    def _set_tmpdir_if_scratch_available(self) -> None:
        # This is very Rubin-specific.  We generally have a large
        # world-writeable filesystem out in SCRATCH_PATH (/scratch).
        # Assuming that TMPDIR is not already set (e.g. by the spawner),
        # we will try to create <SCRATCH_PATH>/<user>/tmp and ensure it is a
        # writeable directory, and if it is, TMPDIR will be repointed to it.
        # This will then reduce our ephemeral storage issues, which have
        # caused mass pod eviction and destruction of the prepull cache.
        #
        # In our tests at the IDF, on a 2CPU/8GiB "Medium", TMPDIR on
        # /scratch (NFS) is about 15% slower than on local ephemeral storage.
        self._logger.debug(f"Resetting TMPDIR if {SCRATCH_PATH} available")
        user = self._env["USER"]  # We know it's set now
        tmpdir = self._env.get("TMPDIR", "")
        if tmpdir:
            self._logger.debug(f"Not setting TMPDIR: already set to {tmpdir}")
            return
        if not SCRATCH_PATH.is_dir():
            self._logger.debug(
                f"{SCRATCH_PATH} is not a directory.  Not setting TMPDIR."
            )
        user_scratch = SCRATCH_PATH / user / "tmp"
        try:
            user_scratch.mkdir(parents=True, exist_ok=True)
        except (OSError, FileExistsError) as exc:
            self._logger.warning(
                f"Could not create TMPDIR at {user_scratch!s}: {exc}"
            )
            return
        if not os.access(user_scratch, os.W_OK):
            self._logger.warning(f"Unable to write to {user_scratch}")
            return
        self._env["TMPDIR"] = str(user_scratch)

    def _set_butler_cache(self) -> None:
        # This should be called *after* _set_tmpdir_if_scratch_available()
        # at least for now.  We may eventually want to force it to local
        # ephemeral storage and demand enough ephemeral storage to cover it
        # (currently about 500MB).
        #
        # For now, though, let's set it to `butler_cache` inside `TMPDIR`
        dbcd = self._env.get("DAF_BUTLER_CACHE_DIRECTORY", "")
        if dbcd:
            self._logger.debug(
                f"Not setting DAF_BUTLER_CACHE_DIRECTORY: already set to"
                f" {dbcd}"
            )
            return
        # Yes, we know that ruff doesn't like `/tmp`
        # In any sane RSP environment, either we will have set TMPDIR, or
        # /tmp will be on ephemeral storage.
        tmpdir = Path(self._env.get("TMPDIR", "/tmp"))  # noqa: S108
        dbc = tmpdir / "butler_cache"
        try:
            dbc.mkdir(parents=True, exist_ok=True)
        except (OSError, FileExistsError) as exc:
            self._logger.warning(
                f"Could not create DAF_BUTLER_CACHE_DIRECTORY at"
                f" {dbc!s}: {exc}"
            )
            return
        if not os.access(dbc, os.W_OK):
            self._logger.warning(f"Unable to write to {dbc}")
            return
        self._env["DAF_BUTLER_CACHE_DIRECTORY"] = str(dbc)

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

    def _set_launch_params(self) -> None:
        # We're getting rid of the complicated stuff based on
        # HUB_SERVICE_HOST, since that was pre-version-3 nublado.
        self._logger.debug("Setting launch parameters")
        base_url = self._env["JUPYTERHUB_BASE_URL"]
        jh_path = f"{base_url}hub"
        ext_url = self._env.get("EXTERNAL_INSTANCE_URL", "")
        host = urlparse(ext_url).hostname or ""

        self._stash["jupyterhub_path"] = jh_path
        self._stash["external_host"] = host
        self._logger.debug(
            f"Set host to '{host}', and Hub path to '{jh_path}'"
        )

    def _set_firefly_variables(self) -> None:
        self._logger.debug("Setting firefly variables")
        firefly_route = self._env.get("FIREFLY_ROUTE", "/firefly")
        self._env["FIREFLY_URL"] = self._externalize(firefly_route)
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
    # The second big block is a bunch of file manipulation.
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
        # alas, Path.walk() requires Python 3.12, which isn't in the
        # stack containers yet.  Once the Lab/stack split is finalized,
        # we can make this simpler.
        contents = os.walk(etc_skel)
        #
        # We assume that if the file exists at all, we should leave it alone.
        # Users are allowed to modify these, after all.
        #
        for entry in contents:
            dirs = [Path(x) for x in entry[1]]
            files = [Path(x) for x in entry[2]]
            # Determine what the destination directory should be
            if entry[0] == str(etc_skel):
                current_dir = self._home
            else:
                current_dir = self._home / entry[0][(len(str(etc_skel)) + 1) :]
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

    def _setup_git(self) -> None:
        # Refresh standard notebooks
        self._refresh_notebooks()
        # Set up Git LFS
        self._setup_gitlfs()

    def _refresh_notebooks(self) -> None:
        # Find the notebook specs.  I think we can ditch our fallbacks now.
        self._logger.debug("Refreshing notebooks")
        urls = self._env.get("AUTO_REPO_SPECS", "").split(",")
        if not urls:
            self._logger.debug("No repos listed in 'AUTO_REPO_SPECS'")
            return
        timeout = 30  # Probably don't need to parameterize it.
        reloc_msg = ""
        now = datetime.datetime.now(datetime.UTC).isoformat()
        for url in urls:
            try:
                repo, branch = url.split("@", maxsplit=1)
            except ValueError:
                self._logger.warning(
                    "Could not get repo/branch information from"
                    f" '{self._env['AUTO_REPO_SPECS']}'"
                )
                return
            repo_path = urlparse(repo).path
            repo_name = Path(repo_path).name
            if repo_name.endswith(".git"):
                repo_name = repo_name[:-4]
            dirname = self._home / "notebooks" / repo_name
            if dirname.is_dir():
                # We're going to make the simplifying assumption that the
                # user owns the directory and is in the directory's group.
                # If not, probably a lot else has already gone wrong.
                can_write = dirname.stat().st_mode & 0o222
                if can_write:
                    self._logger.debug(f"'{dirname!s}' is writeable; moving")
                    newname = Path(f"{dirname!s}.{now}")
                    reloc_msg += f"* '{dirname!s}' -> '{newname!s}'\n"
                    # We're also going to assume the user DOES have write
                    # permission in the parent directory.  Again, if not,
                    # terrible things probably already happened.
                    dirname.rename(newname)
                else:
                    # If the repository exists and is not writeable, and has
                    # the same last commit as the remote, then we don't
                    # need to update it.
                    if self._compare_local_and_remote(
                        dirname, branch, timeout
                    ):
                        self._logger.debug(f"'{dirname!s}' is r/o and current")
                        continue  # Up-to-date; we don't need to do anything
                    # It's writeable or stale; re-clone.
                    self._logger.debug(f"Need to remove '{dirname!s}'")
                    symbolicmode.chmod(dirname, "u+w", recurse=True)
                    shutil.rmtree(dirname)
            # If the directory existed, it's gone now.
            self._logger.debug(f"Cloning {repo}@{branch}")
            proc = self._cmd.run(
                "git",
                "clone",
                "--depth",
                "1",
                repo,
                "-b",
                branch,
                str(dirname),
                timeout=timeout,
            )
            if proc.returncode != 0:
                self._logger.error("git clone failed", proc=proc)
                return
            symbolicmode.chmod(dirname, "a-w", recurse=True)
        if reloc_msg:
            hdr = (
                "# Directory relocation\n\n"
                "The following directories were writeable, and were moved:\n"
                "\n"
                "\n"
            )
            reloc_msg = hdr + reloc_msg
            (self._home / "notebooks" / "00_README_RELOCATION.md").write_text(
                reloc_msg
            )

        self._logger.debug("Refreshed notebooks")

    def _compare_local_and_remote(
        self, path: Path, branch: str, timeout: int
    ) -> bool:
        # Returns True if git repo checked out to path has the same
        # commit hash as the remote.
        #
        # Git wants you to be in the working tree
        rx = self._cmd.run(
            "git",
            "rev-parse",
            "HEAD",
            cwd=path,
            timeout=timeout,
        )
        local_sha = rx.stdout.strip() if rx else None
        if not local_sha:
            self._logger.error(f"Could not determine local SHA for '{path!s}'")
            return False
        rx = self._cmd.run(
            "git",
            "config",
            "--get",
            "remote.origin.url",
            cwd=path,
            timeout=timeout,
        )
        remote = rx.stdout.strip() if rx else None
        if not remote:
            self._logger.error(
                "Could not determine git remote origin for" f"'{path!s}'"
            )
            return False
        rx = self._cmd.run(
            "git",
            "ls-remote",
            remote,
            timeout=timeout,
        )
        ls_remote = rx.stdout.strip() if rx else None
        lsr_lines = ls_remote.split("\n")
        remote_sha = None
        for line in lsr_lines:
            line.strip()
            if line.endswith(f"\trefs/heads/{branch}"):
                remote_sha = line.split()[0]
                break
        if not remote_sha:
            self._logger.error("Could not determine SHA for {remote}")
            return False
        self._logger.debug(f"local /remote SHA: {local_sha}/{remote_sha}")
        return local_sha == remote_sha

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
            "python3",
            "-s",
            "-m",
            "jupyter",
            "labhub",
            "--ip=0.0.0.0",
            "--port=8888",
            "--no-browser",
            f"--notebook-dir={self._home!s}",
            f"--hub-prefix={self._stash['jupyterhub_path']}",
            f"--hub-host={self._stash['external_host']}",
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
        # Set environment variable to indicate we are inside JupyterLab
        # (we want the shell to source loadLSST.bash once we are)
        if self._debug:
            # Maybe we want to parameterize these?
            retries = 10
            sleep_interval = 60
            for i in range(retries):
                self._logger.debug(f"Lab spawn attempt {i+1}/{retries}:")
                try:
                    proc = self._cmd.run(*cmd, env=self._env)
                except SubprocessError as exc:
                    self._logger.exception(
                        f"Command {cmd} failed to run", exc=exc
                    )
                if proc:
                    if proc.returncode:
                        self._logger.error(
                            f"Lab exited with returncode {proc.returncode}",
                            proc=proc,
                        )
                    else:
                        self._logger.warning(
                            "Lab process exited with returncode 0", proc=proc
                        )
                else:
                    self._logger.error(f"Lab process {cmd} failed to run")
                self._logger.info(f"Waiting for {sleep_interval}s")
                sleep(sleep_interval)
            self._logger.debug("Exiting")
            sys.exit(0)
        # Flush open files before exec()
        sys.stdout.flush()
        sys.stderr.flush()
        # In non-debug mode, we don't use a subprocess: we exec the
        # Jupyter Python process directly.  We use os.execvpe() because we
        # want the Python in the path (which we currently know to be the
        # stack Python), we have a list of arguments we just created, and
        # we want to pass the environment we built up.
        os.execvpe(cmd[0], cmd, env=self._env)
