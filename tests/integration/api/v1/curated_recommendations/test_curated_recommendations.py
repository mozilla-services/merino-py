"""Tests the curated recommendation endpoint /api/v1/curated-recommendations"""

import asyncio
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

from merino.configs import settings
from merino.curated_recommendations import (
    ScheduledSurfaceBackend,
    CuratedRecommendationsProvider,
    get_provider,
    get_legacy_provider,
    ConstantPrior,
    interest_picker,
    LocalModelBackend,
)
from merino.curated_recommendations.legacy.provider import LegacyCuratedRecommendationsProvider
from merino.curated_recommendations.corpus_backends.protocol import (
    Topic,
    SurfaceId,
    SectionsProtocol,
)
from merino.curated_recommendations.engagement_backends.protocol import (
    EngagementBackend,
    Engagement,
)
from merino.curated_recommendations.localization import LOCALIZED_SECTION_TITLES
from merino.curated_recommendations.ml_backends.protocol import (
    InferredLocalModel,
    ModelData,
    ModelType,
    DayTimeWeightingConfig,
)
from merino.curated_recommendations.prior_backends.protocol import PriorBackend
from merino.curated_recommendations.protocol import (
    ExperimentName,
    Layout,
    Locale,
    CoarseOS,
)
from merino.curated_recommendations.protocol import CuratedRecommendation
from merino.main import app
from merino.providers.manifest import get_provider as get_manifest_provider
from merino.providers.manifest.backends.protocol import Domain


class MockEngagementBackend(EngagementBackend):
    """Mock class implementing the protocol for EngagementBackend."""

    def get(self, corpus_item_id: str, region: str | None = None) -> Engagement | None:
        """Return random click and impression counts based on the scheduled corpus id and region."""
        HIGH_CTR_ITEMS = {
            "b2c10703-5377-4fe8-89d3-32fbd7288187": (1_000_000, 1_000_000),  # ML music 100% CTR
            "f509393b-c1d6-4500-8ed2-29f8a23f39a7": (1_000_000, 1_000_000),  # ML NFL 100% CTR
            "2afcef43-4663-446e-9d69-69cbc6966162": (1_000_000, 1_000_000),  # ML Movies 100% CTR
            "dc4b30c4-170b-4e9f-a068-bdc51474a0fb": (1_000_000, 1_000_000),  # ML Soccer 100% CTR
            "9261e868-beff-4419-8071-7750d063d642": (1_000_000, 1_000_000),  # ML NBA 100% CTR
            "63909b8c-a619-45f3-9ebc-fd8fcaeb72b1": (1_000_000, 1_000_000),  # ML Food 100% CTR
            # The above 6 ML recs have the highest CTR & will be included in top_stories_section
            "41111154-ebb1-45d9-9799-a882f13cd8cc": (
                990_000,
                1_000_000,
            ),  # ML music 99% CTR (highest CTR in Music
            # feed)
            "4095b364-02ff-402c-b58a-792a067fccf2": (1_000_000, 1_000_000),  # Non-ML food 100% CTR
        }
        seed_input = "_".join(filter(None, [corpus_item_id, region]))
        rng = np.random.default_rng(seed=int.from_bytes(seed_input.encode()))

        if corpus_item_id in HIGH_CTR_ITEMS:
            # Give the first item (corpus rec & ML section) 100% click-through rate to put it on top with high
            # certainty.
            click_count, impression_count = HIGH_CTR_ITEMS[corpus_item_id]
            return Engagement(
                corpus_item_id=corpus_item_id,
                click_count=click_count,
                impression_count=impression_count,
            )
        elif rng.random() < 0.5:
            # 50% chance of no engagement data being available.
            return None
        else:
            # Uniformly random clicks (10k-50k) and impressions (1M-5M)
            return Engagement(
                corpus_item_id=corpus_item_id,
                click_count=rng.integers(10_000, 50_000),
                impression_count=rng.integers(1_000_000, 5_000_000),
            )

    def initialize(self) -> None:
        """Mock class must implement this method, but no initialization needs to happen."""
        pass


class MockLocalModelBackend(LocalModelBackend):
    """Mock class implementing the protocol for EngagementBackend."""

    def get(self, surface_id: str | None = None) -> InferredLocalModel | None:
        """Return sample local model"""
        model_data = ModelData(
            model_type=ModelType.CLICKS,
            rescale=True,
            day_time_weighting=DayTimeWeightingConfig(
                days=[3, 14, 45],
                relative_weight=[1, 1, 1],
            ),
            interest_vector={},
        )
        return InferredLocalModel(
            model_id="fake", model_version=0, surface_id=surface_id, model_data=model_data
        )

    def initialize(self) -> None:
        """Mock class must implement this method, but no initialization needs to happen."""
        pass


@pytest.fixture
def engagement_backend():
    """Fixture for the MockEngagementBackend"""
    return MockEngagementBackend()


@pytest.fixture
def local_model_backend():
    """Fixture for the MockLocalModelBackend"""
    return MockLocalModelBackend()


@pytest.fixture(name="prior_backend")
def constant_prior_backend() -> PriorBackend:
    """Mock constant prior backend."""
    return ConstantPrior()


@pytest.fixture(autouse=True)
def setup_manifest_provider(manifest_provider):
    """Set up the manifest provider dependency"""
    app.dependency_overrides[get_manifest_provider] = lambda: manifest_provider
    yield
    if get_manifest_provider in app.dependency_overrides:
        del app.dependency_overrides[get_manifest_provider]


@pytest.fixture(name="corpus_provider")
def provider(
    scheduled_surface_backend: ScheduledSurfaceBackend,
    sections_backend: SectionsProtocol,
    engagement_backend: EngagementBackend,
    prior_backend: PriorBackend,
    local_model_backend: LocalModelBackend,
) -> CuratedRecommendationsProvider:
    """Mock curated recommendations provider."""
    return CuratedRecommendationsProvider(
        scheduled_surface_backend=scheduled_surface_backend,
        engagement_backend=engagement_backend,
        prior_backend=prior_backend,
        sections_backend=sections_backend,
        local_model_backend=local_model_backend,
    )


@pytest.fixture(name="legacy_corpus_provider")
def legacy_provider() -> LegacyCuratedRecommendationsProvider:
    """Mock legacy curated recommendations provider."""
    return LegacyCuratedRecommendationsProvider()


@pytest.fixture(autouse=True)
def setup_curated_recommendations_provider(corpus_provider):
    """Set up the curated recommendations provider"""
    app.dependency_overrides[get_provider] = lambda: corpus_provider


