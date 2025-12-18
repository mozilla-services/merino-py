"""Tests the curated recommendation endpoint /api/v1/curated-recommendations"""

import asyncio
import json
from datetime import timedelta, datetime
import logging
from typing import Any
from unittest.mock import AsyncMock
from uuid import UUID

import aiodogstatsd
from fastapi.testclient import TestClient
import freezegun
import numpy as np
import pytest
from httpx import Response, HTTPStatusError
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
    MLRecsBackend,
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
from merino.curated_recommendations.ml_backends.static_local_model import (
    CONTEXTUAL_RANKING_TREATMENT_COUNTRY,
    CONTEXTUAL_RANKING_TREATMENT_TZ,
    DEFAULT_PRODUCTION_MODEL_ID,
)
from merino.curated_recommendations.ml_backends.protocol import (
    ContextualArticleRankings,
    InferredLocalModel,
    ModelData,
    ModelType,
    DayTimeWeightingConfig,
)
from merino.curated_recommendations.prior_backends.engagment_rescaler import (
    SECTIONS_HOLDBACK_TOTAL_PERCENT,
)
from merino.curated_recommendations.prior_backends.protocol import PriorBackend
from merino.curated_recommendations.protocol import (
    ExperimentName,
    DailyBriefingBranch,
    Layout,
    Locale,
    CoarseOS,
)
from merino.main import app
from merino.providers.manifest import get_provider as get_manifest_provider
from merino.providers.manifest.backends.protocol import Domain
from tests.types import FilterCaplogFixture

# Music, NFL, Movies, Soccer, NBA
REC_HIGH_CTR_IDS = [
    "b2c10703-5377-4fe8-89d3-32fbd7288187",
    "f509393b-c1d6-4500-8ed2-29f8a23f39a7",
    "2afcef43-4663-446e-9d69-69cbc6966162",
    "dc4b30c4-170b-4e9f-a068-bdc51474a0fb",
    "9261e868-beff-4419-8071-7750d063d642",
    "63909b8c-a619-45f3-9ebc-fd8fcaeb72b1",
]


def is_manual_section(section_id: str) -> bool:
    """Check if section ID is a UUID (manually created sections use UUIDs, ML sections use human-readable IDs).

    Note: This heuristic may become obsolete if all sections adopt UUID identifiers in the future.
    """
    try:
        UUID(section_id)
        return True
    except ValueError:
        return False


class MockMLRecommendationsBackend(MLRecsBackend):
    """Mock class implementing the protocol for MLRecsBackend."""

    def __init__(self) -> None:
        super().__init__()
        HIGH_CONTEXUAL_SCORES = {k: [1.0, 1.0] for k in REC_HIGH_CTR_IDS}

        self.data: dict[str, ContextualArticleRankings] = {}
        rankings = ContextualArticleRankings(
            granularity="not_set",
            # Give low scores to all except high CTR items
            shards={
                **HIGH_CONTEXUAL_SCORES,
                "1ac64aea-fdce-41e7-b017-0dc2103bb3fd": [0.001, 0.001],
            },
        )
        self.data["global"] = rankings
        self.data["US"] = rankings
        tz_rankings = ContextualArticleRankings(
            granularity="not_set",
            # Extra item is crazy high
            shards={
                **HIGH_CONTEXUAL_SCORES,
                "1ac64aea-fdce-41e7-b017-0dc2103bb3fd": [10000, 10000],
            },
        )
        self.data["US_16"] = tz_rankings  # PDT timezone

    def get(
        self, region: str | None = None, utcOffset: str | None = None
    ) -> ContextualArticleRankings | None:
        """Return sample ML recommendations"""
        if region and utcOffset:
            key = f"{region}_{utcOffset}"
            rankings = self.data.get(key, None)
            if rankings:
                return rankings
        if region:
            rankings = self.data.get(region, None)
            if rankings:
                return rankings
        return self.data.get("global", None)

    def is_valid(self) -> bool:
        """Return whether the backend is valid."""
        return True

    def get_most_popular_content_id_by_timezone(self, utcOffset: int) -> str:
        """Return the most popular content ID for a given timezone offset."""
        if utcOffset == 16:
            return "1ac64aea-fdce-41e7-b017-0dc2103bb3fd"  # High scoring item in US_16
        return REC_HIGH_CTR_IDS[0]  # Default high CTR item


