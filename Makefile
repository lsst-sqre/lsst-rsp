.PHONY: help
help:
	@echo "Make targets for lsst-rsp:"
	@echo "make clean - Remove generated files"
	@echo "make init - Set up dev environment (install pre-commit hooks)"
	@echo "make linkcheck - Check for broken links in documentation"

.PHONY: clean
clean:
	rm -rf .tox
	rm -rf docs/_build
	rm -rf docs/api

.PHONY: init
init:
	pip install --upgrade pip tox pre-commit
	pip install --upgrade -e ".[dev]"
	pre-commit install
	rm -rf .tox
