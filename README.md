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
If you want to use a development version, you must first create a virtualenv, install the necessary packages, and then create a JupyterLab kernel pointing to it.

In a terminal session, run the following commands:

```bash
VENV="lsst_rsp"
mkdir -p ${HOME}/venvs
python -m venv ${HOME}/venvs/${VENV}
. ${HOME}/venvs/${VENV}/bin/activate
mkdir -p ${HOME}/src
cd ${HOME}/src
git clone https://github.com/lsst-sqre/lsst-rsp
# or git clone git@github.com:lsst-sqre/lsst-rsp.git if you prefer
cd lsst-rsp
make init
pip install ipykernel
python -m ipykernel install --user --name=${VENV}
```

Now you will need to shut down your lab and restart it in order to pick up the new lsst-rsp installation.

Once you're in your new container, you will notice that you have a new kernel named `lsst_rsp`.
Now you have an editable version installed in your custom kernel, and you can run all the usual tox environments.

If you start a notebook with your custom kernel, you can see the development version with:

```python
import lsst.rsp

lsst.rsp.__version__
```

You will still need to restart the kernel to pick up changes you make to your copy of `lsst_rsp`.

### Uninstalling a development version from the RSP

In a terminal window, run the following:

```bash
. $HOME/venvs/lsst_rsp/bin/activate
jupyter kernelspec uninstall lsst_rsp
```

Respond `y` and then `deactivate` to the resulting prompts.

Shut down and restart your notebook as before.
When you come back in, in a terminal window, run:

```bash
rm -rf $HOME/venvs/lsst_rsp
```

You cannot remove the virtualenv directory until you have restarted the JupyterLab container, since otherwise JupyterLab will be holding some files open for the running kernel.
