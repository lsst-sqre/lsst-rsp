.PHONY: help
help:
	@echo "Make targets for lsst-rsp:"
	@echo "make init - Set up dev environment (install pre-commit hooks)"
	@echo "make update - Update pre-commit dependencies and run make init"
	@echo "make update-deps - Update pre-commit dependencies"

.PHONY: init
init:
	uv sync --frozen --all-groups
	uv run pre-commit install

.PHONY: update
update: update-deps init

.PHONY: update-deps
update-deps:
	uv lock --upgrade
	uv run --only-group=lint pre-commit autoupdate
	./scripts/update-uv-version.sh
