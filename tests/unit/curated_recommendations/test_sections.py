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
    CrawlExperimentBranchName,
    CuratedRecommendation,
)
from merino.curated_recommendations.sections import (
    adjust_ads_in_sections,
    exclude_recommendations_from_blocked_sections,
    is_subtopics_experiment,
    update_received_feed_rank,
    get_sections_with_enough_items,
    get_corpus_sections,
    map_corpus_section_to_section,
    map_section_item_to_recommendation,
    remove_story_recs,
    get_corpus_sections_for_legacy_topic,
    cycle_layouts_for_ranked_sections,
    LAYOUT_CYCLE,
    get_top_story_list,
    is_crawl_section_id,
    get_legacy_topic_ids,
    split_headlines_section,
    put_headlines_first_then_top_stories,
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
    """Build three corpus sections using legacy topic IDs: 'business' with 2 items, 'sports' with 1 item, 'tech' with 3 items."""
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
        for sec_id, count in [("business", 2), ("sports", 1), ("tech", 3)]
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
    """Tests covering is_subtopics_experiment"""

    @pytest.mark.parametrize(
        "name,branch,expected",
        [
            (ExperimentName.ML_SECTIONS_EXPERIMENT.value, "treatment", True),
            (ExperimentName.ML_SECTIONS_EXPERIMENT.value, "control", False),
            ("other", "treatment", False),
        ],
    )
    def test_flag_logic(self, name, branch, expected):
        """Test that experiment flag logic matches expected behavior for both ML sections and crawl experiments."""
        req = SimpleNamespace(experimentName=name, experimentBranch=branch)
        assert is_subtopics_experiment(req) is expected

    def test_crawl_experiment_subtopics(self):
        """Test that crawl experiment affects subtopics inclusion"""
        # Control branch - should not include subtopics
        req_control = SimpleNamespace(
            experimentName=ExperimentName.RSS_VS_ZYTE_EXPERIMENT.value,
            experimentBranch=CrawlExperimentBranchName.CONTROL.value,
        )
        assert is_subtopics_experiment(req_control) is False

        # Treatment crawl (no subtopics) - should not include subtopics
        req_treatment_no_subtopics = SimpleNamespace(
            experimentName=ExperimentName.RSS_VS_ZYTE_EXPERIMENT.value,
            experimentBranch=CrawlExperimentBranchName.TREATMENT_CRAWL.value,
        )
        assert is_subtopics_experiment(req_treatment_no_subtopics) is False

        # Treatment crawl WITH subtopics - should include subtopics
        req_treatment_with_subtopics = SimpleNamespace(
            experimentName=ExperimentName.RSS_VS_ZYTE_EXPERIMENT.value,
            experimentBranch=CrawlExperimentBranchName.TREATMENT_CRAWL_PLUS_SUBTOPICS.value,
        )
        assert is_subtopics_experiment(req_treatment_with_subtopics) is True

        # Not enrolled in crawl experiment - should return False
        req_not_enrolled = SimpleNamespace(
            experimentName="other",
            experimentBranch="control",
        )
        assert is_subtopics_experiment(req_not_enrolled) is False

    def test_both_experiments_interaction(self):
        """Test that ML sections and crawl experiments work together correctly"""
        # ML sections enabled - should include subtopics regardless of crawl experiment
        req_ml_enabled = SimpleNamespace(
            experimentName=ExperimentName.ML_SECTIONS_EXPERIMENT.value,
            experimentBranch="treatment",
        )
        assert is_subtopics_experiment(req_ml_enabled) is True

        # Crawl subtopics enabled - should include subtopics regardless of ML sections
        req_crawl_subtopics = SimpleNamespace(
            experimentName=ExperimentName.RSS_VS_ZYTE_EXPERIMENT.value,
            experimentBranch=CrawlExperimentBranchName.TREATMENT_CRAWL_PLUS_SUBTOPICS.value,
        )
        assert is_subtopics_experiment(req_crawl_subtopics) is True

        # Neither enabled - should not include subtopics
        req_neither = SimpleNamespace(
            experimentName=ExperimentName.RSS_VS_ZYTE_EXPERIMENT.value,
            experimentBranch=CrawlExperimentBranchName.CONTROL.value,
        )
        assert is_subtopics_experiment(req_neither) is False


class TestCrawlExperiment:
    """Tests covering RSS vs. Zyte experiment functionality"""

    @pytest.mark.parametrize(
        "name,branch,expected",
        [
            (
                ExperimentName.RSS_VS_ZYTE_EXPERIMENT.value,
                CrawlExperimentBranchName.TREATMENT_CRAWL.value,
                True,
            ),
            (
                ExperimentName.RSS_VS_ZYTE_EXPERIMENT.value,
                CrawlExperimentBranchName.TREATMENT_CRAWL_PLUS_SUBTOPICS.value,
                True,
            ),
            (
                ExperimentName.RSS_VS_ZYTE_EXPERIMENT.value,
                CrawlExperimentBranchName.CONTROL.value,
                False,
            ),
            # Test with optin- prefix
            (
                f"optin-{ExperimentName.RSS_VS_ZYTE_EXPERIMENT.value}",
                CrawlExperimentBranchName.TREATMENT_CRAWL.value,
                True,
            ),
            (
                f"optin-{ExperimentName.RSS_VS_ZYTE_EXPERIMENT.value}",
                CrawlExperimentBranchName.TREATMENT_CRAWL_PLUS_SUBTOPICS.value,
                True,
            ),
            (
                f"optin-{ExperimentName.RSS_VS_ZYTE_EXPERIMENT.value}",
                CrawlExperimentBranchName.CONTROL.value,
                False,
            ),
            ("other", CrawlExperimentBranchName.TREATMENT_CRAWL.value, False),
        ],
    )
    def test_crawl_experiment_flag_logic(self, name, branch, expected):
        """Test that crawl experiment flag matches expected logic"""
        req = SimpleNamespace(experimentName=name, experimentBranch=branch)
        from merino.curated_recommendations.sections import is_crawl_experiment_treatment

        assert is_crawl_experiment_treatment(req) is expected

    @pytest.mark.parametrize(
        "name,branch,expected_branch",
        [
            (
                ExperimentName.RSS_VS_ZYTE_EXPERIMENT.value,
                CrawlExperimentBranchName.CONTROL.value,
                CrawlExperimentBranchName.CONTROL.value,
            ),
            (
                ExperimentName.RSS_VS_ZYTE_EXPERIMENT.value,
                CrawlExperimentBranchName.TREATMENT_CRAWL.value,
                CrawlExperimentBranchName.TREATMENT_CRAWL.value,
            ),
            (
                ExperimentName.RSS_VS_ZYTE_EXPERIMENT.value,
                CrawlExperimentBranchName.TREATMENT_CRAWL_PLUS_SUBTOPICS.value,
                CrawlExperimentBranchName.TREATMENT_CRAWL_PLUS_SUBTOPICS.value,
            ),
            # Test with optin- prefix
            (
                f"optin-{ExperimentName.RSS_VS_ZYTE_EXPERIMENT.value}",
                CrawlExperimentBranchName.CONTROL.value,
                CrawlExperimentBranchName.CONTROL.value,
            ),
            (
                f"optin-{ExperimentName.RSS_VS_ZYTE_EXPERIMENT.value}",
                CrawlExperimentBranchName.TREATMENT_CRAWL.value,
                CrawlExperimentBranchName.TREATMENT_CRAWL.value,
            ),
            (
                f"optin-{ExperimentName.RSS_VS_ZYTE_EXPERIMENT.value}",
                CrawlExperimentBranchName.TREATMENT_CRAWL_PLUS_SUBTOPICS.value,
                CrawlExperimentBranchName.TREATMENT_CRAWL_PLUS_SUBTOPICS.value,
            ),
            ("other", "treatment", None),
        ],
    )
    def test_get_crawl_experiment_branch(self, name, branch, expected_branch):
        """Test that get_crawl_experiment_branch returns correct branch"""
        req = SimpleNamespace(experimentName=name, experimentBranch=branch)
        from merino.curated_recommendations.sections import get_crawl_experiment_branch

        assert get_crawl_experiment_branch(req) == expected_branch

    def test_filter_sections_treatment_crawl(self):
        """Test that treatment-crawl branch gets only crawl legacy sections"""
        from merino.curated_recommendations.sections import filter_sections_by_crawl_experiment

        # Create test sections with legacy topics and subtopics
        sections = [
            MagicMock(externalId="health"),  # legacy
            MagicMock(externalId="health_crawl"),  # legacy crawl
            MagicMock(externalId="tech"),  # legacy
            MagicMock(externalId="tech_crawl"),  # legacy crawl
            MagicMock(externalId="business"),  # legacy
            MagicMock(externalId="ai-trends"),  # subtopic
            MagicMock(
                externalId="ai-trends_crawl"
            ),  # subtopic crawl (shouldn't exist but testing)
        ]

        # treatment-crawl should get only crawl legacy sections
        result = filter_sections_by_crawl_experiment(
            sections, crawl_branch=CrawlExperimentBranchName.TREATMENT_CRAWL.value
        )

        assert len(result) == 2
        assert "health" in result
        assert "tech" in result
        assert result["health"].externalId == "health_crawl"
        assert result["tech"].externalId == "tech_crawl"
        assert "business" not in result  # No crawl version available
        assert "ai-trends" not in result  # Subtopic not included in treatment-crawl

    def test_filter_sections_treatment_crawl_plus_subtopics(self):
        """Test that treatment-crawl-plus-subtopics gets crawl legacy + regular subtopics"""
        from merino.curated_recommendations.sections import filter_sections_by_crawl_experiment

        # Create test sections
        sections = [
            MagicMock(externalId="health"),  # legacy
            MagicMock(externalId="health_crawl"),  # legacy crawl
            MagicMock(externalId="tech_crawl"),  # legacy crawl
            MagicMock(externalId="ai-trends"),  # subtopic
            MagicMock(externalId="ml-research"),  # subtopic
        ]

        # treatment-crawl-plus-subtopics should get crawl legacy + regular subtopics
        result = filter_sections_by_crawl_experiment(
            sections, crawl_branch=CrawlExperimentBranchName.TREATMENT_CRAWL_PLUS_SUBTOPICS.value
        )

        assert len(result) == 4
        assert "health" in result
        assert result["health"].externalId == "health_crawl"
        assert "tech" in result
        assert result["tech"].externalId == "tech_crawl"
        assert "ai-trends" in result
        assert result["ai-trends"].externalId == "ai-trends"
        assert "ml-research" in result
        assert result["ml-research"].externalId == "ml-research"

    def test_filter_sections_control(self):
        """Test that control branch gets only non-crawl sections"""
        from merino.curated_recommendations.sections import filter_sections_by_crawl_experiment

        # Create test sections with and without _crawl suffix
        sections = [
            MagicMock(externalId="health"),
            MagicMock(externalId="health_crawl"),
            MagicMock(externalId="tech"),
            MagicMock(externalId="tech_crawl"),
            MagicMock(externalId="business"),
        ]

        # Control branch should get only non-crawl sections
        result = filter_sections_by_crawl_experiment(
            sections, crawl_branch=CrawlExperimentBranchName.CONTROL.value, include_subtopics=True
        )

        assert len(result) == 3
        assert "health" in result
        assert "tech" in result
        assert "business" in result
        assert "health_crawl" not in result
        assert "tech_crawl" not in result

    def test_filter_sections_by_crawl_experiment_empty_input(self):
        """Test that empty corpus sections return empty result"""
        from merino.curated_recommendations.sections import filter_sections_by_crawl_experiment
        from merino.curated_recommendations.protocol import CrawlExperimentBranchName

        # Empty input should return empty output
        result = filter_sections_by_crawl_experiment(
            [], crawl_branch=CrawlExperimentBranchName.TREATMENT_CRAWL.value
        )
        assert result == {}

        result = filter_sections_by_crawl_experiment(
            [], crawl_branch=CrawlExperimentBranchName.CONTROL.value
        )
        assert result == {}

    def test_filter_sections_by_crawl_experiment_mixed_sections(self):
        """Test that sections with mixed _crawl and non-_crawl for same topic are handled correctly"""
        from merino.curated_recommendations.sections import filter_sections_by_crawl_experiment
        from merino.curated_recommendations.protocol import CrawlExperimentBranchName

        # Create sections with mixed _crawl and non-_crawl for same topic
        sections = [
            MagicMock(externalId="health"),
            MagicMock(externalId="health_crawl"),
            MagicMock(externalId="tech"),
            MagicMock(externalId="tech_crawl"),
            MagicMock(externalId="business"),
            MagicMock(externalId="business_crawl"),
        ]

        # Treatment branch should get only crawl sections
        result = filter_sections_by_crawl_experiment(
            sections, crawl_branch=CrawlExperimentBranchName.TREATMENT_CRAWL.value
        )
        assert len(result) == 3
        assert "health" in result
        assert "tech" in result
        assert "business" in result
        # Verify externalId is preserved
        assert result["health"].externalId == "health_crawl"
        assert result["tech"].externalId == "tech_crawl"
        assert result["business"].externalId == "business_crawl"

        # Control branch should get only non-crawl sections
        result = filter_sections_by_crawl_experiment(
            sections, crawl_branch=CrawlExperimentBranchName.CONTROL.value, include_subtopics=True
        )
        assert len(result) == 3
        assert "health" in result
        assert "tech" in result
        assert "business" in result
        # Verify externalId is preserved
        assert result["health"].externalId == "health"
        assert result["tech"].externalId == "tech"
        assert result["business"].externalId == "business"

    def test_filter_sections_by_crawl_experiment_malformed_ids(self):
        """Test that malformed section IDs are handled gracefully"""
        from merino.curated_recommendations.sections import filter_sections_by_crawl_experiment
        from merino.curated_recommendations.protocol import CrawlExperimentBranchName

        # Create sections with potentially malformed IDs
        sections = [
            MagicMock(externalId="health"),
            MagicMock(externalId="health_crawl"),
            MagicMock(externalId="health_crawl_extra"),  # Extra suffix
            MagicMock(externalId="_crawl"),  # Just the suffix
            MagicMock(externalId="crawl_health"),  # Suffix in middle
            MagicMock(externalId=""),  # Empty ID
        ]

        # Treatment branch should get only sections ending with _crawl that are legacy topics
        result = filter_sections_by_crawl_experiment(
            sections, crawl_branch=CrawlExperimentBranchName.TREATMENT_CRAWL.value
        )
        assert len(result) == 1
        assert "health" in result  # health_crawl -> health
        # _crawl -> "" is not included because "" is not a legacy topic

        # Control branch should get only sections NOT ending with _crawl that are legacy topics
        result = filter_sections_by_crawl_experiment(
            sections, crawl_branch=CrawlExperimentBranchName.CONTROL.value
        )
        assert len(result) == 1
        assert "health" in result
        # Other sections are not included because they're not legacy topics
        assert "health_extra" not in result
        assert "crawl_health" not in result
        assert "" not in result  # Empty string is not a legacy topic


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


class TestGetLegacyTopicIds:
    """Tests for get_legacy_topic_ids."""

    def test_returns_all_legacy_topic_ids(self):
        """Should return the set of all Topic enum values."""
        expected = {
            "business",
            "career",
            "arts",
            "food",
            "health",
            "home",
            "finance",
            "government",
            "sports",
            "tech",
            "travel",
            "education",
            "hobbies",
            "society-parenting",
            "education-science",
            "society",
        }
        assert get_legacy_topic_ids() == expected


class TestIsCrawlSectionId:
    """Tests for is_crawl_section_id."""

    def test_crawl_section_returns_true(self):
        """Should return True for section IDs ending with '_crawl'."""
        assert is_crawl_section_id("technology_crawl") is True
        assert is_crawl_section_id("sports_crawl") is True
        assert is_crawl_section_id("some_section_crawl") is True

    def test_non_crawl_section_returns_false(self):
        """Should return False for section IDs not ending with '_crawl'."""
        assert is_crawl_section_id("technology") is False
        assert is_crawl_section_id("sports") is False
        assert is_crawl_section_id("crawl") is False
        assert is_crawl_section_id("crawl_technology") is False

    def test_empty_string_returns_false(self):
        """Should return False for empty string."""
        assert is_crawl_section_id("") is False


class TestRemoveStoryRecs:
    """Tests for remove_story_recs."""

    def test_remove_story_recs(self):
        """Removes certain recommendations."""
        # generate 5 recs
        recommendations = generate_recommendations(5, ["a", "b", "c", "d", "e"])
        # 3 recs in top_stories_section
        story_ids_to_remove = {"a", "d", "e"}

        result = remove_story_recs(recommendations, story_ids_to_remove)

        # the 3 story ids to remove should not be present, result should have 2 recs
        assert len(result) == 2
        assert result[0].corpusItemId == "b"
        assert result[1].corpusItemId == "c"

    def test_recs_unchanged_no_match_found(self):
        """Return original list of recommendations if no corpus Ids match story_ids_to_remove."""
        # generate 3 recs
        recommendations = generate_recommendations(3, ["a", "b", "c"])
        # rec ids to remove, not found in recs list
        story_ids_to_remove = {"z", "xy"}
        result = remove_story_recs(recommendations, story_ids_to_remove)

        assert result == recommendations

    def test_return_empty_list_all_match(self):
        """Return empty list if  all recommendations are top stories"""
        # generate 3 recs
        recommendations = generate_recommendations(3, ["a", "b", "c"])
        # rec ids to remove, all 3 ids match original recommendations list
        story_ids_to_remove = {"a", "b", "c"}
        result = remove_story_recs(recommendations, story_ids_to_remove)

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
        cycle_layouts_for_ranked_sections(sections, LAYOUT_CYCLE)

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
        cycle_layouts_for_ranked_sections(sections, LAYOUT_CYCLE)

        # top_stories_section layout should remain layout_4_medium
        assert sections["top_stories_section"].layout == layout_4_medium

        # Other sections should have new cycled layouts assigned to them
        other_sections = [
            section for sid, section in sections.items() if sid != "top_stories_section"
        ]

        for idx, section in enumerate(other_sections):
            expected_layout = LAYOUT_CYCLE[idx % len(LAYOUT_CYCLE)]
            assert section.layout == expected_layout


class TestPutHeadlinesFirstThenTopStories:
    """Tests for put_headlines_first_then_top_stories."""

    def test_headlines_not_present(self):
        """Test if headlines section is not present, ranks and order are unchanged for other sections."""
        sections = generate_sections_feed(section_count=4, has_top_stories=True)

        # Save original sectionId -> rank for comparison
        original_sections = {sid: sec.receivedFeedRank for sid, sec in sections.items()}

        result = put_headlines_first_then_top_stories(sections)

        # Nothing should be changed
        assert result is sections
        new_sections = {sid: sec.receivedFeedRank for sid, sec in result.items()}
        assert new_sections == original_sections

    def test_with_headlines_and_top_stories(self):
        """Test when headlines is put on top (0), top_stories right after (1) & other sections are rank=2...N and preserve relative order."""
        feed = generate_sections_feed(section_count=6, has_top_stories=True)
        top_stories_section = feed["top_stories_section"]
        top_stories_section.receivedFeedRank = 0

        # Insert headlines section at rank 3
        feed["headlines_section"] = Section(
            receivedFeedRank=3,
            recommendations=[],
            title="Headlines",
            layout=copy.deepcopy(layout_4_medium),
        )
        headlines_section = feed["headlines_section"]

        put_headlines_first_then_top_stories(feed)

        # Check ranks for headlines & top_stories are updated
        assert headlines_section.receivedFeedRank == 0
        assert top_stories_section.receivedFeedRank == 1

        # Get the other sections besides headlines & top_stories
        remaining_sections = sorted(
            (sid for sid in feed if sid not in ("headlines_section", "top_stories_section")),
            key=lambda sid: feed[sid].receivedFeedRank,
        )

        # Expected: headlines first -> top_stories_section second, then rest in keys order without headlines & top
        expected_order = ["headlines_section", "top_stories_section"] + remaining_sections

        for idx, sid in enumerate(expected_order):
            assert feed[sid].receivedFeedRank == idx

    def test_with_headlines_and_no_top_stories(self):
        """Test when no top_stories present, headlines is put on top & other sections are rank=1...N and preserve relative order."""
        feed = generate_sections_feed(section_count=6, has_top_stories=False)

        # Insert headlines section at rank 3
        feed["headlines_section"] = Section(
            receivedFeedRank=3,
            recommendations=[],
            title="Headlines",
            layout=copy.deepcopy(layout_4_medium),
        )
        headlines_section = feed["headlines_section"]

        # Get the other sections besides headlines & top_stories
        remaining_sections = sorted(
            (sid for sid in feed if sid not in ("headlines_section", "top_stories_section")),
            key=lambda sid: feed[sid].receivedFeedRank,
        )

        put_headlines_first_then_top_stories(feed)

        # Headlines should be on top rank==0
        assert headlines_section.receivedFeedRank == 0

        # Expected: headlines first -> then rest in keys order without headlines & top
        expected_order = ["headlines_section"] + remaining_sections

        for idx, sid in enumerate(expected_order):
            assert feed[sid].receivedFeedRank == idx


class TestSplitHeadlinesSection:
    """Tests for split_headlines_section."""

    def generate_corpus_section(self, external_id: str, title: str = "") -> CorpusSection:
        """Generate a minimal corpus section."""
        corpus_section = MagicMock()
        corpus_section.externalId = external_id
        corpus_section.title = title

        return corpus_section

    def test_returns_headlines_section_and_remaining_sections_when_present(self):
        """Test if headlines_crawl exists, return it separately and exclude from remaining sections."""
        headlines = self.generate_corpus_section("headlines_crawl", "Headlines")
        sports = self.generate_corpus_section("sports")
        tech = self.generate_corpus_section("tech")

        headlines_section, remaining_sections = split_headlines_section([headlines, sports, tech])

        # headlines should not be in the remaining sections
        assert all(cs.externalId != "headlines_crawl" for cs in remaining_sections)

        assert headlines_section is not None
        assert headlines_section.title == headlines.title
        assert remaining_sections == [sports, tech]

    def test_returns_none_for_headlines_when_not_present(self):
        """Test if headlines_crawl is not present, return None and original section list."""
        sports = self.generate_corpus_section("sports")
        tech = self.generate_corpus_section("tech")

        headlines, remaining = split_headlines_section([sports, tech])

        assert headlines is None
        assert remaining == [sports, tech]


class TestGetCorpusSections:
    """Tests for get_corpus_sections function."""

    @pytest.fixture
    def sections_backend_with_crawl_data(self):
        """Fake SectionsProtocol returning data with both _crawl and non-_crawl sections."""
        mock_backend = MagicMock(spec=SectionsProtocol)

        # Create test data with both _crawl and non-_crawl sections
        # Mock the required attributes properly
        health_crawl = MagicMock()
        health_crawl.externalId = "health_crawl"
        health_crawl.title = "Health (Crawl)"
        health_crawl.sectionItems = []
        health_crawl.iab = None

        tech_crawl = MagicMock()
        tech_crawl.externalId = "tech_crawl"
        tech_crawl.title = "Tech (Crawl)"
        tech_crawl.sectionItems = []
        tech_crawl.iab = None

        sports = MagicMock()
        sports.externalId = "sports"
        sports.title = "Sports"
        sports.sectionItems = []
        sports.iab = None

        arts = MagicMock()
        arts.externalId = "arts"
        arts.title = "Arts"
        arts.sectionItems = []
        arts.iab = None

        crawl_data = [health_crawl, tech_crawl, sports, arts]

        mock_backend.fetch = AsyncMock(return_value=crawl_data)
        return mock_backend

    @pytest.fixture
    def sections_backend_with_headlines_section_and_crawl_data(self):
        """Fake SectionsProtocol returning data with both headlines, _crawl and non-_crawl sections."""
        mock_backend = MagicMock(spec=SectionsProtocol)

        # Create test data with both _crawl and non-_crawl sections
        # Mock the required attributes properly
        tech_crawl = MagicMock()
        tech_crawl.externalId = "tech_crawl"
        tech_crawl.title = "Tech (Crawl)"
        tech_crawl.sectionItems = []
        tech_crawl.iab = None

        sports = MagicMock()
        sports.externalId = "sports"
        sports.title = "Sports"
        sports.sectionItems = []
        sports.iab = None

        # headlines_section -- to be split out from the rest of the sections
        headlines_crawl = MagicMock()
        headlines_crawl.externalId = "headlines_crawl"
        headlines_crawl.title = "Headlines"
        headlines_crawl.sectionItems = []
        headlines_crawl.iab = {"taxonomy": "IAB-3.0", "categories": ["386", "JLBCU7"]}

        crawl_data = [tech_crawl, sports, headlines_crawl]

        mock_backend.fetch = AsyncMock(return_value=crawl_data)
        return mock_backend

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
        headlines, result = await get_corpus_sections(
            sections_backend=sections_backend, surface_id=SurfaceId.NEW_TAB_EN_US, min_feed_rank=5
        )

        # No headlines section present here
        assert headlines is None

        assert set(result.keys()) == {cs.externalId for cs in sample_backend_data}
        section_a = result["business"]
        assert section_a.receivedFeedRank == 5
        assert len(section_a.recommendations) == 2
        assert section_a.layout == layout_6_tiles

        section_b = result["sports"]
        assert section_b.receivedFeedRank == 6
        assert len(section_b.recommendations) == 1
        assert section_b.layout == layout_6_tiles

        section_c = result["tech"]
        assert section_c.receivedFeedRank == 7
        assert len(section_c.recommendations) == 3
        assert section_c.layout == layout_6_tiles

    @pytest.mark.asyncio
    async def test_crawl_treatment_filters_correctly(self, sections_backend_with_crawl_data):
        """Test that treatment branch only gets _crawl sections."""
        from merino.curated_recommendations.protocol import CrawlExperimentBranchName

        _, result = await get_corpus_sections(
            sections_backend=sections_backend_with_crawl_data,
            surface_id=SurfaceId.NEW_TAB_EN_US,
            min_feed_rank=1,
            crawl_branch=CrawlExperimentBranchName.TREATMENT_CRAWL.value,
        )

        # Should only contain _crawl sections mapped to their base IDs
        assert "health" in result  # health_crawl -> health
        assert "tech" in result  # tech_crawl -> tech
        assert "sports" not in result
        assert "arts" not in result
        assert len(result) == 2

    @pytest.mark.asyncio
    async def test_control_branch_filters_correctly(self, sections_backend_with_crawl_data):
        """Test that control branch only gets non-_crawl sections."""
        from merino.curated_recommendations.protocol import CrawlExperimentBranchName

        _, result = await get_corpus_sections(
            sections_backend=sections_backend_with_crawl_data,
            surface_id=SurfaceId.NEW_TAB_EN_US,
            min_feed_rank=1,
            crawl_branch=CrawlExperimentBranchName.CONTROL.value,
        )

        # Should only contain non-_crawl sections that are legacy topics
        assert "health_crawl" not in result
        assert "tech_crawl" not in result
        assert "sports" in result
        # arts is a legacy topic so it should be included
        assert "arts" in result
        assert len(result) == 2

    @pytest.mark.asyncio
    async def test_default_parameter_filters_correctly(self, sections_backend_with_crawl_data):
        """Test that default parameter (False) filters out _crawl sections."""
        _, result = await get_corpus_sections(
            sections_backend=sections_backend_with_crawl_data,
            surface_id=SurfaceId.NEW_TAB_EN_US,
            min_feed_rank=1,
            # is_crawl_treatment defaults to False
        )

        # Should only contain non-_crawl sections that are legacy topics (default behavior)
        assert "health_crawl" not in result
        assert "tech_crawl" not in result
        assert "sports" in result
        # arts is a legacy topic so it should be included
        assert "arts" in result
        assert len(result) == 2

    @pytest.mark.asyncio
    async def test_headlines_split_and_returned_when_present(
        self, sections_backend_with_headlines_section_and_crawl_data
    ):
        """Test when headlines_crawl exists, it is split out from the other sections & returned separately."""
        headlines, result = await get_corpus_sections(
            sections_backend=sections_backend_with_headlines_section_and_crawl_data,
            surface_id=SurfaceId.NEW_TAB_EN_US,
            min_feed_rank=1,
        )

        # Headlines should be returned separately from the rest of the result
        assert headlines is not None
        assert headlines.title == "Headlines"

        # The remaining result should not contain headlines_section; should contain only non-crawl legacy topics
        assert "headlines_crawl" not in result
        assert "sports" in result
        assert "tech_crawl" not in result  # no crawl branch selected
        assert len(result) == 1

    @pytest.mark.asyncio
    async def test_headlines_not_filtered_by_crawl_branch(
        self, sections_backend_with_headlines_section_and_crawl_data
    ):
        """Test headlines_crawl is isolated from crawl/zyte filter."""
        from merino.curated_recommendations.protocol import CrawlExperimentBranchName

        headlines, result = await get_corpus_sections(
            sections_backend=sections_backend_with_headlines_section_and_crawl_data,
            surface_id=SurfaceId.NEW_TAB_EN_US,
            min_feed_rank=1,
            crawl_branch=CrawlExperimentBranchName.TREATMENT_CRAWL.value,
        )

        # Headlines should be returned separately from the rest of the result
        assert headlines is not None
        assert headlines.title == "Headlines"

        # Remaining sections should only contain _crawl sections mapped to their base IDs
        assert "sports" not in result
        assert "tech" in result  # tech_crawl -> tech
        assert len(result) == 1
