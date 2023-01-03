# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

"""Module for test configurations for the unit test directory."""
import os

import pytest

from merino.middleware.geolocation import Location
from merino.providers.base import SuggestionRequest
from tests.unit.types import SuggestionRequestFixture


@pytest.fixture(scope="session", name="srequest")
def fixture_srequest() -> SuggestionRequestFixture:
    """Return a function that will create a SuggestionRequest object with a given
    `query`
    """

    def srequest(query: str) -> SuggestionRequest:
        """Create a SuggestionRequest object with a given `query`"""
        return SuggestionRequest(query=query, geolocation=Location())

    return srequest


@pytest.fixture
def project_root() -> str:
    """Define the project root of merino for testing the reading of
    the .git/refs/heads file that contains the SHA-1 hash. This is
    passed to Sentry for the release tag.
    """
    return os.path.dirname(os.path.abspath(__name__))
