"""Tests the curated recommendation endpoint /api/v1/curated-recommendations"""

import asyncio
from collections import Counter
from datetime import timedelta, datetime
from unittest.mock import AsyncMock

import aiodogstatsd
import freezegun
import numpy as np
import pytest
from httpx import AsyncClient, Response, HTTPStatusError
from pydantic import HttpUrl
from pytest_mock import MockerFixture
from scipy.stats import linregress

from merino.config import settings
from merino.curated_recommendations import (
    CorpusApiBackend,
    CuratedRecommendationsProvider,
    get_provider,
    ConstantPrior,
    ExtendedExpirationCorpusBackend,
)
from merino.curated_recommendations.corpus_backends.protocol import Topic, ScheduledSurfaceId
from merino.curated_recommendations.engagement_backends.protocol import (
    EngagementBackend,
    Engagement,
)
from merino.curated_recommendations.fakespot_backend.protocol import (
    FAKESPOT_DEFAULT_CATEGORY_NAME,
    FAKESPOT_FOOTER_COPY,
    FAKESPOT_HEADER_COPY,
    FAKESPOT_CTA_COPY,
    FAKESPOT_CTA_URL,
    FakespotBackend,
    FakespotFeed,
)
from merino.curated_recommendations.localization import LOCALIZED_SECTION_TITLES
from merino.curated_recommendations.prior_backends.protocol import PriorBackend
from merino.curated_recommendations.protocol import (
    ExperimentName,
    Layout,
    CuratedRecommendationsFeed,
    Section,
)
from merino.curated_recommendations.protocol import CuratedRecommendation
from merino.main import app
from tests.integration.api.conftest import fakespot_feed


class MockEngagementBackend(EngagementBackend):
    """Mock class implementing the protocol for EngagementBackend."""

    def get(self, scheduled_corpus_item_id: str, region: str | None = None) -> Engagement | None:
        """Return random click and impression counts based on the scheduled corpus id and region."""
        seed_input = "_".join(filter(None, [scheduled_corpus_item_id, region]))
        rng = np.random.default_rng(seed=int.from_bytes(seed_input.encode()))

        if scheduled_corpus_item_id == "50f86ebe-3f25-41d8-bd84-53ead7bdc76e":
            # Give the first item 100% click-through rate to put it on top with high certainty.
            return Engagement(
                scheduled_corpus_item_id=scheduled_corpus_item_id,
                click_count=1000000,
                impression_count=1000000,
            )
        elif rng.random() < 0.5:
            # 50% chance of no engagement data being available.
            return None
        else:
            # Uniformly random clicks (10k-50k) and impressions (1M-5M)
            return Engagement(
                scheduled_corpus_item_id=scheduled_corpus_item_id,
                click_count=rng.integers(10_000, 50_000),
                impression_count=rng.integers(1_000_000, 5_000_000),
            )

    def initialize(self) -> None:
        """Mock class must implement this method, but no initialization needs to happen."""
        pass


@pytest.mark.usefixtures("fakespot_feed")
class MockFakespotBackend(FakespotBackend):
    """Mock class implementing the protocol for FakespotBackend."""

    def get(self, key: str) -> FakespotFeed | None:
        """Return fakespot feed from mock JSON file."""
        return fakespot_feed()

    def initialize(self) -> None:
        """Mock class must implement this method, but no initialization needs to happen."""
        pass


@pytest.fixture
def engagement_backend():
    """Fixture for the MockEngagementBackend"""
    return MockEngagementBackend()


@pytest.fixture(name="prior_backend")
def constant_prior_backend() -> PriorBackend:
    """Mock constant prior backend."""
    return ConstantPrior()


@pytest.fixture(name="fakespot_backend")
def fakespot_backend():
    """Fixture for the FakespotBackend"""
    return MockFakespotBackend()


@pytest.fixture()
def extended_expiration_corpus_backend(
    corpus_backend: CorpusApiBackend, engagement_backend: EngagementBackend
) -> ExtendedExpirationCorpusBackend:
    """Mock extended expiration corpus api backend."""
    return ExtendedExpirationCorpusBackend(
        backend=corpus_backend, engagement_backend=engagement_backend
    )


@pytest.fixture(name="corpus_provider")
def provider(
    corpus_backend: CorpusApiBackend,
    extended_expiration_corpus_backend: ExtendedExpirationCorpusBackend,
    engagement_backend: EngagementBackend,
    prior_backend: PriorBackend,
    fakespot_backend: FakespotBackend,
) -> CuratedRecommendationsProvider:
    """Mock curated recommendations provider."""
    return CuratedRecommendationsProvider(
        corpus_backend=corpus_backend,
        extended_expiration_corpus_backend=extended_expiration_corpus_backend,
        engagement_backend=engagement_backend,
        prior_backend=prior_backend,
        fakespot_backend=fakespot_backend,
    )


@pytest.fixture(autouse=True)
def setup_providers(corpus_provider):
    """Set up the curated recommendations provider"""
    app.dependency_overrides[get_provider] = lambda: corpus_provider


async def fetch_en_us(client: AsyncClient) -> Response:
    """Make a curated recommendations request with en-US locale"""
    return await client.post(
        "/api/v1/curated-recommendations", json={"locale": "en-US", "topics": [Topic.FOOD]}
    )


async def fetch_en_us_with_need_to_know(client: AsyncClient) -> Response:
    """Make a curated recommendations request with en-US locale and feeds=["need_to_know"]"""
    return await client.post(
        "/api/v1/curated-recommendations", json={"locale": "en-US", "feeds": ["need_to_know"]}
    )


async def fetch_en_us_with_fakespot(client: AsyncClient) -> Response:
    """Make a curated recommendations request with en-US locale and feeds=["fakespot"]"""
    return await client.post(
        "/api/v1/curated-recommendations", json={"locale": "en-US", "feeds": ["fakespot"]}
    )


def get_max_total_retry_duration() -> float:
    """Compute the maximum retry duration for the exponential backoff and jitter strategy."""
    initial = settings.curated_recommendations.corpus_api.retry_wait_initial_seconds
    jitter = settings.curated_recommendations.corpus_api.retry_wait_jitter_seconds
    retry_count = settings.curated_recommendations.corpus_api.retry_count

    return float(initial * (2**retry_count - 1) + retry_count * jitter)


