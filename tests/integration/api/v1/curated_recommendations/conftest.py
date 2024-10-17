"""Module for test configurations for the curated-recommendations integration tests."""

# When the conftest plugin is loaded the following fixtures will be loaded as well.
pytest_plugins = [
    "tests.integration.api.v1.curated_recommendations.corpus_backends.fixtures",
]
