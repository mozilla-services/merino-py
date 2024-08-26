"""Unit test for CuratedRecommendationsProvider."""

import pytest
import random

from pydantic import HttpUrl

from merino.curated_recommendations.corpus_backends.protocol import ScheduledSurfaceId, Topic
from merino.curated_recommendations.provider import (
    CuratedRecommendation,
    CuratedRecommendationsProvider,
    Locale,
    MAX_TILE_ID,
    MIN_TILE_ID,
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


class TestCuratedRecommendationsProviderSpreadPublishers:
    """Unit tests for spread_publishers."""

    @staticmethod
    def generate_recommendations(item_ids: list[str]) -> list[CuratedRecommendation]:
        """Create dummy recommendations for the tests below."""
        recs = []
        for item_id in item_ids:
            rec = CuratedRecommendation(
                tileId=MIN_TILE_ID + random.randint(0, 101),
                receivedRank=random.randint(0, 101),
                scheduledCorpusItemId=item_id,
                url=HttpUrl("https://littlelarry.com/"),
                title="little larry",
                excerpt="is failing english",
                topic=random.choice(list(Topic)),
                publisher="cohens",
                imageUrl=HttpUrl("https://placehold.co/600x400/"),
            )

            recs.append(rec)

        return recs

    def test_spread_publishers_single_reorder(self):
        """Should only re-order one element."""
        recs = self.generate_recommendations(["1", "2", "3", "4", "5", "6", "7", "8"])
        recs[0].publisher = "thedude.com"
        recs[1].publisher = "walter.com"
        recs[2].publisher = "donnie.com"
        recs[3].publisher = "thedude.com"
        recs[4].publisher = "innout.com"
        recs[5].publisher = "bowling.com"
        recs[6].publisher = "walter.com"
        recs[7].publisher = "abides.com"

        reordered = CuratedRecommendationsProvider.spread_publishers(recs, spread_distance=3)

        # ensure the elements are re-ordered in the way we expect

        # this domain check is redundant, but it's kind of a nice illustration of what we expect and is easier
        # to read than the item ids, so i'm leaving it
        assert [x.publisher for x in reordered] == [
            "thedude.com",
            "walter.com",
            "donnie.com",
            "innout.com",
            "thedude.com",
            "bowling.com",
            "walter.com",
            "abides.com",
        ]
        assert [x.scheduledCorpusItemId for x in reordered] == [
            "1",
            "2",
            "3",
            "5",
            "4",
            "6",
            "7",
            "8",
        ]

    def test_spread_publishers_multiple_reorder(self):
        """Should re-order multiple elements."""
        recs = self.generate_recommendations(["1", "2", "3", "4", "5", "6", "7", "8"])
        recs[0].publisher = "thedude.com"
        recs[1].publisher = "walter.com"
        recs[2].publisher = "walter.com"
        recs[3].publisher = "thedude.com"
        recs[4].publisher = "innout.com"
        recs[5].publisher = "innout.com"
        recs[6].publisher = "donnie.com"
        recs[7].publisher = "abides.com"

        reordered = CuratedRecommendationsProvider.spread_publishers(recs, spread_distance=3)

        # ensure the elements are re-ordered in the way we expect

        # this domain check is redundant, but it's kind of a nice illustration of what we expect and is easier
        # to read than the item ids, so i'm leaving it
        assert [x.publisher for x in reordered] == [
            "thedude.com",
            "walter.com",
            "innout.com",
            "donnie.com",
            "thedude.com",
            "walter.com",
            "innout.com",
            "abides.com",
        ]
        assert [x.scheduledCorpusItemId for x in reordered] == [
            "1",
            "2",
            "5",
            "7",
            "4",
            "3",
            "6",
            "8",
        ]

    def test_spread_publishers_give_up_at_the_end(self):
        """Should not re-order when the end of the list cannot satisfy the requested spread."""
        recs = self.generate_recommendations(["1", "2", "3", "4", "5", "6", "7", "8"])
        recs[0].publisher = "thedude.com"
        recs[1].publisher = "abides.com"
        recs[2].publisher = "walter.com"
        recs[3].publisher = "donnie.com"
        recs[4].publisher = "donnie.com"
        recs[5].publisher = "innout.com"
        recs[6].publisher = "donnie.com"
        recs[7].publisher = "innout.com"

        reordered = CuratedRecommendationsProvider.spread_publishers(recs, spread_distance=3)

        # ensure the elements are re-ordered in the way we expect

        # if the number of elements at the end of the list cannot satisfy the spread, we give up and just append
        # the remainder
        assert [x.scheduledCorpusItemId for x in reordered] == [
            "1",
            "2",
            "3",
            "4",
            "6",
            "5",
            "7",
            "8",
        ]

    def test_spread_publishers_cannot_spread(self):
        """If we don't have enough variance in publishers, spread can't happen."""
        recs = self.generate_recommendations(["1", "2", "3", "4", "5", "6", "7", "8"])
        recs[0].publisher = "thedude.com"
        recs[1].publisher = "abides.com"
        recs[2].publisher = "donnie.com"
        recs[3].publisher = "donnie.com"
        recs[4].publisher = "thedude.com"
        recs[5].publisher = "abides.com"
        recs[6].publisher = "thedude.com"
        recs[7].publisher = "donnie.com"

        reordered = CuratedRecommendationsProvider.spread_publishers(recs, spread_distance=3)

        # ensure the elements aren't reordered at all (as we don't have enough publisher variance)
        assert [x.scheduledCorpusItemId for x in reordered] == [
            "1",
            "2",
            "3",
            "4",
            "5",
            "6",
            "7",
            "8",
        ]


class TestCuratedRecommendationsProviderBoostPreferredTopic:
    """Unit tests for boost_preferred_topic & is_boostable."""

    @staticmethod
    def generate_recommendations(topics: list[Topic]) -> list[CuratedRecommendation]:
        """Create dummy recommendations for the tests below with specific topics."""
        recs = []
        i = 1
        for topic in topics:
            rec = CuratedRecommendation(
                tileId=MIN_TILE_ID + random.randint(0, 101),
                receivedRank=random.randint(0, 101),
                scheduledCorpusItemId=str(i),
                url=HttpUrl("https://littlelarry.com/"),
                title="little larry",
                excerpt="is failing english",
                topic=topic,
                publisher="cohens",
                imageUrl=HttpUrl("https://placehold.co/600x400/"),
            )
            recs.append(rec)
            i += 1
        return recs

    def test_boost_preferred_topic_one_topic(self):
        """Should boost first 2 recs found with preferred topic to the first two slots."""
        recs = self.generate_recommendations(
            [Topic.TRAVEL, Topic.ARTS, Topic.EDUCATION, Topic.FOOD, Topic.EDUCATION]
        )
        reordered_recs = CuratedRecommendationsProvider.boost_preferred_topic(
            recs, [Topic.EDUCATION]
        )

        assert len(recs) == len(reordered_recs)
        # for readability
        # assert that the first two recs have topic EDUCATION
        assert reordered_recs[0].topic == Topic.EDUCATION
        assert reordered_recs[1].topic == Topic.EDUCATION
        assert reordered_recs[0].scheduledCorpusItemId == "3"
        assert reordered_recs[1].scheduledCorpusItemId == "5"

    def test_boost_preferred_topic_two_topics(self):
        """If two preferred topics are provided but only one topic is found in list or recs, boost first 2 recs
        to first two slots.
        """
        recs = self.generate_recommendations(
            [Topic.TRAVEL, Topic.ARTS, Topic.SPORTS, Topic.FOOD, Topic.EDUCATION, Topic.FOOD]
        )
        # career topic is not present in rec list, boost item with food topic to second slot
        reordered_recs = CuratedRecommendationsProvider.boost_preferred_topic(
            recs, [Topic.CAREER, Topic.FOOD]
        )

        assert len(recs) == len(reordered_recs)
        # for readability
        assert reordered_recs[0].topic == Topic.FOOD
        assert reordered_recs[0].scheduledCorpusItemId == "4"
        assert reordered_recs[1].topic == Topic.FOOD
        assert reordered_recs[1].scheduledCorpusItemId == "6"

    @pytest.mark.parametrize(
        "preferred_topics, expected_topics, expected_ids",
        [
            # Test case for 2 preferred topics
            (
                [Topic.SPORTS, Topic.FOOD],
                [Topic.SPORTS, Topic.SPORTS, Topic.FOOD, Topic.FOOD],
                ["4", "13", "5", "7"],
            ),
            # Test case for 3 preferred topics
            (
                [Topic.BUSINESS, Topic.FOOD, Topic.TRAVEL],
                [
                    Topic.BUSINESS,
                    Topic.BUSINESS,
                    Topic.FOOD,
                    Topic.FOOD,
                    Topic.TRAVEL,
                    Topic.TRAVEL,
                ],
                ["1", "14", "5", "7", "2", "8"],
            ),
            # Test case for 4 preferred topics
            (
                [Topic.POLITICS, Topic.ARTS, Topic.TRAVEL, Topic.SPORTS],
                [
                    Topic.POLITICS,
                    Topic.POLITICS,
                    Topic.ARTS,
                    Topic.ARTS,
                    Topic.TRAVEL,
                    Topic.TRAVEL,
                    Topic.SPORTS,
                    Topic.SPORTS,
                ],
                ["9", "12", "3", "10", "2", "8", "4", "13"],
            ),
            # Test case for 5 preferred topics
            (
                [Topic.POLITICS, Topic.ARTS, Topic.TRAVEL, Topic.SPORTS, Topic.EDUCATION],
                [
                    Topic.POLITICS,
                    Topic.POLITICS,
                    Topic.ARTS,
                    Topic.ARTS,
                    Topic.TRAVEL,
                    Topic.TRAVEL,
                    Topic.SPORTS,
                    Topic.SPORTS,
                    Topic.EDUCATION,
                    Topic.EDUCATION,
                ],
                ["9", "12", "3", "10", "2", "8", "4", "13", "6", "16"],
            ),
            # Test case for 6+ preferred topics (assuming max 10 items in total)
            (
                [
                    Topic.POLITICS,
                    Topic.ARTS,
                    Topic.TRAVEL,
                    Topic.SPORTS,
                    Topic.EDUCATION,
                    Topic.FOOD,
                ],
                [
                    Topic.POLITICS,
                    Topic.POLITICS,
                    Topic.ARTS,
                    Topic.ARTS,
                    Topic.TRAVEL,
                    Topic.TRAVEL,
                    Topic.SPORTS,
                    Topic.SPORTS,
                    Topic.EDUCATION,
                    Topic.EDUCATION,
                ],
                ["9", "12", "3", "10", "2", "8", "4", "13", "6", "16"],
            ),
        ],
    )
    def test_boost_preferred_topic(self, preferred_topics, expected_topics, expected_ids):
        """Test boosting works correctly for 2, 3, 4, 5, 6+ preferred topics."""
        recs = self.generate_recommendations(
            [
                Topic.BUSINESS,  # 1
                Topic.TRAVEL,  # 2
                Topic.ARTS,  # 3
                Topic.SPORTS,  # 4
                Topic.FOOD,  # 5
                Topic.EDUCATION,  # 6
                Topic.FOOD,  # 7
                Topic.TRAVEL,  # 8
                Topic.POLITICS,  # 9
                Topic.ARTS,  # 10
                Topic.ARTS,  # 11
                Topic.POLITICS,  # 12
                Topic.SPORTS,  # 13
                Topic.BUSINESS,  # 14
                Topic.PARENTING,  # 15
                Topic.EDUCATION,  # 16
            ]
        )

        reordered_recs = CuratedRecommendationsProvider.boost_preferred_topic(
            recs, preferred_topics
        )
        # Check that the length of the reordered recommendations matches
        assert len(reordered_recs) == len(recs)

        # Check that the expected topics and IDs are in the correct positions
        for idx, (expected_topic, expected_id) in enumerate(zip(expected_topics, expected_ids)):
            assert reordered_recs[idx].topic == expected_topic
            assert reordered_recs[idx].scheduledCorpusItemId == expected_id

    def test_boost_preferred_topic_no_preferred_topic_found(self):
        """Don't reorder list of recs if no items with preferred topics are found."""
        recs = self.generate_recommendations(
            [Topic.POLITICS, Topic.ARTS, Topic.SPORTS, Topic.FOOD, Topic.PERSONAL_FINANCE]
        )
        reordered_recs = CuratedRecommendationsProvider.boost_preferred_topic(recs, [Topic.CAREER])

        assert len(recs) == len(reordered_recs)
        # assert that the order of recs has not changed since recs don't have preferred topic
        assert reordered_recs == recs

    def test_is_boostable_return_true(self):
        """Should return True if all preferred topics are not in the top N slots (2 recs per topic)"""
        recs = self.generate_recommendations(
            [Topic.TRAVEL, Topic.TRAVEL, Topic.ARTS, Topic.SPORTS, Topic.EDUCATION, Topic.SPORTS]
        )
        # should return true as recs with TRAVEL topic are in the first two slots, but 3rd slot is occupied by ARTS
        # topic but should be occupied with SPORTS topic
        is_boostable = CuratedRecommendationsProvider.is_boostable(
            recs, [Topic.TRAVEL, Topic.SPORTS]
        )

        assert is_boostable

    def test_is_boostable_return_false(self):
        """Should return False if any of preferred topics is already in top 2 recs"""
        recs = self.generate_recommendations(
            [Topic.TRAVEL, Topic.TRAVEL, Topic.SPORTS, Topic.SPORTS, Topic.EDUCATION, Topic.SPORTS]
        )
        # should return false as 2 topics are provided and top 4 slots are filled with recs from those topics
        # 2 recs per topic
        is_boostable = CuratedRecommendationsProvider.is_boostable(
            recs, [Topic.TRAVEL, Topic.SPORTS]
        )

        assert not is_boostable


class TestCuratedRecommendationTileId:
    """Unit tests for CuratedRecommendation tileId generation."""

    # Common parameters for initializing CuratedRecommendation
    common_params = {
        "url": HttpUrl("https://example.com"),
        "title": "Example Title",
        "excerpt": "Example Excerpt",
        "topic": Topic.CAREER,
        "publisher": "Example Publisher",
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
