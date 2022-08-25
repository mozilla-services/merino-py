APP_DIR := merino
TEST_DIR := tests
APP_TEST_DIR := $(APP_DIR) $(TEST_DIR)
INSTALL_STAMP := .install.stamp
POETRY := $(shell command -v poetry 2> /dev/null)

.PHONEY: dev format lint test run

install: $(INSTALL_STAMP)
$(INSTALL_STAMP): pyproject.toml poetry.lock
	@if [ -z $(POETRY) ]; then echo "Poetry could not be found. See https://python-poetry.org/docs/"; exit 2; fi
	$(POETRY) install
	touch $(INSTALL_STAMP)

lint: $(INSTALL_STAMP)
	$(POETRY) run isort --check-only $(APP_TEST_DIR)
	$(POETRY) run black --quiet --diff --check merino $(APP_TEST_DIR)
	$(POETRY) run flake8 $(APP_TEST_DIR)
	$(POETRY) run bandit --quiet -r $(APP_TEST_DIR) -c "pyproject.toml"

format: $(INSTALL_STAMP)
	$(POETRY) run isort $(APP_TEST_DIR)
	$(POETRY) run black $(APP_TEST_DIR)

test: $(INSTALL_STAMP)
	$(POETRY) run pytest -v $(TEST_DIR) --cov $(APP_DIR)

dev: $(INSTALL_STAMP)
	$(POETRY) run uvicorn $(APP_DIR).main:app --reload

run: $(INSTALL_STAMP)
	$(POETRY) run uvicorn $(APP_DIR).main:app

contract-test:
	docker-compose -f test-engineering/contract-tests/docker-compose.yml -p merino-py-contract-tests up --abort-on-container-exit --build

contract-test-clean:
	docker-compose -f test-engineering/contract-tests/docker-compose.yml -p merino-py-contract-tests down
