"""Test the RSPClient."""

import pytest
from pytest_httpx import HTTPXMock

from lsst.rsp import get_query_history


@pytest.mark.usefixtures("_rsp_env")
@pytest.mark.asyncio
async def test_get_query_history(httpx_mock: HTTPXMock) -> None:
    """Ensure that get_query_history() works, which in turn will ensure
    that the RSPClient has the right headers and assembles its URL correctly.
    """
    httpx_mock.add_response(
        url="https://rsp.example.com/api/tap/async",
        match_headers={
            "Authorization": "Bearer gf-dummytoken",
            "Content-Type": "application/json",
        },
        text=(
            """<?xml version="1.0" encoding="UTF-8"?>
<uws:jobs xmlns:uws="http://www.ivoa.net/xml/UWS/v1.0"
            xmlns:xlink="http://www.w3.org/1999/xlink" version="1.1">
  <uws:jobref id="phdl67i3tmklfdbz">
    <uws:phase>COMPLETED</uws:phase>
    <uws:runId>dp02_dc2_catalogs.Object - data-dev</uws:runId>
    <uws:ownerId>adam</uws:ownerId>
    <uws:creationTime>2025-01-15T23:36:17.931Z</uws:creationTime>
  </uws:jobref>
  <uws:jobref id="r4qyb04xesh7mbz3">
    <uws:phase>COMPLETED</uws:phase>
    <uws:ownerId>adam</uws:ownerId>
    <uws:creationTime>2024-12-05T17:49:27.518Z</uws:creationTime>
  </uws:jobref>
  <uws:jobref id="yk16agxjefl6gly6">
    <uws:phase>COMPLETED</uws:phase>
    <uws:runId>ivoa.ObsCore - data-dev</uws:runId>
    <uws:ownerId>adam</uws:ownerId>
    <uws:creationTime>2025-01-15T23:37:03.089Z</uws:creationTime>
  </uws:jobref>
</uws:jobs>"""
        ),
    )
    jobs = await get_query_history()
    assert jobs == ["phdl67i3tmklfdbz", "r4qyb04xesh7mbz3", "yk16agxjefl6gly6"]
    # The httpx mock will throw an error at teardown if we did not exercise
    # the mock, so we know the request matched both the URL and the headers.
