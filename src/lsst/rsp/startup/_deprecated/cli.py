"""CLI launchers for the Lab Runner and the landing page provisioner.

These items are deprecated; their functionality was moved to Nublado in the
Nublado 11.0.0 release.
"""

import logging

from deprecated import deprecated

from .constants import NUBLADO_TOO_OLD
from .services.labrunner import LabRunner
from .services.landing_page.provisioner import Provisioner


@deprecated(reason=NUBLADO_TOO_OLD)
def launch_lab() -> None:
    """Make a LabRunner and call its single public method.  All settings are
    in the environment.
    """
    LabRunner().go()


@deprecated(reason=NUBLADO_TOO_OLD)
def provision_landing_page() -> None:
    """Entry point for landing page provisioner.

    This is expected to be the entry point for an init container that sets
    up the landing page for the Nublado user's lab.

    Environment variable ``NUBLADO_HOME`` must be set.  This is
    Nublado-controller specific and set for Nublado init containers.

    We never want to raise an exception from here: if the container fails,
    we still want to start the user lab, but the experience might be
    suboptimal.
    """
    logger = logging.getLogger("landing_page_provisioner")
    logging.basicConfig()  # Not great but it'll do.
    try:
        provisioner = Provisioner.from_env()
        provisioner.go()
    except Exception:
        logger.exception("Provisioner failed")
