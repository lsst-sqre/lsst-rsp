.PHONY: init
init:
	pip install --upgrade pip pre-commit setuptools wheel
	pip install --upgrade --editable .
	rm -rf .tox
	pip install --upgrade tox
	pre-commit install
