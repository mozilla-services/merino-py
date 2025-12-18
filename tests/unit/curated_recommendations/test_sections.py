"""Module with tests covering merino/curated_recommendations/sections.py"""

import copy
import random
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
    CreateSource,
)
from merino.curated_recommendations.engagement_backends.protocol import Engagement
from merino.curated_recommendations.layouts import (
    layout_4_medium,
    layout_6_tiles,
)
from merino.curated_recommendations.prior_backends.constant_prior import ConstantPrior
from merino.curated_recommendations.prior_backends.engagment_rescaler import (
    SchedulerHoldbackRescaler,
    CrawledContentRescaler,
    UKCrawledContentRescaler,
)
from merino.curated_recommendations.protocol import (
    Section,
    SectionConfiguration,
    ExperimentName,
    DailyBriefingBranch,
    CuratedRecommendation,
    RankingData,
)
from merino.curated_recommendations.rankers import ThompsonSamplingRanker
from merino.curated_recommendations.sections import (
    adjust_ads_in_sections,
    exclude_recommendations_from_blocked_sections,
    is_subtopics_experiment,
    is_daily_briefing_experiment,
    should_show_popular_today_with_headlines,
    update_received_feed_rank,
    get_sections_with_enough_items,
    get_corpus_sections,
    map_corpus_section_to_section,
    map_section_item_to_recommendation,
    get_corpus_sections_for_legacy_topic,
    cycle_layouts_for_ranked_sections,
    LAYOUT_CYCLE,
    HEADLINES_SECTION_KEY,
    get_top_story_list,
    get_legacy_topic_ids,
    put_headlines_first_then_top_stories,
    dedupe_recommendations_across_sections,
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
            createSource=CreateSource.ML,
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
        "name,branch,region,expected",
        [
            (ExperimentName.SCHEDULER_HOLDBACK_EXPERIMENT.value, "control", "US", False),
            (ExperimentName.SCHEDULER_HOLDBACK_EXPERIMENT.value, "other", "US", True),
            (ExperimentName.SCHEDULER_HOLDBACK_EXPERIMENT.value, "other", "CA", False),
            ("other", "treatment", "US", True),
            ("other", "treatment", "ZZ", False),
        ],
    )
    def test_flag_subtopics_experiment_logic(self, name, branch, region, expected):
        """Test that experiment flag logic matches expected behavior for ML sections"""
        req = SimpleNamespace(experimentName=name, experimentBranch=branch, region=region)
        assert is_subtopics_experiment(req) is expected


class TestDailyBriefingExperiment:
    """Tests covering is_daily_briefing_experiment and should_show_popular_today_with_headlines"""

    @pytest.mark.parametrize(
        "name,branch,expected",
        [
            # briefing-with-popular branch enables daily briefing
            (
                ExperimentName.DAILY_BRIEFING_EXPERIMENT.value,
                DailyBriefingBranch.BRIEFING_WITH_POPULAR.value,
                True,
            ),
            # briefing-without-popular branch also enables daily briefing
            (
                ExperimentName.DAILY_BRIEFING_EXPERIMENT.value,
                DailyBriefingBranch.BRIEFING_WITHOUT_POPULAR.value,
                True,
            ),
            # control branch does not enable daily briefing
            (ExperimentName.DAILY_BRIEFING_EXPERIMENT.value, "control", False),
            # other experiment does not enable daily briefing
            ("other-experiment", "treatment", False),
            # no experiment does not enable daily briefing
            (None, None, False),
        ],
    )
    def test_is_daily_briefing_experiment(self, name, branch, expected):
        """Test that is_daily_briefing_experiment returns True for either treatment branch."""
        req = SimpleNamespace(experimentName=name, experimentBranch=branch)
        assert is_daily_briefing_experiment(req) is expected

    @pytest.mark.parametrize(
        "name,branch,expected",
        [
            # briefing-with-popular shows Popular Today
            (
                ExperimentName.DAILY_BRIEFING_EXPERIMENT.value,
                DailyBriefingBranch.BRIEFING_WITH_POPULAR.value,
                True,
            ),
            # briefing-without-popular does NOT show Popular Today
            (
                ExperimentName.DAILY_BRIEFING_EXPERIMENT.value,
                DailyBriefingBranch.BRIEFING_WITHOUT_POPULAR.value,
                False,
            ),
            # control branch does not show Popular Today with headlines
            (ExperimentName.DAILY_BRIEFING_EXPERIMENT.value, "control", False),
            # other experiment does not affect this
            ("other-experiment", "treatment", False),
        ],
    )
    def test_should_show_popular_today_with_headlines(self, name, branch, expected):
        """Test that should_show_popular_today_with_headlines returns True only for briefing-with-popular."""
        req = SimpleNamespace(experimentName=name, experimentBranch=branch)
        assert should_show_popular_today_with_headlines(req) is expected


