"""Client for other services running in the same RSP instance."""

from pathlib import Path

import httpx


class RSPClient(httpx.AsyncClient):
    """Configured client for other services in the RSP.

    It uses knowledge present in the Lab instance it's running in to
    configure token authentication and a base URL.
    """

    def __init__(
        self,
        service_endpoint: str,
        *,
        jupyterlab_dir: Path = Path("/opt/lsst/software/jupyterlab"),
    ) -> None:
        token = (jupyterlab_dir / "secrets" / "token").read_text().strip()
        instance_url = (
            (jupyterlab_dir / "environment" / "EXTERNAL_INSTANCE_URL")
            .read_text()
            .strip()
        )
        if instance_url.endswith("/") or service_endpoint.startswith("/"):
            service_root = f"{instance_url}{service_endpoint}"
        else:
            service_root = f"{instance_url}/{service_endpoint}"
        http_headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        }
        super().__init__(
            base_url=service_root, follow_redirects=True, headers=http_headers
        )
