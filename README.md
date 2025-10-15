# lsst-rsp

This Python package provides utility functions for the [Rubin Science Platform](https://rsp.lsst.io/), primarily for use within the Notebook Aspect.
These utility functions are documented in the [Notebook aspect documentation](https://rsp.lsst.io/guides/notebooks/index.html) for the Rubin Science Platform.

## Installation

The package can be installed from PyPI:

```sh
pip install lsst-rsp
```

However, most functionality of lsst-rsp is only useful inside a Rubin Science Platform JupyterLab container.
This package is pre-installed in the standard containers.

## Development

The best way to start contributing to lsst-rsp is by cloning this repository, creating a virtual environment, and running the `make init` command:

```sh
git clone https://github.com/lsst-sqre/lsst-rsp.git
cd lsst-rsp
make init
```

You can run tests with [tox](https://tox.wiki/en/latest/):

```sh
tox run
```

To learn more about the individual environments:

```sh
tox list
```

### Developing on the RSP

The `LSST` kernel in the RSP `sciplat-lab` image already has a release version of `lsst-rsp` included.
If you want to use a development version, you can install a newer version locally in your home directory.
In a terminal session, run the following commands:

```bash
mkdir -p ${HOME}/src
cd ${HOME}/src
git clone https://github.com/lsst-sqre/lsst-rsp
cd lsst-rsp
pip install .
```

You can now import functions from `lsst.rsp` in a notebook and should see the new version of the code.

If you already imported functions from `lsst.rsp` in your session, you will need to restart your kernel before the new version of `lsst.rsp` will be visible.
If you make any additional local changes, you will need to restart the kernel to see those changes.

### Uninstalling a development version from the RSP

Once you have installed a development version, that version will shadow the release version until you explicitly uninstall it.
You will therefore want to uninstall the development version once you're done testing.
To do that, run the following in a terminal window:

```bash
pip uninstall lsst-rsp
```

You will be prompted to confirm the removal of your local version.
As before, after running this command, you will need to restart your kernel to return to using the released version.
