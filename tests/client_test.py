"""Test the RSPClient."""

from pathlib import Path

import pytest
from pytest_httpx import HTTPXMock

from lsst.rsp import RSPClient


@pytest.mark.usefixtures("_rsp_env")
@pytest.mark.asyncio
async def test_client(httpx_mock: HTTPXMock) -> None:
    """Ensure that the RSPClient has the right headers and assembles its
    URL correctly.
    """
    httpx_mock.add_response(
        url="https://rsp.example.com/test-service/foo",
        match_headers={
            "Authorization": "Bearer gf-dummytoken",
            "Content-Type": "application/json",
        },
    )
    jupyterlab_dir = (
        Path(__file__).parent / "support" / "files" / "client" / "jupyterlab"
    )
    client = RSPClient("/test-service", jupyterlab_dir=jupyterlab_dir)
    await client.get("/foo")
    # The httpx mock will throw an error at teardown if we did not exercise
    # the mock, so we know the request matched both the URL and the headers.
