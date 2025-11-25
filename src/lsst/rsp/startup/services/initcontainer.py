"""Init container for RSP."""

import configparser
import contextlib
import datetime
import hashlib
import json
import shutil
import time
from pathlib import Path
from typing import Any
from urllib.parse import parse_qsl, urlparse

import yaml

from ... import get_access_token
from ...utils import get_jupyterlab_config_dir, get_runtime_mounts_dir
from ..constants import (
    ETC_PATH,
    MAX_NUMBER_OUTPUTS,
    PREVIOUS_LOGGING_CHECKSUMS,
)
from ..exceptions import RSPErrorCode, RSPStartupError
from ._rspstartup import _RSPStartup


class InitContainer(_RSPStartup):
    """Class for running when the RSP is started.  All of the work that does
    not require environment propagation to the Lab environment goes here.

    This includes copying credential files into the user's home space,
    setting up git-lfs if needed, and basically whatever we can do that
    doesn't involve setting environment variables in the JupyterLab process.

    Because we cannot directly pass errors to the next phase, and we don't
    want the init container to exit with a non-zero return code, if there
    is an error in the init container, we will write a sentinel file to the
    user's home directory containing the error, and then when the startup
    process in the JupyterLab pod itself starts, read and remove that file,
    and start with "abnormal startup" set.

    Of course, this has its own problem: the most common error is that the
    user has exhausted their quota and cannot write files.  We will still
    test for free space in the startup container, and thus the error
    generated there will be the one that would have been generated here;
    perhaps not the specific file, but at least the notification that there
    is no space left for the user.
    """

    async def go(self) -> None:
        """Start the init container."""
        try:
            await self._tidy_homedir()
            await self._relocate_user_environment_if_requested()
            await self._copy_files_to_user_homedir()
            await self._setup_git()
            await self._modify_settings()
        except OSError as exc:
            await self._set_abnormal_startup(exc)

    # In general, if it does I/O, it's async, otherwise not.
    # Almost everything in the init container does I/O.

    async def _tidy_homedir(self) -> None:
        await self._clear_previous_error_files()
        await self._clean_astropy_cache()
        await self._test_for_space()

    async def _clear_previous_error_files(self) -> None:
        # We haven't written any on this spawning attempt yet; just because
        # we failed last startup doesn't mean we will this time.
        startup_errs = list(self._home.glob("ABNORMAL_STARTUP_*"))
        if startup_errs:
            # We know, conventionally, that we're going to put a Unix
            # datestamp into the startup file name and that will be lexically
            # sortable, so it's the last one that should generate the
            # exception we show as the error.
            #
            # Clean them all up, anyway, to the degree we can.  Hope springs
            # eternal.
            for errfile in startup_errs:
                try:
                    errfile.unlink(missing_ok=True)
                except Exception:
                    self._logger.exception(f"Could not remove {errfile!s}")

    async def _clean_astropy_cache(self) -> None:
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
                    await self._handle_expiry(c, value)

    async def _handle_expiry(self, cachefile: Path, expiry: str) -> None:
        try:
            exptime = int(expiry)
        except ValueError:
            self._logger.exception("Could not parse Expires header")
            return
        if time.time() > exptime:
            self._logger.debug(f"Removing expired cache {cachefile!s}")
            try:
                await self._remove_astropy_cachedir(cachefile)
            except OSError:
                self._logger.exception(f"Failed to remove cache {cachefile!s}")
                # Having found the parameter, we are done with this url.
                return

    async def _remove_astropy_cachedir(self, cachedir: Path) -> None:
        (cachedir / "url").unlink()
        (cachedir / "contents").unlink()
        cachedir.rmdir()

    async def _relocate_user_environment_if_requested(self) -> None:
        # If the user somehow manages to screw up their local environment
        # so badly that Jupyterlab won't even start, we will have to
        # bail them out on the fileserver end.  Since Jupyter Lab is in
        # its own venv, which is not writeable by the user, this should
        # require quite a bit of creativity.
        if not self._env.get("RESET_USER_ENV", ""):
            return
        self._logger.debug("User environment relocation requested")
        now = datetime.datetime.now(datetime.UTC).strftime("%Y%m%d%H%M%S")
        reloc = self._home / f".user_env.{now}"
        for candidate in (
            "cache",
            "conda",
            "config",
            "eups",
            "local",
            "jupyter",
        ):
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

    async def _copy_files_to_user_homedir(self) -> None:
        self._logger.debug("Copying files to user home directory")
        await self._copy_butler_credentials()
        await self._setup_dask()
        await self._copy_logging_profile()
        await self._copy_dircolors()
        await self._copy_etc_skel()

    async def _copy_butler_credentials(self) -> None:
        self._set_butler_credential_variables()
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
        # Note that this is a sync method because of ConfigParser.write().
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
            for connection, passwd in config.items():
                f.write(f"{connection}:{passwd}\n")

    async def _setup_dask(self) -> None:
        self._logger.debug("Setting up dask dashboard proxy information")
        cfgdir = self._home / ".config" / "dask"
        good_dashboard_config = False
        if cfgdir.is_dir():
            good_dashboard_config = await self._tidy_extant_config(cfgdir)
            # If we found and replaced the dashboard config, or if it was
            # already correct, we do not need to write a new file.
            #
            # If there is no config dir, there's nothing to tidy.
        if not good_dashboard_config:
            # We need to write a new file with the correct config.
            await self._inject_new_proxy(cfgdir / "dashboard.yaml")

    async def _tidy_extant_config(self, cfgdir: Path) -> bool:
        #
        # This is the controversial method.  We have had (at least) four
        # regimes of dask usage in the RSP.
        #
        # 1) Back in the mists of time (2018-ish), dask was present, and
        # all configuration was left to the user.
        # 2) For a while in 2019-2021-ish, we had a pretty sophisticated
        # system that allowed users to spawn whole additional pods, and we used
        # this for a really cool demo with Gaia DR1 data.  But then we moved to
        # the Nublado controller from KubeSpawner, and that no longer worked...
        # but we didn't do anything about the user config, so users had broken
        # config left over.
        # 3) from 2022-ish-to-2025 dask was not present.  The broken config
        # thus didn't cause any harm.
        # 4) in 2025, we added lsdb to the RSP.  lsdb relies on dask.  Suddenly
        # the abandoned config could cause harm, and without config, the wrong
        # dashboard information is presented to the user, which makes the lsdb
        # tutorial for Rubin DP1 data needlessly confusing.
        #
        # This is an attempt to clean that mess up.
        #
        # First we check for any files that don't do anything.  We know the
        # config will be YAML (dask config can also be JSON, but the RSP
        # machinery never wrote any such files, so we assume any JSON is
        # user-generated and not directly our problem), and those files will
        # be named with "yaml" or "yml" suffixes (both exist in extant user
        # config) per https://github.com/dask/dask/blob/main/dask/config.py .
        #
        # "Don't do anything" means that when deserialized to a Python object,
        # that object is None or empty, or it's a dictionary that contains only
        # empty objects as its leaves.  We move these files aside, with a date
        # suffix so that dask will no longer try to load them.
        #
        # Second, assuming the file survived that process, we check
        # specifically for the dashboard link, and correct it from its old,
        # non-user-domain-aware form, to a form that will be correct whether or
        # not user domains are enabled.  We save the original file with a date
        # suffix; again, dask will no longer try to load it.
        #
        # Other settings should stay the same; this may mean that the user has
        # settings for in-cluster kubernetes-driven workers, and those will
        # fail to spawn, but we haven't yet figured out how to safely remove
        # that configuration.
        #
        # If, after doing all of this, at least one file contains the correct
        # dashboard config, return True.  Otherwise, return False.

        retval = False

        for suffix in ("yaml", "yml"):
            files = list(cfgdir.glob(f"*.{suffix}"))
            if files:
                for fl in files:
                    today = (
                        datetime.datetime.now(tz=datetime.UTC)
                        .date()
                        .isoformat()
                    )
                    bk = Path(f"{fl!s}.{today}")
                    newcfg = await self._clean_empty_config(fl, bk)
                    if not newcfg:
                        continue  # next file
                    retval = await self._fix_dashboard(newcfg, fl, bk)
        return retval

    async def _clean_empty_config(
        self, fl: Path, bk: Path
    ) -> dict[str, Any] | None:
        # returns the deserialized yaml object if 1) it was deserializable
        # in the first place, and 2) it survived flensing.
        try:
            obj = yaml.safe_load(fl.read_text())
        except Exception:
            self._logger.exception(
                f"Failed to deserialize {fl!s} as yaml; moving to {bk}"
            )
            obj = None
        flensed = self._flense_dict(obj) if obj else None
        if not flensed:
            self._logger.warning(
                f"{fl} is empty after flensing; moving to {bk}"
            )
            shutil.move(fl, bk)
            return None
        # It's legal YAML and it's not empty
        return flensed

    async def _fix_dashboard(
        self, cfg: dict[str, Any], fl: Path, bk: Path
    ) -> bool:
        # Look for "distributed.dashboard.link".
        # It may have an older, non-user-domain-aware link in it,
        # and if so, then we need to replace it with the newer,
        # user-domain-aware one.

        # Dask does the template-from-environment substitution so these are
        # just strings.  The point is that "old" is not correct in a
        # user-domain-aware world, but "new" works in either case (and also
        # is something JupyterHub gives us for free, and does not rely on our
        # very-RSP-specific-and-going-away-with-service-discovery
        # EXTERNAL_INSTANCE_URL variable).

        # We return True if the deserialized contents of the file named by fl
        # (which will be passed to us as cfg) is a dashboard config with the
        # new template (whether initially or after correction) and False
        # otherwise.

        old = "{EXTERNAL_INSTANCE_URL}{JUPYTERHUB_SERVICE_PREFIX}"
        new = "{JUPYTERHUB_PUBLIC_URL}"

        try:
            val = cfg["distributed"]["dashboard"]["link"]
            if not isinstance(val, str):
                # Pretty sure this is an error, but leave it as the user's
                # problem.
                self._logger.warning(
                    "distributed.dashboard.link is not a string"
                )
                return False
        except KeyError:
            # We don't have the structure.  This file is not our problem.
            self._logger.debug(
                f"{fl!s} does not contain `distributed.dashboard.link`"
            )
            return False
        if val.find(new) > -1:
            # The structure is there and is already correct.
            # Return True and don't update anything.
            return True
        if val.find(old) < 0:
            # The structure is there but doesn't have the old-style link.
            # Assume, again, that's intentional.
            self._logger.debug(f"{val} does not contain {old}")
            return False

        # At this point, we have found distributed.dashboard.link.
        # It is a string, and it contains the old-style template so we want
        # to copy the original file to something without a yaml/yml suffix,
        # and replace the contents of the file with the old data but the
        # corrected link.
        try:
            # Make a backup.
            shutil.copy2(fl, bk)
        except Exception:
            self._logger.exception(f"Failed to back up {fl!s} to {bk!s}")
            return False
        newval = val.replace(old, new)
        if newval == val:
            self._logger.warning(
                f"Replacing '{old}' with '{new}' in '{val}' had no effect"
            )
            return False
        cfg["distributed"]["dashboard"]["link"] = newval
        self._logger.info(f"Replaced link in {fl!s}: {old}->{new}")
        try:
            fl.write_text(yaml.dump(cfg, default_flow_style=False))
        except Exception:
            self._logger.exception(f"Failed to write '{cfg}' to {fl!s}")
            return False
        return True

    async def _inject_new_proxy(self, tgt: Path) -> None:
        # Conventional for RSP.
        parent = tgt.parent
        try:
            parent.mkdir(parents=True, exist_ok=True)
        except FileExistsError:
            self._logger.exception(
                f"{parent!s} exists and is not a directory; aborting"
            )
            return
        newlink = "{JUPYTERHUB_PUBLIC_URL}proxy/{port}/status"
        goodlink = {"distributed": {"dashboard": {"link": newlink}}}
        if tgt.exists():
            try:
                obj = self._flense_dict(yaml.safe_load(tgt.read_text()))
                if obj is None:
                    obj = {}
                    # We'll turn it into an empty dict and get it in the
                    # update.  Why was there an empty dashboard.yaml?  Weird.
                elif obj == goodlink:
                    # This is the expected case.  There's only one entry in
                    # the target dashboard.yaml, and it's already correct.
                    return
                else:
                    self._logger.warning(
                        f"{tgt!s} exists; contains '{obj}'"
                        f" not just '{goodlink}'"
                    )
                obj.update(goodlink)
            except Exception:
                self._logger.exception(f"Failed to load {tgt!s}")
        else:
            obj = goodlink
        try:
            tgt.write_text(yaml.dump(obj, default_flow_style=False))
        except Exception:
            self._logger.exception(f"Failed to write '{obj}' to {tgt!s}")

    def _flense_dict(
        self, obj: dict[str, Any] | None
    ) -> dict[str, Any] | None:
        """Recursively walk a dict; any place a null value is found, it
        and its corresponding key are removed.
        """
        if not obj:
            return None
        retval: dict[str, Any] = {}
        for key, val in obj.items():
            if val is None:
                continue
            if not isinstance(val, dict):
                retval[key] = val
                continue
            flensed = self._flense_dict(val)
            if flensed is None:
                continue
            retval[key] = flensed
        return retval if retval else None

    async def _copy_logging_profile(self) -> None:
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

    async def _copy_dircolors(self) -> None:
        self._logger.debug("Copying dircolors if needed")
        if not (self._home / ".dir_colors").exists():
            self._logger.debug("Copying dircolors")
            dc = ETC_PATH / "dircolors.ansi-universal"
            dc_txt = dc.read_text()
            (self._home / ".dir_colors").write_text(dc_txt)
        else:
            self._logger.debug("Copying dircolors not needed")

    async def _copy_etc_skel(self) -> None:
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
    async def _setup_git(self) -> None:
        # Check for git-lfs
        self._logger.debug("Installing Git LFS if needed")
        if not await self._check_for_git_lfs():
            self._cmd.run("git", "lfs", "install")
            self._logger.debug("Git LFS installed")

    async def _check_for_git_lfs(self) -> bool:
        gitconfig = self._home / ".gitconfig"
        if gitconfig.is_file():
            gc = gitconfig.read_text().splitlines()
            for line in gc:
                line.strip()
                if line == '[filter "lfs"]':
                    return True
        return False

    async def _modify_settings(self) -> None:
        self._logger.debug("Modifying settings if needed")
        # These both write files; if either fails, start up but warn
        # the user their experience is likely to be bad.
        try:
            await self._manage_access_token()
            await self._increase_log_limit()
        except OSError as exc:
            await self._set_abnormal_startup(exc)

    async def _manage_access_token(self) -> None:
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

    async def _increase_log_limit(self) -> None:
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

    async def _set_abnormal_startup(self, exc: OSError) -> None:
        # Serialize error for consumption by lab startup process.
        # We return the instant at which we wrote it so that we can
        # remove the file if we can fix the error.
        await super()._set_abnormal_startup(exc)
        now = datetime.datetime.now(tz=datetime.UTC).timestamp()
        startup_error = RSPStartupError.from_os_error(exc)
        fn = f"ABNORMAL_STARTUP_{now}"
        errfile = self._home / fn
        try:
            errfile.write_text(startup_error.to_json())
        except OSError:
            # This likely indicates the user is out of space.
            self._logger.exception(
                f"Failed to write abnormal startup text for {exc}."
            )