@freezegun.freeze_time("2012-01-14 03:21:34", tz_offset=0)
@pytest.mark.asyncio
@pytest.mark.parametrize(
    "repeat",  # See thompson_sampling config in testing.toml for how to repeat this test.
    range(settings.curated_recommendations.rankers.thompson_sampling.test_repeat_count),
)
async def test_curated_recommendations(repeat):
    """Test the curated recommendations endpoint response is as expected."""
    async with AsyncClient(app=app, base_url="http://test") as ac:
        # expected recommendation with topic = None
        expected_recommendation = CuratedRecommendation(
            scheduledCorpusItemId="de614b6b-6df6-470a-97f2-30344c56c1b3",
            corpusItemId="4095b364-02ff-402c-b58a-792a067fccf2",
            url=HttpUrl(
                "https://getpocket.com/explore/item/milk-powder-is-the-key-to-better-cookies-brownies-and-cakes?utm_source=firefox-newtab-en-us"
            ),
            title="Milk Powder Is the Key to Better Cookies, Brownies, and Cakes",
            excerpt="Consider this pantry staple your secret ingredient for making more flavorful desserts.",
            topic=Topic.FOOD,
            publisher="Epicurious",
            isTimeSensitive=False,
            imageUrl="https://s3.us-east-1.amazonaws.com/pocket-curatedcorpusapi-prod-images/40e30ce2-a298-4b34-ab58-8f0f3910ee39.jpeg",
            receivedRank=0,
            tileId=301455520317019,
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
        assert all(item["tileId"] for item in corpus_items)

        # Assert that receivedRank equals 0, 1, 2, ...
        for i, item in enumerate(corpus_items):
            assert item["receivedRank"] == i

        # The expected recommendation has 100% CTR, and is always present in the response.
        # In 97% of cases it's the first recommendation, but due to the random nature of
        # Thompson sampling this is not always the case.
        assert any(
            CuratedRecommendation(**item)
            == expected_recommendation.model_copy(update={"receivedRank": i})
            for i, item in enumerate(corpus_items)
        )


@freezegun.freeze_time("2012-01-14 03:25:34", tz_offset=0)
@pytest.mark.asyncio
async def test_curated_recommendations_utm_source():
    """Test the curated recommendations endpoint returns urls with correct(new) utm_source"""
    async with AsyncClient(app=app, base_url="http://test") as ac:
        # Mock the endpoint
        response = await fetch_en_us(ac)
        data = response.json()

        # Check if the mock response is valid
        assert response.status_code == 200

        corpus_items = data["data"]
        # assert total of 80 items returned
        assert len(corpus_items) == 80
        # Assert all corpus_items have expected fields populated.
        # check that utm_source is present and has the correct value in all urls
        assert all("?utm_source=firefox-newtab-en-us" in item["url"] for item in corpus_items)
        assert all(item["publisher"] for item in corpus_items)
        assert all(item["imageUrl"] for item in corpus_items)


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
    async def test_curated_recommendations_count(self, count, fixture_response_data):
        """Test the curated recommendations endpoint accepts valid count."""
        async with AsyncClient(app=app, base_url="http://test") as ac:
            response = await ac.post(
                "/api/v1/curated-recommendations", json={"locale": "en-US", "count": count}
            )
            assert response.status_code == 200
            data = response.json()
            schedule_count = len(fixture_response_data["data"]["scheduledSurface"]["items"])
            assert len(data["data"]) == min(count, schedule_count)

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
            ["home"],
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
                "home",
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
        "locale",
        ["fr", "fr-FR", "es", "es-ES", "it", "it-IT", "de", "de-DE", "de-AT", "de-CH"],
    )
    @pytest.mark.parametrize("topics", [None, ["arts", "finance"]])
    async def test_curated_recommendations_non_en_topic_is_null(self, locale, topics):
        """Test that topic is missing/null for non-English locales."""
        async with AsyncClient(app=app, base_url="http://test") as ac:
            response = await ac.post(
                "/api/v1/curated-recommendations", json={"locale": locale, "topics": topics}
            )
            data = response.json()
            corpus_items = data["data"]

            assert len(corpus_items) > 0
            # Assert that the topic is None for all items in non-en-US locales.
            assert all(item["topic"] is None for item in corpus_items)

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        "locale",
        ["en-US", "en-GB"],
    )
    @pytest.mark.parametrize("topics", [None, ["arts", "finance"]])
    async def test_curated_recommendations_en_topic(self, locale, topics):
        """Test that topic is present for English locales."""
        async with AsyncClient(app=app, base_url="http://test") as ac:
            response = await ac.post(
                "/api/v1/curated-recommendations", json={"locale": locale, "topics": topics}
            )
            data = response.json()
            corpus_items = data["data"]

            assert len(corpus_items) > 0
            assert all(item["topic"] is not None for item in corpus_items)

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        "preferred_topics",
        [
            [Topic.EDUCATION],
            [Topic.EDUCATION, Topic.PERSONAL_FINANCE],
            [Topic.EDUCATION, Topic.PERSONAL_FINANCE, Topic.BUSINESS],
            [Topic.EDUCATION, Topic.PERSONAL_FINANCE, Topic.BUSINESS, Topic.TECHNOLOGY],
            [
                Topic.EDUCATION,
                Topic.PERSONAL_FINANCE,
                Topic.TECHNOLOGY,
                Topic.TRAVEL,
                Topic.FOOD,
                Topic.BUSINESS,
            ],
            [
                Topic.EDUCATION,
                Topic.PERSONAL_FINANCE,
                Topic.BUSINESS,
                Topic.TECHNOLOGY,
                Topic.TRAVEL,
                Topic.FOOD,
                Topic.ARTS,
            ],
            [
                Topic.EDUCATION,
                Topic.PERSONAL_FINANCE,
                Topic.BUSINESS,
                Topic.TECHNOLOGY,
                Topic.TRAVEL,
                Topic.FOOD,
                Topic.ARTS,
                Topic.POLITICS,
            ],
            [
                Topic.EDUCATION,
                Topic.PERSONAL_FINANCE,
                Topic.BUSINESS,
                Topic.TECHNOLOGY,
                Topic.TRAVEL,
                Topic.FOOD,
                Topic.ARTS,
                Topic.POLITICS,
                Topic.GAMING,
            ],
            [
                Topic.EDUCATION,
                Topic.PERSONAL_FINANCE,
                Topic.BUSINESS,
                Topic.TECHNOLOGY,
                Topic.TRAVEL,
                Topic.FOOD,
                Topic.ARTS,
                Topic.POLITICS,
                Topic.GAMING,
                Topic.SPORTS,
            ],
            [
                Topic.EDUCATION,
                Topic.PERSONAL_FINANCE,
                Topic.BUSINESS,
                Topic.TECHNOLOGY,
                Topic.TRAVEL,
                Topic.FOOD,
                Topic.ARTS,
                Topic.POLITICS,
                Topic.GAMING,
                Topic.SPORTS,
                Topic.SCIENCE,
            ],
            [
                Topic.EDUCATION,
                Topic.PERSONAL_FINANCE,
                Topic.BUSINESS,
                Topic.TECHNOLOGY,
                Topic.TRAVEL,
                Topic.FOOD,
                Topic.ARTS,
                Topic.POLITICS,
                Topic.GAMING,
                Topic.SPORTS,
                Topic.SCIENCE,
                Topic.SELF_IMPROVEMENT,
            ],
            [
                Topic.EDUCATION,
                Topic.PERSONAL_FINANCE,
                Topic.BUSINESS,
                Topic.TECHNOLOGY,
                Topic.TRAVEL,
                Topic.FOOD,
                Topic.ARTS,
                Topic.POLITICS,
                Topic.GAMING,
                Topic.SPORTS,
                Topic.SCIENCE,
                Topic.SELF_IMPROVEMENT,
                Topic.PARENTING,
            ],
            [
                Topic.EDUCATION,
                Topic.PERSONAL_FINANCE,
                Topic.BUSINESS,
                Topic.TECHNOLOGY,
                Topic.TRAVEL,
                Topic.FOOD,
                Topic.ARTS,
                Topic.POLITICS,
                Topic.GAMING,
                Topic.SPORTS,
                Topic.SCIENCE,
                Topic.SELF_IMPROVEMENT,
                Topic.PARENTING,
                Topic.CAREER,
            ],
            [
                Topic.EDUCATION,
                Topic.PERSONAL_FINANCE,
                Topic.BUSINESS,
                Topic.TECHNOLOGY,
                Topic.TRAVEL,
                Topic.FOOD,
                Topic.ARTS,
                Topic.POLITICS,
                Topic.GAMING,
                Topic.SPORTS,
                Topic.SCIENCE,
                Topic.SELF_IMPROVEMENT,
                Topic.PARENTING,
                Topic.CAREER,
                Topic.HEALTH_FITNESS,
            ],
            [
                Topic.EDUCATION,
                Topic.PERSONAL_FINANCE,
                Topic.BUSINESS,
                Topic.TECHNOLOGY,
                Topic.TRAVEL,
                Topic.FOOD,
                Topic.ARTS,
                Topic.POLITICS,
                Topic.GAMING,
                Topic.SPORTS,
                Topic.SCIENCE,
                Topic.SELF_IMPROVEMENT,
                Topic.PARENTING,
                Topic.CAREER,
                Topic.HEALTH_FITNESS,
                Topic.HOME,
            ],
        ],
    )
    async def test_curated_recommendations_preferred_topic(self, preferred_topics):
        """Test the curated recommendations endpoint accepts 1-15 preferred topics &
        top N recommendations contain the preferred topics.
        """
        async with AsyncClient(app=app, base_url="http://test") as ac:
            response = await ac.post(
                "/api/v1/curated-recommendations",
                json={"locale": "en-US", "topics": preferred_topics},
            )
            data = response.json()
            corpus_items = data["data"]

            assert response.status_code == 200
            # assert total of 80 items returned
            assert len(corpus_items) == 80

            # determine the number of recs that are expected to be preferred
            # based on number of preferred topics
            top_recs = min(10, 2 * len(preferred_topics))
            # store the topics for the top N recs in an array
            top_topics = [item["topic"] for item in corpus_items[:top_recs]]
            # assert that all top_topics are preferred topics
            assert all([topic in preferred_topics for topic in top_topics])

    @pytest.mark.asyncio
    @freezegun.freeze_time("2012-01-14 03:25:34", tz_offset=0)
    async def test_curated_recommendations_preferred_topic_no_reorder(
        self, fixture_response_data_short, fixture_request_data, corpus_http_client
    ):
        """Test the curated recommendations endpoint accepts a preferred topic & does
        not reorder the list if preferred topics already in top 2 recs.
        """
        async with AsyncClient(app=app, base_url="http://test") as ac:
            corpus_http_client.post.return_value = Response(
                status_code=200,
                json=fixture_response_data_short,
                request=fixture_request_data,
            )
            response = await fetch_en_us(ac)
            data = response.json()
            corpus_items = data["data"]

            assert response.status_code == 200
            # assert total of 4 items returned (using scheduled_surface_short.json for response)
            assert len(corpus_items) == 5
            # assert that recs didn't need boosting so order remains the same
            for i in range(len(corpus_items)):
                assert (
                    fixture_response_data_short["data"]["scheduledSurface"]["items"][i]["id"]
                    == corpus_items[i]["scheduledCorpusItemId"]
                )

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        "topics, expected_topics, expected_warning",
        [
            # Valid topic, but must be wrapped in a list
            (
                "arts",
                [Topic.CAREER, Topic.FOOD, Topic.PARENTING, Topic.PARENTING, Topic.FOOD],
                "Topics not wrapped in a list: arts",
            ),
            # Invalid topic & must be wrapped in a list
            (
                "invalid-topic",
                [Topic.CAREER, Topic.FOOD, Topic.PARENTING, Topic.PARENTING, Topic.FOOD],
                "Topics not wrapped in a list: invalid-topic",
            ),
            # Invalid topic in a list
            (
                ["not-a-valid-topic"],
                [Topic.CAREER, Topic.FOOD, Topic.PARENTING, Topic.PARENTING, Topic.FOOD],
                "Invalid topic: not-a-valid-topic",
            ),
            # 2 valid topics, 1 invalid topic
            (
                ["food", "invalid_topic", "society-parenting"],
                [Topic.FOOD, Topic.PARENTING, Topic.PARENTING, Topic.FOOD, Topic.CAREER],
                "Invalid topic: invalid_topic",
            ),
        ],
    )
    @pytest.mark.parametrize(
        "repeat",  # See thompson_sampling config in testing.toml for how to repeat this test.
        range(settings.curated_recommendations.rankers.thompson_sampling.test_repeat_count),
    )
    async def test_curated_recommendations_invalid_topic_return_200(
        self,
        topics,
        expected_topics,
        expected_warning,
        fixture_response_data_short,
        fixture_request_data,
        corpus_http_client,
        caplog,
        repeat,
    ):
        """Test the curated recommendations endpoint ignores invalid topic in topics param.
        Should treat invalid topic as blank.
        """
        async with AsyncClient(app=app, base_url="http://test") as ac:
            corpus_http_client.post.return_value = Response(
                status_code=200,
                json=fixture_response_data_short,
                request=fixture_request_data,
            )
            response = await ac.post(
                "/api/v1/curated-recommendations", json={"locale": "en-US", "topics": topics}
            )
            data = response.json()
            corpus_items = data["data"]
            # assert 200 is returned even tho some invalid topics
            assert response.status_code == 200
            # get topics in returned recs
            result_topics = [item["topic"] for item in corpus_items]
            assert result_topics == expected_topics
            # Assert that a warning was logged with a descriptive message when invalid topic
            warnings = [r for r in caplog.records if r.levelname == "WARNING"]
            assert len(warnings) == 1
            assert expected_warning in warnings[0].message

    @pytest.mark.asyncio
    async def test_curated_recommendations_locale_bad_request(self):
        """Test the curated recommendations endpoint response is 400 if locale is not provided"""
        async with AsyncClient(app=app, base_url="http://test") as ac:
            # Mock the endpoint
            response = await ac.post("/api/v1/curated-recommendations", json={"foo": "bar"})

            # Check if the response returns 400
            assert response.status_code == 400


