"""Module with tests covering merino/curated_recommendations/sections.py"""

import copy

import pytest

from merino.curated_recommendations.corpus_backends.protocol import Topic
from merino.curated_recommendations.layouts import layout_3_ads
from merino.curated_recommendations.protocol import Section, SectionConfiguration
from merino.curated_recommendations.sections import (
    adjust_ads_in_sections,
    set_double_row_layout,
    exclude_recommendations_from_blocked_sections,
)
from tests.unit.curated_recommendations.fixtures import (
    generate_recommendations,
    generate_sections_feed,
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

        result_recs = exclude_recommendations_from_blocked_sections(
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

        result_recs = exclude_recommendations_from_blocked_sections(
            original_recs, requested_sections
        )

        # Call should output should match the input.
        assert result_recs == original_recs

    def test_accepts_empty_sections_list(self):
        """Test that the function accepts an empty list of requested sections"""
        original_recs = generate_recommendations(2)
        requested_sections = []

        result_recs = exclude_recommendations_from_blocked_sections(
            original_recs, requested_sections
        )

        # Call should output should match the input.
        assert result_recs == original_recs

    def test_keeps_recommendations_without_topics(self):
        """Test that the function keeps recommendations without topics"""
        original_recs = generate_recommendations(2)
        original_recs[0].topic = None

        requested_sections = []

        result_recs = exclude_recommendations_from_blocked_sections(
            original_recs, requested_sections
        )

        assert result_recs == original_recs


class TestSetDoubleRowLayout:
    """Tests covering set_double_row_layout"""

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
        set_double_row_layout(feed)
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

        set_double_row_layout(sample_feed)

        assert second_section.layout == original_layout

    @pytest.mark.asyncio
    async def test_sufficient_recommendations(self, sample_feed: dict[str, Section]):
        """Test that second section layout remains unchanged if this section doesn't have enough recommendations."""
        # Find the second section (receivedFeedRank == 1)
        second_section = next(s for s in sample_feed.values() if s.receivedFeedRank == 1)
        # Set enough recommendations for layout_3_ads
        second_section.recommendations = generate_recommendations(layout_3_ads.max_tile_count)

        set_double_row_layout(sample_feed)

        assert second_section.layout == layout_3_ads


class TestAdjustAdsInSections:
    """Tests covering CuratedRecommendationsProvider.adjust_ads_in_sections"""

    @staticmethod
    def ads_in_section(section: Section) -> bool:
        """Check if a section contains ads."""
        return any(
            tile.hasAd for layout in section.layout.responsiveLayouts for tile in layout.tiles
        )

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        "section_count, expected_section_ranks_with_ads",
        [
            (11, {0, 1, 2, 4, 6, 8}),  # All 6 expected sections (1,2,3,5,7,9) to have ads
            (4, {0, 1, 2}),  # Partially expected sections to have ads
        ],
    )
    async def test_ads_adjusted_in_sections_by_section_count(
        self, section_count, expected_section_ranks_with_ads
    ):
        """Test that ads show up only in expected sections."""
        # generate sample feed with provided # of sections
        sample_feed = generate_sections_feed(section_count=section_count)

        # Assert all sections have ads in some tiles
        for section in sample_feed.values():
            assert self.ads_in_section(section)

        # Adjust ad display in sections
        adjust_ads_in_sections(sample_feed)

        # Assert that only expected sections with provided ranks have ads
        for section in sample_feed.values():
            if section.receivedFeedRank in expected_section_ranks_with_ads:
                assert self.ads_in_section(section)
            else:
                assert not self.ads_in_section(section)
