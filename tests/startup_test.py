"""Tests for startup object."""

import json
import os
import subprocess
from pathlib import Path

import pytest


@pytest.mark.usefixtures("_rsp_env")
def test_startup() -> None:
    env = {
        "JUPYTERHUB_BASE_URL": "/nb",
        "EXTERNAL_BASE_URL": "https://rsp.example.com",
    }
    command = ["env"]

    root = (Path(os.getenv("HOME", ""))).parent.parent
    startup = root / "lab_startup"
    (startup / "env.json").write_text(json.dumps(env))
    (startup / "args.json").write_text(json.dumps(command))

    # Our command will just dump the environment to stdout...
    p1 = subprocess.run(
        ["launch-rubin-jupyterlab"], check=True, text=True, capture_output=True
    )
    # ...and we check that the environment variables we set in env are
    # present there.
    lines = p1.stdout.split("\n")
    for xl in lines:
        ln = xl.strip()
        if not ln:
            continue
        (k, v) = ln.split("=")
        if k in env:
            assert env[k] == v

    # Do it again but with "noninteractive.json" instead.
    (startup / "args.json").unlink()
    (startup / "noninteractive.json").write_text(json.dumps(command))

    p1 = subprocess.run(
        ["launch-rubin-jupyterlab"], check=True, text=True, capture_output=True
    )
    lines = p1.stdout.split("\n")
    for xl in lines:
        ln = xl.strip()
        if not ln:
            continue
        (k, v) = ln.split("=")
        if k in env:
            assert env[k] == v