class TestFilterSectionsByExperiment:
    """Tests covering filter_sections_by_experiment"""

    @pytest.mark.parametrize(
        "name,branch,region,surface_id,expected_class",
        [
            (
                ExperimentName.SCHEDULER_HOLDBACK_EXPERIMENT.value,
                "control",
                "US",
                None,
                SchedulerHoldbackRescaler,
            ),
            # Whenever we launch sections somewhere else we'll have crawled content, so best
            # to set it as default.
            ("other", "treatment", "US", SurfaceId.NEW_TAB_EN_US, CrawledContentRescaler),
            ("other", "treatment", "US", None, CrawledContentRescaler),
            ("other", "treatment", "CA", SurfaceId.NEW_TAB_EN_US, CrawledContentRescaler),
            (None, None, "US", None, CrawledContentRescaler),
            (None, None, "CA", None, CrawledContentRescaler),
            (None, None, "IE", SurfaceId.NEW_TAB_EN_GB, UKCrawledContentRescaler),
            (None, None, "UK", SurfaceId.NEW_TAB_EN_GB, UKCrawledContentRescaler),
            (None, None, "ZZ", SurfaceId.NEW_TAB_EN_GB, UKCrawledContentRescaler),
        ],
    )
    def test_get_ranking_rescaler_for_branch(
        self, name, branch, region, surface_id, expected_class
    ):
        """Test that we get the appropriate rescaler"""
        req = SimpleNamespace(experimentName=name, experimentBranch=branch, region=region)
        from merino.curated_recommendations.sections import get_ranking_rescaler_for_branch

        if expected_class is not None:
            assert isinstance(
                get_ranking_rescaler_for_branch(req, surface_id=surface_id), expected_class
            )
        else:
            assert get_ranking_rescaler_for_branch(req) is None

    def test_filter_sections_includes_both_manual_and_ml(self):
        """Test that filter_sections_by_experiment includes both MANUAL and ML sections"""
        from merino.curated_recommendations.sections import filter_sections_by_experiment
        from merino.curated_recommendations.corpus_backends.protocol import CreateSource

        # Create test sections with different createSource values
        sections = [
            MagicMock(externalId="health", createSource=CreateSource.ML),
            MagicMock(externalId="custom-section-1", createSource=CreateSource.MANUAL),
            MagicMock(externalId="tech", createSource=CreateSource.ML),
            MagicMock(externalId="custom-section-2", createSource=CreateSource.MANUAL),
        ]

        # Should include both MANUAL and ML sections (legacy topics)
        result = filter_sections_by_experiment(sections, include_subtopics=False)

        assert len(result) == 4
        assert "custom-section-1" in result
        assert "custom-section-2" in result
        assert "health" in result
        assert "tech" in result
        assert result["custom-section-1"].createSource == CreateSource.MANUAL
        assert result["custom-section-2"].createSource == CreateSource.MANUAL
        assert result["health"].createSource == CreateSource.ML
        assert result["tech"].createSource == CreateSource.ML

    def test_filter_sections_respects_subtopics_flag(self):
        """Test that filter_sections_by_experiment respects the include_subtopics flag"""
        from merino.curated_recommendations.sections import filter_sections_by_experiment
        from merino.curated_recommendations.corpus_backends.protocol import CreateSource

        # Create test sections including a non-legacy topic ML section
        sections = [
            MagicMock(externalId="health", createSource=CreateSource.ML),  # legacy
            MagicMock(externalId="custom-section-1", createSource=CreateSource.MANUAL),
            MagicMock(externalId="nfl", createSource=CreateSource.ML),  # non-legacy subtopic
        ]

        # With subtopics=False: should include MANUAL + legacy ML only
        result = filter_sections_by_experiment(sections, include_subtopics=False)
        assert "custom-section-1" in result
        assert "health" in result
        assert "nfl" not in result

        # With subtopics=True: should include MANUAL + all ML sections
        result = filter_sections_by_experiment(sections, include_subtopics=True)
        assert "custom-section-1" in result
        assert "health" in result
        assert "nfl" in result


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
        assert rec.features == {f"s_{section_id}": 1.0, f"t_{item.topic.value}": 1.0}
        assert not rec.in_experiment("unknown_experiment")

    def test_basic_mapping_manual_section(self):
        """Map a valid CorpusItem into a CuratedRecommendation."""
        item = generate_corpus_item()
        section_id = "secX"
        rec = map_section_item_to_recommendation(item, 3, section_id, is_manual_section=True)
        assert isinstance(rec, CuratedRecommendation)
        assert rec.receivedRank == 3
        assert rec.features == {f"t_{item.topic.value}": 1.0}

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
        empty_cs = CorpusSection(
            sectionItems=[], title="Empty", externalId="empty", createSource=CreateSource.ML
        )
        sec = map_corpus_section_to_section(empty_cs, 7)
        assert sec.recommendations == []
        assert sec.receivedFeedRank == 7

    def test_dedupes_duplicate_items(self):
        """Duplicate corpus items are removed within a section while preserving order."""
        dup_item = generate_corpus_item("dup", "sched_dup")
        unique_item = generate_corpus_item("unique", "sched_unique")
        cs = CorpusSection(
            sectionItems=[dup_item, dup_item, unique_item],
            title="With Duplicates",
            externalId="dup-section",
            createSource=CreateSource.ML,
        )

        sec = map_corpus_section_to_section(cs, 2)

        assert [rec.corpusItemId for rec in sec.recommendations] == ["dup", "unique"]
        assert [rec.receivedRank for rec in sec.recommendations] == [0, 1]


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