class TestCuratedRecommendationsRequestFeeds:
    """Tests covering the feeds request param."""

    @staticmethod
    def assert_need_to_know_feed(need_to_know_feed):
        """Assert the need_to_know feed is as expected."""
        # Assert that the `need_to_know` feed has a localized title returned
        title = need_to_know_feed["title"]
        assert title == "In the news"

        # Assert that the `need_to_know` feed has 10 items
        feed = need_to_know_feed["recommendations"]
        assert len(feed) == 10

        # Assert all `need_to_know` stories have expected fields populated.
        assert all(item["url"] for item in feed)
        assert all(item["publisher"] for item in feed)
        assert all(item["imageUrl"] for item in feed)
        assert all(item["tileId"] for item in feed)

    @staticmethod
    def assert_fakespot_feed(_fakespot_feed):
        """Assert the fakespot feed is as expected."""
        fakespot_products = _fakespot_feed["products"]
        # currently 8 products in mock JSON file
        assert len(fakespot_products) == 8
        # Assert all fakespot products have expected fields populated.
        required_fields = ["id", "title", "category", "imageUrl", "url"]
        for product in fakespot_products:
            assert all(product.get(field) for field in required_fields)
        # Assert the default category name, header, footer, cta copy are present
        assert _fakespot_feed["defaultCategoryName"] == FAKESPOT_DEFAULT_CATEGORY_NAME
        assert _fakespot_feed["headerCopy"] == FAKESPOT_HEADER_COPY
        assert _fakespot_feed["footerCopy"] == FAKESPOT_FOOTER_COPY
        assert _fakespot_feed["cta"]["ctaCopy"] == FAKESPOT_CTA_COPY
        assert _fakespot_feed["cta"]["url"] == FAKESPOT_CTA_URL

    @freezegun.freeze_time("2012-01-14 03:21:34", tz_offset=0)
    @pytest.mark.asyncio
    async def test_curated_recommendations_with_need_to_know_feed(self):
        """Test the curated recommendations endpoint response is as expected
        when requesting the 'need_to_know' feed for en-US locale.
        """
        async with AsyncClient(app=app, base_url="http://test") as ac:
            # Mock the endpoint
            response = await fetch_en_us_with_need_to_know(ac)
            data = response.json()

            # Check if the mock response is valid
            assert response.status_code == 200

            corpus_items = data["data"]

            # Assert total of 70 items returned (minus the ten items marked as `isTimeSensitive` in the data
            assert len(corpus_items) == 70

            # Assert all corpus_items have expected fields populated.
            assert all(item["url"] for item in corpus_items)
            assert all(item["publisher"] for item in corpus_items)
            assert all(item["imageUrl"] for item in corpus_items)
            assert all(item["tileId"] for item in corpus_items)

            # Assert that receivedRank equals 0, 1, 2, ...
            for i, item in enumerate(corpus_items):
                assert item["receivedRank"] == i

            # Assert the `need_to_know` feed
            self.assert_need_to_know_feed(data["feeds"]["need_to_know"])

    @freezegun.freeze_time("2012-01-14 03:21:34", tz_offset=0)
    @pytest.mark.asyncio
    async def test_curated_recommendations_with_fakespot_feed(self):
        """Test the curated recommendations endpoint response is as expected
        when requesting the 'fakespot' feed for en-US locale.
        """
        async with AsyncClient(app=app, base_url="http://test") as ac:
            # Mock the endpoint
            response = await fetch_en_us_with_fakespot(ac)
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
            assert all(item["tileId"] for item in corpus_items)

            # Assert that receivedRank equals 0, 1, 2, ...
            for i, item in enumerate(corpus_items):
                assert item["receivedRank"] == i

            # Assert the fakespot feed is present
            self.assert_fakespot_feed(data["feeds"]["fakespot"])

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
            "en-GB",
            "de",
            "de-DE",
            "de-AT",
            "de-CH",
        ],
    )
    async def test_curated_recommendations_with_fakespot_feed_non_en_us(self, locale):
        """Test the curated recommendations endpoint response is as expected with non en-US locale & fakespot feed
        requested. Fakespot feed should not be returned for non en-US locale.
        """
        async with AsyncClient(app=app, base_url="http://test") as ac:
            response = await ac.post(
                "/api/v1/curated-recommendations", json={"locale": locale, "feeds": ["fakespot"]}
            )
            assert response.status_code == 200, f"{locale} resulted in {response.status_code}"
            data = response.json()
            # assert feeds is empty
            assert data["feeds"] is None

    @freezegun.freeze_time("2012-01-14 03:21:34", tz_offset=0)
    @pytest.mark.asyncio
    async def test_curated_recommendations_with_need_to_know_fakespot_feeds_non_en_us(self):
        """Test the curated recommendations endpoint response is as expected
        when requesting the 'need_to_know' and 'fakespot' feed together for non en-US.
        Fakespot feed should be null for non en-US locales.
        """
        async with AsyncClient(app=app, base_url="http://test") as ac:
            # Mock the endpoint
            response = await ac.post(
                "/api/v1/curated-recommendations",
                json={"locale": "en-GB", "feeds": ["need_to_know", "fakespot"]},
            )
            data = response.json()

            # Check if the mock response is valid
            assert response.status_code == 200

            corpus_items = data["data"]

            # Assert total of 70 items returned (minus the ten items marked as `isTimeSensitive` in the data
            assert len(corpus_items) == 70

            # Assert all corpus_items have expected fields populated.
            assert all(item["url"] for item in corpus_items)
            assert all(item["publisher"] for item in corpus_items)
            assert all(item["imageUrl"] for item in corpus_items)
            assert all(item["tileId"] for item in corpus_items)

            # Assert that receivedRank equals 0, 1, 2, ...
            for i, item in enumerate(corpus_items):
                assert item["receivedRank"] == i

            # Assert the `need_to_know` feed is returned correctly
            self.assert_need_to_know_feed(data["feeds"]["need_to_know"])

            # Assert the fakespot feed is not returned even though requested, as non en-US locale
            assert data["feeds"]["fakespot"] is None

    @freezegun.freeze_time("2012-01-14 03:21:34", tz_offset=0)
    @pytest.mark.asyncio
    async def test_curated_recommendations_with_need_to_know_fakespot_feeds_en_us(self):
        """Test the curated recommendations endpoint response is as expected
        when requesting the 'need_to_know' and 'fakespot' feed together for en-US.
        Both feeds should be returned correctly.
        """
        async with AsyncClient(app=app, base_url="http://test") as ac:
            # Mock the endpoint
            response = await ac.post(
                "/api/v1/curated-recommendations",
                json={"locale": "en-US", "feeds": ["need_to_know", "fakespot"]},
            )
            data = response.json()

            # Check if the mock response is valid
            assert response.status_code == 200

            corpus_items = data["data"]

            # Assert total of 70 items returned (minus the ten items marked as `isTimeSensitive` in the data
            assert len(corpus_items) == 70

            # Assert all corpus_items have expected fields populated.
            assert all(item["url"] for item in corpus_items)
            assert all(item["publisher"] for item in corpus_items)
            assert all(item["imageUrl"] for item in corpus_items)
            assert all(item["tileId"] for item in corpus_items)

            # Assert that receivedRank equals 0, 1, 2, ...
            for i, item in enumerate(corpus_items):
                assert item["receivedRank"] == i

            # Assert the `need_to_know` feed is returned correctly
            self.assert_need_to_know_feed(data["feeds"]["need_to_know"])

            # Assert the fakespot feed is present
            self.assert_fakespot_feed(data["feeds"]["fakespot"])


