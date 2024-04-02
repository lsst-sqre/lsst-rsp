#!/usr/bin/env python3

import os
import logging
import structlog

from pathlib import Path
from shlex import join
from typing import Any, Self

from ..storage.process import run, ProcessResult
from ..util import str_bool

class LabRunner:
    """Class to start JupyterLab using the environment supplied by
    JupyterHub and the Nublado controller.  This environment is very
    Rubin-specific and opinionated, and will likely not work for anyone
    else's science platform.

    If that's you, use this for inspiration, but don't expect this to
    work out of the box.
    """

    def __init__(self) -> None:
        self.debug = str_bool(os.getenv("DEBUG"),"")
        self._configure_logging()
        self.logger=structlog.get_logger("nublado")
        self.user = self._get_user()
        self.env = self._create_env()

    def _configure_logging(self) -> None:
        """Stripped-down version of Safir's "configure_logging()"; we
        always add timestamps, and if we're not running with debugging,
        it's INFO-level JSON logs; if we are running with debugging,
        DEBUG-level text-format.
        """
        log_level = "DEBUG" if self.debug else "INFO"
        stream_handler = logging.StreamHandler(stream=sys.stdout)
        stream_handler.setFormatter(logging.Formatter("%(message)s"))
        self.logger = logging.getLogger("nublado")
        self.logger.handlers = []
        self.logger.addHandler(stream_handler)
        logger.setLevel(log_level)
        processors: list[Any] = [
            structlog.stdlib.filter_by_level,
	    structlog.stdlib.add_logger_name,
            structlog.stdlib.PositionalArgumentsFormatter(),
        ]
        processors.append(structlog.processors.TimeStamper(fmt="iso"))
        processors.extend(
            [
                structlog.processors.StackInfoRenderer(),
                structlog.processors.UnicodeDecoder(),
            ]
        )
        if self.debug:
            # Key-value formatted logging
            processors.append(structlog.stdlib.add_log_level)
            processors.append(structlog.dev.ConsoleRenderer())
        else:
            # JSON-formatted logging
            processors.append(add_log_severity)
            processors.append(structlog.processors.format_exc_info)
            processors.append(structlog.processors.JSONRenderer())
        structlog.configure(
            processors=processors,
            logger_factory=structlog.stdlib.LoggerFactory(),
            wrapper_class=structlog.stdlib.BoundLogger,
            cache_logger_on_first_use=True,
        )
        
        
    def _run(
        *args: str,
        timeout: Optional[int] = None,
    ) -> ProcessResult|None:
        """Convenience method for running subprocesses with the correct
        logger."""
        return run(*args, logger=self.logger, timeout=timeout)
        
    def _get_user(self) -> str:
        user = os.getenv("USER")
        if user:
            return user
        return self._run("id", "-u", "-n").strip()
    
    def _create_env(self) -> dict[str,str]:
        pass
        
        

    def copy_butler_credentials() -> None:
        pass
    

def main() -> None:
    pass



# function copy_butler_credentials() {
#     # Copy the credentials from the root-owned mounted secret to our homedir,
#     # set the permissions accordingly, and repoint the environment variables.
#     creddir="${HOME}/.lsst"
#     mkdir -p "${creddir}"
#     chmod 0700 "${creddir}"
#     if [ -n "${AWS_SHARED_CREDENTIALS_FILE}" ]; then
#         awsname="$(basename ${AWS_SHARED_CREDENTIALS_FILE})"
#         newcreds="${creddir}/${awsname}"
# 	python /opt/lsst/software/jupyterlab/confmerge.py ini "${AWS_SHARED_CREDENTIALS_FILE}" "${newcreds}"
#         ORIG_AWS_SHARED_CREDENTIALS_FILE="${AWS_SHARED_CREDENTIALS_FILE}"
#         AWS_SHARED_CREDENTIALS_FILE="${newcreds}"
#         export ORIG_AWS_SHARED_CREDENTIALS_FILE AWS_SHARED_CREDENTIALS_FILE
#     fi
#     if [ -n "${PGPASSFILE}" ]; then
#         pgname="$(basename ${PGPASSFILE})"
#         newpg="${creddir}/${pgname}"
# 	python /opt/lsst/software/jupyterlab/confmerge.py pgpass "${PGPASSFILE}" "${newpg}"
#         ORIG_PGPASSFILE="${PGPASSFILE}"
#         PGPASSFILE="${newpg}"
#         export ORIG_PGPASSFILE PGPASSFILE
#     fi
# }


if __name__== "__main__":
    main()
