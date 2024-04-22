# Change log

lsst-rsp is versioned with [semver](https://semver.org/).

Find changes for the upcoming release in the project's [changelog.d directory](https://github.com/lsst-sqre/lsst-rsp/tree/main/changelog.d/).

<!-- scriv-insert-here -->

<a id='changelog-0.5.2'></a>
## 0.5.2 (2024-04-22)

### Bug fixes

- If the user credentials directory `$HOME/.lsst` does not exist, create it.

<a id='changelog-0.4.3'></a>
## 0.4.3 (2024-03-22)

### Bug fixes

- Raise `ValueError` for invalid arguments to utility functions rather than bare `Exception`.

### Other changes

- lsst-rsp now uses the [Ruff](https://beta.ruff.rs/docs/) linter and formatter instead of Black, flake8, isort, and pydocstyle.
- lsst-rsp now uses [uv](https://github.com/astral-sh/uv) to set up a development environment.
