"""Constants for RSP startup."""

from pathlib import Path

__all__ = [
    "app_name",
    "logging_checksums",
    "max_number_outputs",
    "noninteractive_config",
    "profile_path",
    "top_dir",
]

app_name = "nublado"
logging_checksums = [
    "2997fe99eb12846a1b724f0b82b9e5e6acbd1d4c29ceb9c9ae8f1ef5503892ec"
]
max_number_outputs = 10000
profile_path = Path("/etc/profile.d/local05-path.sh")
top_dir = Path("/opt/lsst/software")
noninteractive_config = Path(
    top_dir / "jupyterlab" / "noninteractive" / "command" / "command.json"
)
