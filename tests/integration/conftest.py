"""Module for test configurations for the integration test directory."""

# When the conftest plugin is loaded the following fixtures will be loaded as well.
pytest_plugins = [
    "tests.integration.fixtures.gcs",
    "tests.integration.fixtures.metrics",
    "tests.integration.fixtures.app_client",
    "tests.integration.fixtures.manifest",
    "tests.integration.api.v1.curated_recommendations.corpus_backends.fixtures",
]
