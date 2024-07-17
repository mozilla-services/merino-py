"""Tests the curated recommendation endpoint /api/v1/curated-recommendations"""

import asyncio
import json
from datetime import timedelta, datetime
from unittest.mock import AsyncMock

import aiodogstatsd
import freezegun
import pytest
from httpx import AsyncClient, Request, Response, HTTPStatusError
from pydantic import HttpUrl
from pytest_mock import MockerFixture

from merino.curated_recommendations import (
    CorpusApiBackend,
    CuratedRecommendationsProvider,
    get_provider,
)
from merino.curated_recommendations.corpus_backends.corpus_api_backend import CorpusApiGraphConfig
from merino.curated_recommendations.corpus_backends.protocol import Topic
from merino.curated_recommendations.provider import CuratedRecommendation
from merino.main import app
from merino.metrics import get_metrics_client


@pytest.fixture()
def fixture_response_data():
    """Load mock response data for the scheduledSurface query"""
    with open("tests/data/scheduled_surface.json") as f:
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


@pytest.fixture(name="corpus_http_client")
def fixture_mock_corpus_http_client(fixture_response_data, fixture_request_data) -> AsyncMock:
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


@pytest.fixture(name="corpus_backend")
def fixture_mock_corpus_backend(corpus_http_client: AsyncMock) -> CorpusApiBackend:
    """Mock corpus api backend."""
    # Initialize the backend with the mock HTTP client
    return CorpusApiBackend(
        http_client=corpus_http_client,
        graph_config=CorpusApiGraphConfig(),
        metrics_client=get_metrics_client(),
    )


@pytest.fixture
def provider(corpus_backend: CorpusApiBackend) -> CuratedRecommendationsProvider:
    """Mock curated recommendations provider."""
    return CuratedRecommendationsProvider(corpus_backend=corpus_backend)


@pytest.fixture(autouse=True)
def setup_providers(provider):
    """Set up the curated recommendations provider"""
    app.dependency_overrides[get_provider] = lambda: provider


async def fetch_en_us(client: AsyncClient) -> Response:
    """Make a curated recommendations request with en-US locale"""
    return await client.post("/api/v1/curated-recommendations", json={"locale": "en-US"})


@freezegun.freeze_time("2012-01-14 03:21:34", tz_offset=0)
@pytest.mark.asyncio
async def test_curated_recommendations():
    """Test the curated recommendations endpoint response is as expected."""
    async with AsyncClient(app=app, base_url="http://test") as ac:
        # expected recommendation with topic = None
        expected_recommendation = CuratedRecommendation(
            scheduledCorpusItemId="50f86ebe-3f25-41d8-bd84-53ead7bdc76e",
            url=HttpUrl(
                "https://www.themarginalian.org/2024/05/28/passenger-pigeon/?utm_source=pocket-newtab-en-us"
            ),
            title="Thunder, Bells, and Silence: the Eclipse That Went Extinct",
            excerpt="Juneteenth isn’t the “other” Independence Day, it is THE Independence Day.",
            topic=Topic.CAREER,
            publisher="The Marginalian",
            imageUrl=HttpUrl(
                "https://s3.us-east-1.amazonaws.com/pocket-curatedcorpusapi-prod-images/87fd6901-5bf5-4b12-8bde-24b86be79003.jpeg"
            ),
            receivedRank=1,
        )
        # Mock the endpoint
        response = await fetch_en_us(ac)
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
        actual_recommendation = CuratedRecommendation(**corpus_items[1])
        assert actual_recommendation == expected_recommendation


