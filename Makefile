APP_PROJECT_DIR := apps/merino
APP_DIR := $(APP_PROJECT_DIR)/merino
TEST_DIR := $(APP_PROJECT_DIR)/tests
COMMON_PROJECT_DIR := packages/merino-common
COMMON_PACKAGE_DIR := $(COMMON_PROJECT_DIR)/merino_common
COMMON_TEST_DIR := $(COMMON_PROJECT_DIR)/tests
FLEECE_PROJECT_DIR := apps/fleece
FLEECE_PACKAGE_DIR := $(FLEECE_PROJECT_DIR)/merino_fleece
FLEECE_TEST_DIR := $(FLEECE_PROJECT_DIR)/tests
FLEECE_WORKER_MAIN := $(FLEECE_PACKAGE_DIR)/sanitize/worker/main.py
UNIT_TEST_DIR := $(TEST_DIR)/unit
INTEGRATION_TEST_DIR := $(TEST_DIR)/integration
LOAD_TEST_DIR := tools/load-tests
APP_AND_TEST_DIRS := $(APP_DIR) $(TEST_DIR) $(COMMON_PACKAGE_DIR) $(COMMON_TEST_DIR) $(FLEECE_PACKAGE_DIR) $(FLEECE_TEST_DIR) $(LOAD_TEST_DIR)
INSTALL_STAMP := .install.stamp
UV := $(shell command -v uv 2> /dev/null)
PROJECT_MANIFESTS := pyproject.toml $(APP_PROJECT_DIR)/pyproject.toml $(FLEECE_PROJECT_DIR)/pyproject.toml $(COMMON_PROJECT_DIR)/pyproject.toml $(LOAD_TEST_DIR)/pyproject.toml
TEST_PROBE := $(TEST_DIR)/utils/test_probe.py
ALL_TEST_FILES := $(shell PYTHONPATH=$(APP_PROJECT_DIR) $(UV) run python $(TEST_PROBE) 2> /dev/null)
DIRECT_TEST_FILES := $(shell PYTHONPATH=$(APP_PROJECT_DIR) $(UV) run python $(TEST_PROBE) -q 2> /dev/null)
# keyword for test selection, set it to an empty string if undefined
keyword ?=

# This will be run if no target is provided
.DEFAULT_GOAL := help

# Parameter for the Navigational Suggestions job
SAMPLE_SIZE ?= 20
METRICS_DIR ?= ./local_data
ENABLE_MONITORING ?= false
NAV_OPTS ?=

.PHONY: install
install: $(INSTALL_STAMP)  ##  Install dependencies with uv
$(INSTALL_STAMP): $(PROJECT_MANIFESTS) uv.lock
	@if [ -z $(UV) ]; then echo "uv could not be found."; exit 2; fi
	$(UV) sync --all-groups --all-packages
	touch $(INSTALL_STAMP)

.PHONY: ruff-format
ruff-format: $(INSTALL_STAMP)  ##  Run ruff format
	$(UV) run ruff format $(APP_AND_TEST_DIRS)

.PHONY: format
format: $(INSTALL_STAMP)  ##  Sort imports and reformat code
	$(UV) run ruff check --fix $(APP_AND_TEST_DIRS)
	$(UV) run ruff format $(APP_AND_TEST_DIRS)

.PHONY: dev
dev: $(INSTALL_STAMP)  ##  Run merino locally and reload automatically
	$(UV) run --package merino fastapi dev $(APP_DIR)/main.py --reload

.PHONY: dev-otel
dev-otel: $(INSTALL_STAMP)  ##  Run merino locally with OTEL auto-instrumentation (mimics k8s operator)
	OTEL_SERVICE_NAME=merino OTEL_EXPORTER_OTLP_ENDPOINT=http://localhost:4318 OTEL_EXPORTER_OTLP_PROTOCOL=http/protobuf $(UV) run --package merino opentelemetry-instrument fastapi run $(APP_DIR)/main.py --host 0.0.0.0 --port 8000

.PHONY: dev-fleece
dev-fleece: $(INSTALL_STAMP)  ##  Run fleece locally
	$(UV) run --package merino-fleece opentelemetry-instrument fastapi run $(FLEECE_PACKAGE_DIR)/main.py --host 0.0.0.0 --port 8001

.PHONY: dev-fleece-otel
dev-fleece-otel: $(INSTALL_STAMP)  ##  Run fleece locally with OTEL auto-instrumentation (mimics k8s operator)
	OTEL_SERVICE_NAME=merino OTEL_EXPORTER_OTLP_ENDPOINT=http://localhost:4318 OTEL_EXPORTER_OTLP_PROTOCOL=http/protobuf $(UV) run --package merino-fleece opentelemetry-instrument fastapi run $(FLEECE_PACKAGE_DIR)/main.py --host 0.0.0.0 --port 8001

.PHONY: run
run: $(INSTALL_STAMP)  ##  Run merino locally
	$(UV) run --package merino fastapi run $(APP_DIR)/main.py

