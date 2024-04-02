"""Utility functions for RSP startup."""

__all__ = ["str_bool"]


def str_bool(inp: str) -> bool:
    """Convert a string to our best guess of whether it means ``true`` or
    ``false``.
    """
    # The empty string is false.
    if not inp:
        return False

    # Is it plausibly a number?  If it is and its value is zero, it's false.
    # If it is a nonzero number, it's true.
    try:
        return float(inp) != 0
    except ValueError:
        pass

    # Canonicalize it to uppercase
    inp = inp.upper()

    # Does it start with "N" or "F"?  It's false.  Otherwise, it's true.
    if inp.startswith(("N", "F")):
        return False
    return True
