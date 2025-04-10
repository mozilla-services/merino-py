"""Pytest fixtures for the Corpus API backend"""

import json
from unittest.mock import AsyncMock

import pytest
from httpx import AsyncClient, Request, Response

from merino.curated_recommendations.corpus_backends.utils import CorpusApiGraphConfig
from merino.curated_recommendations.corpus_backends.scheduled_surface_backend import (
    ScheduledSurfaceBackend,
)
from merino.curated_recommendations.corpus_backends.sections_backend import (
    SectionsBackend,
)
from merino.utils.metrics import get_metrics_client


@pytest.fixture()
def scheduled_surface_response_data():
    """Load mock response data for the scheduledSurface query."""
    with open("tests/data/scheduled_surface.json") as f:
        return json.load(f)


@pytest.fixture()
def scheduled_surface_response_data_short():
    """Load mock response data (shortened) for the scheduledSurface query."""
    with open("tests/data/scheduled_surface_short.json") as f:
        return json.load(f)


@pytest.fixture()
def sections_response_data():
    """Load mock response data for the getSections query."""
    with open("tests/data/sections.json") as f:
        return json.load(f)


@pytest.fixture()
def fixture_graphql_200ok_with_error_response():
    """Load mock response data for a GraphQL error response."""
    with open("tests/data/graphql_error.json") as f:
        return json.load(f)


@pytest.fixture()
def fixture_request_data() -> Request:
    """Load mock request data for the corpus API backend."""
    graph_config = CorpusApiGraphConfig()
    return Request(
        method="POST",
        url=graph_config.endpoint,
        headers=graph_config.headers,
        json={"locale": "en-US"},
    )


@pytest.fixture()
def scheduled_surface_http_client(
    scheduled_surface_response_data, fixture_request_data
) -> AsyncMock:
    """Mock HTTP client for the scheduled corpus API backend."""
    mock_http_client = AsyncMock(spec=AsyncClient)
    mock_http_client.post.return_value = Response(
        status_code=200,
        json=scheduled_surface_response_data,
        request=fixture_request_data,
    )
    return mock_http_client


@pytest.fixture()
def sections_http_client(sections_response_data, fixture_request_data) -> AsyncMock:
    """Mock HTTP client for the sections corpus API backend."""
    mock_http_client = AsyncMock(spec=AsyncClient)
    mock_http_client.post.return_value = Response(
        status_code=200,
        json=sections_response_data,
        request=fixture_request_data,
    )
    return mock_http_client


@pytest.fixture()
def scheduled_surface_backend(
    scheduled_surface_http_client: AsyncMock, manifest_provider
) -> ScheduledSurfaceBackend:
    """Create a mock ScheduledCorpusBackend instance with the corpus HTTP client."""
    return ScheduledSurfaceBackend(
        http_client=scheduled_surface_http_client,
        graph_config=CorpusApiGraphConfig(),
        metrics_client=get_metrics_client(),
        manifest_provider=manifest_provider,
    )


@pytest.fixture()
def sections_backend(sections_http_client: AsyncMock, manifest_provider) -> SectionsBackend:
    """Create a mock SectionsCorpusBackend instance with the sections HTTP client."""
    return SectionsBackend(
        http_client=sections_http_client,
        graph_config=CorpusApiGraphConfig(),
        metrics_client=get_metrics_client(),
        manifest_provider=manifest_provider,
    )
