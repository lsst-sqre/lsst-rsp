"""Tests for startup object."""

import pytest

from lsst.rsp.startup.services.labrunner import LabRunner
from lsst.rsp.startup.util import str_bool


def test_object() -> None:
    lr = LabRunner()
    assert lr.debug is False


def test_debug_object(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DEBUG", "1")
    lr = LabRunner()
    assert lr.debug is True


def test_str_bool() -> None:
    assert str_bool("1") is True
    assert str_bool("0") is False
    assert str_bool("420.69") is True
    assert str_bool("y") is True
    assert str_bool("Yo Mama") is True
    assert str_bool("nevermore") is False
    assert str_bool("Flibbertigibbet") is False
