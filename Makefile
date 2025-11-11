APP_DIR := merino
TEST_DIR := tests
TEST_RESULTS_DIR ?= "workspace/test-results"
COV_FAIL_UNDER := 95
UNIT_TEST_DIR := $(TEST_DIR)/unit
INTEGRATION_TEST_DIR := $(TEST_DIR)/integration
LOAD_TEST_DIR := $(TEST_DIR)/load
APP_AND_TEST_DIRS := $(APP_DIR) $(TEST_DIR)
INSTALL_STAMP := .install.stamp
UV := $(shell command -v uv 2> /dev/null)

# In order to be consumed by the ETE Test Metric Pipeline, files need to follow a strict naming
# convention: {job_number}__{utc_epoch_datetime}__{repository}__{workflow}__{test_suite}__results{-index}.xml
EPOCH_TIME := $(shell date +"%s")
TEST_FILE_PREFIX := $(if $(GITHUB_ACTIONS),$(GITHUB_RUN_NUMBER)__$(EPOCH_TIME)__$(GITHUB_REPONAME)__$(GITHUB_WORKFLOW)__)
UNIT_JUNIT_XML := $(TEST_RESULTS_DIR)/$(TEST_FILE_PREFIX)unit__results.xml
UNIT_COVERAGE_JSON := $(TEST_RESULTS_DIR)/$(TEST_FILE_PREFIX)unit__coverage.json
INTEGRATION_JUNIT_XML := $(TEST_RESULTS_DIR)/$(TEST_FILE_PREFIX)integration__results.xml
INTEGRATION_COVERAGE_JSON := $(TEST_RESULTS_DIR)/$(TEST_FILE_PREFIX)integration__coverage.json

# This will be run if no target is provided
.DEFAULT_GOAL := help

# Parameter for the Navigational Suggestions job
SAMPLE_SIZE ?= 20
METRICS_DIR ?= ./local_data
ENABLE_MONITORING ?= false
NAV_OPTS ?=

.PHONY: install
install: $(INSTALL_STAMP)  ##  Install dependencies with uv
$(INSTALL_STAMP): pyproject.toml uv.lock
	@if [ -z $(UV) ]; then echo "uv could not be found."; exit 2; fi
	$(UV) sync --all-groups
	touch $(INSTALL_STAMP)

.PHONY: ruff-lint
ruff-lint: $(INSTALL_STAMP)  ##  Run ruff linting
	$(UV) run ruff check $(APP_AND_TEST_DIRS)

.PHONY: ruff-fmt
ruff-fmt: $(INSTALL_STAMP)  ##  Run ruff format checker
	$(UV) run ruff format --check $(APP_AND_TEST_DIRS)

.PHONY: ruff-format
ruff-format: $(INSTALL_STAMP)  ##  Run ruff format
	$(UV) run ruff format $(APP_AND_TEST_DIRS)

.PHONY: bandit
bandit: $(INSTALL_STAMP)  ##  Run bandit
	$(UV) run bandit --quiet -r $(APP_AND_TEST_DIRS) -c "pyproject.toml"

.PHONY: mypy
mypy: $(INSTALL_STAMP)  ##  Run mypy
	$(UV) run mypy $(APP_AND_TEST_DIRS) --config-file="pyproject.toml"

.PHONY: lint
lint: $(INSTALL_STAMP) ruff-lint ruff-fmt bandit mypy ##  Run various linters

.PHONY: format
format: $(INSTALL_STAMP)  ##  Sort imports and reformat code
	$(UV) run ruff check --fix $(APP_AND_TEST_DIRS)
	$(UV) run ruff format $(APP_AND_TEST_DIRS)

.PHONY: dev
dev: $(INSTALL_STAMP)  ##  Run merino locally and reload automatically
	$(UV) run fastapi dev $(APP_DIR)/main.py --reload

.PHONY: run
run: $(INSTALL_STAMP)  ##  Run merino locally
	$(UV) run fastapi run $(APP_DIR)/main.py

.PHONY: test
test: unit-tests integration-tests test-coverage-check  ##  Run unit and integration tests and evaluate combined coverage

.PHONY: test-coverage-check
test-coverage-check: $(INSTALL_STAMP)  ##  Evaluate combined unit and integration test coverage
	$(UV) run coverage combine --data-file=$(TEST_RESULTS_DIR)/.coverage
	$(UV) run coverage report \
	    --data-file=$(TEST_RESULTS_DIR)/.coverage \
	    --fail-under=$(COV_FAIL_UNDER)

.PHONY: unit-tests
unit-tests: $(INSTALL_STAMP)  ##  Run unit tests
	COVERAGE_FILE=$(TEST_RESULTS_DIR)/.coverage.unit \
	    MERINO_ENV=testing \
	    $(UV) run pytest $(UNIT_TEST_DIR) \
	    --junit-xml=$(UNIT_JUNIT_XML) -vv -sx

