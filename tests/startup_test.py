"""Tests for startup object."""

import configparser
import json
import os
import shutil
from collections.abc import Iterable
from pathlib import Path
from unittest.mock import patch

import pytest
import symbolicmode

import lsst.rsp
from lsst.rsp.startup.services.labrunner import LabRunner
from lsst.rsp.utils import get_jupyterlab_config_dir, get_runtime_mounts_dir


@pytest.mark.usefixtures("_rsp_env")
def test_object() -> None:
    lr = LabRunner()
    assert lr._debug is False


@pytest.mark.usefixtures("_rsp_env")
def test_debug_object(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DEBUG", "1")
    lr = LabRunner()
    assert lr._debug is True


#
# Environment methods
#


@pytest.mark.usefixtures("_rsp_env")
def test_set_tmpdir(monkeypatch: pytest.MonkeyPatch) -> None:
    # Happy path.
    lr = LabRunner()
    lr._set_tmpdir_if_scratch_available()
    assert lr._env["TMPDIR"].endswith("/scratch/hambone/tmp")
    # Exists, but it's not a directory
    scratch_path = Path(lr._env["TMPDIR"])
    scratch_path.rmdir()
    scratch_path.touch()
    lr = LabRunner()
    lr._set_tmpdir_if_scratch_available()
    assert "TMPDIR" not in lr._env
    # Put it back the way it was
    scratch_path.unlink()
    scratch_path.mkdir()
    # Pre-set TMPDIR.
    monkeypatch.setenv("TMPDIR", "/preset")
    lr = LabRunner()
    lr._set_tmpdir_if_scratch_available()
    assert lr._env["TMPDIR"] == "/preset"
    monkeypatch.delenv("TMPDIR")
    # Can't write SCRATCH_DIR
    with patch(
        "lsst.rsp.startup.services.labrunner.SCRATCH_PATH",
        (Path("/nonexistent") / "scratch"),
    ):
        with patch(
            "lsst.rsp.startup.constants.SCRATCH_PATH",
            (Path("nonexistent") / "scratch"),
        ):
            lr = LabRunner()
            lr._set_tmpdir_if_scratch_available()
            assert "TMPDIR" not in lr._env


@pytest.mark.usefixtures("_rsp_env")
def test_set_butler_cache(monkeypatch: pytest.MonkeyPatch) -> None:
    # Happy path.
    lr = LabRunner()
    lr._set_tmpdir_if_scratch_available()
    lr._set_butler_cache()
    assert lr._env["DAF_BUTLER_CACHE_DIRECTORY"].endswith(
        "/scratch/hambone/tmp/butler_cache"
    )
    # Exists, but it's not a directory
    dbc = Path(lr._env["DAF_BUTLER_CACHE_DIRECTORY"])
    dbc.rmdir()
    dbc.touch()
    lr = LabRunner()
    lr._set_tmpdir_if_scratch_available()
    lr._set_butler_cache()
    assert "DAF_BUTLER_CACHE_DIRECTORY" not in lr._env
    # Put it back the way it was
    dbc.unlink()
    # Pre-set DAF_BUTLER_CACHE_DIR.
    monkeypatch.setenv("DAF_BUTLER_CACHE_DIRECTORY", "/preset")
    lr = LabRunner()
    lr._set_butler_cache()
    assert lr._env["DAF_BUTLER_CACHE_DIRECTORY"] == "/preset"
    monkeypatch.delenv("DAF_BUTLER_CACHE_DIRECTORY")
    # Pre-set TMPDIR so cache is not writeable
    monkeypatch.setenv("TMPDIR", "/nonexistent")
    lr = LabRunner()
    lr._set_butler_cache()
    assert "DAF_BUTLER_CACHE_DIRECTORY" not in lr._env
    monkeypatch.delenv("TMPDIR")
    # No TMPDIR set: should go under `/tmp`
    lr = LabRunner()
    lr._set_butler_cache()
    e_dbcd = lr._env["DAF_BUTLER_CACHE_DIRECTORY"]
    # Yes, we know that ruff doesn't like `/tmp`
    # In any sane RSP environment, either we will have set TMPDIR, or
    # /tmp will be on ephemeral storage.
    assert e_dbcd == "/tmp/butler_cache"  # noqa: S108
    Path(e_dbcd).rmdir()


@pytest.mark.usefixtures("_rsp_env")
def test_cpu_vars(monkeypatch: pytest.MonkeyPatch) -> None:
    lr = LabRunner()
    lr._set_cpu_variables()
    assert lr._env["CPU_LIMIT"] == "1"
    # We need a new LabRunner each time, because it reads its environment
    # only at __init()__
    monkeypatch.setenv("CPU_LIMIT", "NaN")
    lr = LabRunner()
    lr._set_cpu_variables()
    assert lr._env["CPU_COUNT"] == "1"
    monkeypatch.setenv("CPU_LIMIT", "0.1")
    lr = LabRunner()
    lr._set_cpu_variables()
    assert lr._env["GOTO_NUM_THREADS"] == "1"
    monkeypatch.setenv("CPU_LIMIT", "3.1")
    lr = LabRunner()
    lr._set_cpu_variables()
    assert lr._env["MKL_DOMAIN_NUM_THREADS"] == "3"
    monkeypatch.setenv("CPU_LIMIT", "14")
    lr = LabRunner()
    lr._set_cpu_variables()
    assert lr._env["MPI_NUM_THREADS"] == "14"


# No test for set_image_digest() because we test that in utils_test


@pytest.mark.usefixtures("_rsp_env")
def test_expand_panda_tilde(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("PANDA_CONFIG_ROOT", "~")
    lr = LabRunner()
    lr._expand_panda_tilde()
    assert lr._env["PANDA_CONFIG_ROOT"] == os.environ["HOME"]
    monkeypatch.setenv("PANDA_CONFIG_ROOT", "~hambone")
    lr = LabRunner()
    lr._expand_panda_tilde()
    assert lr._env["PANDA_CONFIG_ROOT"] == os.environ["HOME"]
    monkeypatch.setenv("PANDA_CONFIG_ROOT", "~hambone/")
    lr = LabRunner()
    lr._expand_panda_tilde()
    assert lr._env["PANDA_CONFIG_ROOT"] == os.environ["HOME"]
    monkeypatch.setenv("PANDA_CONFIG_ROOT", "~whoopsi")
    lr = LabRunner()
    lr._expand_panda_tilde()
    assert lr._env["PANDA_CONFIG_ROOT"] == "~whoopsi"
    monkeypatch.setenv("PANDA_CONFIG_ROOT", "/etc/panda")
    lr = LabRunner()
    lr._expand_panda_tilde()
    assert lr._env["PANDA_CONFIG_ROOT"] == "/etc/panda"
    monkeypatch.setenv("PANDA_CONFIG_ROOT", "~/bar")
    lr = LabRunner()
    lr._expand_panda_tilde()
    assert lr._env["PANDA_CONFIG_ROOT"] == str(
        Path(os.environ["HOME"]) / "bar"
    )


@pytest.mark.usefixtures("_rsp_env")
def test_set_timeout_vars(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("NO_ACTIVITY_TIMEOUT", "300")
    lr = LabRunner()
    lr._set_timeout_variables()
    assert lr._env["NO_ACTIVITY_TIMEOUT"] == "300"
    assert "CULL_KERNEL_IDLE_TIMEOUT" not in lr._env


@pytest.mark.usefixtures("_rsp_env")
def test_set_launch_params(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("JUPYTERHUB_BASE_URL", "/nb/")
    monkeypatch.setenv("EXTERNAL_INSTANCE_URL", "https://lab.example.com:8443")
    lr = LabRunner()
    lr._set_launch_params()
    assert lr._stash["jupyterhub_path"] == "/nb/hub"
    assert lr._stash["external_host"] == "lab.example.com"


@pytest.mark.usefixtures("_rsp_env")
def test_set_firefly_variables(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("EXTERNAL_INSTANCE_URL", "https://lab.example.com:8443")
    lr = LabRunner()
    lr._set_firefly_variables()
    assert lr._env["FIREFLY_URL"] == "https://lab.example.com:8443/firefly"


@pytest.mark.usefixtures("_rsp_env")
def test_force_jupyter_prefer_env_path_false() -> None:
    lr = LabRunner()
    lr._force_jupyter_prefer_env_path_false()
    assert lr._env["JUPYTER_PREFER_ENV_PATH"] == "no"


@pytest.mark.usefixtures("_rsp_env")
def test_set_butler_credential_vars(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AWS_SHARED_CREDENTIALS_FILE", "/etc/secret/aws.creds")
    monkeypatch.setenv("PGPASSFILE", "/etc/secret/pgpass")
    lr = LabRunner()
    lr._set_butler_credential_variables()
    assert lr._env["AWS_SHARED_CREDENTIALS_FILE"] == str(
        lr._home / ".lsst" / "aws.creds"
    )
    assert (
        lr._env["ORIG_AWS_SHARED_CREDENTIALS_FILE"] == "/etc/secret/aws.creds"
    )
    assert lr._env["PGPASSFILE"] == str(lr._home / ".lsst" / "pgpass")
    assert lr._env["ORIG_PGPASSFILE"] == "/etc/secret/pgpass"


#
# File manipulation tests
#


@pytest.mark.usefixtures("_rsp_env")
def test_create_credential_dir(monkeypatch: pytest.MonkeyPatch) -> None:
    secret_dir = get_runtime_mounts_dir() / "secrets"
    monkeypatch.setenv(
        "AWS_SHARED_CREDENTIALS_FILE", str(secret_dir / "aws-credentials.ini")
    )
    monkeypatch.setenv(
        "PGPASSFILE", str(secret_dir / "postgres-credentials.txt")
    )
    cred_dir = Path(os.environ["HOME"]) / ".lsst"
    assert cred_dir.exists()
    shutil.rmtree(cred_dir)
    assert not cred_dir.exists()
    lr = LabRunner()
    lr._set_butler_credential_variables()
    assert not cred_dir.exists()
    lr._copy_butler_credentials()
    assert cred_dir.exists()


@pytest.mark.usefixtures("_rsp_env")
def test_copy_butler_credentials(monkeypatch: pytest.MonkeyPatch) -> None:
    secret_dir = get_runtime_mounts_dir() / "secrets"
    monkeypatch.setenv(
        "AWS_SHARED_CREDENTIALS_FILE", str(secret_dir / "aws-credentials.ini")
    )
    monkeypatch.setenv(
        "PGPASSFILE", str(secret_dir / "postgres-credentials.txt")
    )
    lr = LabRunner()
    pg = lr._home / ".lsst" / "postgres-credentials.txt"
    lines = pg.read_text().splitlines()
    aws = lr._home / ".lsst" / "aws-credentials.ini"
    for line in lines:
        if line.startswith("127.0.0.1:5432:db01:postgres:"):
            assert line.rsplit(":", maxsplit=1)[1] == "gets_overwritten"
        if line.startswith("127.0.0.1:5532:db02:postgres:"):
            assert line.rsplit(":", maxsplit=1)[1] == "should_stay"
    cp = configparser.ConfigParser()
    cp.read(str(aws))
    assert set(cp.sections()) == {"default", "tertiary"}
    assert cp["default"]["aws_secret_access_key"] == "gets_overwritten"
    assert cp["tertiary"]["aws_secret_access_key"] == "key03"
    lr._set_butler_credential_variables()
    lr._copy_butler_credentials()
    lines = pg.read_text().splitlines()
    aws = lr._home / ".lsst" / "aws-credentials.ini"
    for line in lines:
        if line.startswith("127.0.0.1:5432:db01:postgres:"):
            assert line.rsplit(":", maxsplit=1)[1] == "s33kr1t"
        if line.startswith("127.0.0.1:5532:db02:postgres:"):
            assert line.rsplit(":", maxsplit=1)[1] == "should_stay"
    cp = configparser.ConfigParser()
    cp.read(str(aws))
    assert set(cp.sections()) == {"default", "secondary", "tertiary"}
    assert cp["default"]["aws_secret_access_key"] == "key01"
    assert cp["secondary"]["aws_secret_access_key"] == "key02"
    assert cp["tertiary"]["aws_secret_access_key"] == "key03"


@pytest.mark.usefixtures("_rsp_env")
def test_copy_logging_profile(monkeypatch: pytest.MonkeyPatch) -> None:
    lr = LabRunner()
    pfile = (
        lr._home / ".ipython" / "profile_default" / "startup" / "20-logging.py"
    )
    assert not pfile.exists()
    pfile.parent.mkdir(parents=True)
    lr._copy_logging_profile()
    assert pfile.exists()
    h_contents = pfile.read_text()
    sfile = get_jupyterlab_config_dir() / "etc" / "20-logging.py"
    assert sfile.exists()
    s_contents = sfile.read_text()
    assert s_contents == h_contents
    h_contents += "\n# Locally modified\n"
    pfile.write_text(h_contents)
    lr._copy_logging_profile()
    new_contents = pfile.read_text()
    assert new_contents == h_contents
    assert new_contents != s_contents


@pytest.mark.usefixtures("_rsp_env")
def test_copy_dircolors(monkeypatch: pytest.MonkeyPatch) -> None:
    lr = LabRunner()
    assert not (lr._home / ".dir_colors").exists()
    lr._copy_dircolors()
    assert (lr._home / ".dir_colors").exists()


@pytest.mark.usefixtures("_rsp_env")
def test_copy_etc_skel(monkeypatch: pytest.MonkeyPatch) -> None:
    lr = LabRunner()
    assert not (lr._home / ".gitconfig").exists()
    assert not (lr._home / ".pythonrc").exists()
    etc = lsst.rsp.startup.constants.ETC_PATH
    prc = (etc / "skel" / ".pythonrc").read_text()
    prc += "\n# Local mods\n"
    (lr._home / ".pythonrc").write_text(prc)
    lr._copy_etc_skel()
    assert (lr._home / ".gitconfig").exists()
    sgc = (etc / "skel" / ".gitconfig").read_text()
    lgc = (lr._home / ".gitconfig").read_text()
    assert sgc == lgc
    src = (etc / "skel" / ".pythonrc").read_text()
    lrc = (lr._home / ".pythonrc").read_text()
    assert src != lrc
    assert (lr._home / "notebooks" / ".user_setups").exists()


@pytest.mark.usefixtures("_rsp_env")
def test_relocate_user_files(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("RESET_USER_ENV", "1")
    lr = LabRunner()
    assert not (lr._home / ".local").exists()
    assert not (lr._home / "notebooks" / ".user_setups").exists()
    (lr._home / ".local").mkdir()
    (lr._home / ".local" / "foo").write_text("bar")
    (lr._home / "notebooks").mkdir()
    (lr._home / "notebooks" / ".user_setups").write_text("#!/bin/sh\n")
    lr._relocate_user_environment_if_requested()
    assert not (lr._home / ".local").exists()
    assert not (lr._home / "notebooks" / ".user_setups").exists()
    reloc = next(iter((lr._home).glob(".user_env.*")))
    assert (reloc / "local" / "foo").read_text() == "bar"
    assert (reloc / "notebooks" / "user_setups").read_text() == "#!/bin/sh\n"


#
# Git
#


@pytest.mark.usefixtures("_rsp_env")
def test_refresh_notebooks(
    monkeypatch: pytest.MonkeyPatch, git_repo: Path
) -> None:
    source_repo = git_repo
    monkeypatch.setenv("AUTO_REPO_SPECS", f"file://{source_repo!s}@main")
    lr = LabRunner()
    repo = lr._home / "notebooks" / source_repo.name
    assert not repo.exists()
    lr._refresh_notebooks()
    paths = (repo, repo / "README.md")
    assert _is_readonly(paths)
    lr._refresh_notebooks()
    assert _is_readonly(paths)
    for p in paths:
        symbolicmode.chmod(p, "u+w")
    assert not _is_readonly(paths)
    lr._refresh_notebooks()
    assert _is_readonly(paths)


def _is_readonly(paths: Iterable[Path]) -> bool:
    for p in paths:
        assert p.exists()
        mode = p.stat().st_mode
        mask = 0o222
        if mode & mask != 0:
            return False
    return True


@pytest.mark.usefixtures("_rsp_env")
def test_setup_gitlfs(monkeypatch: pytest.MonkeyPatch) -> None:
    lr = LabRunner()
    assert lr._check_for_git_lfs() is False
    lr._setup_gitlfs()
    assert lr._check_for_git_lfs() is True


#
# Interactive-mode-only tests
#


@pytest.mark.usefixtures("_rsp_env")
def test_increase_log_limit(monkeypatch: pytest.MonkeyPatch) -> None:
    lr = LabRunner()
    settings = (
        lr._home
        / ".jupyter"
        / "lab"
        / "user-settings"
        / "@jupyterlab"
        / "notebook-extension"
        / "tracker.jupyterlab.settings"
    )
    assert not settings.exists()
    lr._increase_log_limit()
    assert settings.exists()
    with settings.open() as f:
        obj = json.load(f)
    assert obj["maxNumberOutputs"] >= 10000


@pytest.mark.usefixtures("_rsp_env")
def test_manage_access_token(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DEBUG", "1")
    token = "token-of-esteem"
    monkeypatch.setenv("ACCESS_TOKEN", token)
    ctr_file = get_runtime_mounts_dir() / "secrets" / "token"
    # Save the token
    assert ctr_file.exists()
    save_token = ctr_file.read_text()
    # Remove the token file
    ctr_file.unlink()
    assert not ctr_file.exists()
    lr = LabRunner()
    tfile = lr._home / ".access_token"
    assert not tfile.exists()
    lr._manage_access_token()
    assert tfile.exists()
    assert tfile.read_text() == token
    tfile.unlink()
    ctr_file.write_text(token)
    assert ctr_file.exists()
    assert not tfile.exists()
    lr = LabRunner()
    lr._manage_access_token()
    assert tfile.exists()
    assert tfile.read_text() == token
    # Remove the rewritten saved file and replace with saved token.
    ctr_file.unlink()
    assert not ctr_file.exists()
    ctr_file.write_text(save_token)
    assert ctr_file.exists()
