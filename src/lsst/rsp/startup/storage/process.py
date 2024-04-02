"""Subprocess wrapper for simplified command dispatch."""
import subprocess
from dataclasses import dataclass
from shlex import join
from typing import Self

@dataclass
class ProcessResult:
    """Convenience class for capturing the salient features of a completed
    subprocess."""
    rc: int
    stdout: str
    stderr: str

    @classmethod
    def from_proc(cls, proc: subprocess.CompletedProcess) -> Self:
        return cls(
            rc = proc.returncode,
            stdout = proc.stdout.decode(),
            stderr = proc.stderr.decode()
        )

def run(
    *args: str,
    logger: logging.Logger,
    timeout: Optional[int] = None,
) -> ProcessResult|None:
    """Convenience method for running subprocesses."""
    argstr = join(*args)
    logger.info(f"Running command '{argstr}'")
    try:
        proc = ProcessResult.from_proc(
            subprocess.run(args, capture_output=True, timeout=timeout)
        )
    except subprocess.TimeoutExpired:
        logger.error(
            f"Command '{argstr}' timed out after {timeout} seconds"
        )
        return None
    if proc.returncode != 0:
        logger.warning(
            f"Command '{argstr}' failed", proc=proc
        )
    else:
        logger.debug(
            f"Command '{argstr}' succeeded", proc=proc
        )
