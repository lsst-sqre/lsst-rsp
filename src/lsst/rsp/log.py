"""Log configuration for Notebooks."""

__all__ = ["IPythonHandler", "forward_lsst_log"]

import html
import logging
import traceback

from IPython.display import HTML, display

try:
    import lsst.log as lsstLog
except ImportError:
    lsstLog = None

# Each log level will have the level name use a different color to
# ensure that warning log messages can be seen more easily.
_level_colors = {
    "CRITICAL": "var(--jp-error-color0)",
    "ERROR": "var(--jp-error-color2)",
    "WARNING": "var(--jp-warn-color0)",
    "INFO": "var(--jp-info-color0)",
    "VERBOSE": "var(--jp-info-color3)",
    "DEBUG": "var(--jp-success-color0)",
    "DEFAULT": "var(--jp-success-color3)",
}

# CSS style for the PRE block to use for displaying log messages.
# The margin prevents excessive space between log messages.
# The border gives a vertical bar at the start of a log message to improve
# delineation between log output and standard output.
# The left padding gives space between that bar and the first character.
# By default PRE blocks do not use a font size that matches the print()
# output so force it here.
_pre_style = """margin: 0.1em;
padding-left: 0.25em;
border-left-style: solid;
font-family: var(--jp-code-font-family);
font-size: var(--jp-code-font-size);
line-height: var(--jp-code-line-height);
"""


class IPythonHandler(logging.Handler):
    """Special log handler for IPython Notebooks.
    This log handler emits log messages as formatted HTML output with
    the following content:
    * The name of the logger.
    * The level of the log message, color coded based on severity.
    * The message itself.
    It can be enabled (forcing other log handlers to be removed) with:
    .. code-block:: python
       logging.basicConfig(level=logging.INFO, force=True,
                           handlers=[IPythonHandler()])
    """

    def emit(self, record: logging.LogRecord) -> None:
        name_color = "var(--jp-warn-color2)"
        level_color = _level_colors.get(
            record.levelname, _level_colors["DEFAULT"]
        )
        message = html.escape(record.getMessage())
        name_msg = f'<span style="color: {name_color}">{record.name}</span>'
        level_msg = (
            f'<span style="color: {level_color}">{record.levelname}</span>'
        )
        text = (
            f'<pre style="{_pre_style}">{name_msg} {level_msg}: '
            + f"{message}</pre>"
        )
        # Sometimes exception information is included so must be extracted.
        if record.exc_info:
            etype = record.exc_info[0]
            evalue = record.exc_info[1]
            tb = record.exc_info[2]
            text += (
                f'<pre style="{_pre_style}">'
                + "".join(traceback.format_exception(etype, evalue, tb))
                + "</pre>"
            )
        display(HTML(text))


def forward_lsst_log(level: str) -> None:
    """Forward ``lsst.log`` level messages to Python logging.
    Parameters
    ----------
    level : `str`
        The level name to forward.
    """
    if lsstLog is not None:
        lsstLog.configure_pylog_MDC(level, MDC_class=None)
        lsstLog.usePythonLogging()