class MockEngagementBackend(EngagementBackend):
    """Mock class implementing the protocol for EngagementBackend.
    experiment_traffic_fraction defines a fraction of traffic expected for an experiment

    The merino service Rescaler class will scale the traffic up, so we must scale it down in terms
    of what is estimated as the real-world traffic.
    """

    def __init__(self, experiment_traffic_fraction: float = 1.0) -> None:
        # {corpusItemId: (reports, impressions)}
        self.metrics: dict[str, tuple[int, int]] = {}
        self.experiment_traffic_fraction = experiment_traffic_fraction
        # Optional overrides for deterministic CTRs keyed by corpusItemId.
        self.ctr_overrides: dict[str, tuple[int, int]] = {}

    def get(self, corpus_item_id: str, region: str | None = None) -> Engagement | None:
        """Return random click and impression counts based on the scheduled corpus id and region."""
        if corpus_item_id in self.ctr_overrides:
            clicks, impressions = self.ctr_overrides[corpus_item_id]
            return Engagement(
                corpus_item_id=corpus_item_id,
                region=region,
                click_count=clicks,
                impression_count=impressions,
            )
        if corpus_item_id in self.metrics:
            reports, impressions = self.metrics[corpus_item_id]
            return Engagement(
                corpus_item_id=corpus_item_id,
                region=region,
                click_count=0,
                impression_count=impressions,
                report_count=reports,
            )

        VERY_HIGH_CTR = {
            k: (
                1_000_000 * self.experiment_traffic_fraction,
                1_000_000 * self.experiment_traffic_fraction,
            )
            for k in REC_HIGH_CTR_IDS
        }
        HIGH_CTR_ITEMS = {
            **VERY_HIGH_CTR,
            "41111154-ebb1-45d9-9799-a882f13cd8cc": (
                990_000 * self.experiment_traffic_fraction,
                1_000_000 * self.experiment_traffic_fraction,
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


def seed_deterministic_ctr_overrides(
    engagement_backend: MockEngagementBackend, feeds: dict[str, Any]
) -> None:
    """Assign deterministic CTR overrides to ensure ranking tests stay stable."""
    baseline_sections = {
        name: section
        for name, section in feeds.items()
        if section and name != "top_stories_section"
    }
    assert len(baseline_sections) >= 2

    sorted_section_ids = sorted(baseline_sections)
    split_idx = max(1, len(sorted_section_ids) // 2)
    favored_section_ids = sorted_section_ids[:split_idx]
    deprioritized_section_ids = sorted_section_ids[split_idx:]

    engagement_backend.ctr_overrides.clear()

    def assign_overrides(section_ids: list[str], clicks: int, impressions: int) -> None:
        for sid in section_ids:
            for rec in baseline_sections[sid]["recommendations"][:6]:
                engagement_backend.ctr_overrides[rec["corpusItemId"]] = (clicks, impressions)

    assign_overrides(favored_section_ids, clicks=1_000_000, impressions=1_000_000)
    assign_overrides(deprioritized_section_ids, clicks=1_000, impressions=1_000_000)


class MockLocalModelBackend(LocalModelBackend):
    """Mock class implementing the protocol for EngagementBackend."""

    def get(
        self,
        surface_id: str | None = None,
        model_id: str | None = None,
        experiment_name: str | None = None,
        experiment_branch: str | None = None,
    ) -> InferredLocalModel | None:
        """Return sample local model"""
        model_data = ModelData(
            model_type=ModelType.CLICKS,
            rescale=True,
            noise_scale=0.002,
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
    """Fixture for the MockEngagementBackend for standard use case"""
    return MockEngagementBackend()


@pytest.fixture
def ml_recommendations_backend():
    """Fixture for the MockMLRecommendationsBackend for standard use case"""
    return MockMLRecommendationsBackend()


@pytest.fixture
def engagement_backend_legacy_sections_us():
    """Fixture for the MockEngagementBackend for an experiment that has a fraction of traffic"""
    return MockEngagementBackend(SECTIONS_HOLDBACK_TOTAL_PERCENT)


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
    ml_recommendations_backend: MLRecsBackend,
) -> CuratedRecommendationsProvider:
    """Mock curated recommendations provider."""
    return CuratedRecommendationsProvider(
        scheduled_surface_backend=scheduled_surface_backend,
        engagement_backend=engagement_backend,
        prior_backend=prior_backend,
        sections_backend=sections_backend,
        local_model_backend=local_model_backend,
        ml_recommendations_backend=ml_recommendations_backend,
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


def fetch_en_us(client: TestClient) -> Response:
    """Make a curated recommendations request with en-US locale and sections feed."""
    return client.post(
        "/api/v1/curated-recommendations",
        json={"locale": "en-US", "feeds": ["sections"], "topics": [Topic.FOOD]},
    )


def fetch_de_de(client: TestClient) -> Response:
    """Make a curated recommendations request with de-DE locale (uses scheduled_surface backend)"""
    return client.post(
        "/api/v1/curated-recommendations", json={"locale": "de-DE", "topics": [Topic.FOOD]}
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
@pytest.mark.parametrize(
    "repeat",  # See thompson_sampling config in testing.toml for how to repeat this test.
    range(settings.curated_recommendations.rankers.thompson_sampling.test_repeat_count),
)
def test_curated_recommendations_sections_request(repeat, client: TestClient):
    """Test the curated recommendations endpoint with sections feed."""
    response = fetch_en_us(client)
    data = response.json()

    assert response.status_code == 200
    assert data["surfaceId"] == SurfaceId.NEW_TAB_EN_US

    # Sections requests return data in feeds, not data
    assert data["data"] == []
    feeds = data["feeds"]
    sections = {name: section for name, section in feeds.items() if section is not None}

    # At least one section should be present
    assert len(sections) > 0

    # All sections should have recommendations with expected fields
    for section in sections.values():
        for item in section["recommendations"]:
            assert item["url"]
            assert item["publisher"]
            assert item["imageUrl"]
            assert item["features"]
            # Sections requests do not set scheduledCorpusItemId or tileId
            assert item["scheduledCorpusItemId"] is None
            assert item["tileId"] is None


class TestLegacyEndpoints:
    """Test the legacy curated recommendations endpoints (fx114 and fx115-129).

    These endpoints have two code paths:
    - US/CA locales (en-US, en-CA): use sections backend via get_legacy_recommendations_from_sections
    - Other locales (de-DE, en-GB, etc.): use scheduler backend via CuratedRecommendationsProvider
    """

    # Locales that use the sections backend (US/CA)
    SECTIONS_BACKEND_LOCALES = ["en-US", "en-CA"]
    # Locales that use the scheduler backend (non-US/CA)
    SCHEDULER_BACKEND_LOCALES = ["de-DE", "en-GB", "fr-FR", "es-ES", "it-IT"]

    @pytest.mark.parametrize(
        "locale",
        SECTIONS_BACKEND_LOCALES + SCHEDULER_BACKEND_LOCALES,
    )
    def test_fx115_129_returns_valid_response(self, locale: str, client: TestClient):
        """Test the legacy fx115-129 endpoint returns expected response for all supported locales."""
        response = client.get(
            "/api/v1/curated-recommendations/legacy-115-129", params={"locale": locale}
        )

        assert response.status_code == 200
        data = response.json()
        corpus_items = data["data"]

        # Default max is 30 items
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

    @pytest.mark.parametrize(
        "locale_lang",
        SECTIONS_BACKEND_LOCALES + SCHEDULER_BACKEND_LOCALES,
    )
    def test_fx114_returns_valid_response(self, locale_lang: str, client: TestClient):
        """Test the legacy fx114 endpoint returns expected response for all supported locales."""
        response = client.get(
            "/api/v1/curated-recommendations/legacy-114",
            params={"locale_lang": locale_lang},
        )

        assert response.status_code == 200
        data = response.json()
        corpus_items = data["recommendations"]

        # Default max is 20 items
        assert len(corpus_items) == 20
        # Assert all corpus_items have expected fields populated.
        assert all(item["id"] for item in corpus_items)
        assert all(item["title"] for item in corpus_items)
        assert all(item["url"] for item in corpus_items)
        assert all(item["excerpt"] for item in corpus_items)
        assert all(item["domain"] for item in corpus_items)
        assert all(item["image_src"] for item in corpus_items)
        assert all(item["raw_image_src"] for item in corpus_items)

    @pytest.mark.parametrize(
        "endpoint,locale_param,count_param,default_count",
        [
            ("legacy-115-129", "locale", "count", 30),
            ("legacy-114", "locale_lang", "count", 20),
        ],
    )
    @pytest.mark.parametrize("locale", SECTIONS_BACKEND_LOCALES + SCHEDULER_BACKEND_LOCALES)
    def test_count_parameter(
        self,
        endpoint: str,
        locale_param: str,
        count_param: str,
        default_count: int,
        locale: str,
        client: TestClient,
    ):
        """Test that the count parameter limits results for both endpoints and all locales."""
        requested_count = 5
        response = client.get(
            f"/api/v1/curated-recommendations/{endpoint}",
            params={locale_param: locale, count_param: requested_count},
        )

        assert response.status_code == 200
        data = response.json()

        # Get items from correct response field
        items = data["data"] if endpoint == "legacy-115-129" else data["recommendations"]
        assert len(items) == requested_count

    @pytest.mark.parametrize(
        "endpoint,locale_param",
        [
            ("legacy-115-129", "locale"),
            ("legacy-114", "locale_lang"),
        ],
    )
    def test_region_parameter(self, endpoint: str, locale_param: str, client: TestClient):
        """Test that the region parameter is accepted for both endpoints."""
        response = client.get(
            f"/api/v1/curated-recommendations/{endpoint}",
            params={locale_param: "en-US", "region": "CA"},
        )

        assert response.status_code == 200

    @freezegun.freeze_time("2012-01-14 03:21:34", tz_offset=0)
    def test_en_us_non_sections_request(self, client: TestClient):
        """Test en-US non-sections request via main endpoint (backward-compatible path).

        This tests the main /api/v1/curated-recommendations endpoint with en-US locale
        but WITHOUT feeds=["sections"], which uses get_legacy_recommendations_from_sections.
        """
        response = client.post(
            "/api/v1/curated-recommendations",
            json={"locale": "en-US"},
        )
        data = response.json()

        assert response.status_code == 200
        assert data["surfaceId"] == SurfaceId.NEW_TAB_EN_US

        # Non-sections request returns data in data[], not feeds
        corpus_items = data["data"]
        assert len(corpus_items) == 100

        # Assert all items have expected fields
        assert all(item["url"] for item in corpus_items)
        assert all(item["publisher"] for item in corpus_items)
        assert all(item["imageUrl"] for item in corpus_items)
        assert all(item["tileId"] for item in corpus_items)
        # scheduledCorpusItemId equals corpusItemId (sections backend behavior)
        assert all(item["scheduledCorpusItemId"] == item["corpusItemId"] for item in corpus_items)

        # Assert receivedRank is sequential
        for i, item in enumerate(corpus_items):
            assert item["receivedRank"] == i


@freezegun.freeze_time("2012-01-14 03:25:34", tz_offset=0)
def test_curated_recommendations_utm_source(client: TestClient):
    """Test the curated recommendations endpoint returns urls with correct(new) utm_source"""
    response = fetch_en_us(client)
    data = response.json()

    assert response.status_code == 200

    # Extract all recommendations from sections
    feeds = data["feeds"]
    all_recs = [
        rec
        for section in feeds.values()
        if section is not None
        for rec in section["recommendations"]
    ]

    # Assert items returned, otherwise the following assertions would not test anything.
    assert len(all_recs) > 0
    # Check that utm_source is present and has the correct value in all urls
    assert all("utm_source=firefox-newtab-en-us" in item["url"] for item in all_recs)
    assert all(item["publisher"] for item in all_recs)
    assert all(item["imageUrl"] for item in all_recs)


def test_curated_recommendations_features(client: TestClient):
    """Test the curated recommendations endpoint returns topic and section features"""
    response = fetch_en_us(client)
    data = response.json()

    # Extract all recommendations from sections
    feeds = data["feeds"]
    all_recs = [
        rec
        for section in feeds.values()
        if section is not None
        for rec in section["recommendations"]
    ]

    num_recs_with_section_features = 0
    for rec in all_recs:
        # With sections backend, features include both topic (t_ prefix) and section (s_ prefix)
        # Topic feature must be present
        topic_feature = f"t_{rec['topic']}"
        assert topic_feature in rec["features"]
        assert rec["features"][topic_feature] == 1.0

        # At least one section feature (s_ prefix) should be present
        section_features = [k for k in rec["features"].keys() if k.startswith("s_")]
        if len(section_features) > 0:
            num_recs_with_section_features += 1
    assert (
        num_recs_with_section_features > 0
    )  # We are omitting some UUID based sections until they are deprecated


class TestCuratedRecommendationsRequestParameters:
    """Test request body parameters for the curated-recommendations endpoint"""

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
    def test_curated_recommendations_locales(self, locale, surface_id, client: TestClient):
        """Test the curated recommendations endpoint accepts valid locales & returns correct surfaceId."""
        response = client.post("/api/v1/curated-recommendations", json={"locale": locale})
        assert response.status_code == 200, f"{locale} resulted in {response.status_code}"
        data = response.json()
        assert data["surfaceId"] == surface_id

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
    def test_curated_recommendations_locales_failure(self, locale, client: TestClient):
        """Test the curated recommendations endpoint rejects invalid locales."""
        response = client.post("/api/v1/curated-recommendations", json={"locale": locale})
        assert response.status_code == 400

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
    def test_curated_recommendations_valid_os(self, coarse_os, client: TestClient):
        """Test the curated recommendations endpoint accepts valid coarse_os values."""
        response = client.post(
            "/api/v1/curated-recommendations",
            json={"locale": Locale.EN_US, "coarse_os": coarse_os},
        )
        assert response.status_code == 200

    @pytest.mark.parametrize("coarse_os", ["", "windows11"])
    def test_curated_recommendations_invalid_os(self, coarse_os, client: TestClient):
        """Test the curated recommendations endpoint rejects invalid coarse_os values."""
        response = client.post(
            "/api/v1/curated-recommendations",
            json={"locale": Locale.EN_US, "coarseOs": coarse_os},
        )
        assert response.status_code == 400

    @pytest.mark.parametrize("utcOffset", [0, 12, 24])
    def test_curated_recommendations_valid_utc_offset(self, utcOffset, client: TestClient):
        """Test the curated recommendations endpoint accepts valid utcOffset values."""
        response = client.post(
            "/api/v1/curated-recommendations",
            json={"locale": Locale.EN_US, "utcOffset": utcOffset},
        )
        assert response.status_code == 200

    @pytest.mark.parametrize("utcOffset", [-1, 11.5, 25, None, "Z"])
    def test_curated_recommendations_invalid_utc_offset(self, utcOffset, client: TestClient):
        """Test the curated recommendations endpoint doesn't reject malformed utc offsets."""
        response = client.post(
            "/api/v1/curated-recommendations",
            json={"locale": Locale.EN_US, "utcOffset": utcOffset},
        )
        assert response.status_code == 200

    @pytest.mark.parametrize("count", [10, 50, 100])
    def test_curated_recommendations_count(
        self, count, scheduled_surface_response_data, client: TestClient
    ):
        """Test the curated recommendations endpoint accepts valid count."""
        response = client.post(
            "/api/v1/curated-recommendations", json={"locale": "en-US", "count": count}
        )
        assert response.status_code == 200
        data = response.json()
        schedule_count = len(scheduled_surface_response_data["data"]["scheduledSurface"]["items"])
        assert len(data["data"]) == min(count, schedule_count)

    @pytest.mark.parametrize("count", [None, 100.5])
    def test_curated_recommendations_count_failure(self, count, client: TestClient):
        """Test the curated recommendations endpoint rejects invalid count."""
        response = client.post(
            "/api/v1/curated-recommendations", json={"locale": "en-US", "count": count}
        )
        assert response.status_code == 400

    @pytest.mark.parametrize("region", [None, "US", "DE", "SXM"])
    def test_curated_recommendations_region(self, region, client: TestClient):
        """Test the curated recommendations endpoint accepts valid region."""
        response = client.post(
            "/api/v1/curated-recommendations", json={"locale": "en-US", "region": region}
        )
        assert response.status_code == 200

    @pytest.mark.parametrize("region", [675])
    def test_curated_recommendations_region_failure(self, region, client: TestClient):
        """Test the curated recommendations endpoint rejects invalid region."""
        response = client.post(
            "/api/v1/curated-recommendations", json={"locale": "en-US", "region": region}
        )
        assert response.status_code == 400

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
    def test_curated_recommendations_topics(self, topics, client: TestClient):
        """Test the curated recommendations endpoint accepts valid topics."""
        response = client.post(
            "/api/v1/curated-recommendations", json={"locale": "en-US", "topics": topics}
        )
        assert response.status_code == 200, f"{topics} resulted in {response.status_code}"

    @pytest.mark.parametrize(
        "locale",
        ["en-US", "en-GB", "fr-FR", "es-ES", "it-IT", "de-DE"],
    )
    @pytest.mark.parametrize("topics", [None, ["arts", "finance"]])
    def test_curated_recommendations_en_topic(self, locale, topics, client: TestClient):
        """Test that topic is present."""
        response = client.post(
            "/api/v1/curated-recommendations", json={"locale": locale, "topics": topics}
        )
        data = response.json()
        corpus_items = data["data"]

        assert len(corpus_items) > 0
        assert all(item["topic"] is not None for item in corpus_items)

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
    def test_non_sections_request_boosts_preferred_topics(
        self, preferred_topics, client: TestClient
    ):
        """Test non-sections requests boost preferred topics to top positions.

        Uses de-DE locale (scheduler backend path) which supports topic boosting.
        Note: en-US non-sections requests intentionally do NOT apply topic boosting.
        """
        response = client.post(
            "/api/v1/curated-recommendations",
            json={"locale": "de-DE", "topics": preferred_topics},
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
    def test_curated_recommendations_invalid_topic_return_200(
        self,
        topics,
        expected_topics,
        expected_warning,
        scheduled_surface_response_data_short,
        fixture_request_data,
        scheduled_surface_http_client,
        caplog,
        repeat,
        filter_caplog: FilterCaplogFixture,
        client: TestClient,
    ):
        """Test the curated recommendations endpoint ignores invalid topic in topics param.
        Should treat invalid topic as blank.
        Uses de-DE locale to test scheduled_surface backend behavior.
        """
        caplog.set_level(logging.WARN)
        scheduled_surface_http_client.post.return_value = Response(
            status_code=200,
            json=scheduled_surface_response_data_short,
            request=fixture_request_data,
        )
        response = client.post(
            "/api/v1/curated-recommendations", json={"locale": "de-DE", "topics": topics}
        )
        data = response.json()
        corpus_items = data["data"]
        # assert 200 is returned even tho some invalid topics
        assert response.status_code == 200
        # get topics in returned recs
        result_topics = [item["topic"] for item in corpus_items]
        assert set(result_topics) == set(expected_topics)
        # Assert that a warning was logged with a descriptive message when invalid topic
        warnings = filter_caplog(caplog.records, "merino.curated_recommendations.protocol")

        assert len(warnings) == 1
        assert expected_warning in warnings[0].message

    def test_curated_recommendations_locale_bad_request(self, client: TestClient):
        """Test the curated recommendations endpoint response is 400 if locale is not provided"""
        response = client.post("/api/v1/curated-recommendations", json={"foo": "bar"})

        # Check if the response returns 400
        assert response.status_code == 400


class TestCorpusApiCaching:
    """Tests covering the caching behavior of the Corpus backend.
    Uses de-DE locale to test scheduled_surface backend caching (en-US uses sections backend).
    """

    @freezegun.freeze_time("2012-01-14 03:21:34", tz_offset=0)
    def test_single_request_multiple_fetches(
        self, scheduled_surface_http_client, client: TestClient
    ):
        """Test that only a single request is made to the curated-corpus-api."""
        # Gather multiple fetch calls
        results = [fetch_de_de(client) for _ in range(3)]
        # Assert that recommendations were returned in each response.
        assert all(len(result.json()["data"]) > 0 for result in results)

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
        client: TestClient,
    ):
        """Test that only a few requests are made to the curated-corpus-api when it is down.
        Additionally, test that if the backend returns a GraphQL error, it is handled correctly.
        """
        # Pre-warm the backend via an arbitrary API request. Without this, the initial UserAgentMiddleware call
        # incurs ~2-second latency, distorting the simulated downtime of `retry_wait_initial_seconds` seconds.
        client.get("/__heartbeat__")

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
                result = fetch_de_de(client)
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
        self,
        scheduled_surface_http_client,
        scheduled_surface_response_data,
        fixture_request_data,
        client: TestClient,
    ):
        """Test that the cache expires, and subsequent requests return new data.
        Uses de-DE locale to test scheduled_surface backend caching.
        """
        with freezegun.freeze_time(tick=True) as frozen_datetime:
            # First fetch to populate cache
            initial_response = fetch_de_de(client)
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
            fetch_de_de(client)
            await asyncio.sleep(0.01)  # Allow asyncio background task to make an API request

            # Next fetch should get the new data
            new_response = fetch_de_de(client)
            assert scheduled_surface_http_client.post.call_count == 2
            new_data = new_response.json()
            assert new_data["recommendedAt"] > initial_data["recommendedAt"]
            assert all("NEW" in item["title"] for item in new_data["data"])

    def test_valid_cache_returned_on_error(
        self, scheduled_surface_http_client, fixture_request_data, caplog, client: TestClient
    ):
        """Test that the cache does not cache error data even if expired & returns latest valid data from cache."""
        # First fetch to populate cache with good data
        initial_response = fetch_de_de(client)
        initial_data = initial_response.json()
        assert initial_response.status_code == 200
        assert scheduled_surface_http_client.post.call_count == 1

        # Simulate 503 error from Corpus API
        scheduled_surface_http_client.post.return_value = Response(
            status_code=503,
            request=fixture_request_data,
        )

        # Try to fetch data when cache expired
        new_response = fetch_de_de(client)
        new_data = new_response.json()

        assert new_response.status_code == 200
        assert len(initial_data) == len(new_data)
        assert all([a == b for a, b in zip(initial_data, new_data)])


class TestCuratedRecommendationsMetrics:
    """Tests that the right metrics are recorded for curated-recommendations requests.
    Uses de-DE locale to test scheduled_surface backend metrics.
    """

    def test_metrics_cache_miss(self, mocker: MockerFixture, client: TestClient) -> None:
        """Test that metrics are recorded when corpus api items are not yet cached."""
        report = mocker.patch.object(aiodogstatsd.Client, "_report")

        fetch_de_de(client)

        # TODO: Remove reliance on internal details of aiodogstatsd
        metric_keys: list[str] = [call.args[0] for call in report.call_args_list]
        assert metric_keys == [
            "corpus_api.scheduled_surface.timing",
            "corpus_api.scheduled_surface.status_codes.200",
            "post.api.v1.curated-recommendations.timing",
            "post.api.v1.curated-recommendations.status_codes.200",
            "response.status_codes.200",
        ]

    def test_metrics_cache_hit(self, mocker: MockerFixture, client: TestClient) -> None:
        """Test that metrics are recorded when corpus api items are cached."""
        # The first call populates the cache.
        fetch_de_de(client)

        # This test covers only the metrics emitted from the following cached call.
        report = mocker.patch.object(aiodogstatsd.Client, "_report")
        fetch_de_de(client)

        # TODO: Remove reliance on internal details of aiodogstatsd
        metric_keys: list[str] = [call.args[0] for call in report.call_args_list]
        assert metric_keys == [
            "post.api.v1.curated-recommendations.timing",
            "post.api.v1.curated-recommendations.status_codes.200",
            "response.status_codes.200",
        ]

    def test_metrics_corpus_api_error(
        self,
        mocker: MockerFixture,
        scheduled_surface_http_client,
        fixture_request_data,
        scheduled_surface_response_data,
        client: TestClient,
    ) -> None:
        """Test that metrics are recorded when the curated-corpus-api returns a 500 error"""
        report = mocker.patch.object(aiodogstatsd.Client, "_report")

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

        fetch_de_de(client)

        # TODO: Remove reliance on internal details of aiodogstatsd
        metric_keys: list[str] = [call.args[0] for call in report.call_args_list]
        assert metric_keys == [
            "corpus_api.scheduled_surface.timing",
            "corpus_api.scheduled_surface.status_codes.500",
            "corpus_api.scheduled_surface.timing",
            "corpus_api.scheduled_surface.status_codes.200",
            "post.api.v1.curated-recommendations.timing",
            "post.api.v1.curated-recommendations.status_codes.200",  # final call should return 200
            "response.status_codes.200",
        ]


class TestCorpusApiRanking:
    """Tests covering the ranking behavior of the Corpus backend"""

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
    def test_thompson_sampling_behavior(
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
        client: TestClient,
    ):
        """Test that Thompson sampling produces different orders and favors higher CTRs."""
        n_iterations = 20
        past_id_orders = []

        for i in range(n_iterations):
            response = client.post(
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
            SurfaceId.NEW_TAB_EN_GB,
        ],
    )
    def test_section_translations(self, surface_id):
        """Check that there is a translation for 'top-stories' (the only key used).

        Section titles come from the backend API. Only the 'top-stories' key is
        used for client-side localization of the Popular Today section title.
        """
        # Get the localized titles for the current surface_id
        localized_titles = LOCALIZED_SECTION_TITLES[surface_id]

        # Assert top-stories has a translation (the only key used)
        assert (
            "top-stories" in localized_titles and localized_titles["top-stories"]
        ), f"Missing translation for 'top-stories' in {surface_id}"

    def test_corpus_sections_feed_content(
        self,
        client: TestClient,
    ):
        """Test the curated recommendations endpoint response is as expected
        when requesting the 'sections' feed for different locales.
        """
        response = client.post(
            "/api/v1/curated-recommendations",
            json={
                "locale": "en-US",
                "feeds": ["sections"],
                "experimentName": None,
                "experimentBranch": None,
                "region": "US",
            },
        )
        data = response.json()

        # Check if the response is valid
        assert response.status_code == 200

        feeds = data["feeds"]
        sections = {name: section for name, section in feeds.items() if section is not None}

        # the first layouts for the subtopic sections should be a double-row layout, after which it should cycle.
        layout_names = [sec["layout"]["name"] for sec in sections.values()]
        assert layout_names[0] == "7-double-row-2-ad"  # top_stories double‐row layout
        assert layout_names[1] == "6-small-medium-1-ad"  # first ML section
        assert layout_names[2] == "4-large-small-medium-1-ad"  # second ML section

        assert "music" in sections

        # headlines section should not be in the final response even if present in the corpus-api response
        # it should only be available when headlines experiment is enabled
        assert "headlines" not in sections

        # assert IAB metadata is present in ML sections (there are 8 of them)
        expected_iab_metadata = {
            "nfl": "484",
            "tv": "640",
            "music": "338",
            "movies": "324",
            "nba": "547",
            "soccer": "533",
            "mlb": "545",
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

    @pytest.mark.parametrize(
        "experiment_payload",
        [
            {
                "experimentName": ExperimentName.SCHEDULER_HOLDBACK_EXPERIMENT.value,
                "experimentBranch": "control",
                "region": "BQ",
            },
            {"experimentName": None, "experimentBranch": None, "region": "CA"},
        ],
    )
    def test_sections_legacy_holdback(self, experiment_payload, client: TestClient):
        """Test the curated recommendations endpoint response is as expected
        when requesting the 'sections' feed for different locales.
        Note this also is sent in non-US countries
        """
        response = client.post(
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

        # Should have top_stories_section and legacy topic sections
        # (may also have manually created sections)
        assert "top_stories_section" in sections
        legacy_topics = {topic.value for topic in Topic}
        legacy_sections_present = [sid for sid in sections if sid in legacy_topics]
        assert len(legacy_sections_present) > 0, "Should have at least some legacy topic sections"

    @pytest.mark.parametrize(
        "experiment_payload",
        [
            {},  # No experiment
            {
                "experimentName": ExperimentName.ML_SECTIONS_EXPERIMENT.value,
                "experimentBranch": "treatment",
            },
        ],
    )
    def test_sections_feed_content(self, experiment_payload, caplog, client: TestClient):
        """Test the curated recommendations endpoint response is as expected
        when requesting the 'sections' feed for en-US locale.
        """
        locale = "en-US"
        response = client.post(
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

        # Check section types based on experiment
        legacy_topics = {topic.value for topic in Topic}

        if experiment_payload.get("experimentName") != ExperimentName.ML_SECTIONS_EXPERIMENT.value:
            # Non-ML sections experiment: Should have legacy topics and may have manually created sections
            # but should not have ML subtopics
            for sid in sections:
                if sid != "top_stories_section" and sid not in legacy_topics:
                    # Non-legacy sections should only be manually created sections
                    assert is_manual_section(sid), f"Unexpected section type: {sid}"

        # Check the recs used in top_stories_section are removed from their original ML sections.
        top_story_ids = {
            rec["corpusItemId"] for rec in sections["top_stories_section"]["recommendations"]
        }

        for sid, sec in sections.items():
            if sid != "top_stories_section":
                for rec in sec["recommendations"]:
                    assert rec["corpusItemId"] not in top_story_ids

        # check editorial section with extra metadata is also returned along with ML subfeeds
        editorial_section_id = "042b10d6-4fab-4df6-8006-e73ae5fd021d"
        if (
            data["feeds"].get(editorial_section_id) is not None
            and experiment_payload.get("experimentName")
            == ExperimentName.ML_SECTIONS_EXPERIMENT.value
        ):
            assert data["feeds"][editorial_section_id]["title"] == "Amsterdam Tips"
            assert data["feeds"][editorial_section_id]["subtitle"] == "Travel tips in Amsterdam"
            assert (
                data["feeds"][editorial_section_id]["heroTitle"]
                == "Discover the Best of Amsterdam"
            )
            assert (
                data["feeds"][editorial_section_id]["heroSubtitle"]
                == "Insider advice on where to eat, what to see, and how to enjoy the city like a local."
            )

    def test_sections_include_both_manual_and_ml(self, client: TestClient):
        """Test that sections feed includes both manually created and ML-generated sections.

        Both MANUAL and ML sections should be returned together.
        """
        response = client.post(
            "/api/v1/curated-recommendations",
            json={
                "locale": "en-US",
                "feeds": ["sections"],
            },
        )
        data = response.json()

        # Check if the response is valid
        assert response.status_code == 200

        feeds = data["feeds"]
        sections = {name: section for name, section in feeds.items() if section is not None}

        # top_stories_section should always be present
        assert "top_stories_section" in sections

        # Should have ML sections (legacy topics)
        legacy_topics = {topic.value for topic in Topic}
        ml_sections_found = [sid for sid in sections if sid in legacy_topics]
        assert len(ml_sections_found) > 0, "Should have at least some ML legacy topic sections"

        # Check if any manually created sections appear (they may or may not, depending on
        # whether they have enough items after top stories are removed)
        manual_sections = [sid for sid in sections if is_manual_section(sid)]
        if manual_sections:
            # If the "Tech stuff" manual section appears, verify it has the correct title
            tech_stuff_id = "d532b687-108a-4edb-a076-58a6945de714"
            if tech_stuff_id in sections:
                assert sections[tech_stuff_id]["title"] == "Tech stuff"

    @pytest.mark.parametrize(
        "experiment_branch",
        [
            CONTEXTUAL_RANKING_TREATMENT_TZ,
            CONTEXTUAL_RANKING_TREATMENT_COUNTRY,
        ],
    )
    def test_sections_contextual_ranking(self, client: TestClient, experiment_branch):
        """Test that sections feed includes both manually created and ML-generated sections for contextual ranking.

        Both MANUAL and ML sections should be returned together.
        """
        response = client.post(
            "/api/v1/curated-recommendations",
            json={
                "locale": "en-US",
                "feeds": ["sections"],
                "experimentName": ExperimentName.CONTEXTUAL_RANKING_CONTENT_EXPERIMENT.value,
                "experimentBranch": experiment_branch,
            },
        )
        data = response.json()

        # Check if the response is valid
        assert response.status_code == 200

        feeds = data["feeds"]
        sections = {name: section for name, section in feeds.items() if section is not None}

        # top_stories_section should always be present
        assert "top_stories_section" in sections

        # Should have ML sections (legacy topics)
        legacy_topics = {topic.value for topic in Topic}
        ml_sections_found = [sid for sid in sections if sid in legacy_topics]
        assert len(ml_sections_found) > 0, "Should have at least some ML legacy topic sections"

        # Check if any manually created sections appear (they may or may not, depending on
        # whether they have enough items after top stories are removed)
        manual_sections = [sid for sid in sections if is_manual_section(sid)]
        if manual_sections:
            # If the "Tech stuff" manual section appears, verify it has the correct title
            tech_stuff_id = "d532b687-108a-4edb-a076-58a6945de714"
            if tech_stuff_id in sections:
                assert sections[tech_stuff_id]["title"] == "Tech stuff"

    def test_sections_contextual_ranking_result_for_timezone(
        self, ml_recommendations_backend, engagement_backend, sections_backend, client: TestClient
    ):
        """Test end to end content ranking based on timezone utc_offset. Note that engagement_backend is required
        because the ml_recommendations_backend relies on it to find fresh items, which are limited
        """
        response = client.post(
            "/api/v1/curated-recommendations",
            json={
                "locale": "en-US",
                "feeds": ["sections"],
                "experimentName": ExperimentName.CONTEXTUAL_RANKING_CONTENT_EXPERIMENT.value,
                "experimentBranch": CONTEXTUAL_RANKING_TREATMENT_TZ,
                "utc_offset": 16,
                "region": "US",
            },
        )

        data = response.json()
        # Check if the response is valid
        assert response.status_code == 200

        feeds = data["feeds"]
        sections = {name: section for name, section in feeds.items() if section is not None}

        # top_stories_section should always be present
        assert "top_stories_section" in sections
        assert sections["top_stories_section"]["recommendations"][0][
            "corpusItemId"
        ] == ml_recommendations_backend.get_most_popular_content_id_by_timezone(16)

        response = client.post(
            "/api/v1/curated-recommendations",
            json={
                "locale": "en-US",
                "feeds": ["sections"],
                "experimentName": ExperimentName.CONTEXTUAL_RANKING_CONTENT_EXPERIMENT.value,
                "experimentBranch": CONTEXTUAL_RANKING_TREATMENT_TZ,
                "utc_offset": 0,
                "region": "US",
            },
        )
        data = response.json()
        # Check if the response is valid
        assert response.status_code == 200

        feeds = data["feeds"]
        sections = {name: section for name, section in feeds.items() if section is not None}

        # top_stories_section should always be present
        assert "top_stories_section" in sections
        # Confirm that we have different content for different timezone
        assert sections["top_stories_section"]["recommendations"][0][
            "corpusItemId"
        ] != ml_recommendations_backend.get_most_popular_content_id_by_timezone(16)

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
            {
                "experimentName": ExperimentName.ML_SECTIONS_EXPERIMENT.value,
                "experimentBranch": "control",
            },
            {
                "experimentName": ExperimentName.CONTEXTUAL_AD_NIGHTLY_EXPERIMENT.value,
                "experimentBranch": "treatment",
            },
            {
                "experimentName": ExperimentName.CONTEXTUAL_AD_V2_NIGHTLY_EXPERIMENT.value,
                "experimentBranch": "treatment",
            },
            {
                "experimentName": ExperimentName.CONTEXTUAL_AD_BETA_EXPERIMENT.value,
                "experimentBranch": "treatment",
            },
            {
                "experimentName": ExperimentName.CONTEXTUAL_AD_V2_BETA_EXPERIMENT.value,
                "experimentBranch": "treatment",
            },
            {
                "experimentName": ExperimentName.CONTEXTUAL_AD_RELEASE_EXPERIMENT.value,
                "experimentBranch": "treatment",
            },
            {
                "experimentName": ExperimentName.CONTEXTUAL_AD_V2_RELEASE_EXPERIMENT.value,
                "experimentBranch": "treatment",
            },
        ],
    )
    def test_sections_layouts(self, sections_payload, experiment_payload, client: TestClient):
        """Test that the correct layouts & ads are returned along with sections."""
        response = client.post(
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
        first_section = next((s for s in sections.values() if s["receivedFeedRank"] == 0), None)
        assert first_section is not None

        # Assert layout of the first section (Popular Today).
        assert first_section["title"] == "Popular Today"
        print(experiment_payload.get("experimentName"))
        if (
            experiment_payload.get("experimentName") == ExperimentName.ML_SECTIONS_EXPERIMENT.value
            or experiment_payload.get("experimentName") is None
        ):
            assert first_section["layout"]["name"] == "7-double-row-2-ad"
        else:
            # If contextual ads experiment, Popular Today should be 1 row
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

    @pytest.mark.parametrize(
        "experiment_payload",
        [
            {},  # No experiment
            {
                "experimentName": ExperimentName.SCHEDULER_HOLDBACK_EXPERIMENT.value,
                "experimentBranch": "control",
            },
            {
                "experimentName": ExperimentName.SCHEDULER_HOLDBACK_EXPERIMENT.value,
                "experimentBranch": "other",
            },
        ],
    )
    def test_curated_recommendations_with_sections_feed_boost_followed_sections(
        self, caplog, experiment_payload, client: TestClient
    ):
        """Test the curated recommendations endpoint response is as expected
        when requesting the 'sections' feed for en-US locale. Sections requested to be boosted (followed)
        should be boosted and isFollowed attribute set accordingly, regardless of experiment toggles.
        """
        response = client.post(
            "/api/v1/curated-recommendations",
            json={
                "locale": "en-US",
                "feeds": ["sections"],
                "sections": [
                    {"sectionId": "sports", "isFollowed": True, "isBlocked": False},
                    {"sectionId": "arts", "isFollowed": True, "isBlocked": False},
                    {"sectionId": "education", "isFollowed": False, "isBlocked": True},
                    {"sectionId": "health", "isFollowed": True, "isBlocked": False},
                ],
            }
            | experiment_payload,
        )
        data = response.json()

        # Check if the response is valid
        assert response.status_code == 200
        # Assert no errors were logged
        errors = [r for r in caplog.records if r.levelname == "ERROR"]
        assert len(errors) == 0

        feeds = data["feeds"]
        sections = {name: section for name, section in feeds.items() if section is not None}

        # headlines_section should not be in the final response unless that experiment is enabled
        assert "headlines_section" not in sections

        # assert isFollowed & isBlocked have been correctly set
        if data["feeds"].get("arts") is not None:
            assert data["feeds"]["arts"]["isFollowed"]
            assert not data["feeds"]["arts"]["isBlocked"]
            # assert followed section ARTS comes after top-stories and before unfollowed sections (education).
            assert data["feeds"]["arts"]["receivedFeedRank"] in [1, 2, 3]
            assert data["feeds"]["arts"]["iab"] == {
                "taxonomy": "IAB-3.0",
                "categories": ["JLBCU7"],
            }
        if data["feeds"].get("education") is not None:
            assert not data["feeds"]["education"]["isFollowed"]
            assert data["feeds"]["education"]["isBlocked"]
        if data["feeds"].get("sports") is not None:
            assert data["feeds"]["sports"]["isFollowed"]
            assert not data["feeds"]["sports"]["isBlocked"]
            # assert followed section SPORTS comes after top-stories and before unfollowed sections (education).
            assert data["feeds"]["sports"]["receivedFeedRank"] in [1, 2, 3]
            assert data["feeds"]["sports"]["iab"] == {
                "taxonomy": "IAB-3.0",
                "categories": ["483"],  # Production uses 483 for sports
            }
        if data["feeds"].get("health") is not None:
            assert data["feeds"]["health"]["isFollowed"]
            assert not data["feeds"]["health"]["isBlocked"]

    @pytest.mark.parametrize(
        "experiment_payload",
        [
            {"region": "US"},
            {"region": "CA"},
            {
                "experimentName": ExperimentName.SCHEDULER_HOLDBACK_EXPERIMENT.value,
                "experimentBranch": "control",
                "region": "US",
            },
            {
                "experimentName": "other",
                "experimentBranch": "other",
                "region": "US",
            },
        ],
    )
    def test_sections_filtering_by_region_and_holdback(
        self, caplog, experiment_payload, client: TestClient
    ):
        """Test that section filtering respects region and holdback states."""
        print(json.dumps(experiment_payload))
        response = client.post(
            "/api/v1/curated-recommendations",
            json={"locale": "en-US", "feeds": ["sections"]} | experiment_payload,
        )
        data = response.json()
        assert response.status_code == 200
        assert not [r for r in caplog.records if r.levelname == "ERROR"]

        sections = {name: section for name, section in data["feeds"].items() if section}

        # headlines_section should not be present unless the daily briefing experiment is enabled separately.
        assert "headlines_section" not in sections

        assert len(sections) >= 4

        for sid in sections:
            if sid != "top_stories_section":
                assert not sid.endswith("_crawl"), f"{sid} shouldn't have _crawl suffix"

        legacy_topics = {topic.value for topic in Topic}
        experiment_name = experiment_payload.get("experimentName")
        experiment_branch = experiment_payload.get("experimentBranch")
        region = experiment_payload.get("region")
        expect_subtopics = region == "US" and not (
            experiment_name == ExperimentName.SCHEDULER_HOLDBACK_EXPERIMENT.value
            and experiment_branch == "control"
        )

        # Categorize non-legacy, non-top_stories sections
        non_legacy_section_ids = [
            sid
            for sid in sections
            if sid not in legacy_topics and sid not in {"top_stories_section"}
        ]
        ml_subtopic_section_ids = [
            sid for sid in non_legacy_section_ids if not is_manual_section(sid)
        ]

        if expect_subtopics:
            assert ml_subtopic_section_ids, "Expected ML subtopic sections for US treatment"
        else:
            assert (
                not ml_subtopic_section_ids
            ), f"Unexpected ML subtopic sections: {ml_subtopic_section_ids}"

        # Manually created sections may appear regardless of experiment settings

    def test_daily_briefing_experiment_headlines_section_returned(self, client: TestClient):
        """Test that the Headlines section is returned when the daily briefing experiment is enabled.

        - Headlines section should be ranked on the very top (rank ==0)
        - Popular Today section should be ranked right after headlines (rank ==1)
        - The remaining sections should be ranked right after (rank == 2...N)
        """
        response = client.post(
            "/api/v1/curated-recommendations",
            json={
                "locale": "en-US",
                "feeds": ["sections"],
                "experimentName": ExperimentName.DAILY_BRIEFING_EXPERIMENT.value,
                "experimentBranch": DailyBriefingBranch.BRIEFING_WITH_POPULAR.value,
                "region": "US",
            },
        )

        data = response.json()

        # Check if the response is valid
        assert response.status_code == 200

        feeds = data["feeds"]
        sections = {name: section for name, section in feeds.items() if section is not None}

        # Assert headlines section is returned as "headlines"
        assert "headlines" in sections
        headlines_section = sections.get("headlines")
        if headlines_section is not None:
            assert headlines_section["receivedFeedRank"] == 0
            assert headlines_section["title"] == "Headlines"
            assert headlines_section["subtitle"] == "Top Headlines today"
            assert headlines_section["layout"]["name"] == "4-large-small-medium-1-ad"

        # Assert that top_stories section has rank == 1
        top_stories_section = sections.get("top_stories_section")
        if top_stories_section is not None:
            assert top_stories_section["receivedFeedRank"] == 1
            assert top_stories_section["title"] == "Popular Today"
            assert top_stories_section["layout"]["name"] == "4-medium-small-1-ad"

        remaining_sections = sorted(
            (sid for sid in sections if sid not in ("headlines", "top_stories_section")),
            key=lambda sid: sections[sid]["receivedFeedRank"],
        )

        # Expected: headlines first -> top_stories_section second, then rest in keys order without headlines & top
        expected_order = ["headlines", "top_stories_section"] + remaining_sections
        for idx, sid in enumerate(expected_order):
            assert sections[sid]["receivedFeedRank"] == idx

        # Check the recs used in headlines section are removed from their original sections.
        headlines_story_ids = {
            rec["corpusItemId"] for rec in sections["headlines"]["recommendations"]
        }

        for sid, sec in sections.items():
            if sid != "headlines":
                for rec in sec["recommendations"]:
                    assert rec["corpusItemId"] not in headlines_story_ids

    def test_daily_briefing_without_popular_excludes_top_stories(self, client: TestClient):
        """Test that Popular Today is NOT returned when in briefing-without-popular branch.

        - Headlines section should be ranked on the very top (rank == 0)
        - Popular Today (top_stories_section) should NOT be present
        - The remaining sections should be ranked right after headlines (rank == 1...N)
        """
        response = client.post(
            "/api/v1/curated-recommendations",
            json={
                "locale": "en-US",
                "feeds": ["sections"],
                "experimentName": ExperimentName.DAILY_BRIEFING_EXPERIMENT.value,
                "experimentBranch": DailyBriefingBranch.BRIEFING_WITHOUT_POPULAR.value,
                "region": "US",
            },
        )

        data = response.json()

        # Check if the response is valid
        assert response.status_code == 200

        feeds = data["feeds"]
        sections = {name: section for name, section in feeds.items() if section is not None}

        # Assert headlines section is returned
        assert "headlines" in sections
        headlines_section = sections.get("headlines")
        if headlines_section is not None:
            assert headlines_section["receivedFeedRank"] == 0
            assert headlines_section["title"] == "Headlines"

        # Assert that top_stories_section is NOT present
        assert "top_stories_section" not in sections

        # Verify remaining sections start at rank 1
        remaining_sections = sorted(
            (sid for sid in sections if sid != "headlines"),
            key=lambda sid: sections[sid]["receivedFeedRank"],
        )
        for idx, sid in enumerate(remaining_sections, start=1):
            assert sections[sid]["receivedFeedRank"] == idx

    def test_curated_recommendations_with_sections_feed_removes_blocked_topics(
        self, caplog, client: TestClient
    ):
        """Test that when topic sections are blocked, those recommendations don't show up, not even
        in other sections like Popular Today.
        """
        blocked_topics = [Topic.CAREER.value, Topic.SCIENCE.value, Topic.HEALTH_FITNESS.value]

        response = client.post(
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

    @freezegun.freeze_time("2025-03-20 12:00:00", tz_offset=0)
    def test_curated_recommendations_with_sections_feed_followed_at(
        self, caplog, client: TestClient
    ):
        """Test the curated recommendations endpoint response is as expected
        when requesting the 'sections' feed for en-US locale & providing followedAt.
        Most recently followed sections are boosted higher and response fields are set correctly.
        """
        response = client.post(
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
    def test_curated_recommendations_with_invalid_followed_at_formats(
        self, sections_payload, client: TestClient
    ):
        """Test the curated recommendations endpoint response when providing invalid followedAt time formats:
        - missing timezone
        - not ISO format
        - Unix timestamp as integer
        """
        payload = {
            "locale": "en-US",
            "feeds": ["sections"],
        }
        if sections_payload is not None:
            payload["sections"] = sections_payload
        response = client.post("/api/v1/curated-recommendations", json=payload)
        # assert 400 is returned for invalid followedAt
        assert response.status_code == 400

    def test_sections_feed_titles(self, client: TestClient):
        """Test the curated recommendations endpoint 'sections' have the expected titles."""
        expected_titles = {
            "top_stories_section": "Popular Today",
            "arts": "Entertainment",
            "education": "Education",
            "sports": "Sports",
        }
        response = client.post(
            "/api/v1/curated-recommendations",
            json={"locale": "en-US", "feeds": ["sections"]},
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

    @pytest.mark.parametrize("enable_interest_picker", [True, False])
    def test_sections_interest_picker(
        self, enable_interest_picker, monkeypatch, client: TestClient
    ):
        """Test the curated recommendations endpoint returns an interest picker when enabled"""
        # The fixture data doesn't have enough sections for the interest picker to show up, so lower
        # the minimum number of sections that it needs to have to 1.
        monkeypatch.setattr(interest_picker, "MIN_INTEREST_PICKER_COUNT", 1)

        response = client.post(
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
            assert (
                interest_picker_response["title"] == "Follow topics to fine-tune your experience"
            )
        else:
            assert interest_picker_response is None
        # Ensure top_stories_section always has receivedFeedRank == 0
        top_stories_section = data["feeds"].get("top_stories_section")
        assert top_stories_section is not None
        assert top_stories_section["receivedFeedRank"] == 0

    @pytest.mark.parametrize("enable_interest_picker", [True, False])
    def test_sections_interest_picker_ml_sections(
        self, enable_interest_picker, monkeypatch, client: TestClient
    ):
        """Test the curated recommendations endpoint returns expected response when an
        interest picker & ML sections enabled
        """
        # The fixture data doesn't have enough sections for the interest picker to show up, so lower
        # the minimum number of sections that it needs to have to 1.
        monkeypatch.setattr(interest_picker, "MIN_INTEREST_PICKER_COUNT", 1)

        response = client.post(
            "/api/v1/curated-recommendations",
            json={
                "experimentName": "optin-new-tab-ml-sections",
                "experimentBranch": "treatment",
                "utc_offset": 17,
                "coarse_os": "win",
                "surface_id": "",
                "locale": "en-US",
                "region": "US",
                "enableInterestPicker": enable_interest_picker,
                "feeds": ["sections"],
            },
        )
        data = response.json()
        interest_picker_response = data["interestPicker"]
        if enable_interest_picker:
            assert interest_picker_response is not None
            assert (
                interest_picker_response["title"] == "Follow topics to fine-tune your experience"
            )
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
    def test_ml_sections_thompson_sampling(self, repeat, engagement_backend, client: TestClient):
        """Statistically verify ML sections order by engagement (higher CTR → lower feed rank)."""
        payload = {
            "locale": "en-US",
            "feeds": ["sections"],
            "experimentName": ExperimentName.ML_SECTIONS_EXPERIMENT.value,
            "experimentBranch": "treatment",
        }
        seed_response = client.post("/api/v1/curated-recommendations", json=payload)
        assert seed_response.status_code == 200
        seed_deterministic_ctr_overrides(engagement_backend, seed_response.json()["feeds"])

        response = client.post("/api/v1/curated-recommendations", json=payload)
        assert response.status_code == 200
        feeds = response.json()["feeds"]

        # collect non-top_stories sections
        sub_topic_sections = [
            sec for name, sec in feeds.items() if name != "top_stories_section" and sec is not None
        ]

        # compute avg CTR over the recommendations for each section
        avg_ctrs = []
        for sec in sub_topic_sections:
            recs = sec["recommendations"]
            ctrs = []
            for rec in recs:
                e = engagement_backend.get(rec["corpusItemId"], region=None)
                if e:
                    ctrs.append(e.click_count / e.impression_count)
            avg = sum(ctrs) / len(ctrs) if ctrs else 0.0
            avg_ctrs.append((sec["receivedFeedRank"], avg))

        # run linear regression: rank vs avg CTR
        ranks, avgs = zip(*avg_ctrs)
        slope, _, _, _, _ = linregress(ranks, avgs)

        # assert that slope is negative: better‑engaged sections get better (lower) ranks
        assert slope < 0, f"Sections not ordered by engagement (slope={slope})"

    @pytest.mark.parametrize("enable_interest_vector", [True, False])
    def test_sections_model_interest_vector(
        self, enable_interest_vector, monkeypatch, client: TestClient
    ):
        """Test the curated recommendations endpoint returns a model when interest vector is passed"""
        response = client.post(
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

    def test_sections_model_interest_vector_greedy_ranking(self, monkeypatch, client: TestClient):
        """Test the curated recommendations endpoint ranks sections accorcding to inferredInterests"""
        np.random.seed(43)  # NumPy's RNG (used internally by scikit-learn)

        response = client.post(
            "/api/v1/curated-recommendations",
            json={"locale": Locale.EN_US, "feeds": ["sections"]},
        )
        data = response.json()

        ## sort sections received
        sorted_sections = sorted(
            data["feeds"], key=lambda x: data["feeds"][x]["receivedFeedRank"]
        )[::-1]
        ## we should get some sections out
        assert len(sorted_sections) > 3

        # define interest vector, reversed from previous order
        interests: dict[str, float | str] = {
            sorted_sections[i]: (1 - i / 8) * 10 for i in range(4)
        }
        interests["model_id"] = DEFAULT_PRODUCTION_MODEL_ID
        # make the api call
        response = client.post(
            "/api/v1/curated-recommendations",
            json={
                "locale": Locale.EN_US,
                "feeds": ["sections"],
                "inferredInterests": interests,
            },
        )
        data = response.json()
        # expect interests to be sorted by value
        sorted_interests = sorted(
            [k for k, v in interests.items() if isinstance(v, float)],
            key=interests.get,  # type: ignore
        )[::-1]
        # expect top stories to be first
        sorted_interests.insert(0, "top_stories_section")
        # order is in receivedFeedRank
        for i, sec in enumerate(sorted_interests):
            assert data["feeds"][sec]["receivedFeedRank"] == i

    def test_topic_model_interest_vector_most_popular(self, monkeypatch, client: TestClient):
        """Test the curated recommendations endpoint ranks sections accorcding to inferredInterests"""
        np.random.seed(43)  # NumPy's RNG (used internally by scikit-learn)

        # define interest vector, reversed from previous order
        interests = {
            "sports": 0.0,
            "other": 0.0,
            "arts": 0.5,
            "model_id": DEFAULT_PRODUCTION_MODEL_ID,
        }

        # make the api call
        response = client.post(
            "/api/v1/curated-recommendations",
            json={
                "locale": Locale.EN_US,
                "feeds": ["sections"],
                "inferredInterests": interests,
            },
        )
        data = response.json()

        ## sort sections received
        sections = data["feeds"]

        ## we should get some sections out
        assert len(sections) > 3
        assert sections["top_stories_section"]["receivedFeedRank"] == 0
        assert len(sections["top_stories_section"]["recommendations"]) > 10

        # TODO - Verify this in the future
        # assert sections["top_stories_section"]["recommendations"][0]["topic"] == "arts"

    @pytest.mark.parametrize(
        "repeat",
        range(settings.curated_recommendations.rankers.thompson_sampling.test_repeat_count),
    )
    def test_sections_ranked_by_top_items_engagement(
        self, repeat, engagement_backend, client: TestClient
    ):
        """Sections should be ordered so that those with higher average CTR
        among their top 3 items get a better (lower) feed rank.
        """
        payload = {
            "locale": "en-US",
            "feeds": ["sections"],
            "experimentName": ExperimentName.ML_SECTIONS_EXPERIMENT.value,
            "experimentBranch": "treatment",
        }
        seed_response = client.post("/api/v1/curated-recommendations", json=payload)
        assert seed_response.status_code == 200
        seed_deterministic_ctr_overrides(engagement_backend, seed_response.json()["feeds"])

        response = client.post("/api/v1/curated-recommendations", json=payload)
        assert response.status_code == 200
        feeds = response.json()["feeds"]

        # exclude top_stories_section, which by definition has high engagement.
        sections = [
            section for name, section in feeds.items() if section and name != "top_stories_section"
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
    def test_sections_pass_region_to_engagement_backend(
        self,
        locale,
        region,
        derived_region,
        mocker,
        engagement_backend,
        scheduled_surface_http_client,
        fixture_request_data,
        client: TestClient,
    ):
        """Ensure that when fetching a 'sections' feed we pass the right region into engagement.get"""
        spy = mocker.spy(engagement_backend, "get")

        client.post(
            "/api/v1/curated-recommendations",
            json={
                "locale": locale,
                "region": region,
                "feeds": ["sections"],
                "experimentName": ExperimentName.ML_SECTIONS_EXPERIMENT.value,
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
            passed_region(call) == derived_region  # type: ignore
            for call in spy.call_args_list
        ), f"No engagement.get(..., region={repr(derived_region)}) in {spy.call_args_list}"

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        "reports,impressions,should_remove",
        [
            # Above threshold: 5 / 50 = 0.1 (10% > 0.1%) but 5 reports < 20 → should stay
            (5, 50, False),
            # Below threshold: 1 / 200,000 = 0.000005 (0.0005% < 0.1%) → should stay
            (1, 200_000, False),
            # Exactly at threshold: 1 / 1,000 = 0.001 (0.1% == 0.1%) → should stay
            (1, 1_000, False),
            # No reports: 0 / 100 = 0 < 0.001 → should stay
            (0, 100, False),
            # Above threshold: 20 / 100 = .2 (20% > 0.1%) AND 20 reports → should be removed
            (20, 100, True),
            # Above threshold: 35 / 100 = .35 (35% > 0.1%) AND 35 reports → should be removed
            (35, 100, True),
            # No engagement data → treated as safe → should stay
            (None, None, False),
        ],
    )
    async def test_takedown_reported_recommendations_parametrized(
        self,
        engagement_backend,
        caplog,
        reports,
        impressions,
        should_remove,
        client: TestClient,
    ):
        """Verify takedown_reported_recommendations behaves correctly."""
        payload = {
            "locale": "en-US",
            "feeds": ["sections"],
            "experimentName": ExperimentName.ML_SECTIONS_EXPERIMENT.value,
            "experimentBranch": "treatment",
        }

        baseline_response = client.post("/api/v1/curated-recommendations", json=payload)
        assert baseline_response.status_code == 200
        baseline_feeds = baseline_response.json()["feeds"]
        baseline_ids = [
            rec["corpusItemId"]
            for sid, section in baseline_feeds.items()
            if section
            for rec in section.get("recommendations", [])
        ]
        assert baseline_ids, "Expected at least one recommendation in baseline response"
        corpus_rec_id = baseline_ids[0]

        if reports is not None and impressions is not None:
            engagement_backend.metrics.update({corpus_rec_id: (reports, impressions)})

        caplog.clear()

        response = client.post("/api/v1/curated-recommendations", json=payload)

        assert response.status_code == 200
        feeds = response.json()["feeds"]

        response_ids = {
            rec["corpusItemId"]
            for sid, section in feeds.items()
            if section
            for rec in section.get("recommendations", [])
        }

        if should_remove:
            assert corpus_rec_id not in response_ids
            assert any("Excluding reported recommendation" in r.message for r in caplog.records)
        else:
            assert corpus_rec_id in response_ids
            assert not any(
                "Excluding reported recommendation" in r.message for r in caplog.records
            )

    @pytest.mark.parametrize(
        "region",
        ["GB", "IE"],
    )
    def test_uk_sections_enabled(self, region, client: TestClient):
        """Test that UK/IE users with feeds=['sections'] get sections."""
        response = client.post(
            "/api/v1/curated-recommendations",
            json={
                "locale": "en-GB",
                "region": region,
                "feeds": ["sections"],
            },
        )
        data = response.json()

        assert response.status_code == 200
        assert data["surfaceId"] == SurfaceId.NEW_TAB_EN_GB.value

        # Should have feeds with sections
        assert data["feeds"] is not None
        feeds = data["feeds"]
        sections = {name: section for name, section in feeds.items() if section is not None}

        # Should have top_stories_section and topic sections
        assert len(sections) >= 1
        assert "top_stories_section" in sections

        # Verify top_stories_section has the correct title
        assert sections["top_stories_section"]["title"] == "Popular Today"

        # data array should be empty (all recommendations in feeds)
        assert len(data["data"]) == 0


def test_uk_sections_with_gb_backend_data(
    scheduled_surface_backend: ScheduledSurfaceBackend,
    sections_gb_backend: SectionsProtocol,
    engagement_backend: EngagementBackend,
    prior_backend: PriorBackend,
    local_model_backend: LocalModelBackend,
    ml_recommendations_backend: MLRecsBackend,
    client: TestClient,
):
    """Test that GB sections with real GB-style externalIds are properly included.

    This test uses sections_gb.json which has GB-style externalIds like 'technology',
    'entertainment', 'politics' instead of US-style 'tech', 'arts', 'government'.
    """
    # Create a provider specifically with GB sections backend
    gb_provider = CuratedRecommendationsProvider(
        scheduled_surface_backend=scheduled_surface_backend,
        engagement_backend=engagement_backend,
        prior_backend=prior_backend,
        sections_backend=sections_gb_backend,
        local_model_backend=local_model_backend,
        ml_recommendations_backend=ml_recommendations_backend,
    )

    # Override the provider dependency for this test
    app.dependency_overrides[get_provider] = lambda: gb_provider

    try:
        response = client.post(
            "/api/v1/curated-recommendations",
            json={
                "locale": "en-GB",
                "region": "GB",
                "feeds": ["sections"],
            },
        )
        data = response.json()

        assert response.status_code == 200
        assert data["surfaceId"] == SurfaceId.NEW_TAB_EN_GB.value

        # Should have feeds with sections
        assert data["feeds"] is not None, "Expected feeds to be returned but got None"
        feeds = data["feeds"]
        sections = {name: section for name, section in feeds.items() if section is not None}

        # Should have top_stories_section and topic sections
        assert (
            len(sections) >= 2
        ), f"Expected at least 2 sections but got {len(sections)}: {list(sections.keys())}"
        assert "top_stories_section" in sections

        # Verify that GB-specific sections are present
        # GB sections have externalIds like 'technology', 'entertainment', 'politics'
        # (not US-style 'tech', 'arts', 'government')
        gb_expected_sections = {
            "technology",
            "entertainment",
            "politics",
            "gaming",
            "science",
            "personal-finance",
        }
        found_gb_sections = set(sections.keys()) & gb_expected_sections
        assert len(found_gb_sections) >= 1, (
            f"Expected at least one GB-style section from {gb_expected_sections}, "
            f"but found sections: {list(sections.keys())}"
        )

        # data array should be empty (all recommendations in feeds)
        assert len(data["data"]) == 0
    finally:
        # Reset the provider override
        app.dependency_overrides[get_provider] = lambda: None


def test_curated_recommendations_enriched_with_icons(
    manifest_provider,
    scheduled_surface_http_client,
    fixture_request_data,
    client: TestClient,
):
    """Test the enrichment of a curated recommendation with an added icon-url.
    Uses de-DE locale to test scheduled_surface backend icon enrichment.
    """
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
    manifest_provider.domain_lookup_table = {"microsoft.com": 0}

    mocked_response = {
        "data": {
            "scheduledSurface": {
                "items": [
                    {
                        "id": "scheduledSurfaceItemId-ABC",
                        "corpusItem": {
                            "id": "corpusItemId-XYZ",
                            "url": "https://www.microsoft.com/some-article?utm_source=firefox-newtab-de-de",
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

    response = client.post(
        "/api/v1/curated-recommendations",
        json={"locale": "de-DE"},
    )
    assert response.status_code == 200

    data = response.json()
    items = data["data"]
    assert len(items) == 1

    item = items[0]
    assert item["url"] == "https://www.microsoft.com/some-article?utm_source=firefox-newtab-de-de"

    assert "iconUrl" in item
    assert (
        item["iconUrl"] == "https://merino-images.services.mozilla.com/favicons/microsoft-icon.png"
    )

    # Clean up
    if get_provider in app.dependency_overrides:
        del app.dependency_overrides[get_provider]