.PHONY: dev-fleece-worker
dev-fleece-worker: $(INSTALL_STAMP)  ##  Run fleece worker locally (does not reload)
	PUBSUB_EMULATOR_HOST=localhost:8085 $(UV) run --package merino-fleece $(FLEECE_WORKER_MAIN)


.PHONY: dev-fleece-worker-otel
dev-fleece-worker-otel: $(INSTALL_STAMP)  ##  Run fleece worker locally with OTEL auto-instrumentation (mimics k8s operator)
	PUBSUB_EMULATOR_HOST=localhost:8085 OTEL_SERVICE_NAME=merino OTEL_EXPORTER_OTLP_ENDPOINT=http://localhost:4318 OTEL_EXPORTER_OTLP_PROTOCOL=http/protobuf $(UV) run --package merino-fleece opentelemetry-instrument $(UV) run --package merino-fleece $(FLEECE_WORKER_MAIN)


.PHONY: quick-test
quick-test: $(INSTALL_STAMP)  ## Run specific tests or ones that are only relevant to uncommitted source changes
	@if [ -n "$(keyword)" ]; then \
		echo "MERINO_ENV=testing $(UV) run pytest -k $(keyword) --capture=no"; \
		MERINO_ENV=testing $(UV) run pytest -k $(keyword) --capture=no; \
	elif [ -z "$(ALL_TEST_FILES)" ]; then \
		echo "No change detected, skipping."; \
		exit 0; \
	else \
		echo "MERINO_ENV=testing $(UV) run pytest $(ALL_TEST_FILES)"; \
		MERINO_ENV=testing $(UV) run pytest $(ALL_TEST_FILES); \
	fi

.PHONY: quicker-test
quicker-test: $(INSTALL_STAMP)  ## Same as "quick-test" but quicker
	@if [ -z "$(DIRECT_TEST_FILES)" ]; then \
		echo "No change detected, skipping."; \
		exit 0; \
	else \
		echo "MERINO_ENV=testing $(UV) run pytest $(DIRECT_TEST_FILES)"; \
		MERINO_ENV=testing $(UV) run pytest $(DIRECT_TEST_FILES); \
	fi

.PHONY: unit-test-fixtures
unit-test-fixtures: $(INSTALL_STAMP)  ##  List fixtures in use per unit test
	MERINO_ENV=testing $(UV) run pytest $(UNIT_TEST_DIR) --fixtures-per-test

.PHONY: integration-test-fixtures
integration-test-fixtures: $(INSTALL_STAMP)  ##  List fixtures in use per integration test
	MERINO_ENV=testing $(UV) run pytest $(INTEGRATION_TEST_DIR) --fixtures-per-test

.PHONY: docker-build-jobs
docker-build-jobs:  ## Build the docker image for Merino job runner named "merino-jobs:build"
	docker build -f $(APP_PROJECT_DIR)/Dockerfile --target job_runner -t merino-jobs:build .

.PHONY: load-tests
load-tests:  ##  Run local execution of (Locust) load tests
	docker compose \
      -f $(LOAD_TEST_DIR)/docker-compose.yml \
      -p merino-py-load-tests \
      build locust_master
	docker compose \
      -f $(LOAD_TEST_DIR)/docker-compose.yml \
      -p merino-py-load-tests \
      up --force-recreate --no-build --scale locust_worker=1

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
	$(UV) run python -m scalene $(APP_DIR)/main.py

.PHONY: docker-compose-up
docker-compose-up:  ## Run `docker-compose up` in `./dev`
	docker compose --env-file dev/.env -f dev/docker-compose.yaml up

.PHONY: docker-compose-up-daemon
docker-compose-up-daemon:  ## Run `docker-compose up -d` in `./dev`
	docker compose --env-file dev/.env -f dev/docker-compose.yaml up -d

.PHONY: docker-compose-down
docker-compose-down:  ## Run `docker-compose down` in `./dev`
	docker compose  --env-file dev/.env -f dev/docker-compose.yaml down

# Use if you want to e.g. wipe elasticsearch indices and data
.PHONY: docker-compose-down-v
docker-compose-down-v:  ## Run `docker-compose down` in `./dev` and remove volumes
	docker compose  --env-file dev/.env -f dev/docker-compose.yaml down -v

.PHONY: help
help:
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | awk 'BEGIN {FS = ":.*?## "}; {printf "\033[36m%-20s\033[0m %s\n", $$1, $$2}'

.PHONY: wikipedia-indexer
wikipedia-indexer:
	$(UV) run --package merino merino-jobs $@ ${job}

.PHONY: health-check-prod
health-check-prod:  ##  Check the production suggest endpoint with some test queries
	./scripts/quic.sh prod

.PHONY: health-check-staging
health-check-staging:  ##  Check the staging suggest endpoint with some test queries
	./scripts/quic.sh staging

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
	$(UV) run --package merino merino-jobs navigational-suggestions prepare-domain-metadata \
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