class TestDedupeRecommendationsAcrossSections:
    """Tests for dedupe_recommendations_across_sections."""

    @staticmethod
    def build_section(item_ids: list[str], rank: int, title: str) -> Section:
        """Lightweight helper to create a section with the given ids and rank."""
        return Section(
            receivedFeedRank=rank,
            recommendations=generate_recommendations(item_ids=item_ids),
            title=title,
            layout=copy.deepcopy(layout_4_medium),
        )

    def test_dedupes_and_drops_underfilled_sections(self):
        """Keeps items from higher-priority sections and drops sections that shrink too much."""
        top_ids = ["a", "b", "c", "d", "e"]  # meets layout_4_medium.max_tile_count + 1
        mid_ids = ["b", "c", "f", "g", "h", "i", "j"]  # drops two dupes, still >= threshold
        low_ids = ["b", "k"]  # will be too small after dedupe

        sections = dedupe_recommendations_across_sections(
            {
                "top": self.build_section(top_ids, 0, "Top Stories"),
                "mid": self.build_section(mid_ids, 1, "Mid"),
                "low": self.build_section(low_ids, 2, "Low"),
            }
        )

        assert set(sections.keys()) == {"top", "mid"}
        assert sections["top"].receivedFeedRank == 0
        assert sections["mid"].receivedFeedRank == 1

        assert [rec.corpusItemId for rec in sections["top"].recommendations] == top_ids
        # Duplicates of b/c removed; remaining must re-number ranks
        assert [rec.corpusItemId for rec in sections["mid"].recommendations] == [
            "f",
            "g",
            "h",
            "i",
            "j",
        ]
        assert [rec.receivedRank for rec in sections["mid"].recommendations] == list(
            range(len(sections["mid"].recommendations))
        )


