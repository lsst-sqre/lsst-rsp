"""Launcher for the Lab Runner."""

from .services.labrunner import LabRunner


def main() -> None:
    """Make a LabRunner and call its single public method.  All settings are
    in the environment.
    """
    LabRunner().go()
