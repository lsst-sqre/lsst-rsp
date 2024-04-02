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
	uv pip install --editable .
	uv pip install -r requirements/main.txt -r requirements/dev.txt
	rm -rf .tox
	pre-commit install

.PHONY: update
update: update-deps init

.PHONY: update-deps
update-deps:
	pip install --upgrade uv
	uv pip install pre-commit
	pre-commit autoupdate
	uv pip compile --upgrade --generate-hashes                   \
            --output-file requirements/main.txt requirements/main.in
	uv pip compile --upgrade --generate-hashes                   \
            --output-file requirements/dev.txt requirements/dev.in

# Useful for testing against Git versions of dependencies.
.PHONY: update-deps-no-hashes
update-deps-no-hashes:
	pip install --upgrade uv
	uv pip compile --upgrade                                        \
            --output-file requirements/main.txt requirements/main.in
	uv pip compile --upgrade                                        \
            --output-file requirements/dev.txt requirements/dev.in