class TestGetTopStoryList:
    """Tests for get_top_story_list."""

    # Mixed topical and evergreen topics to not trigger limiting code
    non_dupe_topics = [
        Topic.CAREER,
        Topic.POLITICS,
        Topic.PERSONAL_FINANCE,
        Topic.ARTS,
        Topic.ARTS,
    ]

    def test_returns_top_count_items(self):
        """Should return exactly `top_count` items from start of list if extra_count is 0."""
        items = generate_recommendations(
            item_ids=["a", "b", "c", "d", "e"],
            topics=["arts", "business", "food", "government", "food"],
        )
        result = get_top_story_list(items, top_count=3, extra_count=0)
        assert len(result) == 3
        assert [i.corpusItemId for i in result] == ["a", "b", "c"]

    def test_basic_topic_limiting(self):
        """Extra items should be chosen without repeating topics from top_count items."""
        items = generate_recommendations(
            item_ids=["a", "b", "c", "d", "e", "f"],
            topics=["arts", "arts", "arts", "business", "food", "government"],
        )
        result = get_top_story_list(items, top_count=4, extra_count=0, extra_source_depth=0)

        top_ids = [i.corpusItemId for i in result]

        assert len(result) == 4
        assert "c" not in top_ids
        assert {"a", "b", "d", "e"}.issubset(set(top_ids))

        for ix, item in enumerate(result):
            assert item.receivedRank == ix

    def test_basic_topic_limiting_with_personalization(self):
        """Extra items should be chosen without repeating topics from top_count items."""
        items = generate_recommendations(
            item_ids=["a", "b", "c", "d", "e", "f"],
            topics=["arts", "arts", "arts", "arts", "food", "government"],
        )
        result = get_top_story_list(
            items,
            top_count=6,
            extra_count=0,
            extra_source_depth=0,
            relax_constraints_for_personalization=True,
        )
        top_ids = [i.corpusItemId for i in result]
        assert len(result) == 6
        top_ids[2] == "c"
        for ix, item in enumerate(result):
            assert item.receivedRank == ix

    def test_includes_extra_items_topic_limiting(self):
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
        items = generate_recommendations(item_ids=["a", "b", "c"], topics=self.non_dupe_topics[:3])
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

    # Below tests are for rate-limiting on fresh content with no impressions yet

    def test_returns_top_count_items_when_none_fresh(self):
        """Should return exactly `top_count` items from start of list, not using
        rescaler because no items have fresh label
        """
        rescaler = CrawledContentRescaler(fresh_items_top_stories_max_percentage=0.5)
        items = generate_recommendations(
            item_ids=["a", "b", "c", "d", "e"], topics=self.non_dupe_topics[:5]
        )
        for rec in items:
            rec.ranking_data = RankingData(alpha=1, beta=1, score=1, is_fresh=False)
        result = get_top_story_list(items, top_count=3, extra_count=0, rescaler=rescaler)
        assert len(result) == 3
        assert [i.corpusItemId for i in result] == ["a", "b", "c"]

    def test_all_fresh_items_without_rescaler_returns_top_slice(self):
        """No special handling of fresh items when there is no rescalar."""
        items = generate_recommendations(
            item_ids=["a", "b", "c", "d"], topics=self.non_dupe_topics[:4]
        )
        for rec in items:
            rec.ranking_data = RankingData(alpha=1, beta=1, score=1, is_fresh=True)

        result = get_top_story_list(items, top_count=3, extra_count=0, extra_source_depth=0)

        assert [rec.corpusItemId for rec in result] == ["a", "b", "c"]
        assert [rec.receivedRank for rec in result] == [0, 1, 2]

    def test_rescaler_keeps_probability_capped_fresh_items(self, monkeypatch):
        """Ensure rescaler-controlled fresh limit passes through fresh items."""
        items = generate_recommendations(
            item_ids=["a", "b", "c", "d"], topics=self.non_dupe_topics[:4]
        )
        for rec in items:
            rec.ranking_data = RankingData(alpha=1, beta=1, score=1, is_fresh=True)
        rescaler = CrawledContentRescaler(fresh_items_top_stories_max_percentage=0.5)

        monkeypatch.setattr("merino.curated_recommendations.rankers.utils.random", lambda: 0.1)

        result = get_top_story_list(
            items, top_count=3, extra_count=0, extra_source_depth=0, rescaler=rescaler
        )
        assert [rec.corpusItemId for rec in result] == ["a", "b", "c"]
        assert [rec.receivedRank for rec in result] == [0, 1, 2]

    def test_rescaler_backfills_fresh_when_random_never_allows(self, monkeypatch):
        """When probability never allows fresh picks, backlog of fresh picks fill the quota
        See - filter_fresh_items_with_probability for additional tests
        """
        items = generate_recommendations(
            item_ids=["a", "b", "c", "d"], topics=self.non_dupe_topics[:4]
        )
        for rec in items:
            rec.ranking_data = RankingData(alpha=1, beta=1, score=1, is_fresh=True)
        rescaler = CrawledContentRescaler(fresh_items_top_stories_max_percentage=0.5)

        monkeypatch.setattr("merino.curated_recommendations.rankers.utils.random", lambda: 0.9)

        result = get_top_story_list(
            items, top_count=2, extra_count=0, extra_source_depth=0, rescaler=rescaler
        )

        assert [rec.corpusItemId for rec in result] == ["a", "b"]
        assert [rec.receivedRank for rec in result] == [0, 1]

    def test_random_situations(self):
        """Stress test and check to see that we return enough items, regardless of topic constraints"""
        random.seed(42)
        all_topics = list(Topic)
        for num_items in range(40):
            ids = [f"id-{k}" for k in range(num_items)]
            topics = [random.choice(all_topics) for _k in range(num_items)]

            items = generate_recommendations(item_ids=ids, topics=topics)
            result = get_top_story_list(
                items, top_count=10, extra_count=3, extra_source_depth=4, rescaler=None
            )
            assert len(result) == min(len(items), 10 + 3)
            picked_ids = set([rec.corpusItemId for rec in result])
            assert len(picked_ids) == len(result)  # Check no duplicates


