"""Tests for startup object."""

import configparser
import json
import os
import shutil
from pathlib import Path

import pytest
import yaml

import lsst.rsp
from lsst.rsp.startup.services import InitContainer
from lsst.rsp.utils import get_jupyterlab_config_dir, get_runtime_mounts_dir


@pytest.mark.usefixtures("_rsp_env")
@pytest.mark.asyncio
async def test_create_credential_dir(monkeypatch: pytest.MonkeyPatch) -> None:
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
    ic = InitContainer()
    ic._set_butler_credential_variables()
    assert not cred_dir.exists()
    await ic._copy_butler_credentials()
    assert cred_dir.exists()


@pytest.mark.usefixtures("_rsp_env")
@pytest.mark.asyncio
async def test_copy_butler_credentials(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    secret_dir = get_runtime_mounts_dir() / "secrets"
    monkeypatch.setenv(
        "AWS_SHARED_CREDENTIALS_FILE", str(secret_dir / "aws-credentials.ini")
    )
    monkeypatch.setenv(
        "PGPASSFILE", str(secret_dir / "postgres-credentials.txt")
    )
    ic = InitContainer()
    pg = ic._home / ".lsst" / "postgres-credentials.txt"
    lines = pg.read_text().splitlines()
    aws = ic._home / ".lsst" / "aws-credentials.ini"
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
    await ic._copy_butler_credentials()
    lines = pg.read_text().splitlines()
    aws = ic._home / ".lsst" / "aws-credentials.ini"
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
@pytest.mark.asyncio
async def test_dask_config() -> None:
    newlink = "{JUPYTERHUB_PUBLIC_URL}proxy/{port}/status"

    # First, just see if we create the default proxy settings.
    ic = InitContainer()
    dask_dir = ic._home / ".config" / "dask"
    assert not dask_dir.exists()
    await ic._setup_dask()
    assert dask_dir.exists()
    def_file = dask_dir / "dashboard.yaml"
    assert def_file.exists()
    obj = yaml.safe_load(def_file.read_text())
    assert obj["distributed"]["dashboard"]["link"] == newlink

    def_file.unlink()

    # Now test that we convert an old-style one to a user-domain config
    old_file = dask_dir / "lsst_dask.yml"
    assert not old_file.exists()

    obj["distributed"]["dashboard"]["link"] = (
        "{EXTERNAL_INSTANCE_URL}{JUPYTERHUB_SERVICE_PREFIX}proxy/{port}/status"
    )
    old_file.write_text(yaml.dump(obj, default_flow_style=False))

    assert not def_file.exists()
    assert old_file.exists()

    await ic._setup_dask()  # Should replace the text.
    obj = yaml.safe_load(old_file.read_text())
    assert obj["distributed"]["dashboard"]["link"] == newlink

    old_file.unlink()
    assert not old_file.exists()

    # Test that we remove empty dict keys
    nullobj = {"key1": {"key2": {"key3": None}}}
    assert ic._flense_dict(nullobj) is None

    fl_file = dask_dir / "flense.yaml"
    assert not fl_file.exists()

    fl_file.write_text(yaml.dump(nullobj, default_flow_style=False))
    assert fl_file.exists()

    cm_file = dask_dir / "Comment.yaml"
    assert not cm_file.exists()
    cm_file.write_text("# Nothing but commentary\n")
    assert cm_file.exists()

    assert not def_file.exists()

    # This should create the defaults, and should remove the flensed
    # config and the only-comments file.
    await ic._setup_dask()
    assert not fl_file.exists()
    assert not cm_file.exists()
    assert def_file.exists()

    # Test that we created a backup of the null file and the commentary
    fl_bk = dask_dir.glob("flense.yaml.*")
    assert len(list(fl_bk)) == 1
    cm_bk = dask_dir.glob("Comment.yaml.*")
    assert len(list(cm_bk)) == 1


@pytest.mark.usefixtures("_rsp_env")
@pytest.mark.asyncio
async def test_copy_logging_profile(monkeypatch: pytest.MonkeyPatch) -> None:
    ic = InitContainer()
    pfile = (
        ic._home / ".ipython" / "profile_default" / "startup" / "20-logging.py"
    )
    assert not pfile.exists()
    pfile.parent.mkdir(parents=True)
    await ic._copy_logging_profile()
    assert pfile.exists()
    h_contents = pfile.read_text()
    sfile = get_jupyterlab_config_dir() / "etc" / "20-logging.py"
    assert sfile.exists()
    s_contents = sfile.read_text()
    assert s_contents == h_contents
    h_contents += "\n# Locally modified\n"
    pfile.write_text(h_contents)
    await ic._copy_logging_profile()
    new_contents = pfile.read_text()
    assert new_contents == h_contents
    assert new_contents != s_contents


@pytest.mark.usefixtures("_rsp_env")
@pytest.mark.asyncio
async def test_copy_dircolors(monkeypatch: pytest.MonkeyPatch) -> None:
    ic = InitContainer()
    assert not (ic._home / ".dir_colors").exists()
    await ic._copy_dircolors()
    assert (ic._home / ".dir_colors").exists()


@pytest.mark.usefixtures("_rsp_env")
@pytest.mark.asyncio
async def test_copy_etc_skel(monkeypatch: pytest.MonkeyPatch) -> None:
    ic = InitContainer()
    assert not (ic._home / ".gitconfig").exists()
    assert not (ic._home / ".pythonrc").exists()
    etc = lsst.rsp.startup.constants.ETC_PATH
    prc = (etc / "skel" / ".pythonrc").read_text()
    prc += "\n# Local mods\n"
    (ic._home / ".pythonrc").write_text(prc)
    await ic._copy_etc_skel()
    assert (ic._home / ".gitconfig").exists()
    sgc = (etc / "skel" / ".gitconfig").read_text()
    lgc = (ic._home / ".gitconfig").read_text()
    assert sgc == lgc
    src = (etc / "skel" / ".pythonrc").read_text()
    lrc = (ic._home / ".pythonrc").read_text()
    assert src != lrc
    assert (ic._home / "notebooks" / ".user_setups").exists()


@pytest.mark.usefixtures("_rsp_env")
@pytest.mark.asyncio
async def test_relocate_user_files(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("RESET_USER_ENV", "1")
    ic = InitContainer()
    assert not (ic._home / ".local").exists()
    assert not (ic._home / "notebooks" / ".user_setups").exists()
    (ic._home / ".local").mkdir()
    (ic._home / ".local" / "foo").write_text("bar")
    (ic._home / "notebooks").mkdir()
    (ic._home / "notebooks" / ".user_setups").write_text("#!/bin/sh\n")
    await ic._relocate_user_environment_if_requested()
    assert not (ic._home / ".local").exists()
    assert not (ic._home / "notebooks" / ".user_setups").exists()
    reloc = next(iter((ic._home).glob(".user_env.*")))
    assert (reloc / "local" / "foo").read_text() == "bar"
    assert (reloc / "notebooks" / "user_setups").read_text() == "#!/bin/sh\n"


@pytest.mark.usefixtures("_rsp_env")
@pytest.mark.asyncio
async def test_setup_gitlfs(monkeypatch: pytest.MonkeyPatch) -> None:
    ic = InitContainer()
    assert await ic._check_for_git_lfs() is False
    await ic._setup_git()
    assert await ic._check_for_git_lfs() is True


@pytest.mark.usefixtures("_rsp_env")
@pytest.mark.asyncio
async def test_increase_log_limit(monkeypatch: pytest.MonkeyPatch) -> None:
    ic = InitContainer()
    settings = (
        ic._home
        / ".jupyter"
        / "lab"
        / "user-settings"
        / "@jupyterlab"
        / "notebook-extension"
        / "tracker.jupyterlab.settings"
    )
    assert not settings.exists()
    await ic._increase_log_limit()
    assert settings.exists()
    with settings.open() as f:
        obj = json.load(f)
    assert obj["maxNumberOutputs"] >= 10000


@pytest.mark.usefixtures("_rsp_env")
@pytest.mark.asyncio
async def test_manage_access_token(monkeypatch: pytest.MonkeyPatch) -> None:
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
    ic = InitContainer()
    tfile = ic._home / ".access_token"
    assert not tfile.exists()
    await ic._manage_access_token()
    assert tfile.exists()
    assert tfile.read_text() == token
    tfile.unlink()
    ctr_file.write_text(token)
    assert ctr_file.exists()
    assert not tfile.exists()
    ic = InitContainer()
    await ic._manage_access_token()
    assert tfile.exists()
    assert tfile.read_text() == token
    # Remove the rewritten saved file and replace with saved token.
    ctr_file.unlink()
    assert not ctr_file.exists()
    ctr_file.write_text(save_token)
    assert ctr_file.exists()
