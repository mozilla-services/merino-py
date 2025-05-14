"""Module with tests covering merino/curated_recommendations/sections.py"""

import copy
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from pydantic import HttpUrl

from merino.curated_recommendations.corpus_backends.protocol import (
    Topic,
    SurfaceId,
    SectionsProtocol,
    CorpusSection,
    CorpusItem,
    IABMetadata,
)
from merino.curated_recommendations.layouts import (
    layout_3_ads,
    layout_4_medium,
    layout_6_tiles,
    layout_4_large,
)
from merino.curated_recommendations.protocol import (
    Section,
    SectionConfiguration,
    ExperimentName,
    CuratedRecommendation,
)
from merino.curated_recommendations.sections import (
    adjust_ads_in_sections,
    set_double_row_layout,
    exclude_recommendations_from_blocked_sections,
    create_sections_from_items_by_topic,
    is_ml_sections_experiment,
    update_received_feed_rank,
    get_sections_with_enough_items,
    get_corpus_sections,
    map_corpus_section_to_section,
    map_section_item_to_recommendation,
)
from tests.unit.curated_recommendations.fixtures import (
    generate_recommendations,
    generate_sections_feed,
)


def generate_corpus_item(corpus_id: str = "id", sched_id: str = "sched") -> CorpusItem:
    """Create a CorpusItem instance for testing with provided or default IDs."""
    return CorpusItem(
        corpusItemId=corpus_id,
        scheduledCorpusItemId=sched_id,
        url=HttpUrl(f"https://example.com/{corpus_id}"),
        title=f"Title_{corpus_id}",
        excerpt=f"Excerpt_{corpus_id}",
        topic="society",
        publisher=f"Pub_{corpus_id}",
        isTimeSensitive=False,
        imageUrl=HttpUrl(f"https://example.com/img/{corpus_id}"),
        iconUrl=None,
    )


@pytest.fixture
def sample_backend_data() -> list[CorpusSection]:
    """Build two corpus sections: 'secA' with 2 items, 'secB' with 1 using the helper."""
    return [
        CorpusSection(
            sectionItems=[
                generate_corpus_item(f"{sec_id}_item{i}", f"{sec_id}_sched{i}")
                for i in range(count)
            ],
            title=f"Title_{sec_id}",
            externalId=sec_id,
            iab=IABMetadata(categories=["324"]),
        )
        for sec_id, count in [("secA", 2), ("secB", 1)]
    ]


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


class TestMapSectionItemToRecommendation:
    """Tests for map_section_item_to_recommendation."""

    def test_basic_mapping(self):
        """Map a valid CorpusItem into a CuratedRecommendation."""
        item = generate_corpus_item()
        section_id = "secX"
        rec = map_section_item_to_recommendation(item, 3, section_id)
        assert isinstance(rec, CuratedRecommendation)
        assert rec.receivedRank == 3
        assert rec.features == {f"s_{section_id}": 1.0, f"t_{item.topic}": 1.0}

    def test_basic_mapping_no_topic(self):
        """Map a valid CorpusItem into a CuratedRecommendation."""
        item = generate_corpus_item()
        item.topic = None
        section_id = "secX"
        rec = map_section_item_to_recommendation(item, 3, section_id)
        assert isinstance(rec, CuratedRecommendation)
        assert rec.receivedRank == 3
        assert rec.features == {f"s_{section_id}": 1.0}


class TestMapCorpusSectionToSection:
    """Tests for map_corpus_section_to_section."""

    def test_basic_mapping(self, sample_backend_data):
        """Map CorpusSection into Section with correct feed rank and recs."""
        cs = sample_backend_data[1]
        sec = map_corpus_section_to_section(cs, 5)
        assert sec.receivedFeedRank == 5
        assert sec.title == cs.title
        assert sec.layout == layout_4_medium
        assert sec.iab == cs.iab
        assert len(sec.recommendations) == len(cs.sectionItems)
        for idx, rec in enumerate(sec.recommendations):
            features_compare = {f"s_{cs.externalId}": 1.0}
            if rec.topic is not None:
                features_compare[f"t_{rec.topic}"] = 1.0
            assert rec.receivedRank == idx
            assert rec.features == features_compare

    def test_empty_section_items(self):
        """Empty sectionItems yields empty recommendations."""
        empty_cs = CorpusSection(sectionItems=[], title="Empty", externalId="empty")
        sec = map_corpus_section_to_section(empty_cs, 7)
        assert sec.recommendations == []
        assert sec.receivedFeedRank == 7


class TestGetCorpusSections:
    """Simplified tests for get_corpus_sections."""

    @pytest.fixture
    def sections_backend(self, sample_backend_data):
        """Fake SectionsProtocol returning sample data."""
        mock_backend = MagicMock(spec=SectionsProtocol)
        mock_backend.fetch = AsyncMock(return_value=sample_backend_data)
        return mock_backend

    @pytest.mark.asyncio
    async def test_fetch_called_with_correct_args(self, sections_backend):
        """Ensure fetch is called once with given surface_id."""
        await get_corpus_sections(sections_backend, SurfaceId.NEW_TAB_EN_US, 2)
        sections_backend.fetch.assert_awaited_once_with(SurfaceId.NEW_TAB_EN_US)

    @pytest.mark.asyncio
    async def test_section_transformation(self, sections_backend, sample_backend_data):
        """Verify mapping logic for get_corpus_sections."""
        result = await get_corpus_sections(sections_backend, SurfaceId.NEW_TAB_EN_US, 5)
        assert set(result.keys()) == {cs.externalId for cs in sample_backend_data}
        section = result["secA"]
        assert section.receivedFeedRank == 5
        assert len(section.recommendations) == 2