@pytest.fixture(autouse=True)
def setup_legacy_curated_recommendations_provider(legacy_corpus_provider):
    """Set up the legacy curated recommendations provider"""
    app.dependency_overrides[get_legacy_provider] = lambda: legacy_corpus_provider


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


def get_max_total_retry_duration() -> float:
    """Compute the maximum retry duration for the exponential backoff and jitter strategy."""
    initial = settings.curated_recommendations.corpus_api.retry_wait_initial_seconds
    jitter = settings.curated_recommendations.corpus_api.retry_wait_jitter_seconds
    retry_count = settings.curated_recommendations.corpus_api.retry_count

    return float(initial * (2**retry_count - 1) + retry_count * jitter)


def assert_section_layouts_are_cycled(sections: dict):
    """Assert that layouts of all sections (excluding 'top_stories_section') are cycled through expected pattern."""
    layout_cycle = [
        "6-small-medium-1-ad",
        "4-large-small-medium-1-ad",
        "4-medium-small-1-ad",
    ]
    cycled_sections = [
        section for sid, section in sections.items() if sid != "top_stories_section"
    ]  # Exclude top stories

    # Check layouts were cycled through LAYOUT_CYCLE (no repeating layouts for consecutive sections)
    for idx, sec in enumerate(cycled_sections):
        expected_layout = layout_cycle[idx % len(layout_cycle)]
        actual_layout = sec["layout"]["name"]
        assert actual_layout == expected_layout


@freezegun.freeze_time("2012-01-14 03:21:34", tz_offset=0)
@pytest.mark.asyncio
@pytest.mark.parametrize(
    "repeat",  # See thompson_sampling config in testing.toml for how to repeat this test.
    range(settings.curated_recommendations.rankers.thompson_sampling.test_repeat_count),
)
async def test_curated_recommendations(repeat):
    """Test the curated recommendations endpoint response is as expected."""
    async with AsyncClient(app=app, base_url="http://test") as ac:
        # expected recommendation
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
            features={"t_food": 1.0},
        )
        # Mock the endpoint
        response = await fetch_en_us(ac)
        data = response.json()

        # Check if the mock response is valid
        assert response.status_code == 200

        # Check surfaceId is returned (should be NEW_TAB_EN_US for en-US locale)
        assert data["surfaceId"] == SurfaceId.NEW_TAB_EN_US

        corpus_items = data["data"]
        # assert total of 100 items returned, which is the default maximum number of recommendations in the response.
        assert len(corpus_items) == 100
        # Assert all corpus_items have expected fields populated.
        assert all(item["url"] for item in corpus_items)
        assert all(item["publisher"] for item in corpus_items)
        assert all(item["imageUrl"] for item in corpus_items)
        assert all(item["tileId"] for item in corpus_items)
        assert all(item["features"] for item in corpus_items)

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


@pytest.mark.asyncio
async def test_curated_recommendations_for_fx115_129():
    """Test the legacy fx115-129 curated recommedations endpoint response is as expected"""
    async with AsyncClient(app=app, base_url="http://test") as ac:
        # Mock the endpoint
        response = await ac.get(
            "/api/v1/curated-recommendations/legacy-115-129", params={"locale": "en-US"}
        )
        data = response.json()

        # Check if the mock response is valid
        assert response.status_code == 200

        corpus_items = data["data"]
        # assert total of 30 items returned, which is the default maximum number of recommendations in the response.
        assert len(corpus_items) == 30
        # Assert all corpus_items have expected fields populated.
        assert all(item["__typename"] for item in corpus_items)
        assert all(item["recommendationId"] for item in corpus_items)
        assert all(item["tileId"] for item in corpus_items)
        assert all(item["url"] for item in corpus_items)
        assert all(item["title"] for item in corpus_items)
        assert all(item["excerpt"] for item in corpus_items)
        assert all(item["publisher"] for item in corpus_items)
        assert all(item["imageUrl"] for item in corpus_items)


@pytest.mark.asyncio
async def test_curated_recommendations_for_fx114():
    """Test the legacy fx114 curated recommedations endpoint response is as expected"""
    async with AsyncClient(app=app, base_url="http://test") as ac:
        # Mock the endpoint
        response = await ac.get(
            "/api/v1/curated-recommendations/legacy-114", params={"locale_lang": "en-US"}
        )
        data = response.json()

        # Check if the mock response is valid
        assert response.status_code == 200

        corpus_items = data["recommendations"]
        # assert total of 20 items returned, which is the default maximum number of recommendations in the response.
        assert len(corpus_items) == 20
        # Assert all corpus_items have expected fields populated.
        assert all(item["id"] for item in corpus_items)
        assert all(item["title"] for item in corpus_items)
        assert all(item["url"] for item in corpus_items)
        assert all(item["excerpt"] for item in corpus_items)
        assert all(item["domain"] for item in corpus_items)
        assert all(item["image_src"] for item in corpus_items)
        assert all(item["raw_image_src"] for item in corpus_items)


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
        # assert items returned, otherwise the following assertions would not test anything.
        assert len(corpus_items) == 100
        # Assert all corpus_items have expected fields populated.
        # check that utm_source is present and has the correct value in all urls
        assert all("utm_source=firefox-newtab-en-us" in item["url"] for item in corpus_items)
        assert all(item["publisher"] for item in corpus_items)
        assert all(item["imageUrl"] for item in corpus_items)


@pytest.mark.asyncio
async def test_curated_recommendations_features():
    """Test the curated recommendations endpoint returns topic features"""
    async with AsyncClient(app=app, base_url="http://test") as ac:
        response = await fetch_en_us(ac)

        recommendations = response.json()["data"]
        for rec in recommendations:
            # Topic features have a t_ prefix
            expected_features = {f"t_{rec['topic']}": 1.0}
            assert rec["features"] == expected_features


