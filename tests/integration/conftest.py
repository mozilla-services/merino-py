"""Module for test configurations for the integration test directory."""

# When the conftest plugin is loaded the following fixtures will be loaded as well.
pytest_plugins = [
    "tests.integration.fixtures.gcs",
    "tests.integration.fixtures.metrics",
]