class TestCorpusApiCaching:
    """Tests covering the caching behavior of the Corpus backend"""

    @freezegun.freeze_time("2012-01-14 03:21:34", tz_offset=0)
    @pytest.mark.asyncio
    async def test_single_request_multiple_fetches(self, corpus_http_client):
        """Test that only a single request is made to the curated-corpus-api."""
        async with AsyncClient(app=app, base_url="http://test") as ac:
            # Gather multiple fetch calls
            results = await asyncio.gather(fetch_en_us(ac), fetch_en_us(ac), fetch_en_us(ac))
            # Assert that recommendations were returned in each response.
            assert all(len(result.json()["data"]) == 80 for result in results)

            # Assert that exactly one request was made to the corpus api
            corpus_http_client.post.assert_called_once()

    @freezegun.freeze_time("2012-01-14 00:00:00", tick=True, tz_offset=0)
    @pytest.mark.parametrize(
        "error_type, expected_warning",
        [
            ("graphql", 'Could not find Scheduled Surface with id of "NEW_TAB_EN_UX".'),
            ("http", "'503 Service Unavailable' for url 'https://client-api.getpocket.com'"),
        ],
    )
    @pytest.mark.asyncio
    async def test_single_request_multiple_failed_fetches(
        self,
        corpus_http_client,
        fixture_request_data,
        fixture_response_data,
        fixture_graphql_200ok_with_error_response,
        caplog,
        error_type,
        expected_warning,
    ):
        """Test that only a few requests are made to the curated-corpus-api when it is down.
        Additionally, test that if the backend returns a GraphQL error, it is handled correctly.
        """
        async with AsyncClient(app=app, base_url="http://test") as ac:
            start_time = datetime.now()

            def temporary_downtime(*args, **kwargs):
                # Simulate the backend being unavailable for the minimum wait time.
                downtime_end = start_time + timedelta(
                    seconds=settings.curated_recommendations.corpus_api.retry_wait_initial_seconds
                )

                if datetime.now() < downtime_end:
                    if error_type == "graphql":
                        return Response(
                            status_code=200,
                            json=fixture_graphql_200ok_with_error_response,
                            request=fixture_request_data,
                        )
                    elif error_type == "http":
                        return Response(status_code=503, request=fixture_request_data)
                else:
                    return Response(
                        status_code=200,
                        json=fixture_response_data,
                        request=fixture_request_data,
                    )

            corpus_http_client.post = AsyncMock(side_effect=temporary_downtime)

            # Hit the endpoint until a 200 response is received or until timeout.
            while datetime.now() < start_time + timedelta(seconds=1):
                try:
                    result = await fetch_en_us(ac)
                    if result.status_code == 200:
                        break
                except HTTPStatusError:
                    pass

            assert result.status_code == 200

            # Assert that we did not send a lot of requests to the backend.
            assert corpus_http_client.post.call_count == 2

            # Assert that a warning was logged with a descriptive message.
            warnings = [r for r in caplog.records if r.levelname == "WARNING"]
            assert any(expected_warning in warning.message for warning in warnings)

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

    @freezegun.freeze_time("2012-01-14 00:00:00", tick=True, tz_offset=0)
    @pytest.mark.asyncio
    async def test_valid_cache_returned_on_error(
        self, corpus_http_client, fixture_request_data, caplog
    ):
        """Test that the cache does not cache error data even if expired & returns latest valid data from cache."""
        with freezegun.freeze_time(tick=True) as frozen_datetime:
            async with AsyncClient(app=app, base_url="http://test") as ac:
                # First fetch to populate cache with good data
                initial_response = await fetch_en_us(ac)
                initial_data = initial_response.json()
                assert initial_response.status_code == 200
                assert corpus_http_client.post.call_count == 1

                # Simulate 503 error from Corpus API
                corpus_http_client.post.return_value = Response(
                    status_code=503,
                    request=fixture_request_data,
                )

                # Progress time to after the cache expires.
                frozen_datetime.tick(delta=CorpusApiBackend.cache_time_to_live_max)
                frozen_datetime.tick(delta=timedelta(seconds=1))

                # Try to fetch data when cache expired
                new_response = await fetch_en_us(ac)
                new_data = new_response.json()
                await asyncio.sleep(
                    get_max_total_retry_duration()
                )  # Allow asyncio background task to make an API request
                # assert that Corpus API was called the expected number of times
                # 1 successful request from above, and retry_count number of retries.
                assert (
                    corpus_http_client.post.call_count
                    == settings.curated_recommendations.corpus_api.retry_count + 1
                )

                assert new_response.status_code == 200
                assert len(initial_data) == len(new_data)
                assert all([a == b for a, b in zip(initial_data, new_data)])


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
        self,
        mocker: MockerFixture,
        corpus_http_client,
        fixture_request_data,
        fixture_response_data,
    ) -> None:
        """Test that metrics are recorded when the curated-corpus-api returns a 500 error"""
        report = mocker.patch.object(aiodogstatsd.Client, "_report")

        async with AsyncClient(app=app, base_url="http://test") as ac:
            is_first_request = True

            def first_request_returns_error(*args, **kwargs):
                nonlocal is_first_request
                if is_first_request:
                    is_first_request = False
                    return Response(status_code=500, request=fixture_request_data)
                else:
                    return Response(
                        status_code=200,
                        json=fixture_response_data,
                        request=fixture_request_data,
                    )

            corpus_http_client.post = AsyncMock(side_effect=first_request_returns_error)

            await fetch_en_us(ac)

            # TODO: Remove reliance on internal details of aiodogstatsd
            metric_keys: list[str] = [call.args[0] for call in report.call_args_list]
            assert (
                metric_keys
                == [
                    "corpus_api.request.timing",
                    "corpus_api.request.status_codes.500",
                    "corpus_api.request.timing",
                    "corpus_api.request.status_codes.200",
                    "post.api.v1.curated-recommendations.timing",
                    "post.api.v1.curated-recommendations.status_codes.200",  # final call should return 200
                    "response.status_codes.200",
                ]
            )


