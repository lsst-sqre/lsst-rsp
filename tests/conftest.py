"""Pytest configuration and fixtures."""

from collections.abc import Iterator
from pathlib import Path
from shutil import copytree
from tempfile import TemporaryDirectory
from unittest.mock import patch

import pytest


@pytest.fixture
def rsp_env(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    # For each of these, we want to cover both the "from ..constants import"
    # and the "import lsst.rsp.constants" case.
    with patch(
        "lsst.rsp.startup.services.labrunner.top_dir",
        (Path(__file__).parent / "support" / "files" / "stack_top"),
    ):
        with patch(
            "lsst.rsp.startup.constants.top_dir",
            (Path(__file__).parent / "support" / "files" / "stack_top"),
        ):
            with patch(
                "lsst.rsp.startup.services.labrunner.etc",
                (Path(__file__).parent / "support" / "files" / "etc"),
            ):
                with patch(
                    "lsst.rsp.startup.constants.etc",
                    (Path(__file__).parent / "support" / "files" / "etc"),
                ):
                    template = (
                        Path(__file__).parent / "support" / "files" / "homedir"
                    )
                    # Set up a user with the files we're going to want to
                    # manipulate in the test suite.
                    with TemporaryDirectory() as homedir:
                        monkeypatch.setenv("HOME", homedir)
                        monkeypatch.setenv("USER", "hambone")
                        copytree(
                            template,
                            homedir,
                            dirs_exist_ok=True,
                            symlinks=True,
                        )
                        yield
