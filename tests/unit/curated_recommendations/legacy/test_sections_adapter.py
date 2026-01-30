"""Unit tests for sections_adapter module."""

from copy import deepcopy
from unittest.mock import AsyncMock, patch

import pytest

from merino.curated_recommendations.corpus_backends.protocol import SurfaceId, Topic
from merino.curated_recommendations.legacy.sections_adapter import (
    extract_recommendations_from_sections,
    get_legacy_recommendations_from_sections,
)
from merino.curated_recommendations.prior_backends.protocol import Prior, PriorBackend
from merino.curated_recommendations.engagement_backends.protocol import (
    Engagement,
    EngagementBackend,
)
from merino.curated_recommendations.protocol import Section
from merino.curated_recommendations.layouts import layout_4_medium
from tests.unit.curated_recommendations.fixtures import generate_recommendations


class TestExtractRecommendationsFromSections:
    """Tests for extract_recommendations_from_sections."""

    def test_extracts_recommendations_from_multiple_sections(self):
        """Recommendations from all sections are extracted."""
        recs_section_1 = generate_recommendations(item_ids=["a", "b", "c"])
        recs_section_2 = generate_recommendations(item_ids=["d", "e"])

        sections = {
            "section1": Section(
                receivedFeedRank=0,
                recommendations=recs_section_1,
                title="Section 1",
                layout=deepcopy(layout_4_medium),
            ),
            "section2": Section(
                receivedFeedRank=1,
                recommendations=recs_section_2,
                title="Section 2",
                layout=deepcopy(layout_4_medium),
            ),
        }

        result = extract_recommendations_from_sections(sections)

        assert len(result) == 5
        corpus_ids = [rec.corpusItemId for rec in result]
        assert corpus_ids == ["a", "b", "c", "d", "e"]

    def test_deduplicates_by_corpus_item_id(self):
        """Duplicate corpusItemIds across sections are removed."""
        recs_section_1 = generate_recommendations(item_ids=["a", "b", "c"])
        recs_section_2 = generate_recommendations(item_ids=["b", "c", "d"])  # b, c are duplicates

        sections = {
            "section1": Section(
                receivedFeedRank=0,
                recommendations=recs_section_1,
                title="Section 1",
                layout=deepcopy(layout_4_medium),
            ),
            "section2": Section(
                receivedFeedRank=1,
                recommendations=recs_section_2,
                title="Section 2",
                layout=deepcopy(layout_4_medium),
            ),
        }

        result = extract_recommendations_from_sections(sections)

        assert len(result) == 4
        corpus_ids = [rec.corpusItemId for rec in result]
        assert corpus_ids == ["a", "b", "c", "d"]

    def test_sets_scheduled_corpus_item_id(self):
        """ScheduledCorpusItemId is set to corpusItemId for each recommendation."""
        recs = generate_recommendations(item_ids=["x", "y"])

        sections = {
            "section1": Section(
                receivedFeedRank=0,
                recommendations=recs,
                title="Section 1",
                layout=deepcopy(layout_4_medium),
            ),
        }

        result = extract_recommendations_from_sections(sections)

        for rec in result:
            assert rec.scheduledCorpusItemId == rec.corpusItemId

    def test_empty_sections_returns_empty_list(self):
        """Empty sections dict returns empty list."""
        result = extract_recommendations_from_sections({})

        assert result == []

    def test_sections_with_no_recommendations(self):
        """Sections with empty recommendations lists are handled."""
        sections = {
            "section1": Section(
                receivedFeedRank=0,
                recommendations=[],
                title="Empty Section",
                layout=deepcopy(layout_4_medium),
            ),
        }

        result = extract_recommendations_from_sections(sections)

        assert result == []


