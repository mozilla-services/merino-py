# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

"""Fixtures for navigational_suggestions tests."""

from unittest.mock import AsyncMock

import pytest

# Avoid a circular import error that happens when a single test is run:
# pytest tests/integration/jobs/navigational_suggestions/test_domain_metadata_extractor.py
# E   ImportError: cannot import name 'DOMAIN_MAPPING' from partially initialized module
# 'merino.jobs.utils.domain_category_mapping' (most likely due to a circular import)
import sys, types
_stub = types.ModuleType("merino.jobs.utils.domain_category_mapping")
_stub.DOMAIN_MAPPING = {}
sys.modules["merino.jobs.utils.domain_category_mapping"] = _stub

from merino.jobs.navigational_suggestions.domain_metadata_extractor import Scraper


@pytest.fixture
def mock_scraper_context():
    """Fixture that provides a mock Scraper context manager.

    Returns a tuple containing:
    1. The mock Scraper class to patch with
    2. The shared scraper instance (accessible for modifying behavior)
    """
    # Create shared instance that all mocks will reference
    shared_scraper = AsyncMock(spec=Scraper)
    shared_scraper.open.return_value = "https://example.com"
    shared_scraper.scrape_title.return_value = "Example Website"

    # Create a context manager mock that will return our shared scraper
    class MockScraperContextManager:
        def __enter__(self):
            return shared_scraper

        def __exit__(self, exc_type, exc_val, exc_tb):
            return False

    # Create a mock class for Scraper that returns our context manager
    class MockScraper:
        def __new__(cls, *args, **kwargs):
            return MockScraperContextManager()

    return MockScraper, shared_scraper
