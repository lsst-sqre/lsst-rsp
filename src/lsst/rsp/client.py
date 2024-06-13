"""Client for other services running in the same RSP instance."""

import httpx

from .utils import get_access_token, get_runtime_mounts_dir


class RSPClient(httpx.AsyncClient):
    """Configured client for other services in the RSP.

    It uses knowledge present in the Lab instance it's running in to
    configure token authentication and a base URL.
    """

    def __init__(
        self,
        service_endpoint: str,
    ) -> None:
        token = get_access_token()
        jupyterlab_dir = get_runtime_mounts_dir()
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
