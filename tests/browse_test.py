"""Tests for the browse() function."""

import pytest
from IPython.display import HTML

from lsst.rsp import _browse


def test_correct() -> None:
    """Test that a URL is correctly formatted."""
    received = _browse._generate_html("https://www.google.com", "56.25%")
    assert "padding-top:56.25%" in received
    assert 'src="https://www.google.com"' in received


s_vals = (":", "x", "X", "/")


@pytest.mark.parametrize("splitter", s_vals)
def test_aspect_correct(splitter: str) -> None:
    """Test that aspect ratio is correctly converted."""
    expected = "75.0%"
    received = _browse._unpack_aspect(f"4{splitter}3")
    assert expected == received


t_vals = (0.75, [4, 3], {"height": 9, "width": 16})


@pytest.mark.parametrize("val", t_vals)
def test_bad_type(val: float | list[int] | dict[str, int]) -> None:
    """Test that bad types raise a TypeError."""
    with pytest.raises(TypeError):
        _browse._unpack_aspect(val)  # type: ignore[arg-type]


f_vals = ("4|3", "junk", "0:3", "3:0", "-2:4", "nan:9")


@pytest.mark.parametrize("val", f_vals)
def test_bad_format(val: str) -> None:
    """Test that bad aspect ratios raise a ValueError."""
    with pytest.raises(ValueError, match=r".* as an aspect ratio.*"):
        _browse._unpack_aspect(val)


def test_escape_url() -> None:
    """Test that URLS with weird characters are escaped."""
    url = 'https://calico."cat".com'
    expected = "https://calico.&quot;cat&quot;.com"
    received = _browse._sanitize_url(url)
    assert expected == received


def test_browse(monkeypatch: pytest.MonkeyPatch) -> None:
    """Test that browse() displays escaped, correctly sized HTML."""
    shown: list[HTML] = []
    monkeypatch.setattr(_browse, "display", shown.append)

    _browse.browse('https://example.com/"cat"', "4:3")

    assert len(shown) == 1
    html = shown[0].data
    assert 'src="https://example.com/&quot;cat&quot;"' in html
    assert "padding-top:75.0%" in html
