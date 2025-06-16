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
    exclude_recommendations_from_blocked_sections,
    is_ml_sections_experiment,
    update_received_feed_rank,
    get_sections_with_enough_items,
    get_corpus_sections,
    map_corpus_section_to_section,
    map_section_item_to_recommendation,
    map_topic_to_iab_categories,
    remove_top_story_recs,
    get_corpus_sections_for_legacy_topic,
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
    """Build three corpus sections: 'secA' with 2 items, 'secB' with 1 item, 'secC' with 3 items using the helper."""
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
        for sec_id, count in [("secA", 2), ("secB", 1), ("secC", 3)]
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
        sec = map_corpus_section_to_section(cs, 5, layout_6_tiles)
        assert sec.receivedFeedRank == 5
        assert sec.title == cs.title
        assert sec.layout == layout_6_tiles
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
        sec = map_corpus_section_to_section(empty_cs, 7, layout_4_medium)
        assert sec.recommendations == []
        assert sec.receivedFeedRank == 7


class TestGetCorpusSectionsForLegacyTopics:
    """Tests for get_corpus_sections_for_legacy_topic."""

    def test_get_corpus_sections_for_legacy_topic(self):
        """Only return corpus_sections matching legacy topics."""
        # generate 5 legacy sections
        legacy_sections = generate_sections_feed(5, has_top_stories=False)
        # 2 more non-legacy sections
        non_legacy_sections = {
            "mlb": Section(
                receivedFeedRank=100,
                recommendations=[],
                title="MLB",
                layout=copy.deepcopy(layout_4_medium),
            ),
            "nhl": Section(
                receivedFeedRank=101,
                recommendations=[],
                title="NHL",
                layout=copy.deepcopy(layout_4_medium),
            ),
        }
        corpus_sections = {**legacy_sections, **non_legacy_sections}
        result = get_corpus_sections_for_legacy_topic(corpus_sections)

        # Check that non-legacy sections are filtered out from the result
        assert "mlb" not in result
        assert "nhl" not in result
        # Check that all legacy sections present in result
        for sid in legacy_sections.keys():
            assert sid in result

    def test_return_empty_feed_no_legacy_topics_found(self):
        """Returns an empty feed when no corpus_section IDs match legacy topics."""
        non_legacy_sections = {
            "mlb": Section(
                receivedFeedRank=100,
                recommendations=[],
                title="MLB",
                layout=copy.deepcopy(layout_4_medium),
            ),
            "nhl": Section(
                receivedFeedRank=101,
                recommendations=[],
                title="NHL",
                layout=copy.deepcopy(layout_4_medium),
            ),
        }
        result = get_corpus_sections_for_legacy_topic(non_legacy_sections)
        assert result == {}

    def test_return_all_when_all_legacy_topics(self):
        """Returns entire feed if all corpus_section IDs match legacy topics."""
        # generate 8 legacy sections
        legacy_sections = generate_sections_feed(8, has_top_stories=False)

        result = get_corpus_sections_for_legacy_topic(legacy_sections)
        assert result == legacy_sections


class TestRemoveTopStoryRecs:
    """Tests for remove_top_story_recs."""

    def test_remove_top_story_recs(self):
        """Removes recommendations that are in the top_stories_section."""
        # generate 5 recs
        recommendations = generate_recommendations(5, ["a", "b", "c", "d", "e"])
        # 3 recs in top_stories_section
        top_story_ids = {"a", "d", "e"}

        result = remove_top_story_recs(recommendations, top_story_ids)

        # the 3 top story ids should not be present, result should have 2 recs
        assert len(result) == 2
        assert result[0].corpusItemId == "b"
        assert result[1].corpusItemId == "c"

    def test_recs_unchanged_no_match_found(self):
        """Return original list of recommendations if no corpus Ids match top_story_ids."""
        # generate 3 recs
        recommendations = generate_recommendations(3, ["a", "b", "c"])
        # rec ids for top stories, not found in recs list
        top_story_ids = {"z", "xy"}
        result = remove_top_story_recs(recommendations, top_story_ids)

        assert result == recommendations

    def test_return_empty_list_all_match(self):
        """Return empty list if  all recommendations are top stories"""
        # generate 3 recs
        recommendations = generate_recommendations(3, ["a", "b", "c"])
        # rec ids for top stories, all 3 ids match original recommendations list
        top_story_ids = {"a", "b", "c"}
        result = remove_top_story_recs(recommendations, top_story_ids)

        assert result == []


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
    async def test_section_transformation_and_cycle_layout(
        self, sections_backend, sample_backend_data
    ):
        """Verify mapping logic for get_corpus_sections."""
        result = await get_corpus_sections(sections_backend, SurfaceId.NEW_TAB_EN_US, 5)

        assert set(result.keys()) == {cs.externalId for cs in sample_backend_data}
        section_a = result["secA"]
        assert section_a.receivedFeedRank == 5
        assert len(section_a.recommendations) == 2
        assert section_a.layout == layout_6_tiles

        section_b = result["secB"]
        assert section_b.receivedFeedRank == 6
        assert len(section_b.recommendations) == 1
        assert section_b.layout == layout_4_large

        section_c = result["secC"]
        assert section_c.receivedFeedRank == 7
        assert len(section_c.recommendations) == 3
        assert section_c.layout == layout_4_medium


class TestMapIABCategoriesToSection:
    """Tests for map_topic_to_iab_categories."""

    @pytest.mark.parametrize(
        "section_id,expected_iab_codes",
        [
            (Topic.BUSINESS, ["52"]),
            (Topic.CAREER, ["123"]),
            (Topic.EDUCATION, ["132"]),
            (Topic.ARTS, ["JLBCU7"]),
            (Topic.FOOD, ["210"]),
            (Topic.HEALTH_FITNESS, ["223"]),
            (Topic.HOME, ["274"]),
            (Topic.PERSONAL_FINANCE, ["391"]),
            (Topic.POLITICS, ["386"]),
            (Topic.SPORTS, ["483"]),
            (Topic.TECHNOLOGY, ["596"]),
            (Topic.TRAVEL, ["653"]),
            (Topic.GAMING, ["596"]),
            (Topic.PARENTING, ["192"]),
            (Topic.SCIENCE, ["464"]),
            (Topic.SELF_IMPROVEMENT, ["186"]),
            ("section_id_not_found", []),  # return empty array if section_id not found in mapping
        ],
    )
    def test_mapping_works(self, section_id, expected_iab_codes):
        """Map a valid section_ids to IAB category code(s)."""
        assert map_topic_to_iab_categories(section_id) == expected_iab_codes