@freezegun.freeze_time("2012-01-14 03:25:34", tz_offset=0)
@pytest.mark.asyncio
async def test_curated_recommendations_utm_source():
    """Test the curated recommendations endpoint returns urls with correct(new) utm_source"""
    async with AsyncClient(app=app, base_url="http://test") as ac:
        # expected recommendation with new utm_source
        expected_recommendation = CuratedRecommendation(
            scheduledCorpusItemId="1452b7ea-7ba9-4da9-ba39-ab44e8147d5e",
            url=HttpUrl(
                "https://getpocket.com/explore/item/other-countries-have-social-safety-nets-the-u-s-has-women"
                "?utm_source=pocket-newtab-en-us"
            ),
            title="Other Countries Have Social Safety Nets. The U.S. Has Women.",
            excerpt="Anne Helen Petersen and Jessica Calarco discuss how mothers are experiencing and responding to "
                    "pandemic-related disruptions in their normal routines.",
            topic=Topic.PARENTING,
            publisher="Culture Study",
            imageUrl=HttpUrl(
                "https://s3.amazonaws.com/pocket-curatedcorpusapi-prod-images/3a4a6ed6-a1df-497d-8d31-f777534806ac.jpeg"
            ),
            receivedRank=2,
        )
        # Mock the endpoint
        response = await fetch_en_us(ac)
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
        actual_recommendation: CuratedRecommendation = CuratedRecommendation(**corpus_items[2])
        assert actual_recommendation == expected_recommendation


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "locale",
    [
        "fr",
        "fr-FR",
        "es",
        "es-ES",
        "it",
        "it-IT",
        "en",
        "en-CA",
        "en-GB",
        "en-US",
        "de",
        "de-DE",
        "de-AT",
        "de-CH",
    ],
)
async def test_curated_recommendations_locales(locale):
    """Test the curated recommendations endpoint accepts valid locales."""
    async with AsyncClient(app=app, base_url="http://test") as ac:
        response = await ac.post("/api/v1/curated-recommendations", json={"locale": locale})
        assert response.status_code == 200, f"{locale} resulted in {response.status_code}"


class TestCuratedRecommendationsRequestParameters:
    """Test request body parameters for the curated-recommendations endpoint"""

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        "locale",
        [
            "fr",
            "fr-FR",
            "es",
            "es-ES",
            "it",
            "it-IT",
            "en",
            "en-CA",
            "en-GB",
            "en-US",
            "de",
            "de-DE",
            "de-AT",
            "de-CH",
        ],
    )
    async def test_curated_recommendations_locales(self, locale):
        """Test the curated recommendations endpoint accepts valid locales."""
        async with AsyncClient(app=app, base_url="http://test") as ac:
            response = await ac.post("/api/v1/curated-recommendations", json={"locale": locale})
            assert response.status_code == 200, f"{locale} resulted in {response.status_code}"

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        "locale",
        [
            None,
            "",
            "invalid-locale",
            "en-XX",
            "de-XYZ",
            "es_123",
        ],
    )
    async def test_curated_recommendations_locales_failure(self, locale):
        """Test the curated recommendations endpoint rejects invalid locales."""
        async with AsyncClient(app=app, base_url="http://test") as ac:
            response = await ac.post("/api/v1/curated-recommendations", json={"locale": locale})
            assert response.status_code == 400

    @pytest.mark.asyncio
    @pytest.mark.parametrize("count", [10, 50, 100])
    async def test_curated_recommendations_count(self, count):
        """Test the curated recommendations endpoint accepts valid count."""
        async with AsyncClient(app=app, base_url="http://test") as ac:
            response = await ac.post(
                "/api/v1/curated-recommendations", json={"locale": "en-US", "count": count}
            )
            assert response.status_code == 200

    @pytest.mark.asyncio
    @pytest.mark.parametrize("count", [None, 100.5])
    async def test_curated_recommendations_count_failure(self, count):
        """Test the curated recommendations endpoint rejects invalid count."""
        async with AsyncClient(app=app, base_url="http://test") as ac:
            response = await ac.post(
                "/api/v1/curated-recommendations", json={"locale": "en-US", "count": count}
            )
            assert response.status_code == 400

    @pytest.mark.asyncio
    @pytest.mark.parametrize("region", [None, "US", "DE", "SXM"])
    async def test_curated_recommendations_region(self, region):
        """Test the curated recommendations endpoint accepts valid region."""
        async with AsyncClient(app=app, base_url="http://test") as ac:
            response = await ac.post(
                "/api/v1/curated-recommendations", json={"locale": "en-US", "region": region}
            )
            assert response.status_code == 200

    @pytest.mark.asyncio
    @pytest.mark.parametrize("region", [675])
    async def test_curated_recommendations_region_failure(self, region):
        """Test the curated recommendations endpoint rejects invalid region."""
        async with AsyncClient(app=app, base_url="http://test") as ac:
            response = await ac.post(
                "/api/v1/curated-recommendations", json={"locale": "en-US", "region": region}
            )
            assert response.status_code == 400

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        "topics",
        [
            None,
            [],
            # Each topic by itself is accepted.
            ["arts"],
            ["education"],
            ["hobbies"],
            ["society-parenting"],
            ["business"],
            ["education-science"],
            ["finance"],
            ["food"],
            ["government"],
            ["health"],
            ["society"],
            ["sports"],
            ["tech"],
            ["travel"],
            # Multiple topics
            ["tech", "travel"],
            ["arts", "education", "hobbies", "society-parenting"],
            [
                "arts",
                "education",
                "hobbies",
                "society-parenting",
                "business",
                "education-science",
                "finance",
                "food",
                "government",
                "health",
                "society",
                "sports",
                "tech",
                "travel",
            ],
        ],
    )
    async def test_curated_recommendations_topics(self, topics):
        """Test the curated recommendations endpoint accepts valid topics."""
        async with AsyncClient(app=app, base_url="http://test") as ac:
            response = await ac.post(
                "/api/v1/curated-recommendations", json={"locale": "en-US", "topics": topics}
            )
            assert response.status_code == 200, f"{topics} resulted in {response.status_code}"

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        "topics",
        [
            "arts",  # Must be wrapped in a list
            ["not-a-valid-topic"],
        ],
    )
    async def test_curated_recommendations_topics_failure(self, topics):
        """Test the curated recommendations endpoint rejects invalid topics."""
        async with AsyncClient(app=app, base_url="http://test") as ac:
            response = await ac.post(
                "/api/v1/curated-recommendations", json={"locale": "en-US", "topics": topics}
            )
            assert response.status_code == 400

    @pytest.mark.asyncio
    async def test_curated_recommendations_locale_bad_request(self):
        """Test the curated recommendations endpoint response is 400 if locale is not provided"""
        async with AsyncClient(app=app, base_url="http://test") as ac:
            # Mock the endpoint
            response = await ac.post("/api/v1/curated-recommendations", json={"foo": "bar"})

            # Check if the response returns 400
            assert response.status_code == 400


