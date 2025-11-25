"""Tests for startup object."""

import errno
import os
from pathlib import Path

import pytest

from lsst.rsp.startup.services import LabRunner


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
@pytest.mark.asyncio
async def test_set_tmpdir(monkeypatch: pytest.MonkeyPatch) -> None:
    # Happy path.
    lr = LabRunner()
    await lr._set_tmpdir_if_scratch_available()
    assert lr._env["TMPDIR"].endswith("/scratch/hambone/tmp")
    # Exists, but it's not a directory
    scratch_path = Path(lr._env["TMPDIR"])
    scratch_path.rmdir()
    scratch_path.touch()
    lr = LabRunner()
    await lr._set_tmpdir_if_scratch_available()
    assert "TMPDIR" not in lr._env
    # Put it back the way it was
    scratch_path.unlink()
    # Pre-set TMPDIR.
    monkeypatch.setenv("TMPDIR", "/preset")
    lr = LabRunner()
    assert lr._env["TMPDIR"] == "/preset"
    monkeypatch.delenv("TMPDIR")
    # Can't write to scratch dir
    monkeypatch.setenv("SCRATCH_PATH", "/nonexistent/scratch")
    lr = LabRunner()
    await lr._set_tmpdir_if_scratch_available()
    assert "TMPDIR" not in lr._env
    monkeypatch.delenv("SCRATCH_PATH")
    scratch_path.parent.rmdir()


@pytest.mark.usefixtures("_rsp_env")
@pytest.mark.asyncio
async def test_set_butler_cache(monkeypatch: pytest.MonkeyPatch) -> None:
    env_v = "DAF_BUTLER_CACHE_DIRECTORY"
    # Happy path.
    lr = LabRunner()
    await lr._set_butler_cache()
    assert lr._env[env_v].endswith("/scratch/hambone/butler_cache")
    dbc = Path(lr._env[env_v])
    dbc.rmdir()
    dbc.touch()
    lr = LabRunner()
    await lr._set_butler_cache()
    assert lr._env[env_v] == "/tmp/butler_cache"
    # Put it back the way it was
    dbc.unlink()
    # Pre-set DAF_BUTLER_CACHE_DIR.
    monkeypatch.setenv(env_v, "/preset")
    lr = LabRunner()
    await lr._set_butler_cache()
    assert lr._env[env_v] == "/preset"
    monkeypatch.delenv(env_v)
    dbc.parent.rmdir()


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


# No test for set_firefly_variables because the Discovery mock doesn't support
# mocking anything but data endpoints yet.


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


@pytest.mark.usefixtures("_rsp_env")
@pytest.mark.asyncio
async def test_busted_homedir(monkeypatch: pytest.MonkeyPatch) -> None:
    def out_of_space(lrobj: LabRunner, cachefile: Path) -> None:
        raise OSError(errno.EDQUOT, None, str(cachefile))

    monkeypatch.setattr(LabRunner, "_write_a_megabyte", out_of_space)
    lr = LabRunner()

    await lr._test_for_space()

    assert lr._broken
    assert lr._env["ABNORMAL_STARTUP"] == "TRUE"
    assert lr._env["ABNORMAL_STARTUP_ERRNO"] == str(errno.EDQUOT)

    await lr._clear_abnormal_startup()
    assert lr._broken is not True
