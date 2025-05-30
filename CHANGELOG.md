# Change log

lsst-rsp is versioned with [semver](https://semver.org/).

Find changes for the upcoming release in the project's [changelog.d directory](https://github.com/lsst-sqre/lsst-rsp/tree/main/changelog.d/).

<!-- scriv-insert-here -->

<a id='changelog-0.9.0'></a>
## 0.9.0 (2025-05-30)

### New features

- Added landing page provisioner to startup class.
- Added docker image build for provisioner.

<a id='changelog-0.8.5'></a>
## 0.8.5 (2025-05-16)

### Other changes

- Allow configuration override of scratch directory.

<a id='changelog-0.8.4'></a>
## 0.8.4 (2025-04-28)

### Bug fixes

- Debug mode was not working correctly because it invoked a subshell

<a id='changelog-0.8.3'></a>
## 0.8.3 (2025-04-17)

### Bug fixes

- Added consdbtap to list of TAP services that we add the lsst-token authentication method for in pyvo

### Other changes

- Changed get_siav2_service to work with new SIA app and added data_release parameter to it

<a id='changelog-0.8.1'></a>
## 0.8.1 (2025-03-26)

### Backwards-incompatible changes

-

### New features

-

### Bug fixes

- Package find needed a wildcard to work with current setuptools.

### Other changes

-

<a id='changelog-0.8.0'></a>
## 0.8.0 (2025-03-26)

### Backwards-incompatible changes

- The Lab will now start if it cannot write to the home directory. It will attempt to free up space if it can do so safely, and will set environment variables handled in rsp-jupyter-extensions to present a warning dialog to the user.

- The Lab no longer downloads notebooks from GitHub on startup.

- Python 3.11 support removed.

### New features

-

### Bug fixes

-

### Other changes

- Add consdbtap to list of known TAP services in catalog.get_tap_service

-

<a id='changelog-0.7.1'></a>
## 0.7.1 (2025-02-25)

### Bug fixes

- If there are no jobs in query history, return empty list instead of raising KeyError.

<a id='changelog-0.7.0'></a>
## 0.7.0 (2025-01-27)

### New features

- added `get_query_history()` function

<a id='changelog-0.6.6'></a>
## 0.6.6 (2025-01-23)

### Bug fixes

- Pass in session as a keyword argument to initialization of TAP classes

<a id='changelog-0.6.5'></a>
## 0.6.5 (2025-01-15)

### Other changes

- If the auto notebook pulls from GitHub time out, log an error and keep going rather than crashing.

<a id='changelog-0.6.4'></a>
## 0.6.4 (2024-08-16)

### New features

- Set the default `DAF_BUTLER_CACHE_DIRECTORY` path to a sibling directory of the `TMPDIR` directory if moved into the scratch directory instead of using a subdirectory.

### Bug fixes

- When using a scratch directory as the root of directory of temporary files, set the mode on that directory to 0700 if it has to be created.

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