class StubEngagementBackend(EngagementBackend):
    """Stub engagement backend for testing."""

    def __init__(self, metrics: dict[str, tuple[int, int]] | None = None):
        # {corpusItemId: (click_count, impression_count)}
        self.metrics = metrics or {}

    def get(self, corpus_item_id: str, region: str | None = None) -> Engagement | None:
        """Return a stub Engagement object."""
        if corpus_item_id not in self.metrics:
            return None
        click_count, impression_count = self.metrics[corpus_item_id]
        return Engagement(
            corpus_item_id=corpus_item_id,
            region=region,
            click_count=click_count,
            impression_count=impression_count,
            report_count=0,
        )


class StubPriorBackend(PriorBackend):
    """Stub prior backend for testing."""

    def __init__(self, prior: Prior | None = None):
        self._prior = prior or Prior(alpha=1, beta=10)

    def get(self, region: str | None = None) -> Prior:
        """Return stub prior."""
        return self._prior

    @property
    def update_count(self) -> int:
        """Update count stub."""
        return 0


class TestGetLegacyRecommendationsFromSections:
    """Tests for get_legacy_recommendations_from_sections function."""

    @pytest.mark.asyncio
    @patch("merino.curated_recommendations.legacy.sections_adapter.get_corpus_sections")
    @patch(
        "merino.curated_recommendations.legacy.sections_adapter.get_corpus_sections_for_legacy_topic"
    )
    async def test_filters_gaming_content_from_recommendations(
        self,
        mock_get_legacy_topic,
        mock_get_corpus_sections,
    ):
        """Gaming/hobbies content should be excluded from non-sections US recommendations.

        This test verifies that when gaming content is present in the sections feed,
        it is filtered out before Thompson sampling to prevent overrepresentation
        due to frequent updates of gaming stories.
        """
        # Setup: Create recommendations with mixed gaming and non-gaming content
        gaming_recs = generate_recommendations(
            item_ids=["gaming-1", "gaming-2"],
            topics=[Topic.GAMING, Topic.GAMING],
        )
        sports_recs = generate_recommendations(
            item_ids=["sports-1", "sports-2"],
            topics=[Topic.SPORTS, Topic.SPORTS],
        )
        tech_recs = generate_recommendations(
            item_ids=["tech-1"],
            topics=[Topic.TECHNOLOGY],
        )

        # Create sections with mixed content
        all_sections = {
            "gaming": Section(
                receivedFeedRank=0,
                recommendations=gaming_recs,
                title="Gaming",
                layout=deepcopy(layout_4_medium),
            ),
            "sports": Section(
                receivedFeedRank=1,
                recommendations=sports_recs,
                title="Sports",
                layout=deepcopy(layout_4_medium),
            ),
            "tech": Section(
                receivedFeedRank=2,
                recommendations=tech_recs,
                title="Technology",
                layout=deepcopy(layout_4_medium),
            ),
        }

        # Mock get_corpus_sections to return our test sections
        mock_get_corpus_sections.return_value = (None, all_sections)
        # Mock get_corpus_sections_for_legacy_topic to return the same sections
        mock_get_legacy_topic.return_value = all_sections

        # Setup stub backends
        sections_backend = AsyncMock()
        engagement_backend = StubEngagementBackend()
        prior_backend = StubPriorBackend()

        # Act: Call the function under test
        result = await get_legacy_recommendations_from_sections(
            sections_backend=sections_backend,
            engagement_backend=engagement_backend,
            prior_backend=prior_backend,
            surface_id=SurfaceId.NEW_TAB_EN_US,
            count=10,
            region="US",
        )

        # Assert: Gaming content should be filtered out
        result_corpus_ids = [rec.corpusItemId for rec in result]
        result_topics = [rec.topic for rec in result]

        # Verify no gaming content in results
        assert "gaming-1" not in result_corpus_ids
        assert "gaming-2" not in result_corpus_ids
        assert Topic.GAMING not in result_topics

        # Verify non-gaming content is present
        assert "sports-1" in result_corpus_ids
        assert "sports-2" in result_corpus_ids
        assert "tech-1" in result_corpus_ids

        # Verify we got the expected number of non-gaming items
        assert len(result) == 3  # 2 sports + 1 tech (gaming filtered out)
