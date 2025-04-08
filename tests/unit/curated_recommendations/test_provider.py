"""Unit tests for CuratedRecommendationsProvider."""

import copy
import random
import uuid

import pytest
from pydantic import HttpUrl

from merino.curated_recommendations.corpus_backends.protocol import (
    SurfaceId,
    Topic,
)
from merino.curated_recommendations.layouts import layout_3_ads
from merino.curated_recommendations.protocol import (
    Locale,
    MAX_TILE_ID,
    MIN_TILE_ID,
    CuratedRecommendation,
    SectionConfiguration,
    Section,
)
from merino.curated_recommendations.provider import CuratedRecommendationsProvider
from tests.unit.curated_recommendations.fixtures import generate_sections_feed


def generate_recommendations(
    length: int, time_sensitive_count: int | None = None
) -> list[CuratedRecommendation]:
    """Create dummy recommendations for the tests below.

    @param length: how many recommendations are needed for a test
    @param time_sensitive_count: the number of items to make time-sensitive.
        If None (the default), then half of the recommendations will be time-sensitive.
    @return: A list of curated recommendations
    """
    recs = []

    # If time_sensitive_count is not provided, default to half the length
    if time_sensitive_count is None:
        time_sensitive_count = length // 2

    # Randomly choose indices that will be time-sensitive
    time_sensitive_indices = random.sample(range(length), time_sensitive_count)

    for i in range(length):
        rec = CuratedRecommendation(
            corpusItemId=str(uuid.uuid4()),
            tileId=MIN_TILE_ID + random.randint(0, 101),
            receivedRank=i,
            scheduledCorpusItemId=str(uuid.uuid4()),
            url=HttpUrl("https://littlelarry.com/"),
            title="little larry",
            excerpt="is failing english",
            topic=random.choice(list(Topic)),
            publisher="cohens",
            isTimeSensitive=i in time_sensitive_indices,
            imageUrl=HttpUrl("https://placehold.co/600x400/"),
            iconUrl=None,
        )

        recs.append(rec)

    return recs


class TestCuratedRecommendationsProviderExtractLanguageFromLocale:
    """Unit tests for extract_language_from_locale."""

    @pytest.mark.parametrize(
        "locale, language",
        [
            ("fr", "fr"),
            ("fr-FR", "fr"),
            ("es", "es"),
            ("es-ES", "es"),
            ("it", "it"),
            ("it-IT", "it"),
            ("en", "en"),
            ("en-CA", "en"),
            ("en-GB", "en"),
            ("en-US", "en"),
            ("de", "de"),
            ("de-DE", "de"),
            ("de-AT", "de"),
            ("de-CH", "de"),
        ],
    )
    def test_extract_language_from_locale(self, locale, language):
        """Testing the extract_language_from_locale() method
        & ensure appropriate language is returned.
        """
        assert (
            CuratedRecommendationsProvider.extract_language_from_locale(Locale(locale)) == language
        )

    def test_extract_language_from_locale_return_none(self):
        """Testing the extract_language_from_locale() method
        & ensure if no match is found, return None
        """
        assert CuratedRecommendationsProvider.extract_language_from_locale("1234") is None


class TestCuratedRecommendationsProviderDeriveRegion:
    """Unit tests for derive_region."""

    @pytest.mark.parametrize(
        "locale, region",
        [
            ("fr-FR", "FR"),
            ("es-ES", "ES"),
            ("it-IT", "IT"),
            ("en-CA", "CA"),
            ("en-GB", "GB"),
            ("en-US", "US"),
            ("de-DE", "DE"),
            ("de-AT", "AT"),
            ("de-CH", "CH"),
        ],
    )
    def test_derive_region_from_locale(self, locale, region):
        """Testing the derive_region() method & ensuring region is derived
        if only locale is provided
        """
        assert CuratedRecommendationsProvider.derive_region(Locale(locale)) == region

    @pytest.mark.parametrize(
        "locale, region, derived_region",
        [
            ("de", "US", "US"),
            ("en", "FR", "FR"),
            ("es", "DE", "DE"),
            ("fr", "ES", "ES"),
            ("it", "CA", "CA"),
        ],
    )
    def test_derive_region_from_region(self, locale, region, derived_region):
        """Testing the derive_region() method & ensure region is derived
        from region if region is provided
        """
        assert (
            CuratedRecommendationsProvider.derive_region(Locale(locale), region) == derived_region
        )

    def test_derive_region_return_none(self):
        """Testing the derive_region() method &
        ensure if no match is found, return None
        """
        # if region is passed
        assert CuratedRecommendationsProvider.derive_region("123", "123") is None
        # if only locale is passed
        assert CuratedRecommendationsProvider.derive_region("123") is None
        # if only locale is passed
        assert CuratedRecommendationsProvider.derive_region("en") is None


