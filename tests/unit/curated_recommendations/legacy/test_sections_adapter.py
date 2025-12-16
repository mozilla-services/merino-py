"""Unit tests for sections_adapter module."""

from copy import deepcopy

from merino.curated_recommendations.legacy.sections_adapter import (
    extract_recommendations_from_sections,
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