class TestCorpusApiRanking:
    """Tests covering the ranking behavior of the Corpus backend"""

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        "topics",
        [
            [Topic.POLITICS],
            None,
        ],
    )
    @pytest.mark.parametrize(
        "locale,region,derived_region",
        [
            ("en-US", None, "US"),
            ("en-US", "IN", "IN"),
            ("fr-FR", "FR", "FR"),
        ],
    )
    @pytest.mark.parametrize(
        "experiment_name, experiment_branch, regional_ranking_is_expected",
        [
            (None, None, False),  # No experiment
            (ExperimentName.REGION_SPECIFIC_CONTENT_EXPANSION.value, "control", False),
            (ExperimentName.REGION_SPECIFIC_CONTENT_EXPANSION.value, "treatment", True),
            (f"optin-{ExperimentName.REGION_SPECIFIC_CONTENT_EXPANSION.value}", "treatment", True),
            (ExperimentName.REGION_SPECIFIC_CONTENT_EXPANSION_SMALL.value, "control", False),
            (ExperimentName.REGION_SPECIFIC_CONTENT_EXPANSION_SMALL.value, "treatment", True),
            (ExperimentName.MODIFIED_PRIOR_EXPERIMENT.value, "control", False),
            (ExperimentName.MODIFIED_PRIOR_EXPERIMENT.value, "treatment", False),
            (
                f"optin-{ExperimentName.REGION_SPECIFIC_CONTENT_EXPANSION_SMALL.value}",
                "treatment",
                True,
            ),
        ],
    )
    @pytest.mark.parametrize(
        "repeat",  # See thompson_sampling config in testing.toml for how to repeat this test.
        range(settings.curated_recommendations.rankers.thompson_sampling.test_repeat_count),
    )
    async def test_thompson_sampling_behavior(
        self,
        topics,
        engagement_backend,
        experiment_name,
        experiment_branch,
        locale,
        region,
        derived_region,
        regional_ranking_is_expected,
        repeat,
    ):
        """Test that Thompson sampling produces different orders and favors higher CTRs."""
        n_iterations = 20
        past_id_orders = []

        async with AsyncClient(app=app, base_url="http://test") as ac:
            for i in range(n_iterations):
                response = await ac.post(
                    "/api/v1/curated-recommendations",
                    json={
                        "locale": locale,
                        "region": region,
                        "topics": topics,
                        "experimentName": experiment_name,
                        "experimentBranch": experiment_branch,
                    },
                )
                data = response.json()
                corpus_items = data["data"]

                # Assert that no response was ranked in the same way before.
                id_order = [item["scheduledCorpusItemId"] for item in corpus_items]
                assert id_order not in past_id_orders, f"Duplicate order at iteration {i}."
                past_id_orders.append(id_order)  # a list of lists with all orders

                engagement_region = derived_region if regional_ranking_is_expected else None
                engagements = [
                    engagement_backend.get(item["scheduledCorpusItemId"], region=engagement_region)
                    for item in corpus_items
                ]
                ctr_by_rank = [
                    (rank, e.click_count / e.impression_count)
                    for rank, e in enumerate(engagements)
                    # Exclude no engagement items and the first one, which has 100% CTR.
                    if e is not None and rank > 0
                ]

                # Perform linear regression to find the coefficient
                ranks, ctrs = zip(*ctr_by_rank)
                slope, _, _, _, _ = linregress(ranks, ctrs)

                # Assert that the slope is negative, meaning higher ranks have higher CTRs
                assert slope < 0, f"Thompson sampling did not favor higher CTR on iteration {i}."


