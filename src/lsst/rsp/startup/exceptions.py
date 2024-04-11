"""Exceptions for the LabRunner startup service."""

from __future__ import annotations

import subprocess
from collections.abc import Iterable
from shlex import join

__all__ = [
    "CommandFailedError",
    "CommandTimedOutError",
]


class CommandFailedError(Exception):
    """Execution of a command failed.

    Parameters
    ----------
    args
        Command (args[0]) and arguments to that command.
    exc
        Exception reporting the failure.

    Attributes
    ----------
    stdout
        Standard output from the failed command.
    stderr
        Standard error from the failed command.
    """

    def __init__(
        self,
        args: Iterable[str],
        exc: subprocess.CalledProcessError,
    ) -> None:
        args_str = join(args)
        msg = f"'{args_str}' failed with status {exc.returncode}"
        super().__init__(msg)
        self.stdout = exc.stdout
        self.stderr = exc.stderr


class CommandTimedOutError(Exception):
    """Execution of a command failed.

    Parameters
    ----------
    args
        Command (args[0]) and arguments to that command.
    exc
        Exception reporting the failure.

    Attributes
    ----------
    stdout
        Standard output from the failed command.
    stderr
        Standard error from the failed command.
    """

    def __init__(
        self,
        args: Iterable[str],
        exc: subprocess.TimeoutExpired,
    ) -> None:
        args_str = join(args)
        msg = f"'{args_str}' timed out after {exc.timeout}s"
        super().__init__(msg)
        self.stdout = exc.stdout
        self.stderr = exc.stderr
