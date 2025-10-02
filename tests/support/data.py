"""Helper functions for reading test data."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

__all__ = [
    "data_path",
    "read_test_file",
    "read_test_json",
]


def data_path(fragment: str) -> Path:
    """Construct a path to a test data file.

    Parameters
    ----------
    fragment
        Path relative to :file:`tests/data`.

    Returns
    -------
    Path
        Full path to file.
    """
    return Path(__file__).parent.parent / "data" / fragment


def read_test_file(fragment: str) -> str:
    """Read test data as text.

    Parameters
    ----------
    fragment
        Path relative to :file:`tests/data`.

    Returns
    -------
    str
        Contents of file.
    """
    return data_path(fragment).read_text()


def read_test_json(fragment: str) -> Any:
    """Read test data as JSON and return its decoded form.

    Parameters
    ----------
    fragment
        Path relative to :file:`tests/data`.

    Returns
    -------
    typing.Any
        Parsed contents of the file.
    """
    path = data_path(fragment + ".json")
    with path.open("r") as f:
        return json.load(f)