class TestCuratedRecommendationsProviderGetRecommendationSurfaceId:
    """Unit tests for get_recommendation_surface_id."""

    @pytest.mark.parametrize(
        "locale,region,recommendation_surface_id",
        [
            # Test cases below are from the Newtab locales/region documentation maintained by the Firefox integration
            # team: https://docs.google.com/document/d/1omclr-eETJ7zAWTMI7mvvsc3_-ns2Iiho4jPEfrmZfo/edit Ref:
            # https://github.com/Pocket/recommendation-api/blob/c0fe2d1cab7ec7931c3c8c2e8e3d82908801ab00/tests/unit
            # /data_providers/test_new_tab_dispatch.py#L7 # noqa
            ("en-CA", "US", SurfaceId.NEW_TAB_EN_US),
            ("en-GB", "US", SurfaceId.NEW_TAB_EN_US),
            ("en-US", "US", SurfaceId.NEW_TAB_EN_US),
            ("en-CA", "CA", SurfaceId.NEW_TAB_EN_US),
            ("en-GB", "CA", SurfaceId.NEW_TAB_EN_US),
            ("en-US", "CA", SurfaceId.NEW_TAB_EN_US),
            ("de", "DE", SurfaceId.NEW_TAB_DE_DE),
            ("de-AT", "DE", SurfaceId.NEW_TAB_DE_DE),
            ("de-CH", "DE", SurfaceId.NEW_TAB_DE_DE),
            ("en-CA", "GB", SurfaceId.NEW_TAB_EN_GB),
            ("en-GB", "GB", SurfaceId.NEW_TAB_EN_GB),
            ("en-US", "GB", SurfaceId.NEW_TAB_EN_GB),
            ("en-CA", "IE", SurfaceId.NEW_TAB_EN_GB),
            ("en-GB", "IE", SurfaceId.NEW_TAB_EN_GB),
            ("en-US", "IE", SurfaceId.NEW_TAB_EN_GB),
            ("fr", "FR", SurfaceId.NEW_TAB_FR_FR),
            ("it", "IT", SurfaceId.NEW_TAB_IT_IT),
            ("es", "ES", SurfaceId.NEW_TAB_ES_ES),
            ("en-CA", "IN", SurfaceId.NEW_TAB_EN_INTL),
            ("en-GB", "IN", SurfaceId.NEW_TAB_EN_INTL),
            ("en-US", "IN", SurfaceId.NEW_TAB_EN_INTL),
            ("de", "CH", SurfaceId.NEW_TAB_DE_DE),
            ("de", "AT", SurfaceId.NEW_TAB_DE_DE),
            ("de", "BE", SurfaceId.NEW_TAB_DE_DE),
            # Locale can be a main language only.
            ("en", "CA", SurfaceId.NEW_TAB_EN_US),
            ("en", "US", SurfaceId.NEW_TAB_EN_US),
            ("en", "GB", SurfaceId.NEW_TAB_EN_GB),
            ("en", "IE", SurfaceId.NEW_TAB_EN_GB),
            ("en", "IN", SurfaceId.NEW_TAB_EN_INTL),
            # The locale language primarily determines the market, even if it's not the most common language in the region.
            ("de", "US", SurfaceId.NEW_TAB_DE_DE),
            ("en", "FR", SurfaceId.NEW_TAB_EN_US),
            ("es", "DE", SurfaceId.NEW_TAB_ES_ES),
            ("fr", "ES", SurfaceId.NEW_TAB_FR_FR),
            ("it", "CA", SurfaceId.NEW_TAB_IT_IT),
            # Extract region from locale, if it is not explicitly provided.
            ("en-US", None, SurfaceId.NEW_TAB_EN_US),
            ("en-GB", None, SurfaceId.NEW_TAB_EN_GB),
            ("en-IE", None, SurfaceId.NEW_TAB_EN_GB),
            # locale can vary in case.
            ("eN-US", None, SurfaceId.NEW_TAB_EN_US),
            ("En-GB", None, SurfaceId.NEW_TAB_EN_GB),
            ("EN-ie", None, SurfaceId.NEW_TAB_EN_GB),
            ("en-cA", None, SurfaceId.NEW_TAB_EN_US),
            # region can vary in case.
            ("en", "gB", SurfaceId.NEW_TAB_EN_GB),
            ("en", "Ie", SurfaceId.NEW_TAB_EN_GB),
            ("en", "in", SurfaceId.NEW_TAB_EN_INTL),
            # Default to international NewTab when region is unknown.
            ("en", "XX", SurfaceId.NEW_TAB_EN_US),
            # Default to English when language is unknown.
            ("xx", "US", SurfaceId.NEW_TAB_EN_US),
            ("xx", "CA", SurfaceId.NEW_TAB_EN_US),
            ("xx", "GB", SurfaceId.NEW_TAB_EN_GB),
            ("xx", "IE", SurfaceId.NEW_TAB_EN_GB),
            ("xx", "YY", SurfaceId.NEW_TAB_EN_US),
        ],
    )
    def test_get_recommendation_surface_id(
        self, locale: Locale, region: str, recommendation_surface_id: SurfaceId
    ):
        """Testing the get_recommendation_surface_id() method &
        ensure correct surface id is returned based on passed locale & region
        """
        assert (
            CuratedRecommendationsProvider.get_recommendation_surface_id(locale, region)
            == recommendation_surface_id
        )


