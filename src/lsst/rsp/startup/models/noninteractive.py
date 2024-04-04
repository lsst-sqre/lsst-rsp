"""Run a command noninteractively from a configuration JSON file."""

import json
import os
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Self


class NonInteractiveExecutionType(Enum):
    """Command types for noninteractive execution."""

    nb = "nb"
    """Notebook execution type."""

    command = "command"
    """Command execution type."""


@dataclass
class NonInteractiveExecution:
    """Launch noninteractive Lab container execution from a
    configuration document.
    """

    type: NonInteractiveExecutionType | str
    kernel: str
    command: list[str]

    def __post_init__(self) -> None:
        #
        # Sure, Pydantic does validation like this more easily, but nothing
        # else in the package uses Pydantic, and other than the
        # noninteractive command structure there's really nothing
        # user-facing, so it's a lot of stuff for not much benefit.
        #
        if isinstance(self.type, str):
            self.type = NonInteractiveExecutionType(self.type)
        if self.type != NonInteractiveExecutionType.command:
            raise NotImplementedError(
                "Only 'command' type is currently supported for"
                " noninteractive execution."
            )

    @classmethod
    def from_config(cls, config: Path) -> Self:
        """Load configuration from a JSON document."""
        with config.open() as f:
            obj = json.load(f)
            return cls(
                type=obj["type"], kernel=obj["kernel"], command=obj["command"]
            )

    def execute(
        self,
        env: dict[str, str] = dict(os.environ),  # noqa: B006
    ) -> None:
        """Run the command specified in the object, with a supplied
        environment (defaulting to the ambient environment).
        """
        # Flush any open files before exec()
        os.sync()
        os.execve(self.command[0], self.command, env=env)
