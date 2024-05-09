# Change log

lsst-rsp is versioned with [semver](https://semver.org/).

Find changes for the upcoming release in the project's [changelog.d directory](https://github.com/lsst-sqre/lsst-rsp/tree/main/changelog.d/).

<!-- scriv-insert-here -->

<a id='changelog-0.5.3'></a>
## 0.5.3 (2024-05-09)

### New features

- Add RSPClient, a configured HTTP client for services in the same RSP instance.

### Bug fixes

- If the path to the logging profile directory doesn't exist, create it.

<a id='changelog-0.5.2'></a>
## 0.5.2 (2024-04-22)

### Bug fixes

- If the user credentials directory `$HOME/.lsst` does not exist, create it.

<a id='changelog-0.5.1'></a>
## 0.5.1 (2024-04-11)

### Bug fixes

- Fix working directory for `git config --get` when checking whether a local Git repository needs to be updated.

<a id='changelog-0.5.0'></a>
## 0.5.0 (2024-04-11)

### New features

- Add a lsst.rsp.startup module and `launch-rubin-jupyterlab` entry point to replace most of the `runlab.sh` script in sciplat-lab. This handles startup and configuration of the Rubin-customized JupyterLab.

<a id='changelog-0.4.3'></a>
## 0.4.3 (2024-03-22)

### Bug fixes

- Raise `ValueError` for invalid arguments to utility functions rather than bare `Exception`.

### Other changes

- lsst-rsp now uses the [Ruff](https://beta.ruff.rs/docs/) linter and formatter instead of Black, flake8, isort, and pydocstyle.
- lsst-rsp now uses [uv](https://github.com/astral-sh/uv) to set up a development environment.
