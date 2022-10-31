from typing import Callable

import pytest

from merino.middleware.geolocation import Location
from merino.providers.base import SuggestionRequest

SuggestionRequestFixture = Callable[[str], SuggestionRequest]


@pytest.fixture(scope="session", name="srequest")
def fixture_suggestion_request() -> SuggestionRequestFixture:
    """
    Return a function that will create a SuggestionRequest object with a given `query`
    """

    def srequest(query: str) -> SuggestionRequest:
        """
        Create a SuggestionRequest object with a given `query`
        """
        return SuggestionRequest(query=query, geolocation=Location())

    return srequest
