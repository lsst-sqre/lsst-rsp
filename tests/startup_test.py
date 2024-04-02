"""Tests for startup object."""

import os
from pathlib import Path

import pytest

from lsst.rsp.startup.services.labrunner import LabRunner
from lsst.rsp.startup.util import str_bool


def test_object() -> None:
    lr = LabRunner()
    assert lr._debug is False


def test_debug_object(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DEBUG", "1")
    lr = LabRunner()
    assert lr._debug is True


#
# Environment methods
#


def test_remove_sudo_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SUDO_USER", "hambone")
    lr = LabRunner()
    lr._remove_sudo_env()
    assert "SUDO_USER" not in lr._env


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


def test_expand_panda_tilde(
    monkeypatch: pytest.MonkeyPatch, rsp_env: None
) -> None:
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


def test_set_timeout_vars(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("NO_ACTIVITY_TIMEOUT", "300")
    lr = LabRunner()
    lr._set_timeout_variables()
    assert lr._env["NO_ACTIVITY_TIMEOUT"] == "300"
    assert lr._env["CULL_KERNEL_IDLE_TIMEOUT"] == "43200"


def test_set_launch_params(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("JUPYTERHUB_BASE_URL", "/nb/")
    monkeypatch.setenv("EXTERNAL_INSTANCE_URL", "https://lab.example.com:8443")
    lr = LabRunner()
    lr._set_launch_params()
    assert lr._env["JUPYTERHUB_PATH"] == "/nb/hub"
    assert lr._env["EXTERNAL_HOST"] == "lab.example.com"


def test_set_firefly_variables(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("EXTERNAL_INSTANCE_URL", "https://lab.example.com:8443")
    lr = LabRunner()
    lr._set_firefly_variables()
    assert lr._env["FIREFLY_URL"] == "https://lab.example.com:8443/firefly/"
    assert lr._env["FIREFLY_HTML"] == "slate.html"


def test_unset_jupyter_prefer_env_path() -> None:
    lr = LabRunner()
    lr._unset_jupyter_prefer_env_path()
    assert lr._env["JUPYTER_PREFER_ENV_PATH"] == "no"


def test_set_butler_credential_vars(
    monkeypatch: pytest.MonkeyPatch, rsp_env: None
) -> None:
    monkeypatch.setenv("AWS_SHARED_CREDENTIALS_FILE", "/etc/secret/aws.creds")
    monkeypatch.setenv("PGPASSFILE", "/etc/secret/pgpass")
    lr = LabRunner()
    lr._set_butler_credential_variables()
    assert lr._env["USER_CREDENTIALS_DIR"] == str(lr._home / ".lsst")
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


def test_copy_butler_credentials(
    monkeypatch: pytest.MonkeyPatch, rsp_env: None
) -> None:
    monkeypatch.setenv("AWS_SHARED_CREDENTIALS_FILE", "/etc/secret/aws.creds")
    monkeypatch.setenv("PGPASSFILE", "/etc/secret/pgpass")
    lr = LabRunner()
    lr._set_butler_credential_variables()
    lr._copy_butler_credentials()


#
# Utility function
#


def test_str_bool() -> None:
    assert str_bool("1") is True
    assert str_bool("0") is False
    assert str_bool("420.69") is True
    assert str_bool("y") is True
    assert str_bool("Yo Mama") is True
    assert str_bool("nevermore") is False
    assert str_bool("Flibbertigibbet") is False
