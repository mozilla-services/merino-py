"""Unit tests for CuratedRecommendationsProvider."""

import pytest
import random
import uuid

from pydantic import HttpUrl
from pytest_mock import MockerFixture

from merino.curated_recommendations import EngagementBackend, PriorBackend, FakespotBackend
from merino.curated_recommendations.corpus_backends.protocol import (
    ScheduledSurfaceId,
    Topic,
    CorpusBackend,
)
from merino.curated_recommendations.provider import (
    CuratedRecommendationsProvider,
)
from merino.curated_recommendations.protocol import (
    Locale,
    MAX_TILE_ID,
    MIN_TILE_ID,
    CuratedRecommendation,
    CuratedRecommendationsRequest,
)


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
            ("en-CA", "US", ScheduledSurfaceId.NEW_TAB_EN_US),
            ("en-GB", "US", ScheduledSurfaceId.NEW_TAB_EN_US),
            ("en-US", "US", ScheduledSurfaceId.NEW_TAB_EN_US),
            ("en-CA", "CA", ScheduledSurfaceId.NEW_TAB_EN_US),
            ("en-GB", "CA", ScheduledSurfaceId.NEW_TAB_EN_US),
            ("en-US", "CA", ScheduledSurfaceId.NEW_TAB_EN_US),
            ("de", "DE", ScheduledSurfaceId.NEW_TAB_DE_DE),
            ("de-AT", "DE", ScheduledSurfaceId.NEW_TAB_DE_DE),
            ("de-CH", "DE", ScheduledSurfaceId.NEW_TAB_DE_DE),
            ("en-CA", "GB", ScheduledSurfaceId.NEW_TAB_EN_GB),
            ("en-GB", "GB", ScheduledSurfaceId.NEW_TAB_EN_GB),
            ("en-US", "GB", ScheduledSurfaceId.NEW_TAB_EN_GB),
            ("en-CA", "IE", ScheduledSurfaceId.NEW_TAB_EN_GB),
            ("en-GB", "IE", ScheduledSurfaceId.NEW_TAB_EN_GB),
            ("en-US", "IE", ScheduledSurfaceId.NEW_TAB_EN_GB),
            ("fr", "FR", ScheduledSurfaceId.NEW_TAB_FR_FR),
            ("it", "IT", ScheduledSurfaceId.NEW_TAB_IT_IT),
            ("es", "ES", ScheduledSurfaceId.NEW_TAB_ES_ES),
            ("en-CA", "IN", ScheduledSurfaceId.NEW_TAB_EN_INTL),
            ("en-GB", "IN", ScheduledSurfaceId.NEW_TAB_EN_INTL),
            ("en-US", "IN", ScheduledSurfaceId.NEW_TAB_EN_INTL),
            ("de", "CH", ScheduledSurfaceId.NEW_TAB_DE_DE),
            ("de", "AT", ScheduledSurfaceId.NEW_TAB_DE_DE),
            ("de", "BE", ScheduledSurfaceId.NEW_TAB_DE_DE),
            # Locale can be a main language only.
            ("en", "CA", ScheduledSurfaceId.NEW_TAB_EN_US),
            ("en", "US", ScheduledSurfaceId.NEW_TAB_EN_US),
            ("en", "GB", ScheduledSurfaceId.NEW_TAB_EN_GB),
            ("en", "IE", ScheduledSurfaceId.NEW_TAB_EN_GB),
            ("en", "IN", ScheduledSurfaceId.NEW_TAB_EN_INTL),
            # The locale language primarily determines the market, even if it's not the most common language in the region.
            ("de", "US", ScheduledSurfaceId.NEW_TAB_DE_DE),
            ("en", "FR", ScheduledSurfaceId.NEW_TAB_EN_US),
            ("es", "DE", ScheduledSurfaceId.NEW_TAB_ES_ES),
            ("fr", "ES", ScheduledSurfaceId.NEW_TAB_FR_FR),
            ("it", "CA", ScheduledSurfaceId.NEW_TAB_IT_IT),
            # Extract region from locale, if it is not explicitly provided.
            ("en-US", None, ScheduledSurfaceId.NEW_TAB_EN_US),
            ("en-GB", None, ScheduledSurfaceId.NEW_TAB_EN_GB),
            ("en-IE", None, ScheduledSurfaceId.NEW_TAB_EN_GB),
            # locale can vary in case.
            ("eN-US", None, ScheduledSurfaceId.NEW_TAB_EN_US),
            ("En-GB", None, ScheduledSurfaceId.NEW_TAB_EN_GB),
            ("EN-ie", None, ScheduledSurfaceId.NEW_TAB_EN_GB),
            ("en-cA", None, ScheduledSurfaceId.NEW_TAB_EN_US),
            # region can vary in case.
            ("en", "gB", ScheduledSurfaceId.NEW_TAB_EN_GB),
            ("en", "Ie", ScheduledSurfaceId.NEW_TAB_EN_GB),
            ("en", "in", ScheduledSurfaceId.NEW_TAB_EN_INTL),
            # Default to international NewTab when region is unknown.
            ("en", "XX", ScheduledSurfaceId.NEW_TAB_EN_US),
            # Default to English when language is unknown.
            ("xx", "US", ScheduledSurfaceId.NEW_TAB_EN_US),
            ("xx", "CA", ScheduledSurfaceId.NEW_TAB_EN_US),
            ("xx", "GB", ScheduledSurfaceId.NEW_TAB_EN_GB),
            ("xx", "IE", ScheduledSurfaceId.NEW_TAB_EN_GB),
            ("xx", "YY", ScheduledSurfaceId.NEW_TAB_EN_US),
        ],
    )
    def test_get_recommendation_surface_id(
        self, locale: Locale, region: str, recommendation_surface_id: ScheduledSurfaceId
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


class TestCuratedRecommendationsProviderRankNeedToKnowRecommendations:
    """Unit tests for rank_need_to_know_recommendations method"""

    @staticmethod
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
            )

            recs.append(rec)

        return recs

    @staticmethod
    def mock_curated_recommendations_provider(
        mocker: MockerFixture, backup_recommendations: list[CuratedRecommendation] | None = None
    ) -> CuratedRecommendationsProvider:
        """Mock the necessary components of CuratedRecommendationsProvider.

        @param mocker: MockerFixture
        @param backup_recommendations: a list of curated recommendations to use as backup if there are not enough
        time-sensitive stories in the main feed
        @return: A mocked CuratedRecommendationsProvider
        """
        # Mock the __init__ method to prevent actual initialization
        mocker.patch.object(CuratedRecommendationsProvider, "__init__", return_value=None)

        # Mock the rank_recommendations method
        mocker.patch.object(CuratedRecommendationsProvider, "rank_recommendations")

        # Mock backup recommendations with the data that was provided to this method
        if backup_recommendations:
            mocker.patch.object(
                CuratedRecommendationsProvider,
                "fetch_backup_recommendations",
                return_value=backup_recommendations,
            )

        # Create and return the mocked provider instance
        provider = CuratedRecommendationsProvider(
            mocker.patch.object(CorpusBackend, "__init__", return_value=None),
            mocker.patch.object(EngagementBackend, "__init__", return_value=None),
            mocker.patch.object(PriorBackend, "__init__", return_value=None),
            mocker.patch.object(FakespotBackend, "__init__", return_value=None),
        )

        return provider

    @staticmethod
    def mock_curated_recommendations_request(
        mocker: MockerFixture,
    ) -> CuratedRecommendationsRequest:
        """Mock the necessary components of CuratedRecommendationsRequest.

        @param mocker: MockerFixture
        @return: A mocked CuratedRecommendationsRequest
        """
        # Mock the __init__ methods to prevent actual initialization
        mocker.patch.object(CuratedRecommendationsRequest, "__init__", return_value=None)

        # Create and return the mocked provider instance
        request = CuratedRecommendationsRequest(locale=Locale.EN_US)

        return request

    @pytest.mark.asyncio
    async def test_rank_need_to_know_recommendations(self, mocker: MockerFixture):
        """Test the main flow of logic in the function

        @param mocker: MockerFixture
        """
        # Create mock recommendations
        recommendations = self.generate_recommendations(100)

        # Define the surface ID
        surface_id = ScheduledSurfaceId.NEW_TAB_EN_US

        # Instantiate the mocked classes
        provider = self.mock_curated_recommendations_provider(mocker)
        request = self.mock_curated_recommendations_request(mocker)

        # Mock the rank_recommendations method separately to make sure it returns
        # the correct number of results, and we can make sure it was called later
        rank_recommendations = mocker.patch.object(
            CuratedRecommendationsProvider,
            "rank_recommendations",
            return_value=[r for r in recommendations if not r.isTimeSensitive],
        )

        # Call the method
        general_feed, need_to_know_feed, title = await provider.rank_need_to_know_recommendations(
            recommendations, surface_id, request
        )

        # Verify that the recommendations were split correctly
        assert len(need_to_know_feed) == len([r for r in recommendations if r.isTimeSensitive])
        assert len(general_feed) == len([r for r in recommendations if not r.isTimeSensitive])

        # Verify that the rank_recommendations method was called with the correct arguments
        rank_recommendations.assert_called_once_with(general_feed, surface_id, request)

        # Verify that receivedRank values were reset from zero for the General feed
        for i, rec in enumerate(need_to_know_feed):
            assert i == rec.receivedRank

        # Verify that receivedRank values were reset from zero for the Need to Know feed
        for i, rec in enumerate(need_to_know_feed):
            assert i == rec.receivedRank

        # Verify that the localized title is correct
        assert title == "In the news"

    @pytest.mark.asyncio
    async def test_rank_need_to_know_recommendations_different_surface(
        self, mocker: MockerFixture
    ):
        """Test localization with a non-English New Tab surface

        @param mocker: MockerFixture
        """
        # Create mock recommendations
        recommendations = self.generate_recommendations(20)

        # Define the surface ID
        surface_id = ScheduledSurfaceId.NEW_TAB_DE_DE

        # Instantiate the mocked classes
        provider = self.mock_curated_recommendations_provider(mocker)
        request = self.mock_curated_recommendations_request(mocker)

        # Call the method
        general_feed, need_to_know_feed, title = await provider.rank_need_to_know_recommendations(
            recommendations, surface_id, request
        )

        # Verify that the title is correct for the German New Tab surface
        assert title == "In den News"

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        "time_sensitive_count_today",
        list(range(5)),
    )
    async def test_rank_need_to_know_recommendations_backup_stories(
        self, mocker: MockerFixture, time_sensitive_count_today
    ):
        """Test an edge case when today's stories for the 'Need to know' feed
        have not yet been curated and the feed specifically for these stories
        needs to fall back to yesterday's data.

        @param mocker: MockerFixture
        @param mocker: n_time_sensitive_today The number of time-sensitive items scheduled for today
        """
        # Create mock recommendations for today - this batch WON'T have a sufficient number of
        # time-sensitive stories available
        recs = self.generate_recommendations(20, time_sensitive_count_today)
        # Double-check the initial recommendations don't have any time-sensitive items
        assert len([r for r in recs if r.isTimeSensitive]) == time_sensitive_count_today

        # Create backup recommendations - this batch WILL have a mix of normal
        # and time-sensitive stories
        backup_recs = self.generate_recommendations(100, 10)

        # Define the surface ID
        surface_id = ScheduledSurfaceId.NEW_TAB_EN_US

        # Instantiate the mocked classes
        provider = self.mock_curated_recommendations_provider(mocker, backup_recs)
        request = self.mock_curated_recommendations_request(mocker)

        # Call the method
        general_feed, need_to_know_feed, title = await provider.rank_need_to_know_recommendations(
            recs, surface_id, request
        )

        # Make sure the items in the need_to_know feed came from the backup recommendations
        assert len(need_to_know_feed) == 10