class TestCorpusApiCaching:
    """Tests covering the caching behavior of the Corpus backend"""

    @freezegun.freeze_time("2012-01-14 03:21:34", tz_offset=0)
    @pytest.mark.asyncio
    async def test_single_request_multiple_fetches(self, corpus_http_client):
        """Test that only a single request is made to the curated-corpus-api."""
        async with AsyncClient(app=app, base_url="http://test") as ac:
            # Gather multiple fetch calls
            results = await asyncio.gather(fetch_en_us(ac), fetch_en_us(ac), fetch_en_us(ac))

            # Assert that exactly one request was made to the corpus api
            corpus_http_client.post.assert_called_once()

            # Assert that the results are the same
            assert all(results[0].json() == result.json() for result in results)

    @freezegun.freeze_time("2012-01-14 00:00:00", tick=True, tz_offset=0)
    @pytest.mark.asyncio
    async def test_single_request_multiple_failed_fetches(
            self, corpus_http_client, fixture_request_data, fixture_response_data, caplog
    ):
        """Test that only a few requests are made to the curated-corpus-api when it is down."""
        async with AsyncClient(app=app, base_url="http://test") as ac:
            start_time = datetime.now()

            def temporary_downtime(*args, **kwargs):
                # Simulate the backend being unavailable for 0.2 seconds.
                if datetime.now() < start_time + timedelta(seconds=0.2):
                    return Response(status_code=503, request=fixture_request_data)
                else:
                    return Response(
                        status_code=200,
                        json=fixture_response_data,
                        request=fixture_request_data,
                    )

            corpus_http_client.post = AsyncMock(side_effect=temporary_downtime)

            # Hit the endpoint until a 200 response is received.
            while datetime.now() < start_time + timedelta(seconds=1):
                try:
                    result = await fetch_en_us(ac)
                    if result.status_code == 200:
                        break
                except HTTPStatusError:
                    pass

            assert result.status_code == 200

            # Assert that we did not send a lot of requests to the backend
            # call_count is 400+ for me locally when CorpusApiBackend._backoff_time is changed to 0.
            print("call_count", corpus_http_client.post.call_count)
            assert corpus_http_client.post.call_count == 2

            # Assert that a warning was logged with a descriptive message.
            warnings = [r for r in caplog.records if r.levelname == "WARNING"]
            assert len(warnings) == 1
            assert (
                       "Retrying CorpusApiBackend._fetch_from_backend once after "
                       "Server error '503 Service Unavailable'"
                   ) in warnings[0].message

    @pytest.mark.asyncio
    async def test_cache_returned_on_subsequent_calls(
            self, corpus_http_client, fixture_response_data, fixture_request_data
    ):
        """Test that the cache expires, and subsequent requests return new data."""
        with freezegun.freeze_time(tick=True) as frozen_datetime:
            async with AsyncClient(app=app, base_url="http://test") as ac:
                # First fetch to populate cache
                initial_response = await fetch_en_us(ac)
                initial_data = initial_response.json()

                for item in fixture_response_data["data"]["scheduledSurface"]["items"]:
                    item["corpusItem"]["title"] += " (NEW)"  # Change all the titles
                corpus_http_client.post.return_value = Response(
                    status_code=200,
                    json=fixture_response_data,
                    request=fixture_request_data,
                )

                # Progress time to after the cache expires.
                frozen_datetime.tick(delta=CorpusApiBackend.cache_time_to_live_max)
                frozen_datetime.tick(delta=timedelta(seconds=1))

                # When the cache is expired, the first fetch may return stale data.
                await fetch_en_us(ac)
                await asyncio.sleep(0.01)  # Allow asyncio background task to make an API request

                # Next fetch should get the new data
                new_response = await fetch_en_us(ac)
                assert corpus_http_client.post.call_count == 2
                new_data = new_response.json()
                assert new_data["recommendedAt"] > initial_data["recommendedAt"]
                assert all("NEW" in item["title"] for item in new_data["data"])