class TestNeedToKnow:
    """Test the behavior of the NeedToKnow feed"""

    @pytest.mark.asyncio
    async def test_fetch_days_since_today(
        self,
        corpus_backend: CorpusApiBackend,
        fixture_response_data,
        fixture_response_data_short,
        fixture_request_data,
        corpus_http_client,
    ):
        """Test that the need_to_know feed falls back to yesterday's schedule when there are
        insufficient time-sensitive items today.
        """

        def mock_post_by_date(*args, **kwargs):
            """Mock scheduledSurface response to have no time-sensitive items today."""
            variables = kwargs["json"]["variables"]
            surface_timezone = corpus_backend.get_surface_timezone(variables["scheduledSurfaceId"])
            date_today = corpus_backend.get_scheduled_surface_date(surface_timezone).date()
            days_ago = (
                datetime.strptime(variables.get("date"), "%Y-%m-%d").date() - date_today
            ).days
            response_json = {}
            if days_ago == 0:
                # requests for today (0) get a response fixture WITHOUT any time-sensitive items.
                response_json = fixture_response_data_short
            elif days_ago == -1:
                # requests for yesterday (-1) get a response fixture WITH time-sensitive items.
                response_json = fixture_response_data

            return Response(
                status_code=200,
                json=response_json,
                request=fixture_request_data,
            )

        corpus_http_client.post.side_effect = mock_post_by_date

        async with AsyncClient(app=app, base_url="http://test") as ac:
            response = await ac.post(
                "/api/v1/curated-recommendations",
                json={"locale": "en-US", "feeds": ["need_to_know"]},
            )
            data = response.json()
            need_to_know = data["feeds"]["need_to_know"]["recommendations"]
            assert len(need_to_know) == 10  # The number of time-sensitive items in the fixture.


