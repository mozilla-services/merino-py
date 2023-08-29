APP_DIR := merino
TEST_DIR := tests
TEST_RESULTS_DIR ?= "workspace/test-results"
COV_FAIL_UNDER := 95
UNIT_TEST_DIR := $(TEST_DIR)/unit
INTEGRATION_TEST_DIR := $(TEST_DIR)/integration
CONTRACT_TEST_DIR := $(TEST_DIR)/contract
LOAD_TEST_DIR := $(TEST_DIR)/load
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

.PHONY: isort
isort: $(INSTALL_STAMP)  ##  Run isort
	$(POETRY) run isort --check-only $(APP_AND_TEST_DIRS)

.PHONY: black
black: $(INSTALL_STAMP)  ##  Run black
	$(POETRY) run black --quiet --diff --check merino $(APP_AND_TEST_DIRS)

.PHONY: flake8
flake8: $(INSTALL_STAMP)  ##  Run flake8
	$(POETRY) run flake8 $(APP_AND_TEST_DIRS)

.PHONY: bandit
bandit: $(INSTALL_STAMP)  ##  Run bandit
	$(POETRY) run bandit --quiet -r $(APP_AND_TEST_DIRS) -c "pyproject.toml"

.PHONY: pydocstyle
pydocstyle: $(INSTALL_STAMP)  ##  Run pydocstyle
	$(POETRY) run pydocstyle $(APP_AND_TEST_DIRS) --config="pyproject.toml"

.PHONY: mypy
mypy: $(INSTALL_STAMP)  ##  Run mypy
	$(POETRY) run mypy $(APP_AND_TEST_DIRS) --config-file="pyproject.toml"

.PHONY: lint
lint: $(INSTALL_STAMP) isort black flake8 bandit pydocstyle mypy ##  Run various linters

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
test: unit-tests integration-tests test-coverage-check  ##  Run unit and integration tests and evaluate combined coverage

.PHONY: test-coverage-check
test-coverage-check: $(INSTALL_STAMP)  ##  Evaluate combined unit and integration test coverage
	$(POETRY) run coverage combine --data-file=$(TEST_RESULTS_DIR)/.coverage
	$(POETRY) run coverage report \
	    --data-file=$(TEST_RESULTS_DIR)/.coverage \
	    --fail-under=$(COV_FAIL_UNDER)

.PHONY: unit-tests
unit-tests: $(INSTALL_STAMP)  ##  Run unit tests
	COVERAGE_FILE=$(TEST_RESULTS_DIR)/.coverage.unit \
	    MERINO_ENV=testing \
	    $(POETRY) run pytest $(UNIT_TEST_DIR) \
	    --cov $(APP_DIR) \
	    --junit-xml=$(TEST_RESULTS_DIR)/unit_results.xml

.PHONY: unit-test-fixtures
unit-test-fixtures: $(INSTALL_STAMP)  ##  List fixtures in use per unit test
	MERINO_ENV=testing $(POETRY) run pytest $(UNIT_TEST_DIR) --fixtures-per-test

.PHONY: integration-tests
integration-tests: $(INSTALL_STAMP)  ##  Run integration tests
	COVERAGE_FILE=$(TEST_RESULTS_DIR)/.coverage.integration \
	    MERINO_ENV=testing \
	    $(POETRY) run pytest $(INTEGRATION_TEST_DIR) \
	    --cov $(APP_DIR) \
	    --junit-xml=$(TEST_RESULTS_DIR)/integration_results.xml

.PHONY: integration-test-fixtures
integration-test-fixtures: $(INSTALL_STAMP)  ##  List fixtures in use per integration test
	MERINO_ENV=testing $(POETRY) run pytest $(INTEGRATION_TEST_DIR) --fixtures-per-test

.PHONY: docker-build
docker-build:  ## Build the docker image for Merino named "app:build"
	docker build -t app:build .

.PHONY: docker-build-jobs
docker-build-jobs:  ## Build the docker image for Merino job runner named "merino-jobs:build"
	docker build --target job_runner -t merino-jobs:build .

.PHONY: run-contract-tests
run-contract-tests:  ##  Run contract tests using docker compose
	TEST_RESULTS_DIR=$(TEST_RESULTS_DIR) docker-compose \
      -f $(CONTRACT_TEST_DIR)/docker-compose.yml \
      -p merino-py-contract-tests \
      up --abort-on-container-exit

.PHONY: contract-tests
contract-tests: docker-build run-contract-tests  ## Run contract tests, with build step

.PHONY: contract-tests-clean
contract-tests-clean:  ##  Stop and remove containers and networks for contract tests, delete client
	TEST_RESULTS_DIR=$(TEST_RESULTS_DIR) docker-compose \
      -f $(CONTRACT_TEST_DIR)/docker-compose.yml \
      -p merino-py-contract-tests \
      down
	  docker rmi client kinto-setup

.PHONY: load-tests
load-tests:  ##  Run local execution of (Locust) load tests
	docker-compose \
      -f $(LOAD_TEST_DIR)/docker-compose.yml \
      -p merino-py-load-tests \
      up --scale locust_worker=1

.PHONY: load-tests-clean
load-tests-clean:  ##  Stop and remove containers and networks for load tests
	docker-compose \
      -f $(LOAD_TEST_DIR)/docker-compose.yml \
      -p merino-py-load-tests \
      down
	docker rmi locust

.PHONY: doc-install-deps
doc-install-deps:  ## Install the dependencies for doc generation
	cargo install mdbook && cargo install mdbook-mermaid

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

.PHONY: docker-compose-up
docker-compose-up:  ## Run `docker-compose up` in `./dev`
	docker-compose -f dev/docker-compose.yaml up

.PHONY: docker-compose-up-daemon
docker-compose-up-daemon:  ## Run `docker-compose up -d` in `./dev`
	docker-compose -f dev/docker-compose.yaml up -d

.PHONY: docker-compose-down
docker-compose-down:  ## Run `docker-compose down` in `./dev`
	docker-compose -f dev/docker-compose.yaml down

.PHONY: help
help:
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | awk 'BEGIN {FS = ":.*?## "}; {printf "\033[36m%-20s\033[0m %s\n", $$1, $$2}'

.PHONY: wikipedia-indexer
wikipedia-indexer:
	$(POETRY) run merino-jobs $@ ${job}

.PHONY: health-check-prod
health-check-prod:  ##  Check the production suggest endpoint with some test queries
	./scripts/quic.sh prod

.PHONY: health-check-staging
health-check-staging:  ##  Check the staging suggest endpoint with some test queries
	./scripts/quic.sh staging
