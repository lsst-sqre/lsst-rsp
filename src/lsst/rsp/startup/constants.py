"""Constants for RSP startup."""

from pathlib import Path

__all__ = [
    "app_name",
    "etc",
    "logging_checksums",
    "max_number_outputs",
    "noninteractive_config",
    "top_dir",
]

app_name = "nublado"
etc = Path("/etc")
logging_checksums = [
    "2997fe99eb12846a1b724f0b82b9e5e6acbd1d4c29ceb9c9ae8f1ef5503892ec"
]
max_number_outputs = 10000
top_dir = Path("/opt/lsst/software")
noninteractive_config = Path(
    top_dir / "jupyterlab" / "noninteractive" / "command" / "command.json"
)
