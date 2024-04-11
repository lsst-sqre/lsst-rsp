.PHONY: help
help:
	@echo "Make targets for lsst-rsp:"
	@echo "make clean - Remove generated files"
	@echo "make init - Set up dev environment (install pre-commit hooks)"

.PHONY: clean
clean:
	rm -rf .tox

.PHONY: init
init:
	pip install --upgrade uv
	uv pip install --upgrade pip tox tox-uv pre-commit
	uv pip install --editable ".[dev]"
	rm -rf .tox
	pre-commit install

