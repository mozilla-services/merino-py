APP_DIR := merino
TEST_DIR := tests
UNIT_TEST_DIR := $(TEST_DIR)/unit
INTEGRATION_TEST_DIR := $(TEST_DIR)/integration
CONTRACT_TEST_DIR := $(TEST_DIR)/contract
APP_AND_TEST_DIRS := $(APP_DIR) $(TEST_DIR)
INSTALL_STAMP := .install.stamp
POETRY := $(shell command -v poetry 2> /dev/null)

# This will be run if no target is provided
.DEFAULT_GOAL := help

.PHONY: install
install: $(INSTALL_STAMP)  ##  Install dependencies with poetry
$(INSTALL_STAMP): pyproject.toml poetry.lock
	@if [ -z $(POETRY) ]; then echo "Poetry could not be found. See https://python-poetry.org/docs/"; exit 2; fi
	$(POETRY) install
	touch $(INSTALL_STAMP)

.PHONY: lint
lint: $(INSTALL_STAMP)  ##  Run various linters
	$(POETRY) run isort --check-only $(APP_AND_TEST_DIRS)
	$(POETRY) run black --quiet --diff --check merino $(APP_AND_TEST_DIRS)
	$(POETRY) run flake8 $(APP_AND_TEST_DIRS)
	$(POETRY) run bandit --quiet -r $(APP_AND_TEST_DIRS) -c "pyproject.toml"
	$(POETRY) run pydocstyle $(APP_DIR) --config="pyproject.toml"
	$(POETRY) run mypy $(APP_DIR) $(INTEGRATION_TEST_DIR) $(CONTRACT_TEST_DIR) --config-file="pyproject.toml"

.PHONY: format
format: $(INSTALL_STAMP)  ##  Sort imports and reformat code
	$(POETRY) run isort $(APP_AND_TEST_DIRS)
	$(POETRY) run black $(APP_AND_TEST_DIRS)

.PHONY: dev
dev: $(INSTALL_STAMP)  ##  Run merino locally and reload automatically
	$(POETRY) run uvicorn $(APP_DIR).main:app --reload

.PHONY: run
run: $(INSTALL_STAMP)  ##  Run merino locally
	$(POETRY) run uvicorn $(APP_DIR).main:app

.PHONY: test
test: $(INSTALL_STAMP)  ##  Run unit and integration tests
	MERINO_ENV=testing $(POETRY) run pytest $(UNIT_TEST_DIR) $(INTEGRATION_TEST_DIR) --cov $(APP_DIR)

.PHONY: unit-tests
unit-tests: $(INSTALL_STAMP)  ##  Run unit tests
	MERINO_ENV=testing $(POETRY) run pytest $(UNIT_TEST_DIR) --cov $(APP_DIR)

.PHONY: unit-test-fixtures
unit-test-fixtures: $(INSTALL_STAMP)  ##  List fixtures in use per unit test
	MERINO_ENV=testing $(POETRY) run pytest $(UNIT_TEST_DIR) --fixtures-per-test

.PHONY: integration-tests
integration-tests: $(INSTALL_STAMP)  ##  Run integration tests
	MERINO_ENV=testing $(POETRY) run pytest $(INTEGRATION_TEST_DIR) --cov $(APP_DIR)

.PHONY: integration-test-fixtures
integration-test-fixtures: $(INSTALL_STAMP)  ##  List fixtures in use per integration test
	MERINO_ENV=testing $(POETRY) run pytest $(INTEGRATION_TEST_DIR) --fixtures-per-test

.PHONY: contract-tests
contract-tests:  ##  Run contract tests using docker compose
	docker-compose \
      -f $(CONTRACT_TEST_DIR)/docker-compose.yml \
      -p merino-py-contract-tests \
      up --abort-on-container-exit --build

.PHONY: contract-tests-clean
contract-tests-clean:  ##  Stop and remove containers and networks for contract tests
	docker-compose \
      -f $(CONTRACT_TEST_DIR)/docker-compose.yml \
      -p merino-py-contract-tests \
      down

.PHONY: doc
doc:  ##  Generate Merino docs via mdBook
	./dev/make-all-docs.sh

.PHONY: doc-preview
doc-preview:  ##  Preview Merino docs via the default browser
	mdbook serve --open

# Use `mozlog` format and `INFO` level to reduce noise
.PHONY: profile
profile:  ## Profile Merino with Scalene
	MERINO_LOGGING__FORMAT=mozlog MERINO_LOGGING__LEVEL=INFO python -m scalene merino/main.py

.PHONY: help
help:
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | awk 'BEGIN {FS = ":.*?## "}; {printf "\033[36m%-20s\033[0m %s\n", $$1, $$2}'