class TestCuratedRecommendationsMetrics:
    """Tests that the right metrics are recorded for curated-recommendations requests"""

    @pytest.mark.asyncio
    async def test_metrics_cache_miss(self, mocker: MockerFixture) -> None:
        """Test that metrics are recorded when corpus api items are not yet cached."""
        report = mocker.patch.object(aiodogstatsd.Client, "_report")

        async with AsyncClient(app=app, base_url="http://test") as ac:
            await fetch_en_us(ac)

            # TODO: Remove reliance on internal details of aiodogstatsd
            metric_keys: list[str] = [call.args[0] for call in report.call_args_list]
            assert metric_keys == [
                "corpus_api.request.timing",
                "corpus_api.request.status_codes.200",
                "post.api.v1.curated-recommendations.timing",
                "post.api.v1.curated-recommendations.status_codes.200",
                "response.status_codes.200",
            ]

    @pytest.mark.asyncio
    async def test_metrics_cache_hit(self, mocker: MockerFixture) -> None:
        """Test that metrics are recorded when corpus api items are cached."""
        async with AsyncClient(app=app, base_url="http://test") as ac:
            # The first call populates the cache.
            await fetch_en_us(ac)

            # This test covers only the metrics emitted from the following cached call.
            report = mocker.patch.object(aiodogstatsd.Client, "_report")
            await fetch_en_us(ac)

            # TODO: Remove reliance on internal details of aiodogstatsd
            metric_keys: list[str] = [call.args[0] for call in report.call_args_list]
            assert metric_keys == [
                "post.api.v1.curated-recommendations.timing",
                "post.api.v1.curated-recommendations.status_codes.200",
                "response.status_codes.200",
            ]

    @pytest.mark.asyncio
    async def test_metrics_corpus_api_error(
            self, mocker: MockerFixture, corpus_http_client, fixture_request_data
    ) -> None:
        """Test that metrics are recorded when the curated-corpus-api returns a 500 error"""
        report = mocker.patch.object(aiodogstatsd.Client, "_report")

        async with AsyncClient(app=app, base_url="http://test") as ac:
            corpus_http_client.post.return_value = Response(
                status_code=500,
                request=fixture_request_data,
            )

            with pytest.raises(HTTPStatusError):
                await fetch_en_us(ac)

            # TODO: Remove reliance on internal details of aiodogstatsd
            metric_keys: list[str] = [call.args[0] for call in report.call_args_list]
            assert metric_keys == [
                "corpus_api.request.timing",
                "corpus_api.request.status_codes.500",
                "corpus_api.request.timing",
                "corpus_api.request.status_codes.500",
                "post.api.v1.curated-recommendations.timing",
                "post.api.v1.curated-recommendations.status_codes.500",
                "response.status_codes.500",
            ]
