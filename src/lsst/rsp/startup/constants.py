"""Constants for RSP startup."""

from pathlib import Path

__all__ = ["app_name", "profile_path", "top_dir"]

app_name = "nublado"
profile_path = Path("/etc/profile.d/local05-path.sh")
top_dir = Path("/opt/lsst/software")
