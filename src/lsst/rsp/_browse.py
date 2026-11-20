"""Minimal in-notebook browser.

It's not a full browser; it just embeds a page in an iframe, and it cannot do
authentication, or initial requests that aren't a GET, or much else, really.
"""

import math
from html import escape

from IPython.display import HTML, display

__all__ = ["browse"]


def _unpack_aspect(aspect_ratio: str) -> str:
    """Return an aspect ratio supplied as width:height.

    This may be in the form "w:h", "wxh", "wXh", or "w/h".

    Returns a format suitable for just slotting into the div
    that wraps the iframe.  This is height/width expressed
    as a percentage.

    This is a helper for browse().
    """
    aspect: float | None = None
    if not isinstance(aspect_ratio, str):
        raise TypeError('aspect ratio must be type str (e.g. "16:9")')
    splitters = (":", "x", "X", "/")
    err = f"Could not parse {aspect_ratio!r} as an aspect ratio"
    for item in splitters:
        splat = aspect_ratio.split(item)
        if len(splat) != 2:
            continue
        try:
            aspect = float(splat[1]) / float(splat[0])
        except Exception as exc:
            raise ValueError(err) from exc
        if not (math.isfinite(aspect) and aspect > 0):
            raise ValueError(err)
        break
    if aspect is None:
        raise ValueError(err)
    pct = 100.0 * aspect
    return f"{pct}%"


def _generate_html(url: str, aspect_ratio: str) -> str:
    """Return the HTML we're going to display, a formatted iframe.

    This is a helper for browse().
    """
    style = "border:0;position:absolute;top:0;left:0;width:100%;height:100%;"
    return f"""
    <div style="position:relative;padding-top:{aspect_ratio};">
      <iframe src="{url}" allowfullscreen style="{style}"></iframe>
    </div>
    """


def _sanitize_url(url: str) -> str:
    """HTML-escape any URL we get."""
    return escape(url, quote=True)


def browse(
    url: str,
    aspect_ratio: str = "16:9",
) -> None:
    """Display the URL in an iframe in the notebook.

    Parameters
    ----------
    url
        Source for the iframe.
    aspect_ratio
        The aspect ratio of the displayed page.

    Notes
    -----
    This is a tiny wrapper that displays a page at a fixed
    aspect ratio (defaulting to 16:9, which is likely the
    aspect of your screen).

    This is taken from
    https://jameshfisher.com/2017/08/30/how-do-i-make-a-full-width-iframe/

    If a site sends X-Frame-Options or a CSP ``frame-ancestors`` header,
    the iframe will be blank.

    Also, we make no provision for authentication.  This is intended purely
    as a lightweight convenience function to display the contents of a URL,
    and is not an embedded web browser.
    """
    # Canonicalize our inputs
    url = _sanitize_url(url)
    aspect_ratio = _unpack_aspect(aspect_ratio)
    # Make the div
    html = _generate_html(url, aspect_ratio)
    # Show it
    display(HTML(data=html))
