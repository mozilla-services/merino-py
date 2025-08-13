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
    remove_top_story_recs,
    get_corpus_sections_for_legacy_topic,
    cycle_layouts_for_ranked_sections,
    LAYOUT_CYCLE,
    get_top_story_list,
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
        for k in rec.features.keys():
            if k.startswith("t_"):
                assert "." not in k  # Make sure we're not sending a type but actual value.
        assert rec.features == {f"s_{section_id}": 1.0, f"t_{item.topic.value}": 1.0}
        assert not rec.in_experiment("unknown_experiment")

    def test_basic_mapping_experiment(self):
        """Map a valid CorpusItem into a CuratedRecommendation."""
        item = generate_corpus_item()
        experiment_id = "eid"
        section_id = "secX"
        rec = map_section_item_to_recommendation(
            item, 3, section_id, experiment_flags={experiment_id}
        )
        assert isinstance(rec, CuratedRecommendation)
        assert rec.receivedRank == 3
        for k in rec.features.keys():
            if k.startswith("t_"):
                assert "." not in k  # Make sure we're not sending a type but actual value.
        assert rec.in_experiment(experiment_id)
        assert not rec.in_experiment("bla")
        assert not rec.in_experiment(None)
        assert rec.features == {f"s_{section_id}": 1.0, f"t_{item.topic.value}": 1.0}

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
        assert sec.layout == layout_6_tiles
        assert sec.iab == cs.iab
        assert len(sec.recommendations) == len(cs.sectionItems)
        for idx, rec in enumerate(sec.recommendations):
            features_compare = {f"s_{cs.externalId}": 1.0}
            if rec.topic is not None:
                features_compare[f"t_{rec.topic.value}"] = 1.0
            assert rec.receivedRank == idx
            assert rec.features == features_compare

    def test_empty_section_items(self):
        """Empty sectionItems yields empty recommendations."""
        empty_cs = CorpusSection(sectionItems=[], title="Empty", externalId="empty")
        sec = map_corpus_section_to_section(empty_cs, 7)
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


class TestGetTopStoryList:
    """Tests for get_top_story_list."""

    def test_returns_top_count_items(self):
        """Should return exactly `top_count` items from start of list if extra_count is 0."""
        items = generate_recommendations(item_ids=["a", "b", "c", "d", "e"])
        result = get_top_story_list(items, top_count=3, extra_count=0)
        assert len(result) == 3
        assert [i.corpusItemId for i in result] == ["a", "b", "c"]

    def test_includes_extra_items_no_topic_overlap(self):
        """Extra items should be chosen without repeating topics from top_count items."""
        items = generate_recommendations(
            item_ids=["a", "b", "c", "d", "e", "f"],
            topics=["business", "arts", "business", "business", "food", "government"],
        )
        result = get_top_story_list(items, top_count=2, extra_count=3, extra_source_depth=0)

        top_ids = [i.corpusItemId for i in result]
        assert len(result) == 2 + 3
        assert "a" in top_ids and "b" in top_ids
        assert "d" not in top_ids  # duplicated by "c"
        # check order
        for ix, item in enumerate(result):
            assert item.receivedRank == ix

    def test_returns_less_extra_if_not_enough_unique_topics(self):
        """Should return fewer extras if unique topics run out."""
        items = generate_recommendations(
            item_ids=["a", "b", "c", "d", "e"],
            topics=[
                "business",
                "arts",
                "food",
                "business",
                "arts",
            ],  # duplicates prevent full extra_count
        )
        result = get_top_story_list(items, top_count=3, extra_count=3, extra_source_depth=0)
        for ix, item in enumerate(result):
            assert item.receivedRank == ix
        assert len(result) == 5

    def test_top_count_greater_than_items(self):
        """If top_count > len(items), should return all items without error."""
        items = generate_recommendations(item_ids=["a", "b", "c"], topics=list(Topic)[:3])
        result = get_top_story_list(items, top_count=5, extra_count=0, extra_source_depth=0)
        assert len(result) == 3
        assert [i.corpusItemId for i in result] == ["a", "b", "c"]

    def test_top_count_source_depth(self):
        """Test skipping some items"""
        items = generate_recommendations(
            item_ids=["a", "b", "c", "d", "e"], topics=list(Topic)[:5]
        )
        result = get_top_story_list(items, top_count=2, extra_count=2, extra_source_depth=1)
        assert len(result) == 4
        for ix, item in enumerate(result):
            assert item.receivedRank == ix
        assert [i.corpusItemId for i in result] == ["a", "b", "d", "e"]  # skip one item "c"


class TestCycleLayoutsForRankedSections:
    """Tests for cycle_layouts_for_ranked_sections."""

    def test_cycle_layouts_for_ranked_sections(self):
        """All non-top_story sections get assigned cycled layouts."""
        sections = generate_sections_feed(6, has_top_stories=False)

        # All sections start with layout_4_medium
        assert all(s.layout == layout_4_medium for s in sections.values())

        # Apply layout cycling
        cycle_layouts_for_ranked_sections(sections)

        # Check layouts were cycled through LAYOUT_CYCLE
        for idx, section in enumerate(sections.values()):
            expected_layout = LAYOUT_CYCLE[idx % len(LAYOUT_CYCLE)]
            assert section.layout == expected_layout

    def test_cycle_layouts_for_non_top_stories_only(self):
        """Only sections other than 'top_stories_section' have layouts modified."""
        sections = generate_sections_feed(7, has_top_stories=True)

        # All sections start with layout_4_medium
        assert all(s.layout == layout_4_medium for s in sections.values())

        # Apply layout cycling
        cycle_layouts_for_ranked_sections(sections)

        # top_stories_section layout should remain layout_4_medium
        assert sections["top_stories_section"].layout == layout_4_medium

        # Other sections should have new cycled layouts assigned to them
        other_sections = [
            section for sid, section in sections.items() if sid != "top_stories_section"
        ]

        for idx, section in enumerate(other_sections):
            expected_layout = LAYOUT_CYCLE[idx % len(LAYOUT_CYCLE)]
            assert section.layout == expected_layout


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
        await get_corpus_sections(
            sections_backend=sections_backend, surface_id=SurfaceId.NEW_TAB_EN_US, min_feed_rank=2
        )
        sections_backend.fetch.assert_awaited_once_with(SurfaceId.NEW_TAB_EN_US)

    @pytest.mark.asyncio
    async def test_section_transformation(self, sections_backend, sample_backend_data):
        """Verify mapping logic for get_corpus_sections."""
        result = await get_corpus_sections(
            sections_backend=sections_backend, surface_id=SurfaceId.NEW_TAB_EN_US, min_feed_rank=5
        )

        assert set(result.keys()) == {cs.externalId for cs in sample_backend_data}
        section_a = result["secA"]
        assert section_a.receivedFeedRank == 5
        assert len(section_a.recommendations) == 2
        assert section_a.layout == layout_6_tiles

        section_b = result["secB"]
        assert section_b.receivedFeedRank == 6
        assert len(section_b.recommendations) == 1
        assert section_b.layout == layout_6_tiles

        section_c = result["secC"]
        assert section_c.receivedFeedRank == 7
        assert len(section_c.recommendations) == 3
        assert section_c.layout == layout_6_tiles
