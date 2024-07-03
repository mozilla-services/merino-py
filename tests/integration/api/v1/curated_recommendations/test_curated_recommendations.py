"""Tests the curated recommendation endpoint /api/v1/curated-recommendations"""

import asyncio
import json
from datetime import timedelta
from unittest.mock import AsyncMock

import freezegun
import pytest
from httpx import AsyncClient, Response
from pydantic import HttpUrl

from merino.curated_recommendations import (
    CorpusApiBackend,
    CuratedRecommendationsProvider,
    get_provider,
)
from merino.curated_recommendations.provider import CuratedRecommendation
from merino.main import app


@pytest.fixture()
def fixture_response_data():
    """Load mock response data for the scheduledSurface query"""
    with open("tests/data/scheduled_surface.json") as f:
        return json.load(f)


@pytest.fixture(name="corpus_http_client")
def fixture_mock_corpus_http_client(fixture_response_data) -> AsyncMock:
    """Mock curated corpus api HTTP client."""
    # Create a mock HTTP client
    mock_http_client = AsyncMock(spec=AsyncClient)

    # Mock the POST request response with the loaded json mock data
    mock_http_client.post.return_value = Response(
        status_code=200,
        json=fixture_response_data,
    )

    return mock_http_client


@pytest.fixture(name="corpus_backend")
def fixture_mock_corpus_backend(corpus_http_client: AsyncMock) -> CorpusApiBackend:
    """Mock corpus api backend."""
    # Initialize the backend with the mock HTTP client
    return CorpusApiBackend(http_client=corpus_http_client)


@pytest.fixture
def provider(corpus_backend: CorpusApiBackend) -> CuratedRecommendationsProvider:
    """Mock curated recommendations provider."""
    return CuratedRecommendationsProvider(corpus_backend=corpus_backend)


@pytest.fixture(autouse=True)
def setup_providers(provider):
    """Set up the curated recommendations provider"""
    app.dependency_overrides[get_provider] = lambda: provider


@freezegun.freeze_time("2012-01-14 03:21:34", tz_offset=0)
@pytest.mark.asyncio
async def test_curated_recommendations_locale():
    """Test the curated recommendations endpoint response is as expected."""
    async with AsyncClient(app=app, base_url="http://test") as ac:
        # expected recommendation with topic = None
        expected_recommendation = CuratedRecommendation(
            scheduledCorpusItemId="50f86ebe-3f25-41d8-bd84-53ead7bdc76e",
            url=HttpUrl("https://www.themarginalian.org/2024/05/28/passenger-pigeon/"),
            title="Thunder, Bells, and Silence: the Eclipse That Went Extinct",
            excerpt="Juneteenth isn’t the “other” Independence Day, it is THE Independence Day.",
            topic=None,
            publisher="The Marginalian",
            imageUrl=HttpUrl(
                "https://s3.us-east-1.amazonaws.com/pocket-curatedcorpusapi-prod-images/87fd6901-5bf5-4b12-8bde-24b86be79003.jpeg"
            ),
            receivedRank=1,
        )
        # Mock the endpoint
        response = await ac.post("/api/v1/curated-recommendations", json={"locale": "en-US"})
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
        actual_recommendation: CuratedRecommendation = CuratedRecommendation(**corpus_items[1])
        assert actual_recommendation == expected_recommendation


@pytest.mark.asyncio
async def test_curated_recommendations_locale_bad_request():
    """Test the curated recommendations endpoint response is 400 if locale is not provided"""
    async with AsyncClient(app=app, base_url="http://test") as ac:
        # Mock the endpoint
        response = await ac.post("/api/v1/curated-recommendations", json={"foo": "bar"})

        # Check if the response returns 400
        assert response.status_code == 400


@freezegun.freeze_time("2012-01-14 03:21:34", tz_offset=0)
@pytest.mark.asyncio
async def test_single_request_multiple_fetches(corpus_http_client):
    """Test that only a single request is made to the curated-corpus-api."""
    async with AsyncClient(app=app, base_url="http://test") as ac:

        async def fetch():
            return await ac.post("/api/v1/curated-recommendations", json={"locale": "en-US"})

        # Gather multiple fetch calls
        results = await asyncio.gather(fetch(), fetch(), fetch(), fetch(), fetch())

        # Assert that exactly one request was made to the corpus api
        corpus_http_client.post.assert_called_once()

        # Assert that the results are the same
        assert all(results[0].json() == result.json() for result in results)


@pytest.mark.asyncio
async def test_cache_returned_on_subsequent_calls(corpus_http_client, fixture_response_data):
    """Test that the cache expires, and subsequent requests return new data."""
    with freezegun.freeze_time(tick=True) as frozen_datetime:
        async with AsyncClient(app=app, base_url="http://test") as ac:

            async def fetch():
                return await ac.post("/api/v1/curated-recommendations", json={"locale": "en-US"})

            # First fetch to populate cache
            initial_response = await fetch()
            initial_data = initial_response.json()

            for item in fixture_response_data["data"]["scheduledSurface"]["items"]:
                item["corpusItem"]["title"] += " (NEW)"  # Change all the titles
            corpus_http_client.post.return_value = Response(
                status_code=200,
                json=fixture_response_data,
            )

            # Progress time to after the cache expires.
            frozen_datetime.tick(delta=CorpusApiBackend.cache_time_to_live_max)
            frozen_datetime.tick(delta=timedelta(seconds=1))

            # When the cache is expired, the first fetch may return stale data.
            await fetch()
            await asyncio.sleep(0.01)  # Allow asyncio background task to make an API request

            # Next fetch should get the new data
            new_response = await fetch()
            assert corpus_http_client.post.call_count == 2
            new_data = new_response.json()
            assert new_data["recommendedAt"] > initial_data["recommendedAt"]
            assert all("NEW" in item["title"] for item in new_data["data"])
