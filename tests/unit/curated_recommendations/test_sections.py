"""Module with tests covering merino/curated_recommendations/sections.py"""

import copy
from datetime import datetime, timezone
from types import SimpleNamespace

import pytest

from merino.curated_recommendations.corpus_backends.protocol import Topic, SurfaceId
from merino.curated_recommendations.layouts import (
    layout_3_ads,
    layout_4_medium,
    layout_6_tiles,
    layout_4_large,
)
from merino.curated_recommendations.protocol import Section, SectionConfiguration, ExperimentName
from merino.curated_recommendations.sections import (
    adjust_ads_in_sections,
    set_double_row_layout,
    exclude_recommendations_from_blocked_sections,
    boost_followed_sections,
    create_sections_from_items_by_topic,
    is_ml_sections_experiment,
    update_received_feed_rank,
    get_sections_with_enough_items,
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


class TestBoostFollowedSections:
    """Tests covering boost_followed_sections"""

    at1 = datetime(2025, 1, 1, 0, 0, tzinfo=timezone.utc)
    at2 = datetime(2025, 1, 2, 0, 0, tzinfo=timezone.utc)

    def test_followed_sections_moved_to_top(self):
        """Test that followed sections are moved to the top in boost_followed_sections"""
        feed = generate_sections_feed(section_count=3)
        id_1, id_2 = list(feed.keys())[1:3]

        cfgs = [
            SectionConfiguration(
                sectionId=id_1, isFollowed=False, isBlocked=False, followedAt=self.at1
            ),
            SectionConfiguration(
                sectionId=id_2, isFollowed=True, isBlocked=False, followedAt=self.at2
            ),
        ]
        new_order = boost_followed_sections(cfgs, feed)

        keys = list(new_order.keys())
        assert keys[0] == "top_stories_section"
        assert keys[1] == feed[id_2].title
        assert keys[2] == feed[id_1].title
        assert new_order["top_stories_section"].receivedFeedRank == 0
        assert new_order[feed[id_2].title].receivedFeedRank == 1
        assert new_order[feed[id_1].title].receivedFeedRank == 2

    def test_missing_sections_ignored(self):
        """Test that non-existing sections are ignored"""
        feed = generate_sections_feed(section_count=1)
        cfgs = [
            SectionConfiguration(
                sectionId="foobar", isFollowed=True, isBlocked=False, followedAt=self.at1
            )
        ]
        new_order = boost_followed_sections(cfgs, feed)

        assert list(new_order.keys()) == ["top_stories_section"]
        assert new_order["top_stories_section"].receivedFeedRank == 0


class TestCreateSectionsFromItemsByTopic:
    """Tests covering create_sections_from_items_by_topic"""

    def test_group_by_topic_and_cycle_layout(self):
        """Test grouping items by topic and cycling layouts"""
        items = generate_recommendations(3)
        items[0].topic = Topic.SCIENCE
        items[1].topic = Topic.FOOD
        items[2].topic = None

        sections = create_sections_from_items_by_topic(items, SurfaceId.NEW_TAB_EN_US)
        assert set(sections.keys()) == {Topic.SCIENCE.value, Topic.FOOD.value}

        sci = sections[Topic.SCIENCE.value]
        food = sections[Topic.FOOD.value]
        assert sci.receivedFeedRank == 0
        assert sci.layout == layout_6_tiles
        assert food.receivedFeedRank == 1
        assert food.layout == layout_4_large
        assert sci.recommendations[0].receivedRank == 0
        assert food.recommendations[0].receivedRank == 0

    def test_ignores_none_topics(self):
        """Test that items without a topic produce no sections"""
        items = generate_recommendations(2)
        # Topics aren't expected to be None in practice, but it may happen if a
        # new topic is introduced in the corpus, without Merino having been updated.
        items[0].topic = None
        items[1].topic = None
        result = create_sections_from_items_by_topic(items, SurfaceId.NEW_TAB_EN_US)
        assert result == {}


class TestMlSectionsExperiment:
    """Tests covering is_ml_sections_experiment"""

    @pytest.mark.parametrize(
        "name,branch,expected",
        [
            (ExperimentName.ML_SECTIONS_EXPERIMENT.value, "treatment", True),
            (ExperimentName.ML_SECTIONS_EXPERIMENT.value, "control", False),
            ("other", "treatment", False),
        ],
    )
    def test_flag_logic(self, name, branch, expected):
        """Test that ML sections experiment flag matches expected logic"""
        req = SimpleNamespace(experimentName=name, experimentBranch=branch)
        assert is_ml_sections_experiment(req) is expected


class TestUpdateReceivedFeedRank:
    """Tests covering update_received_feed_rank"""

    def test_ranks_reassigned(self):
        """Test that receivedFeedRank values are reassigned in sorted order"""
        feed = generate_sections_feed(section_count=3)
        secs = list(feed.values())[1:3]
        secs[0].receivedFeedRank = 5
        secs[1].receivedFeedRank = 2

        update_received_feed_rank(feed)

        assert secs[1].receivedFeedRank == 1
        assert secs[0].receivedFeedRank == 2


class TestGetSectionsWithEnoughItems:
    """Tests covering get_sections_with_enough_items"""

    def test_prunes_undersized_sections(self):
        """Test that sections smaller than layout max_tile_count + 1 are removed"""
        feed = generate_sections_feed(section_count=3)
        secs = list(feed.values())[1:3]
        keep_sec, drop_sec = secs
        keep_sec.recommendations = generate_recommendations(layout_4_medium.max_tile_count + 1)
        drop_sec.recommendations = generate_recommendations(layout_4_medium.max_tile_count)
        result = get_sections_with_enough_items({"k": keep_sec, "d": drop_sec})
        assert "k" in result and "d" not in result
