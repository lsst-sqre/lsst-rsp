"""CLI launcher for the Lab."""

import contextlib
import json
import logging
import os
import sys
from pathlib import Path

__all__ = ["launch_lab"]


def launch_lab() -> None:
    """Read startup files and start the Lab (or noninteractive equivalent)."""
    debug = os.getenv("DEBUG")
    logger = logging.getLogger(__name__)
    if debug:
        logging.basicConfig(level=logging.DEBUG)
    else:
        logging.basicConfig(level=logging.INFO)
    home_str = os.getenv("HOME")
    if not home_str:
        raise RuntimeError("Environment variable HOME must be set")
    home = Path(home_str)
    if not home.exists() and home.is_dir():
        raise RuntimeError("$HOME must be a directory")
    logger.debug(f"Home: {home!s}")
    startup_path = Path(os.getenv("RSP_STARTUP_PATH") or "/lab_startup")
    logger.debug(f"Startup path: {startup_path!s}")
    env = json.loads((startup_path / "env.json").read_text())
    # Glue our current path into env if it wasn't there already
    cur_path = os.getenv("PATH")
    if cur_path and "PATH" not in env:
        env["PATH"] = cur_path
    logger.debug(f"Environment: {json.dumps(env)}")
    if (startup_path / "noninteractive.json").exists():
        command = json.loads(
            (startup_path / "noninteractive.json").read_text()
        )
    else:
        command = json.loads((startup_path / "args.json").read_text())
    if not command:
        raise RuntimeError("Command to launch lab cannot be empty")
    logger.debug(f"Command: {json.dumps(command)}")

    with contextlib.chdir(home):
        # We use execvpe() here because we have a list of commands and an
        # environment to supply to it.
        sys.stdout.flush()
        sys.stderr.flush()
        os.execvpe(command[0], command, env=env)
