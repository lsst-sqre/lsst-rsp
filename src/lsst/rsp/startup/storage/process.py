"""Subprocess wrapper for simplified command dispatch."""

import subprocess
from dataclasses import dataclass
from shlex import join
from typing import Self

import structlog

from ..constants import app_name
from .logging import configure_logging

__all__ = ["ProcessResult", "run"]


@dataclass
class ProcessResult:
    """Convenience class for capturing the salient features of a completed
    subprocess.
    """

    rc: int
    stdout: str
    stderr: str

    @classmethod
    def from_proc(cls, proc: subprocess.CompletedProcess) -> Self:
        return cls(
            rc=proc.returncode,
            stdout=proc.stdout.decode(),
            stderr=proc.stderr.decode(),
        )


def run(
    *args: str,
    logger: structlog.BoundLogger | None = None,
    timeout: int | None = None,
) -> ProcessResult | None:
    """Run subprocesses with a simpler interface than raw subprocess.run()."""
    if logger is None:
        configure_logging()
        logger = structlog.get_logger(app_name)
    argstr = join(args)
    logger.info(f"Running command '{argstr}'")
    try:
        proc = ProcessResult.from_proc(
            subprocess.run(
                args, capture_output=True, timeout=timeout, check=False
            )
        )
    except subprocess.TimeoutExpired as exc:
        logger.exception(
            f"Command '{argstr}' timed out after {timeout} seconds",
            exc_info=exc,
        )
        return None
    if proc.rc != 0:
        logger.warning(f"Command '{argstr}' failed", proc=proc)
    else:
        logger.debug(f"Command '{argstr}' succeeded", proc=proc)
    return proc
