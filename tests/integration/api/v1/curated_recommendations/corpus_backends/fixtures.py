"""Pytest fixtures for the Corpus API backend"""

import json
from unittest.mock import AsyncMock

import pytest
from httpx import AsyncClient, Request, Response

from merino.curated_recommendations.corpus_backends.corpus_api_backend import (
    CorpusApiGraphConfig,
    CorpusApiBackend,
)
from merino.metrics import get_metrics_client


@pytest.fixture()
def fixture_response_data():
    """Load mock response data for the scheduledSurface query"""
    with open("tests/data/scheduled_surface.json") as f:
        return json.load(f)


# This fixture is used in tests where recs order is important to check &
# keeping the list short is easier to manipulate.
@pytest.fixture()
def fixture_response_data_short():
    """Load mock response data (shortened) for the scheduledSurface query"""
    with open("tests/data/scheduled_surface_short.json") as f:
        return json.load(f)


@pytest.fixture()
def fixture_graphql_200ok_with_error_response():
    """Load mock response data for a GraphQL error response"""
    with open("tests/data/graphql_error.json") as f:
        return json.load(f)


@pytest.fixture()
def fixture_request_data() -> Request:
    """Load mock response data for the scheduledSurface query"""
    graph_config = CorpusApiGraphConfig()

    return Request(
        method="POST",
        url=graph_config.endpoint,
        headers=graph_config.headers,
        json={"locale": "en-US"},
    )


@pytest.fixture()
def corpus_http_client(fixture_response_data, fixture_request_data) -> AsyncMock:
    """Mock curated corpus api HTTP client."""
    # Create a mock HTTP client
    mock_http_client = AsyncMock(spec=AsyncClient)
    # Mock the POST request response with the loaded json mock data
    mock_http_client.post.return_value = Response(
        status_code=200,
        json=fixture_response_data,
        request=fixture_request_data,
    )

    return mock_http_client


@pytest.fixture()
def corpus_backend(corpus_http_client: AsyncMock) -> CorpusApiBackend:
    """Mock corpus api backend."""
    # Initialize the backend with the mock HTTP client
    return CorpusApiBackend(
        http_client=corpus_http_client,
        graph_config=CorpusApiGraphConfig(),
        metrics_client=get_metrics_client(),
    )
