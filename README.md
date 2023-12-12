# lsst-rsp

User-facing Python classes and functions for use in the RSP environment.
Learn more at https://lsst-rsp.lsst.io

Install from PyPI:

```sh
pip install lsst-rsp
```

but, really, lsst-rsp is only useful inside an RSP JupyterLab container.

See below for how to test new versions within such a container.

lsst-rsp is developed by Rubin Observatory at https://github.com/lsst-sqre/lsst-rsp.

## Developing lsst-rsp

The best way to start contributing to lsst-rsp is by cloning this repository, creating a virtual environment, and running the `make init` command:

```sh
git clone https://github.com/lsst-sqre/lsst-rsp.git
cd lsst-rsp
make init
```

You can run tests and build documentation with [tox](https://tox.wiki/en/latest/):

```sh
tox
```

To learn more about the individual environments:

```sh
tox -av
```

## Developing lsst-rsp on the RSP

The `LSST` kernel in the RSP `sciplat-lab` image already has a release
version of `lsst-rsp` in it.  Therefore, there is some setup you need to
do in order to create a development environment you can use.
Specifically, you need to create a virtualenv for the editable
`lsst-rsp`, install `tox` and `pre-commit` for its test machinery, and
then create a JupyterLab kernel pointing to it.

Open a terminal session:

```bash
VENV="lsst_rsp"
mkdir -p ${HOME}/venvs
python -m venv ${HOME}/venvs/${VENV}
. ${HOME}/venvs/${VENV}/bin/activate
mkdir -p ${HOME}/src
cd ${HOME}/src
git clone https://github.com/lsst-sqre/lsst-rsp # or git@github.com:lsst-sqre/lsst-rsp.git if you prefer
cd lsst-rsp
make init
pip install ipykernel
python -m ipykernel install --user --name=${VENV}
```

Now you will need to shut down your lab and get a new container image.
That's because the process your Lab interface is running inside doesn't
know about the new kernel--but once you restart the Lab container, it
will.

Once you're in your new container, you will notice that you have a new
kernel named `lsst_rsp`.

Now you've got an editable version installed in your custom kernel, and
you can still run all the usual tox environments too.

If you start a notebook with your custom kernel,

```python
import lsst.rsp

lsst.rsp.__version__
```

will show you your development version.  Note that you will still need
to restart the kernel to pick up changes you make to your copy of
`lsst_rsp`.

Uninstalling a development version from the RSP
===============================================

Open a terminal window.

```bash
. $HOME/venvs/lsst_rsp/bin/activate
jupyter kernelspec uninstall lsst_rsp
y
deactivate
```

Shut down and restart your notebook as before.  When you come back in,
in a terminal window:

```bash
rm -rf $HOME/venvs/lsst_rsp
```

You will need to remove the virtualenv directory after restarting the
Lab container, because otherwise JupyterLab will be holding some files
open because it still believes it has a kernel there.