class TestCuratedRecommendationTileId:
    """Unit tests for CuratedRecommendation tileId generation."""

    # Common parameters for initializing CuratedRecommendation
    common_params = {
        "corpusItemId": "00000000-0000-0000-0000-000000000000",
        "url": HttpUrl("https://example.com"),
        "title": "Example Title",
        "excerpt": "Example Excerpt",
        "topic": Topic.CAREER,
        "publisher": "Example Publisher",
        "isTimeSensitive": False,
        "imageUrl": HttpUrl("https://example.com/image.jpg"),
        "receivedRank": 1,
    }

    @pytest.mark.parametrize(
        "scheduled_corpus_item_id, expected",
        [
            # Test random inputs. Boundary cases are not covered because sha256 is hard to reverse.
            ("550e8400-e29b-41d4-a716-446655440000", 367820988390657),
            ("6ba7b810-9dad-11d1-80b4-00c04fd430c8", 1754091520067902),
            ("123e4567-e89b-12d3-a456-426614174000", 1021785982574447),
            ("a3bb189e-8bf9-3888-9912-ace4e6543002", 4390412044299399),
            ("c1a5fc62-9a4e-43f3-b748-2106a12e8151", 8630494423250594),
        ],
    )
    def test_tile_id_generation(self, scheduled_corpus_item_id, expected):
        """Testing the tile_id generation in the CuratedRecommendation constructor."""
        # Create a CuratedRecommendation instance with the given scheduledCorpusItemId
        recommendation = CuratedRecommendation(
            scheduledCorpusItemId=scheduled_corpus_item_id,
            **self.common_params,
        )

        assert recommendation.tileId == expected

    @pytest.mark.parametrize("tile_id", [MIN_TILE_ID, MAX_TILE_ID])
    def test_tile_id_min_max(self, tile_id):
        """Test that the model can be initialized with MIN_TILE_ID and MAX_TILE_ID."""
        recommendation = CuratedRecommendation(
            scheduledCorpusItemId="550e8400-e29b-41d4-a716-446655440000",
            tileId=tile_id,
            **self.common_params,
        )
        assert recommendation.tileId == tile_id

    @pytest.mark.parametrize("invalid_tile_id", [0, 999999, -1, (1 << 53)])
    def test_invalid_tile_id(self, invalid_tile_id):
        """Test that the model cannot be initialized with invalid tile IDs."""
        with pytest.raises(ValueError):
            CuratedRecommendation(
                scheduledCorpusItemId="550e8400-e29b-41d4-a716-446655440000",
                tileId=invalid_tile_id,
                **self.common_params,
            )


