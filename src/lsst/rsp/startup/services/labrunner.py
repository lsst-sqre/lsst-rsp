"""Control RSP startup."""

import configparser
import contextlib
import datetime
import hashlib
import json
import os
import sys
from pathlib import Path
from time import sleep
from typing import Any
from urllib.parse import urlparse

import structlog
import symbolicmode

from ... import get_access_token, get_digest
from ..constants import (
    app_name,
    etc,
    logging_checksums,
    max_number_outputs,
    noninteractive_config,
    top_dir,
)
from ..models.noninteractive import NonInteractiveExecution
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
        self._home = Path(self._env["HOME"])  # If unset, it's OK to die.
        self._user = ""

    def go(self) -> None:
        """Start the user lab."""
        # Reset the environment first.
        # This, currently, runs in the shell launcher shim.
        # There's an argument for leaving it there forever, in case the
        # user has messed up their Python environment so bad that they
        # can't even start a Python interpreter.
        self._configure_env()

        # Modify files.  If $HOME is not mounted and writeable, things will
        # go wrong here.
        self._modify_files()

        # Check out notebooks, set up git parameters and git-lfs
        self._setup_git()

        # Clear EUPS cache
        run("eups", "admin", "clearCache", logger=self._logger)

        # Decide between interactive and noninteractive start, do
        # things that change between those two, and launch the Lab
        self._launch()

    #
    # Next up, a big block of setting up our subprocess environment.
    #
    def _configure_env(self) -> None:
        self._logger.debug("Configuring environment for JupyterLab process")
        # Set USER if not present
        self._set_user()
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

    def _set_user(self) -> None:
        self._logger.debug("Determining user name")
        user = self._env.get("USER", "")
        if not user:
            proc = run("id", "-u", "-n", logger=self._logger)
            if proc is None:
                raise ValueError("Could not determine user")
            user = proc.stdout.strip()
            self._env["USER"] = user

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
            # force it to 1.
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
                if t_user in ("~", f"~{self._env['USER']}"):
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

    #
    # The second big block is a bunch of file manipulation.
    #
    def _modify_files(self) -> None:
        # Copy the Butler credentials into the user's space
        self._copy_butler_credentials()
        # Copy the logging profile
        self._copy_logging_profile()
        # Copy directory colorization info
        self._copy_dircolors()
        # Copy contents of /etc/skel
        self._copy_etc_skel()

    def _copy_butler_credentials(self) -> None:
        if (
            "AWS_SHARED_CREDENTIALS_FILE" in self._env
            or "PGPASSFILE" in self._env
        ):
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
        home_pgpass.touch(mode=0o600, exist_ok=True)
        lines = home_pgpass.read_text().splitlines()
        for line in lines:
            if ":" not in line:
                continue
            pg, pw = line.rsplit(":", maxsplit=1)
            config[pg] = pw.rstrip()
        # Update config from container-supplied one
        ro_pgpass = Path(self._env["ORIG_PGPASSFILE"])
        lines = ro_pgpass.read_text().splitlines()
        for line in lines:
            if ":" not in line:
                continue
            pg, pw = line.rsplit(":", maxsplit=1)
            config[pg] = pw.rstrip()
        with home_pgpass.open("w") as f:
            for pg in config:
                f.write(f"{pg}:{config[pg]}\n")

    def _copy_logging_profile(self) -> None:
        self._logger.debug("Copying logging profile if needed")
        user_profile = (
            self._home
            / ".ipython"
            / "profile_default"
            / "startup"
            / "20-logging.py"
        )
        copy = False
        user_loghash = ""
        if user_profile.is_file():
            user_loghash = hashlib.sha256(
                user_profile.read_bytes()
            ).hexdigest()
        ctr_profile = top_dir / "jupyterlab" / "20-logging.py"
        ctr_contents = ctr_profile.read_bytes()
        ctr_loghash = hashlib.sha256(ctr_contents).hexdigest()
        if user_loghash == ctr_loghash:
            self._logger.debug("User log profile is up-to-date; not copying")
        elif not user_loghash:
            self._logger.debug("No user log profile; copying")
            copy = True
        elif user_loghash in logging_checksums:
            self._logger.debug(
                f"User log profile '{user_loghash}' is" " out-of-date; copying"
            )
            copy = True
        else:
            self._logger.debug(
                f"User log profile '{user_loghash}' is"
                " locally modified; not copying"
            )
        if copy:
            user_profile.write_bytes(ctr_contents)

    def _copy_dircolors(self) -> None:
        self._logger.debug("Copying dircolors if needed")
        if not (self._home / ".dir_colors").exists():
            self._logger.debug("Copying dircolors")
            dc = etc / "dircolors.ansi-universal"
            dc_txt = dc.read_text()
            (self._home / ".dir_colors").write_text(dc_txt)
        else:
            self._logger.debug("Copying dircolors not needed")

    def _copy_etc_skel(self) -> None:
        self._logger.debug("Copying files from /etc/skel if they don't exist")
        es = etc / "skel"
        # alas, Path.walk() requires Python 3.12, which isn't in the
        # stack containers yet.
        contents = os.walk(es)
        #
        # We assume that if the file exists at all, we should leave it alone.
        # Users are allowed to modify these, after all.
        #
        for entry in contents:
            dirs = [Path(x) for x in entry[1]]
            files = [Path(x) for x in entry[2]]
            # Determine what the destination directory should be
            if entry[0] == str(es):
                current_dir = self._home
            else:
                current_dir = self._home / entry[0][(len(str(es)) + 1) :]
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
        # Set up email and name
        self._set_git_email_and_name()
        # Set up Git LFS
        self._setup_gitlfs()

    def _refresh_notebooks(self) -> None:
        # Find the notebook specs.  I think we can ditch our fallbacks now.
        self._logger.debug("Refreshing notebooks")
        urls = self._env.get("AUTO_REPO_SPECS", "")
        url_l = urls.split(",")
        if not url_l:
            self._logger.debug("No repos listed in 'AUTO_REPO_SPECS'")
            return
        # Specs should include the branch too.
        default_branch = self._env.get("AUTO_REPO_BRANCH", "prod")
        now = datetime.datetime.now(datetime.UTC).isoformat()
        timeout = 30  # Probably don't need to parameterize it.
        reloc_msg = ""
        for url in url_l:
            try:
                repo, branch = url.split("@", maxsplit=1)
            except ValueError:
                branch = default_branch
                repo = url
            repo_path = urlparse(repo).path
            repo_name = Path(repo_path).name
            if repo_name.endswith(".git"):
                repo_name = repo_name[:-4]
            dirname = self._home / "notebooks" / repo_name
            if dirname.is_dir():
                # check for writeability
                mode = dirname.stat().st_mode
                perms = mode & 0o777
                # We're going to make the simplifying assumption that the
                # user owns the directory and is in the directory's group.
                # If not, probably a lot else has already gone wrong.
                can_write = perms & 0o222
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
                    symbolicmode.chmod(dirname, "u+w")
                    self._recursive_remove(dirname)
            # If the directory existed, it's gone now.
            self._logger.debug(f"Cloning {repo}@{branch}")
            run(
                "git",
                "clone",
                "--depth",
                "1",
                repo,
                "-b",
                branch,
                str(dirname),
                timeout=timeout,
                logger=self._logger,
            )
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
        with contextlib.chdir(path):
            rx = run(
                "git",
                "rev-parse",
                "HEAD",
                timeout=timeout,
                logger=self._logger,
            )
            local_sha = rx.stdout.strip() if rx else ""
            rx = run(
                "git",
                "config",
                "--get",
                "remote.origin.url",
                timeout=timeout,
                logger=self._logger,
            )
            remote = rx.stdout.strip() if rx else ""
            rx = run(
                "git",
                "ls-remote",
                remote,
                timeout=timeout,
                logger=self._logger,
            )
            ls_remote = rx.stdout.strip() if rx else ""
            lsr_lines = ls_remote.split("\n")
            remote_sha = ""
            for line in lsr_lines:
                line.strip()
                if line.endswith(f"\trefs/heads/{branch}"):
                    remote_sha = line.split()[0]
                    break
        self._logger.debug(f"local /remote SHA: {local_sha}/{remote_sha}")
        return local_sha == remote_sha

    def _recursive_remove(self, tgt: Path) -> None:
        # You can't rmdir() a directory with contents, so...
        if not tgt.is_dir():
            self._logger.warning(f"Removal of non-directory {tgt!s} requested")
            return
        self._logger.debug(f"Removing directory {tgt!s}")
        contents = tgt.glob("*")
        for item in contents:
            if item.is_dir():
                self._recursive_remove(item)
            else:
                item.unlink()
                self._logger.debug(f"Removed item {item!s}")
        # All contents are gone; remove current directory
        tgt.rmdir()
        self._logger.debug(f"Removed directory {tgt!s}")

    def _set_git_email_and_name(self) -> None:
        self._logger.debug("Setting up git")
        ge = self._env.get("GITHUB_EMAIL", "")
        gn = self._env.get("GITHUB_NAME", "")
        if ge:
            self._logger.debug("Setting git 'user.email'")
            run(
                "git",
                "config",
                "--global",
                "--replace-all",
                "user.email",
                ge,
                logger=self._logger,
            )
        if gn:
            self._logger.debug("Setting git 'user.name'")
            run(
                "git",
                "config",
                "--global",
                "--replace-all",
                "user.name",
                gn,
                logger=self._logger,
            )

    def _setup_gitlfs(self) -> None:
        # Check for git-lfs
        self._logger.debug("Installing Git LFS if needed")
        if not self._check_for_git_lfs():
            run("git", "lfs", "install", logger=self._logger)
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
        if str_bool(self._env.get("NONINTERACTIVE", "")):
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
        else:
            settings_file.touch()
        current_limit = settings.get("maxNumberOutputs", 0)
        if current_limit < max_number_outputs:
            self._logger.warning(
                f"Changing maxNumberOutputs in {settings_file!s}"
                f" from {current_limit} to {max_number_outputs}"
            )
            settings["maxNumberOutputs"] = max_number_outputs
            with settings_file.open("w") as f:
                json.dump(settings, f, sort_keys=True, indent=4)
        else:
            self._logger.debug("Log limit increase not needed")

    def _manage_access_token(self) -> None:
        self._logger.debug("Updating access token")
        tokfile = self._home / ".access_token"
        tokfile.unlink(missing_ok=True)
        ctr_token = top_dir / "software" / "jupyterlab" / "secrets" / "token"
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
        launcher = NonInteractiveExecution.from_config(noninteractive_config)
        launcher.execute(env=self._env)

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
            f"--hub-prefix={self._env['JUPYTERHUB_PATH']}",
            f"--hub-host={self._env['EXTERNAL_HOST']}",
            f"--log-level={log_level}",
            "--ContentsManager.allow_hidden=True",
            "--FileContentsManager.hide_globs=[]",
            "--KernelSpecManager.ensure_native_kernel=False",
            "--QtExporter.enabled=False",
            "--PDFExporter.enabled=False",
            "--WebPDFExporter.allow_chromium_download=True",
            "--ServerApp.shutdown_no_activity_timeout="
            + self._env["NO_ACTIVITY_TIMEOUT"],
            "--MappingKernelManager.cull_idle_timeout="
            + self._env["CULL_KERNEL_IDLE_TIMEOUT"],
            "--MappingKernelManager.cull_connected="
            + self._env["CULL_KERNEL_CONNECTED"],
            "--MappingKernelManager.cull_interval="
            + self._env["CULL_KERNEL_INTERVAL"],
            "--MappingKernelManager.default_kernel_name=lsst",
            "--TerminalManager.cull_inactive_timeout="
            + self._env["CULL_TERMINAL_INACTIVE_TIMEOUT"],
            "--TerminalManager.cull_interval="
            + self._env["CULL_TERMINAL_INTERVAL"],
            "--LabApp.check_for_updates_class=jupyterlab.NeverCheckForUpdate",
        ]
        self._logger.debug("Command to run:", command=cmd)
        if self._debug:
            # Maybe we want to parameterize these?
            retries = 10
            sleep_interval = 60
            for i in range(retries):
                self._logger.debug(f"Lab spawn attempt {i+1}/{retries}:")
                proc = run(*cmd, logger=self._logger, env=self._env)
                self._logger.debug("Lab exited", proc=proc)
                self._logger.debug(f"Waiting for {sleep_interval}s")
                sleep(sleep_interval)
            self._logger.debug("Exiting")
            sys.exit(0)
        # Flush any open files before exec()
        os.sync()
        # In non-debug mode, we don't use a subprocess: we exec the
        # Jupyter Python process directly.  We use os.execvpe() because we
        # want the Python in the path (which we currently know to be the
        # stack Python), we have a list of arguments we just created, and
        # we want to pass the environment we built up.
        os.execvpe(cmd[0], cmd, env=self._env)