class TestSections:
    """Test the behavior of the sections feeds"""

    en_us_section_title_top_stories = "Popular Today"
    de_section_title_top_stories = "Meistgelesen"

    @pytest.mark.parametrize(
        "surface_id",
        [
            ScheduledSurfaceId.NEW_TAB_EN_US,
            ScheduledSurfaceId.NEW_TAB_DE_DE,
        ],
    )
    def test_section_translations(self, surface_id):
        """Check that there is a translation for every section title.
        Currently, for en-US and DE.
        """
        # Define the mapping of strings to be replaced, use the Topic enum
        replacement_section_titles = {topic.name.lower(): topic.value for topic in Topic}
        # top-stories is not in the Topic enum, do separately
        replacement_section_titles["top_stories_section"] = "top-stories"
        replacement_section_titles["news_section"] = "news-section"

        # Get all Section titles in CuratedRecommendationsFeed
        # Replace strings using the Topic enum-derived map
        section_titles = [
            # Replace if in section title map, else keep original section title
            replacement_section_titles.get(title_name, title_name)
            for title_name, title_type in CuratedRecommendationsFeed.__annotations__.items()
            if title_type == Section | None
        ]

        # Get the localized titles for the current surface_id
        localized_titles = LOCALIZED_SECTION_TITLES[surface_id]

        # Assert that each section title has a translation
        for title in section_titles:
            assert title in localized_titles and localized_titles[title], (
                f"Missing translation for '{title}' in " f"{surface_id}"
            )

    @pytest.mark.asyncio
    @pytest.mark.parametrize("locale", ["en-US", "de-DE"])
    async def test_sections_feed_content(self, locale, caplog):
        """Test the curated recommendations endpoint response is as expected
        when requesting the 'sections' feed for different locales.
        """
        async with AsyncClient(app=app, base_url="http://test") as ac:
            # Mock the endpoint to request the sections feed
            response = await ac.post(
                "/api/v1/curated-recommendations",
                json={"locale": locale, "feeds": ["sections"]},
            )
            data = response.json()

            # Check if the response is valid
            assert response.status_code == 200
            # Assert no errors were logged
            errors = [r for r in caplog.records if r.levelname == "ERROR"]
            assert len(errors) == 0

            # Assert that an empty data array is returned. All recommendations are under "feeds".
            assert len(data["data"]) == 0

            feeds = data["feeds"]
            sections = {name: section for name, section in feeds.items() if section is not None}

            # The fixture data contains enough recommendations for at least 4 sections. The number
            # of sections varies because top_stories_section is determined by Thompson sampling,
            # and therefore the number of recs per topics is non-deterministic.
            assert len(sections) >= 4

            # All sections have a layout
            assert all(Layout(**section["layout"]) for section in sections.values())

            # Ensure all topics are present and are named according to the Topic Enum value.
            assert all(topic.value in feeds for topic in Topic)

            # Assert that news_section only has time sensitive items, and other sections do not.
            for section_name, section in sections.items():
                is_expected_time_sensitive = section_name == "news_section"
                for recommendation in section["recommendations"]:
                    assert recommendation["isTimeSensitive"] == is_expected_time_sensitive

    @pytest.mark.asyncio
    async def test_curated_recommendations_with_sections_feed_boost_followed_sections(
        self, caplog
    ):
        """Test the curated recommendations endpoint response is as expected
        when requesting the 'sections' feed for en-US locale. Sections requested to be boosted (followed)
        should be boosted and isFollowed attribute set accordingly.
        """
        async with AsyncClient(app=app, base_url="http://test") as ac:
            # Mock the endpoint to request the sections feed
            response = await ac.post(
                "/api/v1/curated-recommendations",
                json={
                    "locale": "en-US",
                    "feeds": ["sections"],
                    "sections": [
                        {"sectionId": "sports", "isFollowed": True, "isBlocked": False},
                        {"sectionId": "arts", "isFollowed": True, "isBlocked": False},
                        {"sectionId": "education", "isFollowed": False, "isBlocked": True},
                    ],
                },
            )
            data = response.json()

            # Check if the response is valid
            assert response.status_code == 200

            # assert isFollowed & isBlocked have been correctly set
            if data["feeds"]["arts"] is not None:
                assert data["feeds"]["arts"]["isFollowed"]
                # assert followed section ARTS comes after top-stories and before unfollowed sections (education).
                assert data["feeds"]["arts"]["receivedFeedRank"] in [1, 2]
            if data["feeds"]["education"] is not None:
                assert not data["feeds"]["education"]["isFollowed"]
                assert data["feeds"]["education"]["isBlocked"]
            if data["feeds"]["sports"] is not None:
                assert data["feeds"]["sports"]["isFollowed"]
                # assert followed section SPORTS comes after top-stories and before unfollowed sections (education).
                assert data["feeds"]["sports"]["receivedFeedRank"] in [1, 2]

            # Assert no errors were logged
            errors = [r for r in caplog.records if r.levelname == "ERROR"]
            assert len(errors) == 0

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        "locale, expected_titles, expected_news_subtitle",
        [
            (
                "en-US",
                {
                    "top_stories_section": "Popular Today",
                    "news_section": "In the News",
                    "arts": "Entertainment",
                    "education": "Education",
                    "sports": "Sports",
                },
                "December 17, 2024",  # Frozen time 2024-12-18 6am UTC = 2024-12-17 10pm PST
            ),
            (
                "de-DE",
                {
                    "top_stories_section": "Meistgelesen",
                    "news_section": "In den News",
                    "arts": "Unterhaltung",
                    "education": "Bildung",
                    "sports": "Sport",
                },
                "18. Dezember 2024",  # Frozen time 2024-12-18 6am UTC = 2024-12-18 7am CET
            ),
        ],
    )
    @freezegun.freeze_time("2024-12-18 06:00:00", tz_offset=0)
    async def test_sections_feed_titles(self, locale, expected_titles, expected_news_subtitle):
        """Test the curated recommendations endpoint 'sections' have the expected (sub)titles."""
        async with AsyncClient(app=app, base_url="http://test") as ac:
            # Mock the endpoint to request the sections feed
            response = await ac.post(
                "/api/v1/curated-recommendations",
                json={"locale": locale, "feeds": ["sections"]},
            )
            data = response.json()
            feeds = data["feeds"]

            # Sections have their expected, localized title
            for section_name, expected_title in expected_titles.items():
                section = feeds.get(section_name)
                if section:
                    assert section["title"] == expected_title

            # Ensure "Today's top stories" is present
            top_stories_section = data["feeds"].get("top_stories_section")
            assert top_stories_section is not None
            assert top_stories_section["subtitle"] is None

            # Ensure "Today's top stories" is present with a valid date subtitle
            news_section = data["feeds"].get("news_section")
            assert news_section is not None
            assert news_section["subtitle"] == expected_news_subtitle


