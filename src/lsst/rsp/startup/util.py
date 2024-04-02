"""Utility functions for RSP startup."""

def str_bool(inp: str) -> bool:
    """Convert a string to our best guess of whether it means "true" or
       "false."
    """
    # The empty string is false.
    if not inp:
        return False
    
    # Is it plausibly a number?  If it is and its value is zero, it's false.
    # If it is a nonzero number, it's true.
    try:
        inp_n = float(inp)
        if inp_n:
            return True
        return False
    except ValueError:
        pass

    # Canonicalize it to uppercase
    inp=inp.upper()

    # Does it start with "N" or "F"?  It's false.  Otherwise, it's true.
    if inp.startswith("N") or inp.startswith("F"):
        return False
    return True