.PHONY: unit-test-fixtures
unit-test-fixtures: $(INSTALL_STAMP)  ##  List fixtures in use per unit test
	MERINO_ENV=testing $(UV) run pytest $(UNIT_TEST_DIR) --fixtures-per-test

.PHONY: integration-tests
integration-tests: $(INSTALL_STAMP)  ##  Run integration tests
	COVERAGE_FILE=$(TEST_RESULTS_DIR)/.coverage.integration \
	    MERINO_ENV=testing \
	    $(UV) run pytest $(INTEGRATION_TEST_DIR) \
	    --junit-xml=$(INTEGRATION_JUNIT_XML)

.PHONY: integration-test-fixtures
integration-test-fixtures: $(INSTALL_STAMP)  ##  List fixtures in use per integration test
	MERINO_ENV=testing $(UV) run pytest $(INTEGRATION_TEST_DIR) --fixtures-per-test

.PHONY: docker-build
docker-build:  ## Build the docker image for Merino named "app:build"
	docker build -t app:build .

.PHONY: docker-build-jobs
docker-build-jobs:  ## Build the docker image for Merino job runner named "merino-jobs:build"
	docker build --target job_runner -t merino-jobs:build .

.PHONY: load-tests
load-tests:  ##  Run local execution of (Locust) load tests
	docker compose \
      -f $(LOAD_TEST_DIR)/docker-compose.yml \
      -p merino-py-load-tests \
      up --scale locust_worker=1

.PHONY: load-tests-clean
load-tests-clean:  ##  Stop and remove containers and networks for load tests
	docker compose \
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
	MERINO_LOGGING__FORMAT=mozlog MERINO_LOGGING__LEVEL=INFO \
	$(UV) run python -m scalene merino/main.py

.PHONY: docker-compose-up
docker-compose-up:  ## Run `docker-compose up` in `./dev`
	docker compose -f dev/docker-compose.yaml up

.PHONY: docker-compose-up-daemon
docker-compose-up-daemon:  ## Run `docker-compose up -d` in `./dev`
	docker compose -f dev/docker-compose.yaml up -d

.PHONY: docker-compose-down
docker-compose-down:  ## Run `docker-compose down` in `./dev`
	docker compose -f dev/docker-compose.yaml down

.PHONY: help
help:
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | awk 'BEGIN {FS = ":.*?## "}; {printf "\033[36m%-20s\033[0m %s\n", $$1, $$2}'

.PHONY: wikipedia-indexer
wikipedia-indexer:
	$(UV) run merino-jobs $@ ${job}

.PHONY: health-check-prod
health-check-prod:  ##  Check the production suggest endpoint with some test queries
	./scripts/quic.sh prod

.PHONY: health-check-staging
health-check-staging:  ##  Check the staging suggest endpoint with some test queries
	./scripts/quic.sh staging

.PHONY: coverage-unit
coverage-unit:
	$(UV) run coverage json \
		--data-file=$(TEST_RESULTS_DIR)/.coverage.unit \
		-o $(UNIT_COVERAGE_JSON)

.PHONY: coverage-integration
coverage-integration:
	$(UV) run coverage json \
		--data-file=$(TEST_RESULTS_DIR)/.coverage.integration \
		-o $(INTEGRATION_COVERAGE_JSON)

.PHONY: nav-suggestions
nav-suggestions: $(INSTALL_STAMP)  ##  Run navigational suggestions job locally (start emulator, run job, stop emulator)
	@echo "Starting navigational suggestions workflow..."
	@docker info > /dev/null 2>&1 || (echo "❌ Docker is not running. Please start Docker and try again." && exit 1)
	@mkdir -p $(METRICS_DIR)/gcs_emulator

	@echo "Starting fake-GCS-server..."
	@docker compose -f dev/docker-compose.yaml up -d fake-gcs
	@echo "Waiting for service to be available..."
	@sleep 3
	@echo "✅ GCS emulator started successfully!"

	@echo "Running navigational suggestions job with $(SAMPLE_SIZE) domains..."
	@MONITOR_FLAG=""; \
	if [ "$(ENABLE_MONITORING)" = "true" ]; then \
		MONITOR_FLAG="--monitor"; \
		echo "System monitoring enabled"; \
	fi; \
	$(UV) run merino-jobs navigational-suggestions prepare-domain-metadata \
		--local \
		--sample-size=$(SAMPLE_SIZE) \
		--metrics-dir=$(METRICS_DIR) \
		$$MONITOR_FLAG $(NAV_OPTS) || { \
		echo "❌ Job failed - stopping emulator..."; \
		docker compose -f dev/docker-compose.yaml down fake-gcs; \
		exit 1; \
	}

	@echo "✅ Job completed successfully!"
	@echo "The results are available in $(METRICS_DIR)"

	@echo "Stopping GCS emulator..."
	@docker compose -f dev/docker-compose.yaml down fake-gcs
	@echo "✅ Workflow completed - GCS emulator stopped"