class DummyTrackingEngagementBackend:
    """Simple engagement backend that records which items were requested."""

    def __init__(self, metrics: dict[str, tuple[int, int]]):
        self._metrics = metrics
        self.requests: list[str] = []

    def get(self, corpus_item_id: str, region: str | None = None) -> Engagement | None:
        """Return engagement"""
        self.requests.append(corpus_item_id)
        if corpus_item_id not in self._metrics:
            return None
        clicks, impressions = self._metrics[corpus_item_id]
        return Engagement(
            corpus_item_id=corpus_item_id,
            region=region,
            click_count=clicks,
            impression_count=impressions,
            report_count=0,
        )

    @property
    def update_count(self) -> int:
        """Dummy function"""
        return 0


class TestSectionThompsonSampling:
    """Tests for section_thompson_sampling fresh item handling."""

    def test_limits_fresh_items_when_rescaler_cap_active(self, monkeypatch):
        """Only allow fresh items up to cap when enough non-fresh content exists."""
        rescaler = CrawledContentRescaler(fresh_items_section_ranking_max_percentage=0.1)
        recs = generate_recommendations(
            item_ids=["fresh1", "fresh2", "fresh3", "stale1", "stale2"],
            time_sensitive_count=0,
            topics=list(Topic)[:5],
        )
        for idx, rec in enumerate(recs):
            rec.ranking_data = RankingData(alpha=1, beta=1, score=1, is_fresh=idx < 3)

        metrics = {rec.corpusItemId: (idx + 1, (idx + 1) * 10) for idx, rec in enumerate(recs)}
        backend = DummyTrackingEngagementBackend(metrics)

        sections = {
            "sec": Section(
                receivedFeedRank=0,
                recommendations=recs,
                title="Section",
                layout=copy.deepcopy(layout_4_medium),
            )
        }

        monkeypatch.setattr(
            "merino.curated_recommendations.rankers.t_sampling.beta.rvs", lambda a, b: 0.5
        )
        monkeypatch.setattr("merino.curated_recommendations.rankers.utils.random", lambda: 0.8)

        top_n = 4

        thomspon_sampling = ThompsonSamplingRanker(backend, ConstantPrior())
        thomspon_sampling.rank_sections(sections, top_n=top_n, rescaler=rescaler)

        # Engagement tracker checks for global and regional engagement
        assert len(backend.requests) == top_n * 2


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
        feed[HEADLINES_SECTION_KEY] = Section(
            receivedFeedRank=3,
            recommendations=[],
            title="Your Briefing",
            layout=copy.deepcopy(layout_4_medium),
        )
        headlines_section = feed[HEADLINES_SECTION_KEY]

        put_headlines_first_then_top_stories(feed)

        # Check ranks for headlines & top_stories are updated
        assert headlines_section.receivedFeedRank == 0
        assert top_stories_section.receivedFeedRank == 1

        # Get the other sections besides headlines & top_stories
        remaining_sections = sorted(
            (sid for sid in feed if sid not in (HEADLINES_SECTION_KEY, "top_stories_section")),
            key=lambda sid: feed[sid].receivedFeedRank,
        )

        # Expected: headlines first -> top_stories_section second, then rest in keys order without headlines & top
        expected_order = [HEADLINES_SECTION_KEY, "top_stories_section"] + remaining_sections

        for idx, sid in enumerate(expected_order):
            assert feed[sid].receivedFeedRank == idx

    def test_with_headlines_and_no_top_stories(self):
        """Test when no top_stories present, headlines is put on top & other sections are rank=1...N and preserve relative order."""
        feed = generate_sections_feed(section_count=6, has_top_stories=False)

        # Insert headlines section at rank 3
        feed[HEADLINES_SECTION_KEY] = Section(
            receivedFeedRank=3,
            recommendations=[],
            title="Your Briefing",
            layout=copy.deepcopy(layout_4_medium),
        )
        headlines_section = feed[HEADLINES_SECTION_KEY]

        # Get the other sections besides headlines & top_stories
        remaining_sections = sorted(
            (sid for sid in feed if sid not in (HEADLINES_SECTION_KEY, "top_stories_section")),
            key=lambda sid: feed[sid].receivedFeedRank,
        )

        put_headlines_first_then_top_stories(feed)

        # Headlines should be on top rank==0
        assert headlines_section.receivedFeedRank == 0

        # Expected: headlines first -> then rest in keys order without headlines & top
        expected_order = [HEADLINES_SECTION_KEY] + remaining_sections

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


