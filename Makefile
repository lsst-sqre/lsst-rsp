.PHONY: help
help:
	@echo "Make targets for lsst-rsp:"
	@echo "make clean - Remove generated files"
	@echo "make init - Set up dev environment (install pre-commit hooks)"
	@echo "make update - Update pre-commit dependencies and run make init"
	@echo "make update-deps - Update pre-commit dependencies"

.PHONY: clean
clean:
	rm -rf .tox

.PHONY: init
init:
	pip install --upgrade uv
	uv pip install --upgrade pip tox pre-commit
	uv pip install --upgrade -e ".[dev]"
	pre-commit install
	rm -rf .tox

.PHONY: update
update: update-deps init

.PHONY: update-deps
update-deps:
	pip install --upgrade uv
	uv pip install pre-commit
	pre-commit autoupdate