class TestCuratedRecommendationsRequestParameters:
    """Test request body parameters for the curated-recommendations endpoint"""

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        "locale,surface_id",
        [
            (Locale.EN, SurfaceId.NEW_TAB_EN_US),
            (Locale.EN_CA, SurfaceId.NEW_TAB_EN_US),
            (Locale.EN_US, SurfaceId.NEW_TAB_EN_US),
            (Locale.EN_GB, SurfaceId.NEW_TAB_EN_GB),
            (Locale.DE, SurfaceId.NEW_TAB_DE_DE),
            (Locale.DE_DE, SurfaceId.NEW_TAB_DE_DE),
            (Locale.DE_AT, SurfaceId.NEW_TAB_DE_DE),
            (Locale.DE_CH, SurfaceId.NEW_TAB_DE_DE),
            (Locale.FR, SurfaceId.NEW_TAB_FR_FR),
            (Locale.FR_FR, SurfaceId.NEW_TAB_FR_FR),
            (Locale.ES, SurfaceId.NEW_TAB_ES_ES),
            (Locale.ES_ES, SurfaceId.NEW_TAB_ES_ES),
            (Locale.IT, SurfaceId.NEW_TAB_IT_IT),
            (Locale.IT_IT, SurfaceId.NEW_TAB_IT_IT),
        ],
    )
    async def test_curated_recommendations_locales(self, locale, surface_id):
        """Test the curated recommendations endpoint accepts valid locales & returns correct surfaceId."""
        async with AsyncClient(app=app, base_url="http://test") as ac:
            response = await ac.post("/api/v1/curated-recommendations", json={"locale": locale})
            assert response.status_code == 200, f"{locale} resulted in {response.status_code}"
            data = response.json()
            assert data["surfaceId"] == surface_id

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
    @pytest.mark.parametrize(
        "coarse_os",
        [
            CoarseOS.MAC,
            CoarseOS.WIN,
            CoarseOS.LINUX,
            CoarseOS.ANDROID,
            CoarseOS.IOS,
            CoarseOS.OTHER,
        ],
    )
    async def test_curated_recommendations_valid_os(self, coarse_os):
        """Test the curated recommendations endpoint accepts valid coarse_os values."""
        async with AsyncClient(app=app, base_url="http://test") as ac:
            response = await ac.post(
                "/api/v1/curated-recommendations",
                json={"locale": Locale.EN_US, "coarse_os": coarse_os},
            )
            assert response.status_code == 200

    @pytest.mark.asyncio
    @pytest.mark.parametrize("coarse_os", ["", "windows11"])
    async def test_curated_recommendations_invalid_os(self, coarse_os):
        """Test the curated recommendations endpoint rejects invalid coarse_os values."""
        async with AsyncClient(app=app, base_url="http://test") as ac:
            response = await ac.post(
                "/api/v1/curated-recommendations",
                json={"locale": Locale.EN_US, "coarseOs": coarse_os},
            )
            assert response.status_code == 400

    @pytest.mark.asyncio
    @pytest.mark.parametrize("utc_offset", [0, 12, 24])
    async def test_curated_recommendations_valid_utc_offset(self, utc_offset):
        """Test the curated recommendations endpoint accepts valid utc_offset values.
        This includes values that require rounding (e.g., 3.7 should be rounded to 4).
        """
        async with AsyncClient(app=app, base_url="http://test") as ac:
            response = await ac.post(
                "/api/v1/curated-recommendations",
                json={"locale": Locale.EN_US, "utcOffset": utc_offset},
            )
            assert response.status_code == 200

    @pytest.mark.asyncio
    @pytest.mark.parametrize("utc_offset", [-1, 11.5, 25, "Z"])
    async def test_curated_recommendations_invalid_utc_offset(self, utc_offset):
        """Test the curated recommendations endpoint rejects invalid utc_offset values."""
        async with AsyncClient(app=app, base_url="http://test") as ac:
            response = await ac.post(
                "/api/v1/curated-recommendations",
                json={"locale": Locale.EN_US, "utcOffset": utc_offset},
            )
            assert response.status_code == 400

    @pytest.mark.asyncio
    @pytest.mark.parametrize("count", [10, 50, 100])
    async def test_curated_recommendations_count(self, count, scheduled_surface_response_data):
        """Test the curated recommendations endpoint accepts valid count."""
        async with AsyncClient(app=app, base_url="http://test") as ac:
            response = await ac.post(
                "/api/v1/curated-recommendations", json={"locale": "en-US", "count": count}
            )
            assert response.status_code == 200
            data = response.json()
            schedule_count = len(
                scheduled_surface_response_data["data"]["scheduledSurface"]["items"]
            )
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
        ["en-US", "en-GB", "fr-FR", "es-ES", "it-IT", "de-DE"],
    )
    @pytest.mark.parametrize("topics", [None, ["arts", "finance"]])
    async def test_curated_recommendations_en_topic(self, locale, topics):
        """Test that topic is present."""
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
            # assert items are returned
            assert len(corpus_items) == 100

            # determine the number of recs that are expected to be preferred
            # based on number of preferred topics
            top_recs = min(10, 2 * len(preferred_topics))
            # store the topics for the top N recs in an array
            top_topics = [item["topic"] for item in corpus_items[:top_recs]]
            # assert that all top_topics are preferred topics
            assert all([topic in preferred_topics for topic in top_topics])

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
        scheduled_surface_response_data_short,
        fixture_request_data,
        scheduled_surface_http_client,
        caplog,
        repeat,
    ):
        """Test the curated recommendations endpoint ignores invalid topic in topics param.
        Should treat invalid topic as blank.
        """
        async with AsyncClient(app=app, base_url="http://test") as ac:
            scheduled_surface_http_client.post.return_value = Response(
                status_code=200,
                json=scheduled_surface_response_data_short,
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
            assert set(result_topics) == set(expected_topics)
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


class TestCorpusApiCaching:
    """Tests covering the caching behavior of the Corpus backend"""

    @freezegun.freeze_time("2012-01-14 03:21:34", tz_offset=0)
    @pytest.mark.asyncio
    async def test_single_request_multiple_fetches(self, scheduled_surface_http_client):
        """Test that only a single request is made to the curated-corpus-api."""
        async with AsyncClient(app=app, base_url="http://test") as ac:
            # Gather multiple fetch calls
            results = await asyncio.gather(fetch_en_us(ac), fetch_en_us(ac), fetch_en_us(ac))
            # Assert that recommendations were returned in each response.
            assert all(len(result.json()["data"]) == 100 for result in results)

            # Assert that exactly one request was made to the corpus api
            scheduled_surface_http_client.post.assert_called_once()

    @freezegun.freeze_time("2012-01-14 00:00:00", tick=True, tz_offset=0)
    @pytest.mark.parametrize(
        "error_type, expected_warning",
        [
            # ("graphql", 'Could not find Scheduled Surface with id of "NEW_TAB_EN_UX".'),
            ("http", "'503 Service Unavailable' for url 'https://client-api.getpocket.com'"),
        ],
    )
    @pytest.mark.asyncio
    async def test_single_request_multiple_failed_fetches(
        self,
        scheduled_surface_http_client,
        fixture_request_data,
        scheduled_surface_response_data,
        fixture_graphql_200ok_with_error_response,
        caplog,
        error_type,
        expected_warning,
    ):
        """Test that only a few requests are made to the curated-corpus-api when it is down.
        Additionally, test that if the backend returns a GraphQL error, it is handled correctly.
        """
        async with AsyncClient(app=app, base_url="http://test") as ac:
            # Pre-warm the backend via an arbitrary API request. Without this, the initial UserAgentMiddleware call
            # incurs ~2-second latency, distorting the simulated downtime of `retry_wait_initial_seconds` seconds.
            await ac.get("/__heartbeat__")

            start_time = datetime.now()

            def temporary_downtime(*args, **kwargs):
                # Simulate the backend being unavailable for the minimum wait time.
                downtime_end = start_time + timedelta(
                    seconds=settings.curated_recommendations.corpus_api.retry_wait_initial_seconds
                )
                now = datetime.now()

                if now < downtime_end:
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
                        json=scheduled_surface_response_data,
                        request=fixture_request_data,
                    )

            scheduled_surface_http_client.post = AsyncMock(side_effect=temporary_downtime)

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
            assert scheduled_surface_http_client.post.call_count == 2

            # Assert that a warning was logged with a descriptive message.
            warnings = [r for r in caplog.records if r.levelname == "WARNING"]
            assert any(expected_warning in warning.message for warning in warnings)

    @pytest.mark.asyncio
    async def test_cache_returned_on_subsequent_calls(
        self, scheduled_surface_http_client, scheduled_surface_response_data, fixture_request_data
    ):
        """Test that the cache expires, and subsequent requests return new data."""
        with freezegun.freeze_time(tick=True) as frozen_datetime:
            async with AsyncClient(app=app, base_url="http://test") as ac:
                # First fetch to populate cache
                initial_response = await fetch_en_us(ac)
                initial_data = initial_response.json()

                for item in scheduled_surface_response_data["data"]["scheduledSurface"]["items"]:
                    item["corpusItem"]["title"] += " (NEW)"  # Change all the titles
                scheduled_surface_http_client.post.return_value = Response(
                    status_code=200,
                    json=scheduled_surface_response_data,
                    request=fixture_request_data,
                )

                # Progress time to after the cache expires.
                frozen_datetime.tick(delta=ScheduledSurfaceBackend.cache_time_to_live_max)
                frozen_datetime.tick(delta=timedelta(seconds=1))

                # When the cache is expired, the first fetch may return stale data.
                await fetch_en_us(ac)
                await asyncio.sleep(0.01)  # Allow asyncio background task to make an API request

                # Next fetch should get the new data
                new_response = await fetch_en_us(ac)
                assert scheduled_surface_http_client.post.call_count == 2
                new_data = new_response.json()
                assert new_data["recommendedAt"] > initial_data["recommendedAt"]
                assert all("NEW" in item["title"] for item in new_data["data"])

    @freezegun.freeze_time("2012-01-14 00:00:00", tick=True, tz_offset=0)
    @pytest.mark.asyncio
    async def test_valid_cache_returned_on_error(
        self, scheduled_surface_http_client, fixture_request_data, caplog
    ):
        """Test that the cache does not cache error data even if expired & returns latest valid data from cache."""
        with freezegun.freeze_time(tick=True) as frozen_datetime:
            async with AsyncClient(app=app, base_url="http://test") as ac:
                # First fetch to populate cache with good data
                initial_response = await fetch_en_us(ac)
                initial_data = initial_response.json()
                assert initial_response.status_code == 200
                assert scheduled_surface_http_client.post.call_count == 1

                # Simulate 503 error from Corpus API
                scheduled_surface_http_client.post.return_value = Response(
                    status_code=503,
                    request=fixture_request_data,
                )

                # Progress time to after the cache expires.
                frozen_datetime.tick(delta=ScheduledSurfaceBackend.cache_time_to_live_max)
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
                    scheduled_surface_http_client.post.call_count
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
                "corpus_api.scheduled_surface.timing",
                "corpus_api.scheduled_surface.status_codes.200",
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
        scheduled_surface_http_client,
        fixture_request_data,
        scheduled_surface_response_data,
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
                        json=scheduled_surface_response_data,
                        request=fixture_request_data,
                    )

            scheduled_surface_http_client.post = AsyncMock(side_effect=first_request_returns_error)

            await fetch_en_us(ac)

            # TODO: Remove reliance on internal details of aiodogstatsd
            metric_keys: list[str] = [call.args[0] for call in report.call_args_list]
            assert (
                metric_keys
                == [
                    "corpus_api.scheduled_surface.timing",
                    "corpus_api.scheduled_surface.status_codes.500",
                    "corpus_api.scheduled_surface.timing",
                    "corpus_api.scheduled_surface.status_codes.200",
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
            (ExperimentName.MODIFIED_PRIOR_EXPERIMENT.value, "control", False),
            (ExperimentName.MODIFIED_PRIOR_EXPERIMENT.value, "treatment", False),
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
                id_order = [item["corpusItemId"] for item in corpus_items]
                assert id_order not in past_id_orders, f"Duplicate order at iteration {i}."
                past_id_orders.append(id_order)  # a list of lists with all orders

                engagement_region = derived_region if regional_ranking_is_expected else None
                engagements = [
                    engagement_backend.get(item["corpusItemId"], region=engagement_region)
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


class TestSections:
    """Test the behavior of the sections feeds"""

    en_us_section_title_top_stories = "Popular Today"
    de_section_title_top_stories = "Meistgelesen"

    @pytest.mark.parametrize(
        "surface_id",
        [
            SurfaceId.NEW_TAB_EN_US,
            SurfaceId.NEW_TAB_DE_DE,
        ],
    )
    def test_section_translations(self, surface_id):
        """Check that there is a translation for every topic and top_stories_section.
        Currently, for en-US and DE.
        """
        # Define the mapping of strings to be replaced, use the Topic enum
        expected_translation_keys = [topic.value for topic in Topic]
        # top-stories is not in the Topic enum, do separately
        expected_translation_keys.append("top-stories")

        # Get the localized titles for the current surface_id
        localized_titles = LOCALIZED_SECTION_TITLES[surface_id]

        # Assert that each section title has a translation
        for key in expected_translation_keys:
            assert key in localized_titles and localized_titles[key], (
                f"Missing translation for '{key}' in " f"{surface_id}"
            )

    @pytest.mark.asyncio
    async def test_corpus_sections_feed_content(self):
        """Test the curated recommendations endpoint response is as expected
        when requesting the 'sections' feed for different locales.
        """
        async with AsyncClient(app=app, base_url="http://test") as ac:
            # Mock the endpoint to request the sections feed
            response = await ac.post(
                "/api/v1/curated-recommendations",
                json={
                    "locale": "en-US",
                    "feeds": ["sections"],
                    "experimentName": "new-tab-ml-sections",
                    "experimentBranch": "treatment",
                },
            )
            data = response.json()

            # Check if the response is valid
            assert response.status_code == 200

            feeds = data["feeds"]
            sections = {name: section for name, section in feeds.items() if section is not None}

            # Assert layouts are cycled
            assert_section_layouts_are_cycled(sections)

            assert "music" in sections

            # assert IAB metadata is present in ML sections (there are 8 of them)
            expected_iab_metadata = {
                "nfl": "484",
                "tv": "640",
                "music": "338",
                "movies": "324",
                "nba": "547",
                "soccer": "533",
                "mlb": None,
                "nhl": "515",
            }
            # Sections have their expected IAB metadata
            for section_name, expected_iab_code in expected_iab_metadata.items():
                section = feeds.get(section_name)
                if section:
                    if section["iab"]:
                        assert section["iab"]["taxonomy"] == "IAB-3.0"
                        assert (
                            section["iab"]["categories"][0] == expected_iab_code
                        )  # only 1 code is sent for now

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        "experiment_payload",
        [
            {},  # No experiment
            {"experimentName": "new-tab-ml-sections", "experimentBranch": "control"},
        ],
    )
    async def test_corpus_sections_feed_content_control(self, experiment_payload):
        """Test the curated recommendations endpoint response is as expected
        when requesting the 'sections' feed for different locales.
        """
        async with AsyncClient(app=app, base_url="http://test") as ac:
            # Mock the endpoint to request the sections feed
            response = await ac.post(
                "/api/v1/curated-recommendations",
                json={"locale": "en-US", "feeds": ["sections"]} | experiment_payload,
            )
            data = response.json()

            # Check if the response is valid
            assert response.status_code == 200

            feeds = data["feeds"]
            sections = {name: section for name, section in feeds.items() if section is not None}

            # Assert layouts are cycled
            assert_section_layouts_are_cycled(sections)

            # The only sections are topic sections or "top_stories_section"
            assert all(
                section_name == "top_stories_section" or section_name in Topic
                for section_name in sections
            )

    @pytest.mark.asyncio
    @pytest.mark.parametrize("locale", ["en-US", "de-DE"])
    @pytest.mark.parametrize(
        "experiment_payload",
        [
            {},  # No experiment
            {"experimentName": "new-tab-ml-sections", "experimentBranch": "treatment"},
        ],
    )
    async def test_sections_feed_content(self, locale, experiment_payload, caplog):
        """Test the curated recommendations endpoint response is as expected
        when requesting the 'sections' feed for different locales.
        """
        async with AsyncClient(app=app, base_url="http://test") as ac:
            # Mock the endpoint to request the sections feed
            response = await ac.post(
                "/api/v1/curated-recommendations",
                json={"locale": locale, "feeds": ["sections"]} | experiment_payload,
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

            # Assert layouts are cycled
            assert_section_layouts_are_cycled(sections)

            # The fixture data contains enough recommendations for at least 4 sections. The number
            # of sections varies because top_stories_section is determined by Thompson sampling,
            # and therefore the number of recs per topics is non-deterministic.
            assert len(sections) >= 4

            # Section receivedFeedRank should be numbered 0, 1, 2, ..., len(sections) - 1.
            assert {s["receivedFeedRank"] for s in sections.values()} == set(range(len(sections)))
            # Recommendation receivedRank should be numbered 0, 1, 2, ..., len(recommendations) - 1.
            for section in sections.values():
                recs = section["recommendations"]
                assert {rec["receivedRank"] for rec in recs} == set(range(len(recs)))

            # Check if non-ML experiment, only legacy sections returned
            legacy_topics = {topic.value for topic in Topic}

            if experiment_payload.get("experimentName") != "new-tab-ml-sections":
                # Non-ML sections experiment: All section keys (excluding top_stories) must be in legacy topics
                for sid in sections:
                    if sid != "top_stories_section":
                        assert sid in legacy_topics

            # Check the recs used in top_stories_section are removed from their original ML sections.
            top_story_ids = {
                rec["corpusItemId"] for rec in sections["top_stories_section"]["recommendations"]
            }

            for sid, sec in sections.items():
                if sid != "top_stories_section":
                    for rec in sec["recommendations"]:
                        assert rec["corpusItemId"] not in top_story_ids

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        "sections_payload",
        [
            {},
            {"sections": [{"sectionId": "sports", "isFollowed": True, "isBlocked": False}]},
        ],
    )
    @pytest.mark.parametrize(
        "experiment_payload",
        [
            {},  # No experiment
            {"experimentName": "new-tab-ml-sections", "experimentBranch": "treatment"},
        ],
    )
    async def test_sections_layouts(self, sections_payload, experiment_payload):
        """Test that the correct layouts & ads are returned along with sections."""
        async with AsyncClient(app=app, base_url="http://test") as ac:
            response = await ac.post(
                "/api/v1/curated-recommendations",
                json={"locale": "en-US", "feeds": ["sections"]}
                | sections_payload
                | experiment_payload,
            )
            assert response.status_code == 200
            data = response.json()
            feeds = data["feeds"]
            sections = {name: section for name, section in feeds.items() if section is not None}

            # All sections have a layout.
            assert all(Layout(**section["layout"]) for section in sections.values())

            # Find the first and second sections by their receivedFeedRank.
            first_section = next(
                (s for s in sections.values() if s["receivedFeedRank"] == 0), None
            )
            assert first_section is not None

            # Assert layout of the first section (Popular Today).
            assert first_section["title"] == "Popular Today"
            assert first_section["layout"]["name"] == "4-large-small-medium-1-ad"

            # Assert layouts are cycled
            assert_section_layouts_are_cycled(sections)

            # Assert only sections 1,2,3,5,7,9 (ranks: 0,1,2,4,6,8) have ads
            expected_section_ranks_with_ads = {0, 1, 2, 4, 6, 8}
            for section in sections.values():
                tiles_with_ads = [
                    tile
                    for layout in section["layout"]["responsiveLayouts"]
                    for tile in layout["tiles"]
                    if tile["hasAd"]
                ]
                if section["receivedFeedRank"] in expected_section_ranks_with_ads:
                    assert tiles_with_ads
                else:
                    assert not tiles_with_ads

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        "experiment_payload",
        [
            {},  # No experiment
            {"experimentName": "new-tab-ml-sections", "experimentBranch": "treatment"},
        ],
    )
    async def test_curated_recommendations_with_sections_feed_boost_followed_sections(
        self, caplog, experiment_payload
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
                }
                | experiment_payload,
            )
            data = response.json()
            feeds = data["feeds"]
            sections = {name: section for name, section in feeds.items() if section is not None}

            # Check if the response is valid
            assert response.status_code == 200

            # assert isFollowed & isBlocked have been correctly set
            if data["feeds"].get("arts") is not None:
                assert data["feeds"]["arts"]["isFollowed"]
                # assert followed section ARTS comes after top-stories and before unfollowed sections (education).
                assert data["feeds"]["arts"]["receivedFeedRank"] in [1, 2]
                assert data["feeds"]["arts"]["iab"] == {
                    "taxonomy": "IAB-3.0",
                    "categories": ["JLBCU7"],
                }
            if data["feeds"].get("education") is not None:
                assert not data["feeds"]["education"]["isFollowed"]
                assert data["feeds"]["education"]["isBlocked"]
            if data["feeds"].get("sports") is not None:
                assert data["feeds"]["sports"]["isFollowed"]
                # assert followed section SPORTS comes after top-stories and before unfollowed sections (education).
                assert data["feeds"]["sports"]["receivedFeedRank"] in [1, 2]
                assert data["feeds"]["sports"]["iab"] == {
                    "taxonomy": "IAB-3.0",
                    "categories": ["483"],
                }

            # Assert layouts are cycled
            assert_section_layouts_are_cycled(sections)

            # Assert no errors were logged
            errors = [r for r in caplog.records if r.levelname == "ERROR"]
            assert len(errors) == 0

    @pytest.mark.asyncio
    async def test_curated_recommendations_with_sections_feed_removes_blocked_topics(self, caplog):
        """Test that when topic sections are blocked, those recommendations don't show up, not even
        in other sections like Popular Today.
        """
        blocked_topics = [Topic.CAREER.value, Topic.SCIENCE.value, Topic.HEALTH_FITNESS.value]

        async with AsyncClient(app=app, base_url="http://test") as ac:
            # Mock the endpoint to request the sections feed
            response = await ac.post(
                "/api/v1/curated-recommendations",
                json={
                    "locale": "en-US",
                    "feeds": ["sections"],
                    "sections": [
                        {"sectionId": topic_id, "isFollowed": False, "isBlocked": True}
                        for topic_id in blocked_topics
                    ],
                },
            )
            data = response.json()

            feeds = data["feeds"]
            sections = {name: section for name, section in feeds.items() if section is not None}

            # Assert layouts are cycled
            assert_section_layouts_are_cycled(sections)

            # assert that none of the recommendations has a blocked topic.
            for _, feed in feeds.items():
                if feed:
                    for recommendation in feed["recommendations"]:
                        assert recommendation["topic"] not in blocked_topics

    @pytest.mark.asyncio
    @freezegun.freeze_time("2025-03-20 12:00:00", tz_offset=0)
    async def test_curated_recommendations_with_sections_feed_followed_at(self, caplog):
        """Test the curated recommendations endpoint response is as expected
        when requesting the 'sections' feed for en-US locale & providing followedAt.
        Most recently followed sections are boosted higher and response fields are set correctly.
        """
        async with AsyncClient(app=app, base_url="http://test") as ac:
            # Mock the endpoint to request the sections feed
            response = await ac.post(
                "/api/v1/curated-recommendations",
                json={
                    "locale": "en-US",
                    "feeds": ["sections"],
                    "sections": [
                        {
                            "sectionId": "sports",
                            "isFollowed": True,
                            "isBlocked": False,
                            "followedAt": "2025-03-17T12:00:00Z",
                        },
                        {
                            "sectionId": "arts",
                            "isFollowed": True,
                            "isBlocked": False,
                            "followedAt": "2025-03-10T14:34:56+02:00",
                        },
                        {"sectionId": "education", "isFollowed": False, "isBlocked": True},
                    ],
                },
            )
            data = response.json()

            # Check if the response is valid
            assert response.status_code == 200

            # assert isFollowed & isBlocked & followedAt have been correctly set
            if data["feeds"].get("arts") is not None:
                assert data["feeds"]["arts"]["isFollowed"]
                # assert followed section ARTS comes after top-stories and before unfollowed sections (education).
                assert data["feeds"]["arts"]["receivedFeedRank"] in [1, 2]
                assert data["feeds"]["arts"]["followedAt"]
            if data["feeds"].get("education") is not None:
                assert not data["feeds"]["education"]["isFollowed"]
                assert not data["feeds"]["education"]["followedAt"]
                assert data["feeds"]["education"]["isBlocked"]
            if data["feeds"].get("sports") is not None:
                assert data["feeds"]["sports"]["isFollowed"]
                # assert followed section SPORTS comes after top-stories and before unfollowed sections (education).
                assert data["feeds"]["sports"]["receivedFeedRank"] in [1, 2]
                assert data["feeds"]["sports"]["followedAt"]

            # in the case both sections are present, sports is recently followed & needs to have higher rank
            if data["feeds"].get("arts") is not None and data["feeds"].get("sports") is not None:
                assert data["feeds"]["sports"]["receivedFeedRank"] == 1
                assert data["feeds"]["arts"]["receivedFeedRank"] == 2

            # Assert no errors were logged
            errors = [r for r in caplog.records if r.levelname == "ERROR"]
            assert len(errors) == 0

    @pytest.mark.asyncio
    @freezegun.freeze_time("2025-03-20 12:00:00", tz_offset=0)
    @pytest.mark.parametrize(
        "sections_payload",
        [
            [
                {
                    "sectionId": "arts",
                    "isFollowed": True,
                    "isBlocked": False,
                    "followedAt": "2025-03-17T12:00:00",  # Missing timezone
                },
            ],
            [
                {
                    "sectionId": "health",
                    "isFollowed": True,
                    "isBlocked": False,
                    "followedAt": "March 17, 2025 12:00 PM",  # Not ISO format
                },
            ],
            [
                {
                    "sectionId": "business",
                    "isFollowed": True,
                    "isBlocked": False,
                    "followedAt": 1742500800,  # Unix timestamp as int
                },
            ],
            [
                {
                    "sectionId": "business",
                    "isFollowed": True,
                    "isBlocked": False,
                    "followedAt": "invalid string",  # bad string
                },
            ],
        ],
    )
    async def test_curated_recommendations_with_invalid_followed_at_formats(
        self, sections_payload
    ):
        """Test the curated recommendations endpoint response when providing invalid followedAt time formats:
        - missing timezone
        - not ISO format
        - Unix timestamp as integer
        """
        async with AsyncClient(app=app, base_url="http://test") as ac:
            payload = {
                "locale": "en-US",
                "feeds": ["sections"],
            }
            if sections_payload is not None:
                payload["sections"] = sections_payload
            response = await ac.post("/api/v1/curated-recommendations", json=payload)
            # assert 400 is returned for invalid followedAt
            assert response.status_code == 400

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        "locale, expected_titles",
        [
            (
                "en-US",
                {
                    "top_stories_section": "Popular Today",
                    "arts": "Entertainment",
                    "education": "Education",
                    "sports": "Sports",
                },
            ),
            (
                "de-DE",
                {
                    "top_stories_section": "Meistgelesen",
                    "Career": "Karriere",
                    "Education": "Bildung",
                    "Sports": "Sport",
                },
            ),
        ],
    )
    async def test_sections_feed_titles(self, locale, expected_titles):
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

    @pytest.mark.asyncio
    @pytest.mark.parametrize("enable_interest_picker", [True, False])
    async def test_sections_interest_picker(self, enable_interest_picker, monkeypatch):
        """Test the curated recommendations endpoint returns an interest picker when enabled"""
        # The fixture data doesn't have enough sections for the interest picker to show up, so lower
        # the minimum number of sections that it needs to have to 1.
        monkeypatch.setattr(interest_picker, "MIN_INTEREST_PICKER_COUNT", 1)

        async with AsyncClient(app=app, base_url="http://test") as ac:
            response = await ac.post(
                "/api/v1/curated-recommendations",
                json={
                    "locale": "en-US",
                    "feeds": ["sections"],
                    "enableInterestPicker": enable_interest_picker,
                },
            )
            data = response.json()

            feeds = data["feeds"]
            sections = {name: section for name, section in feeds.items() if section is not None}

            # Assert layouts are cycled
            assert_section_layouts_are_cycled(sections)

            interest_picker_response = data["interestPicker"]
            if enable_interest_picker:
                assert interest_picker_response is not None
            else:
                assert interest_picker_response is None
            # Ensure top_stories_section always has receivedFeedRank == 0
            top_stories_section = data["feeds"].get("top_stories_section")
            assert top_stories_section is not None
            assert top_stories_section["receivedFeedRank"] == 0

    @pytest.mark.asyncio
    @pytest.mark.parametrize("enable_interest_picker", [True, False])
    async def test_sections_interest_picker_ml_sections(self, enable_interest_picker, monkeypatch):
        """Test the curated recommendations endpoint returns expected response when an
        interest picker & ML sections enabled
        """
        # The fixture data doesn't have enough sections for the interest picker to show up, so lower
        # the minimum number of sections that it needs to have to 1.
        monkeypatch.setattr(interest_picker, "MIN_INTEREST_PICKER_COUNT", 1)

        async with AsyncClient(app=app, base_url="http://test") as ac:
            response = await ac.post(
                "/api/v1/curated-recommendations",
                json={
                    "experimentName": "optin-new-tab-ml-sections",
                    "experimentBranch": "treatment",
                    "utc_offset": 17,
                    "coarse_os": "windows",
                    "surface_id": "",
                    "locale": "en-US",
                    "region": "US",
                    "enableInterestPicker": enable_interest_picker,
                    "feeds": ["sections"],
                },
            )
            data = response.json()

            feeds = data["feeds"]
            sections = {name: section for name, section in feeds.items() if section is not None}

            # Assert layouts are cycled
            assert_section_layouts_are_cycled(sections)

            interest_picker_response = data["interestPicker"]
            if enable_interest_picker:
                assert interest_picker_response is not None
            else:
                assert interest_picker_response is None
            # Ensure top_stories_section always has receivedFeedRank == 0
            top_stories_section = data["feeds"].get("top_stories_section")
            assert top_stories_section is not None
            assert top_stories_section["receivedFeedRank"] == 0

    @pytest.mark.parametrize(
        "repeat",  # See thompson_sampling config in testing.toml for how to repeat this test.
        range(settings.curated_recommendations.rankers.thompson_sampling.test_repeat_count),
    )
    @pytest.mark.asyncio
    async def test_ml_sections_thompson_sampling(self, repeat):
        """Test that Thompson sampling is applied to ML sections"""
        async with AsyncClient(app=app, base_url="http://test") as ac:
            # Mock the endpoint to request the sections feed
            response = await ac.post(
                "/api/v1/curated-recommendations",
                json={
                    "locale": "en-US",
                    "feeds": ["sections"],
                    "experimentName": "new-tab-ml-sections",
                    "experimentBranch": "treatment",
                },
            )
            data = response.json()

            # Check if the response is valid
            assert response.status_code == 200

            feeds = data["feeds"]
            music_recs = feeds["music"]["recommendations"]  # ML feed

            sections = {name: section for name, section in feeds.items() if section is not None}

            # Assert layouts are cycled
            assert_section_layouts_are_cycled(sections)

            # Check the recs used in top_stories_section are removed from their original ML sections.
            top_story_ids = {
                rec["corpusItemId"] for rec in feeds["top_stories_section"]["recommendations"]
            }

            for sid, section in feeds.items():
                if sid != "top_stories_section":
                    for rec in section["recommendations"]:
                        assert rec["corpusItemId"] not in top_story_ids

            # The expected ML sectionItem has 100% CTR, and is always present in the ML section part of the response.
            expected_high_ctr_id = "41111154-ebb1-45d9-9799-a882f13cd8cc"
            # Find the receivedRank of the high CTR ML sectionItem
            high_item_rank = next(
                (
                    rec["receivedRank"]
                    for rec in music_recs
                    if rec["corpusItemId"] == expected_high_ctr_id
                ),
                None,
            )
            assert high_item_rank < 3

    @pytest.mark.asyncio
    @pytest.mark.parametrize("enable_interest_vector", [True, False])
    async def test_sections_model_interest_vector(self, enable_interest_vector, monkeypatch):
        """Test the curated recommendations endpoint returns a model when interest vector is passed"""
        async with AsyncClient(app=app, base_url="http://test") as ac:
            response = await ac.post(
                "/api/v1/curated-recommendations",
                json={
                    "locale": Locale.EN_US,
                    "feeds": ["sections"],
                    "inferredInterests": {} if enable_interest_vector else None,
                },
            )
            data = response.json()
            local_model = data["inferredLocalModel"]
            if enable_interest_vector:
                assert local_model is not None
            else:
                assert local_model is None

    @pytest.mark.asyncio
    async def test_sections_model_interest_vector_greedy_ranking(self, monkeypatch):
        """Test the curated recommendations endpoint ranks sections accorcding to inferredInterests"""
        # define interest vector
        interests = {
            "education-science": 1.0,
            "food": 0.8,
            "government": 0.7,
            "society": 0.00001,
            "model_id": "fake_model_id",
        }
        # make the api call
        async with AsyncClient(app=app, base_url="http://test") as ac:
            response = await ac.post(
                "/api/v1/curated-recommendations",
                json={
                    "locale": Locale.EN_US,
                    "feeds": ["sections"],
                    "inferredInterests": interests,
                },
            )
            data = response.json()
            # expect intests to be sorted by value
            sorted_interests = sorted(
                [k for k, v in interests.items() if isinstance(v, float)], key=interests.get
            )[::-1]
            # expect top stories to be first
            sorted_interests.insert(0, "top_stories_section")
            # order is in receivedFeedRank
            for i, sec in enumerate(sorted_interests):
                assert data["feeds"][sec]["receivedFeedRank"] == i

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        "repeat",
        range(settings.curated_recommendations.rankers.thompson_sampling.test_repeat_count),
    )
    async def test_sections_ranked_by_top_items_engagement(self, repeat, engagement_backend):
        """Sections should be ordered so that those with higher average CTR
        among their top 3 items get a better (lower) feed rank.
        """
        async with AsyncClient(app=app, base_url="http://test") as ac:
            response = await ac.post(
                "/api/v1/curated-recommendations",
                json={
                    "locale": "en-US",
                    "feeds": ["sections"],
                    "experimentName": "new-tab-ml-sections",
                    "experimentBranch": "treatment",
                },
            )
            assert response.status_code == 200
            feeds = response.json()["feeds"]

            # exclude top_stories_section, which by definition has high engagement.
            sections = [
                section
                for name, section in feeds.items()
                if section and name != "top_stories_section"
            ]

            # compute average CTR of the top recs in each section
            avg_ctrs = []
            for sec in sections:
                recs = sec["recommendations"][:6]
                ctrs = []
                for rec in recs:
                    e = engagement_backend.get(rec["corpusItemId"], region=None)
                    if e:
                        ctrs.append(e.click_count / e.impression_count)
                # if no data, treat as 0
                avg = sum(ctrs) / len(ctrs) if ctrs else 0.0
                avg_ctrs.append((sec["receivedFeedRank"], avg))

            # regression: feedRank vs avg CTR should have negative slope
            ranks, avgs = zip(*avg_ctrs)
            slope, _, _, _, _ = linregress(ranks, avgs)
            assert slope < 0, f"Sections not ordered by engagement (slope={slope})"

    @pytest.mark.parametrize(
        "locale,region,derived_region",
        [
            ("en-US", None, "US"),
            ("en-US", "IN", "IN"),
            ("fr-FR", "FR", "FR"),
        ],
    )
    @pytest.mark.asyncio
    async def test_sections_pass_region_to_engagement_backend(
        self,
        locale,
        region,
        derived_region,
        mocker,
        engagement_backend,
        scheduled_surface_http_client,
        fixture_request_data,
    ):
        """Ensure that when fetching a 'sections' feed we pass the right region into engagement.get"""
        spy = mocker.spy(engagement_backend, "get")

        async with AsyncClient(app=app, base_url="http://test") as ac:
            await ac.post(
                "/api/v1/curated-recommendations",
                json={
                    "locale": locale,
                    "region": region,
                    "feeds": ["sections"],
                    "experimentName": "new-tab-ml-sections",
                    "experimentBranch": "treatment",
                },
            )

        def passed_region(call):
            # first look for keyword, otherwise fall back to positional second arg
            if "region" in call.kwargs:
                return call.kwargs["region"]
            if len(call.args) > 1:
                return call.args[1]
            return None

        assert any(
            passed_region(call) == derived_region for call in spy.call_args_list
        ), f"No engagement.get(..., region={repr(derived_region)}) in {spy.call_args_list}"