class TestExtendedExpiration:
    """Test the behavior of the ExtendedExpiration experiment functionality."""

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        "experiment_name, experiment_branch, is_in_experiment",
        [
            (None, None, False),
            (ExperimentName.EXTENDED_EXPIRATION_EXPERIMENT.value, "control", False),
            (ExperimentName.EXTENDED_EXPIRATION_EXPERIMENT.value, "treatment", True),
            (f"optin-{ExperimentName.EXTENDED_EXPIRATION_EXPERIMENT.value}", "treatment", True),
        ],
    )
    async def test_extended_expiration_experiment(
        self,
        corpus_backend: CorpusApiBackend,
        experiment_name,
        experiment_branch,
        is_in_experiment,
        fixture_response_data,
        fixture_request_data,
        corpus_http_client,
    ):
        """Test that older items are fetched in the extended expiration experiment."""

        def mock_post_by_days_ago(*args, **kwargs):
            """Mock Corpus API response to simulate fetching data from different days."""
            variables = kwargs["json"]["variables"]
            surface_timezone = corpus_backend.get_surface_timezone(variables["scheduledSurfaceId"])
            date_today = corpus_backend.get_scheduled_surface_date(surface_timezone).date()
            days_ago = (
                datetime.strptime(variables.get("date"), "%Y-%m-%d").date() - date_today
            ).days

            # Modify IDs and titles in response data to indicate the number of days ago
            modified_response = {
                "data": {
                    "scheduledSurface": {
                        "items": [
                            {
                                "id": f"{item['id']}_days_ago_{days_ago}",
                                "corpusItem": {
                                    **item["corpusItem"],
                                    "title": f"{item['corpusItem']['title']} days ago:{days_ago}",
                                },
                            }
                            for item in fixture_response_data["data"]["scheduledSurface"]["items"]
                        ]
                    }
                }
            }
            return Response(status_code=200, json=modified_response, request=fixture_request_data)

        corpus_http_client.post.side_effect = mock_post_by_days_ago

        async with AsyncClient(app=app, base_url="http://test") as ac:
            response = await ac.post(
                "/api/v1/curated-recommendations",
                json={
                    "locale": "en-US",
                    "experimentName": experiment_name,
                    "experimentBranch": experiment_branch,
                },
            )
            data = response.json()
            items = data["data"]

            # Count the number of items by the days_ago value in the title
            days_ago_counter = Counter(int(item["title"].split("days ago:")[-1]) for item in items)

            if is_in_experiment:
                # Assert that items from 3 days ago were included in the experiment.
                assert set(days_ago_counter.keys()) == {-3, -2, -1, 0}
            else:
                # Check that only today's items are returned if in control or not in the experiment.
                assert set(days_ago_counter.keys()) == {0}