class TestExcludeRecommendationsFromBlockedSections:
    """Tests covering Provider.exclude_recommendations_from_blocked_sections"""

    def test_removes_only_blocked_recommendations(self):
        """Test that blocked (and only blocked) sections are removed"""
        original_recs = generate_recommendations(3)
        original_recs[0].topic = Topic.SPORTS
        original_recs[1].topic = Topic.SCIENCE
        original_recs[2].topic = Topic.FOOD

        # Science is blocked, food is followed.
        requested_sections = [
            SectionConfiguration(
                sectionId=Topic.SCIENCE.value,
                isFollowed=False,
                isBlocked=True,
            ),
            SectionConfiguration(
                sectionId=Topic.FOOD.value,
                isFollowed=True,
                isBlocked=False,
            ),
        ]

        result_recs = CuratedRecommendationsProvider.exclude_recommendations_from_blocked_sections(
            original_recs, requested_sections
        )

        # Only the sports and food recommendation remain, in this order.
        assert len(result_recs) == 2
        assert result_recs[0].topic == Topic.SPORTS
        assert result_recs[1].topic == Topic.FOOD

    def test_handles_non_topic_sections(self):
        """Test that blocked sections not corresponding to a topic are ignored"""
        original_recs = generate_recommendations(2)
        requested_sections = [
            SectionConfiguration(sectionId="top_stories_section", isFollowed=False, isBlocked=True)
        ]

        result_recs = CuratedRecommendationsProvider.exclude_recommendations_from_blocked_sections(
            original_recs, requested_sections
        )

        # Call should output should match the input.
        assert result_recs == original_recs

    def test_accepts_empty_sections_list(self):
        """Test that the function accepts an empty list of requested sections"""
        original_recs = generate_recommendations(2)
        requested_sections = []

        result_recs = CuratedRecommendationsProvider.exclude_recommendations_from_blocked_sections(
            original_recs, requested_sections
        )

        # Call should output should match the input.
        assert result_recs == original_recs

    def test_keeps_recommendations_without_topics(self):
        """Test that the function keeps recommendations without topics"""
        original_recs = generate_recommendations(2)
        original_recs[0].topic = None

        requested_sections = []

        result_recs = CuratedRecommendationsProvider.exclude_recommendations_from_blocked_sections(
            original_recs, requested_sections
        )

        assert result_recs == original_recs


class TestSetDoubleRowLayout:
    """Tests covering CuratedRecommendationsProvider.set_double_row_layout"""

    @pytest.fixture
    def sample_feed(self) -> dict[str, Section]:
        """Return a feed with a top stories section (rank 0) and two additional sections."""
        return generate_sections_feed(section_count=3)

    @pytest.mark.asyncio
    async def test_no_second_section(self):
        """Test that if there is no second section, set_double_row_layout leaves the feed unchanged."""
        # Generate a feed with only the top stories section.
        feed = generate_sections_feed(section_count=1)
        original_feed = copy.deepcopy(feed)
        CuratedRecommendationsProvider.set_double_row_layout(feed)
        # Verify that top_stories_section remains unchanged.
        assert feed["top_stories_section"].layout == original_feed["top_stories_section"].layout

    @pytest.mark.asyncio
    async def test_insufficient_recommendations(self, sample_feed: dict[str, Section]):
        """Test that second section layout remains unchanged if this section doesn't have enough recommendations."""
        # Find the second section (receivedFeedRank == 1)
        second_section = next(s for s in sample_feed.values() if s.receivedFeedRank == 1)
        # Set 1 less recommendation than is required for layout_3_ads
        second_section.recommendations = generate_recommendations(layout_3_ads.max_tile_count - 1)
        original_layout = second_section.layout

        CuratedRecommendationsProvider.set_double_row_layout(sample_feed)

        assert second_section.layout == original_layout

    @pytest.mark.asyncio
    async def test_sufficient_recommendations(self, sample_feed: dict[str, Section]):
        """Test that second section layout remains unchanged if this section doesn't have enough recommendations."""
        # Find the second section (receivedFeedRank == 1)
        second_section = next(s for s in sample_feed.values() if s.receivedFeedRank == 1)
        # Set enough recommendations for layout_3_ads
        second_section.recommendations = generate_recommendations(layout_3_ads.max_tile_count)

        CuratedRecommendationsProvider.set_double_row_layout(sample_feed)

        assert second_section.layout == layout_3_ads
