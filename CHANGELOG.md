# Change log

lsst-rsp is versioned with [semver](https://semver.org/).

Find changes for the upcoming release in the project's [changelog.d directory](https://github.com/lsst-sqre/lsst-rsp/tree/main/changelog.d/).

<!-- scriv-insert-here -->

<a id='changelog-0.6.3'></a>
## 0.6.3 (2024-08-15)

### New features

- Conditionally set environment variable `DAF_BUTLER_CACHE_DIRECTORY`

<a id='changelog-0.6.2'></a>
## 0.6.2 (2024-07-29)

### New features

- Create user-specific TMPDIR under /scratch if applicable.

<a id='changelog-0.6.1'></a>
## 0.6.1 (2024-06-17)

### Bug fixes

- Allow for the relative location of the logging source used in the two-Python model.

<a id='changelog-0.6.0'></a>
## 0.6.0 (2024-06-13)

### New features

- Handle `RESET_USER_ENV` inside `lsst.rsp.startup`.
- Add utility functions to get values that were constants in the single-Python model but now are not.

<a id='changelog-0.5.5'></a>
## 0.5.5 (2024-05-09)

### Backward-incompatible changes

- Stop forcing the value of `FIREFLY_HTML`, since newer versions of the Firefly plugin do not want it to be set. It must be set in the Nublado configuration if needed.

<a id='changelog-0.5.4'></a>
## 0.5.4 (2024-05-09)

### Bug fixes

- Fix creation of the parent directory for the logging configuration.

<a id='changelog-0.5.3'></a>
## 0.5.3 (2024-05-09)

### New features

- Add `RSPClient`, a configured HTTP client for services in the same RSP instance.

### Bug fixes

- Create the path to the logging profile directory if it doesn't exist.

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

- Add an `lsst.rsp.startup` module and `launch-rubin-jupyterlab` entry point to replace most of the `runlab.sh` script in sciplat-lab. This handles startup and configuration of the Rubin-customized JupyterLab.

<a id='changelog-0.4.3'></a>
## 0.4.3 (2024-03-22)

### Bug fixes

- Raise `ValueError` for invalid arguments to utility functions rather than bare `Exception`.

### Other changes

- lsst-rsp now uses the [Ruff](https://beta.ruff.rs/docs/) linter and formatter instead of Black, flake8, isort, and pydocstyle.
- lsst-rsp now uses [uv](https://github.com/astral-sh/uv) to set up a development environment.