class TestGetCorpusSections:
    """Tests for get_corpus_sections function."""

    @pytest.fixture
    def sections_backend_with_headlines_section(self):
        """Fake SectionsProtocol returning data with a headlines section."""
        mock_backend = MagicMock(spec=SectionsProtocol)

        sports = MagicMock()
        sports.externalId = "sports"
        sports.title = "Sports"
        sports.description = None
        sports.heroTitle = None
        sports.heroSubtitle = None
        sports.sectionItems = []
        sports.iab = None
        sports.createSource = CreateSource.ML

        headlines = MagicMock()
        headlines.externalId = HEADLINES_SECTION_KEY
        headlines.title = "Headlines"
        headlines.description = "Top Headlines today"
        headlines.heroTitle = None
        headlines.heroSubtitle = None
        headlines.sectionItems = []
        headlines.iab = {"taxonomy": "IAB-3.0", "categories": ["386", "JLBCU7"]}
        headlines.createSource = CreateSource.ML

        mock_backend.fetch = AsyncMock(return_value=[sports, headlines])
        return mock_backend

    @pytest.fixture
    def sections_backend_with_manual_sections(self):
        """Fake SectionsProtocol returning a mix of manual and ML sections."""
        mock_backend = MagicMock(spec=SectionsProtocol)

        ml_section = MagicMock()
        ml_section.externalId = "sports"
        ml_section.title = "Sports"
        ml_section.sectionItems = []
        ml_section.description = None
        ml_section.heroTitle = None
        ml_section.heroSubtitle = None
        ml_section.iab = None
        ml_section.createSource = CreateSource.ML

        manual_one = MagicMock()
        manual_one.externalId = "custom-section-1"
        manual_one.title = "Custom One"
        manual_one.sectionItems = []
        manual_one.description = None
        manual_one.heroTitle = None
        manual_one.heroSubtitle = None
        manual_one.iab = None
        manual_one.createSource = CreateSource.MANUAL

        manual_two = MagicMock()
        manual_two.externalId = "custom-section-2"
        manual_two.title = "Custom Two"
        manual_two.sectionItems = []
        manual_two.description = None
        manual_two.heroTitle = None
        manual_two.heroSubtitle = None
        manual_two.iab = None
        manual_two.createSource = CreateSource.MANUAL

        mock_backend.fetch = AsyncMock(return_value=[ml_section, manual_one, manual_two])
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
    async def test_headlines_section_split_out(self, sections_backend_with_headlines_section):
        """Headlines section should be returned separately from the other sections."""
        headlines, sections = await get_corpus_sections(
            sections_backend=sections_backend_with_headlines_section,
            surface_id=SurfaceId.NEW_TAB_EN_US,
            min_feed_rank=1,
        )

        assert headlines is not None
        assert headlines.title == "Headlines"
        assert headlines.subtitle == "Top Headlines today"
        assert HEADLINES_SECTION_KEY not in sections
        # Remaining sections should still be mapped.
        assert set(sections.keys()) == {"sports"}

    @pytest.mark.asyncio
    async def test_includes_both_manual_and_ml_sections(
        self, sections_backend_with_manual_sections
    ):
        """Both manual and ML sections are included."""
        _, sections = await get_corpus_sections(
            sections_backend=sections_backend_with_manual_sections,
            surface_id=SurfaceId.NEW_TAB_EN_US,
            min_feed_rank=0,
        )

        # Should include both ML and MANUAL sections
        assert set(sections.keys()) == {"sports", "custom-section-1", "custom-section-2"}
