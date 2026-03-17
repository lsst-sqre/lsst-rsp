"""Test the RSPClient."""

from pathlib import Path

import pytest
from pytest_httpx import HTTPXMock

from lsst.rsp import get_query_history


@pytest.mark.usefixtures("_rsp_env")
@pytest.mark.asyncio
async def test_get_full_query_history(
    httpx_mock: HTTPXMock, discovery_v1_path: Path
) -> None:
    """Ensure that ``get_query_history`` works."""
    data_dir = Path(__file__).parent / "data" / "responses"
    httpx_mock.add_response(
        url="https://data.example.com/api/tap/async",
        match_headers={"Authorization": "Bearer gf-dummytoken"},
        text=(data_dir / "resp-tap.xml").read_text(),
        is_reusable=True,
    )
    httpx_mock.add_response(
        url="https://data.example.com/api/ssotap/async",
        match_headers={"Authorization": "Bearer gf-dummytoken"},
        text=(data_dir / "resp-ssotap.xml").read_text(),
    )
    jobs = await get_query_history(discovery_v1_path=discovery_v1_path)
    assert jobs == [
        "dp03:sw1qsdt9sumffw96",
        "dp1:zka3udcur0haunx2",
        "dp02:zka3udcur0haunx2",
        "dp1:l34ghit5y6cyebqt",
        "dp02:l34ghit5y6cyebqt",
        "dp1:me7z4mj6axxy62lq",
        "dp02:me7z4mj6axxy62lq",
        "dp1:y5i6ws95bcs1ssws",
        "dp02:y5i6ws95bcs1ssws",
        "dp1:n5473f1vbil8yh7j",
        "dp02:n5473f1vbil8yh7j",
        "dp1:bafxydysxdr92f1m",
        "dp02:bafxydysxdr92f1m",
        "dp03:x6vqdjyzt4mlhvom",
        "dp03:hwigwqxmbvqpp0of",
        "dp03:qfyhs7id9nqjwiph",
        "dp03:x8wek4z6pp4xjjy9",
        "dp03:qfv4ixi2douufpoa",
        "dp03:lqp1rjomrprr3vu1",
        "dp03:gcnl77j1rmqq9rlj",
        "dp03:nxlket1unl5b8tiv",
        "dp03:iik7138mhk1j79n2",
        "dp03:pb0h2w593bpfec7u",
        "dp03:v79zpy30afwl9dnl",
        "dp03:k23krbykvslj4x3m",
        "dp03:jd3xb0j338c24kdz",
        "dp03:e05w37d96z9iukwq",
        "dp03:zyivvedt1wuohbg6",
        "dp03:eoghtyo3j357bd84",
        "dp03:p8gxzirxvceyxrp0",
        "dp03:uewsloxfksbqtdjg",
        "dp03:sqjo1u77n99jrc2n",
        "dp03:bjtgr9ncgumolflp",
        "dp03:wcnyt3lr3pgyzuix",
        "dp03:u0uvivd4fkrtf9w8",
        "dp03:rg237zs7n6bpogk3",
        "dp03:bhgdu7485ga2mcsu",
        "dp03:s7nhxxibxiozmqfc",
        "dp03:jfa7f8bvvqnh91ly",
        "dp03:le96m6s4z4u8uiyh",
        "dp03:hll1g5lqcw3ce7ib",
        "dp03:px47av5ws7i8wsqv",
        "dp03:jx25n0e0oqwzrti5",
        "dp03:sie0q08xeml7k81m",
        "dp1:i335lz8kulmm00md",
        "dp02:i335lz8kulmm00md",
        "dp1:g3j96lqi2ojq7z2c",
        "dp02:g3j96lqi2ojq7z2c",
        "dp1:t8fcryvzzsvc6zsx",
        "dp02:t8fcryvzzsvc6zsx",
        "dp1:shwp5pj245z5pg0t",
        "dp02:shwp5pj245z5pg0t",
        "dp1:b14h0uj4acef4wxd",
        "dp02:b14h0uj4acef4wxd",
    ]
    # The httpx mock will throw an error at teardown if we did not exercise
    # the mock, so we know the request matched both the URL and the headers.