@pytest.mark.asyncio
async def test_curated_recommendations_enriched_with_icons(
    manifest_provider,
    scheduled_surface_http_client,
    fixture_request_data,
):
    """Test the enrichment of a curated recommendation with an added icon-url."""
    # Set up the manifest data first
    manifest_provider.manifest_data.domains = [
        Domain(
            rank=2,
            title="Microsoft – AI, Cloud, Productivity, Computing, Gaming & Apps",
            url="https://www.microsoft.com",
            domain="microsoft",
            icon="https://merino-images.services.mozilla.com/favicons/microsoft-icon.png",
            categories=["Business", "Information Technology"],
            serp_categories=[0],
        )
    ]
    manifest_provider.domain_lookup_table = {"microsoft": 0}

    mocked_response = {
        "data": {
            "scheduledSurface": {
                "items": [
                    {
                        "id": "scheduledSurfaceItemId-ABC",
                        "corpusItem": {
                            "id": "corpusItemId-XYZ",
                            "url": "https://www.microsoft.com/some-article?utm_source=firefox-newtab-en-us",
                            "title": "Some MS Article",
                            "excerpt": "All about Microsoft something",
                            "topic": "tech",
                            "publisher": "ExamplePublisher",
                            "isTimeSensitive": False,
                            "imageUrl": "https://somewhere.com/test.jpg",
                        },
                    }
                ]
            }
        }
    }
    scheduled_surface_http_client.post.return_value = Response(
        status_code=200,
        json=mocked_response,
        request=fixture_request_data,
    )

    async with AsyncClient(app=app, base_url="http://test") as ac:
        response = await ac.post(
            "/api/v1/curated-recommendations",
            json={"locale": "en-US"},
        )
        assert response.status_code == 200

    data = response.json()
    items = data["data"]
    assert len(items) == 1

    item = items[0]
    assert item["url"] == "https://www.microsoft.com/some-article?utm_source=firefox-newtab-en-us"

    assert "iconUrl" in item
    assert (
        item["iconUrl"] == "https://merino-images.services.mozilla.com/favicons/microsoft-icon.png"
    )

    # Clean up
    if get_provider in app.dependency_overrides:
        del app.dependency_overrides[get_provider]
