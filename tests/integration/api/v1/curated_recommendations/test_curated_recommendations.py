"""Tests the curated recommendation endpoint /api/v1/curated-recommendations"""

import json
from unittest.mock import AsyncMock

import freezegun
import pytest
from fastapi.testclient import TestClient
from httpx import AsyncClient, Request, Response
from pydantic import HttpUrl

from merino.curated_recommendations import (
    CorpusApiBackend,
    CuratedRecommendationsProvider,
    corpus_api_provider,
)
from merino.curated_recommendations.corpus_backends.corpus_api_backend import (
    CorpusApiGraphConfig,
)
from merino.curated_recommendations.provider import CuratedRecommendation


@pytest.fixture(name="corpus_http_client")
def fixture_mock_corpus_http_client() -> AsyncMock:
    """Mock curated corpus api HTTP client."""
    # load json mock data
    with open("tests/data/scheduled_surface.json") as f:
        scheduled_surface_data = json.load(f)

    # Create a mock HTTP client
    mock_http_client = AsyncMock(spec=AsyncClient)

    # Mock the POST request response with the loaded json mock data
    mock_http_client.post.return_value = Response(
        status_code=200,
        json=scheduled_surface_data,
        request=Request(
            method="POST",
            url=CorpusApiGraphConfig.CORPUS_API_PROD_ENDPOINT,
            headers=CorpusApiGraphConfig.HEADERS,
            json={"locale": "en-US"},
        ),
    )

    return mock_http_client


@pytest.fixture(name="corpus_backend")
def fixture_mock_corpus_backend(corpus_http_client: AsyncMock) -> CorpusApiBackend:
    """Mock corpus api backend."""
    # Initialize the backend with the mock HTTP client
    return CorpusApiBackend(http_client=corpus_http_client)


@pytest.fixture
def provider(corpus_backend):
    """Mock corpus provider."""
    return CuratedRecommendationsProvider(corpus_backend=corpus_backend)


@pytest.fixture(autouse=True)
def setup_providers(provider):
    """Set up the corpus api provider"""
    corpus_api_provider["corpus_provider"] = provider


@freezegun.freeze_time("2012-01-14 03:21:34", tz_offset=0)
@pytest.mark.asyncio
async def test_curated_recommendations_locale(client: TestClient):
    """Test the curated recommendations endpoint response is as expected."""
    # expected recommendation with topic = None
    expected_recommendation = CuratedRecommendation(
        scheduledCorpusItemId="50f86ebe-3f25-41d8-bd84-53ead7bdc76e",
        url=HttpUrl("https://www.themarginalian.org/2024/05/28/passenger-pigeon/"),
        title="Thunder, Bells, and Silence: the Eclipse That Went Extinct",
        excerpt="Juneteenth isn’t the “other” Independence Day, it is THE Independence Day.",
        topic=None,
        publisher="The Marginalian",
        imageUrl=HttpUrl(
            "https://s3.us-east-1.amazonaws.com/pocket-curatedcorpusapi-prod-images/87fd6901-5bf5-4b12-8bde-24b86be79003.jpeg"  # noqa
        ),
        receivedRank=1,
    )
    # Mock the endpoint
    response = client.post("/api/v1/curated-recommendations", json={"locale": "en-US"})
    data = response.json()

    # Check if the mock response is valid
    assert response.status_code == 200

    corpus_items = data["data"]

    # assert total of 80 items returned
    assert len(corpus_items) == 80
    # Assert all corpus_items have expected fields populated.
    assert all(item["url"] for item in corpus_items)
    assert all(item["publisher"] for item in corpus_items)
    assert all(item["imageUrl"] for item in corpus_items)

    # Assert 2nd returned recommendation has topic = None & all fields returned are expected
    actual_recommendation: CuratedRecommendation = CuratedRecommendation(
        **corpus_items[1]
    )
    assert actual_recommendation == expected_recommendation


@pytest.mark.asyncio
async def test_curated_recommendations_locale_bad_request(client: TestClient):
    """Test the curated recommendations endpoint response is 400 if locale is not provided"""
    # Mock the endpoint
    response = client.post("/api/v1/curated-recommendations", json={"foo": "bar"})

    # Check if the response returns 400
    assert response.status_code == 400