@pytest.mark.usefixtures("_rsp_env")
@pytest.mark.asyncio
async def test_get_partial_query_history(
    httpx_mock: HTTPXMock, discovery_v1_path: Path
) -> None:
    """Ensure that ``get_query_history`` works with a limit.

    Given our test data, note that we are pulling five total responses from
    two lists, each with five responses, and that we have at least one from
    each list.
    """
    data_dir = Path(__file__).parent / "data" / "responses"
    httpx_mock.add_response(
        url="https://data.example.com/api/tap/async?last=5",
        match_headers={"Authorization": "Bearer gf-dummytoken"},
        text=(data_dir / "resp-tap-5.xml").read_text(),
        is_reusable=True,
    )
    httpx_mock.add_response(
        url="https://data.example.com/api/ssotap/async?last=5",
        match_headers={"Authorization": "Bearer gf-dummytoken"},
        text=(data_dir / "resp-ssotap-5.xml").read_text(),
    )

    jobs = await get_query_history(
        limit=5, discovery_v1_path=discovery_v1_path
    )
    assert jobs == [
        "dp03:sw1qsdt9sumffw96",
        "dp1:zka3udcur0haunx2",
        "dp02:zka3udcur0haunx2",
        "dp1:l34ghit5y6cyebqt",
        "dp02:l34ghit5y6cyebqt",
    ]


@pytest.mark.usefixtures("_rsp_env")
@pytest.mark.asyncio
async def test_short_responses(
    httpx_mock: HTTPXMock, discovery_v1_path: Path
) -> None:
    """Ensure that ``get_query_history`` works with short data.

    Given our test data, note that we are pulling only two responses from two
    lists, even though we're asking for five.
    """
    data_dir = Path(__file__).parent / "data" / "responses"
    httpx_mock.add_response(
        url="https://data.example.com/api/tap/async?last=5",
        match_headers={"Authorization": "Bearer gf-dummytoken"},
        text=(data_dir / "resp-tap-0.xml").read_text(),
        is_reusable=True,
    )
    httpx_mock.add_response(
        url="https://data.example.com/api/ssotap/async?last=5",
        match_headers={"Authorization": "Bearer gf-dummytoken"},
        text=(data_dir / "resp-ssotap-2.xml").read_text(),
    )

    jobs = await get_query_history(
        limit=5, discovery_v1_path=discovery_v1_path
    )
    assert jobs == [
        "dp03:sw1qsdt9sumffw96",
        "dp03:x6vqdjyzt4mlhvom",
    ]


@pytest.mark.usefixtures("_rsp_env")
@pytest.mark.asyncio
async def test_error_responses(
    httpx_mock: HTTPXMock, discovery_v1_path: Path
) -> None:
    """Ensure that ``get_query_history`` works with a broken TAP server.

    We will get all five results from ``dp02`` and ``dp1``, because ``dp03``
    will give us a 500 status code.
    """
    data_dir = Path(__file__).parent / "data" / "responses"
    httpx_mock.add_response(
        url="https://data.example.com/api/tap/async?last=10",
        match_headers={"Authorization": "Bearer gf-dummytoken"},
        text=(data_dir / "resp-tap-5.xml").read_text(),
        is_reusable=True,
    )
    httpx_mock.add_response(
        url="https://data.example.com/api/ssotap/async?last=10",
        status_code=500,
    )

    jobs = await get_query_history(
        limit=10, discovery_v1_path=discovery_v1_path
    )
    assert jobs == [
        "dp1:zka3udcur0haunx2",
        "dp02:zka3udcur0haunx2",
        "dp1:l34ghit5y6cyebqt",
        "dp02:l34ghit5y6cyebqt",
        "dp1:me7z4mj6axxy62lq",
        "dp02:me7z4mj6axxy62lq",
        "dp1:y5i6ws95bcs1ssws",
        "dp02:y5i6ws95bcs1ssws",
        "dp1:n5473f1vbil8yh7j",
        "dp02:n5473f1vbil8yh7j",
    ]


@pytest.mark.usefixtures("_rsp_env")
@pytest.mark.asyncio
async def test_all_error_responses(
    httpx_mock: HTTPXMock, discovery_v1_path: Path
) -> None:
    """Ensure that ``get_query_history`` works with all TAP servers broken.

    We will get an empty list, because both servers will give us a 500 status
    code.
    """
    httpx_mock.add_response(
        url="https://data.example.com/api/tap/async?last=5",
        status_code=500,
        is_reusable=True,
    )
    httpx_mock.add_response(
        url="https://data.example.com/api/ssotap/async?last=5",
        status_code=500,
    )

    jobs = await get_query_history(
        limit=5, discovery_v1_path=discovery_v1_path
    )
    assert jobs == []
