"""Pytest configuration and fixtures."""

import contextlib
import os
from collections.abc import Iterator
from pathlib import Path
from shutil import copytree
from tempfile import TemporaryDirectory
from unittest.mock import patch

import pytest

from lsst.rsp.startup.storage.command import Command

# Things for startup/labrunner


@pytest.fixture
def _rsp_paths(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    # For each of these, we want to cover both the "from ..constants import"
    # and the "import lsst.rsp.constants" case.
    with patch(
        "lsst.rsp.startup.services.labrunner.labrunner.ETC_PATH",
        (Path(__file__).parent / "support" / "files" / "etc"),
    ):
        with patch(
            "lsst.rsp.startup.constants.ETC_PATH",
            (Path(__file__).parent / "support" / "files" / "etc"),
        ):
            yield


@pytest.fixture
def _rsp_env(
    _rsp_paths: None, monkeypatch: pytest.MonkeyPatch
) -> Iterator[None]:
    file_dir = Path(__file__).parent / "support" / "files"
    template = file_dir / "homedir"
    monkeypatch.setenv(
        "NUBLADO_RUNTIME_MOUNTS_DIR", str(file_dir / "etc" / "nublado")
    )
    monkeypatch.setenv(
        "JUPYTERLAB_CONFIG_DIR",
        str(file_dir / "jupyterlab"),
    )
    with contextlib.suppress(KeyError):
        monkeypatch.delenv("TMPDIR")
        monkeypatch.delenv("DAF_BUTLER_CACHE_DIRECTORY")
    with TemporaryDirectory() as fake_root:
        t_home = Path(fake_root) / "home"
        t_home.mkdir()
        homedir = str(t_home)
        monkeypatch.setenv("HOME", homedir)
        monkeypatch.setenv("USER", "hambone")
        monkeypatch.setenv("JUPYTERHUB_BASE_URL", "/nb/")
        copytree(
            template,
            homedir,
            dirs_exist_ok=True,
            symlinks=True,
        )
        t_scratch = Path(fake_root) / "scratch"
        t_scratch.mkdir()
        monkeypatch.setenv("SCRATCH_PATH", str(t_scratch))
        yield


@pytest.fixture
def git_repo() -> Iterator[Path]:
    with TemporaryDirectory() as repo_str:
        pwd = Path.cwd()
        repo = Path(repo_str)
        os.chdir(repo)
        cmd = Command()
        cmd.run("git", "init")
        (repo / "README.md").write_text("# Test Repo\n")
        cmd.run("git", "config", "user.email", "hambone@opera.borphee.quendor")
        cmd.run("git", "config", "user.name", "Hambone")
        cmd.run("git", "config", "init.defaultBranch", "main")
        cmd.run("git", "checkout", "-b", "main")
        cmd.run("git", "add", "README.md")
        cmd.run("git", "commit", "-am", "Initial Commit")
        os.chdir(pwd)
        yield Path(repo)


# Things for startup/landing_page.


@pytest.fixture(scope="session")
def monkeysession() -> Iterator[pytest.MonkeyPatch]:
    """MonkeyPatch, but session-scoped."""
    mpatch = pytest.MonkeyPatch()
    yield mpatch
    mpatch.undo()


@pytest.fixture(scope="session")
def _init_container_fake_root(
    monkeysession: pytest.MonkeyPatch,
) -> Iterator[None]:
    with TemporaryDirectory() as td:
        contents = {
            "hello.txt": "Hello, world!\n",
            "goodbye.txt": "Goodbye, cruel world.\n",
        }
        tutorial_directory = Path(td) / "tutorials"
        tutorial_directory.mkdir(parents=True)
        for fn, text in contents.items():
            out_file = tutorial_directory / fn
            out_file.write_text(text)
        home_directory = Path(td) / "home" / "gregorsamsa"
        home_directory.mkdir(parents=True)

        monkeysession.setenv("NUBLADO_HOME", str(home_directory))
        monkeysession.setenv(
            "CST_LANDING_PAGE_SRC_DIR", str(tutorial_directory)
        )
        monkeysession.setenv("CST_LANDING_PAGE_TGR_DIR", "notebooks/tutorials")
        monkeysession.setenv(
            "CST_LANDING_PAGE_FILES", "hello.txt", "goodbye.txt"
        )
        yield
