"""Tests covering merino/curated_recommendations/interest_picker.py"""

import pytest

from merino.curated_recommendations.corpus_backends.protocol import Topic
from merino.curated_recommendations.interest_picker import (
    apply_interest_picker,
    MIN_INITIALLY_VISIBLE_SECTION_COUNT,
    MIN_INTEREST_PICKER_COUNT,
)
from merino.curated_recommendations.layouts import layout_4_medium
from merino.curated_recommendations.protocol import (
    CuratedRecommendationsResponse,
    Section,
    CuratedRecommendationsFeed,
)


def generate_feed(section_count: int, followed_count: int = 0) -> CuratedRecommendationsFeed:
    """Create a CuratedRecommendationsFeed populated with sections.
    Args:
        section_count (int): Number of sections to create.
        followed_count (int, optional): Number of sections to follow. Defaults to 0.

    Returns:
        CuratedRecommendationsFeed: A feed instance containing the generated sections.
    """
    feed = CuratedRecommendationsFeed()

    # Set top_stories_section first.
    feed.top_stories_section = Section(
        receivedFeedRank=0,
        recommendations=[],  # No recommendations are added for dummy purposes.
        title="Top Stories",
        layout=layout_4_medium,
    )

    # Iterate over the Topic enum and add topic sections.
    topics = list(Topic)[: section_count - 1]
    for i, topic in enumerate(topics):
        section = Section(
            receivedFeedRank=i + 1,  # Ranks start after top_stories_section.
            recommendations=[],
            title=f"{topic.value.title()} Section",
            layout=layout_4_medium,
            isFollowed=i < followed_count,
        )
        feed.set_topic_section(topic, section)

    return feed


@pytest.fixture
def response():
    """Fixture for CuratedRecommendationsResponse"""
    return CuratedRecommendationsResponse(
        recommendedAt=0, data=[], feeds=None, interestPicker=None
    )


def test_no_feeds(response):
    """Test that if the response has no feeds, the function does nothing."""
    apply_interest_picker(response)
    assert response.interestPicker is None


def test_not_enough_sections(response):
    """Test that the interest picker is not shown if insufficient sections are available."""
    # Create 10 sections. With MIN_INITIALLY_VISIBLE_SECTION_COUNT = 3, there will be 7 sections
    # eligible for the interest picker, which is less than the min of 8.
    section_count = MIN_INTEREST_PICKER_COUNT + MIN_INITIALLY_VISIBLE_SECTION_COUNT - 1
    response.feeds = generate_feed(section_count)
    apply_interest_picker(response)

    # Interest picker should not be created.
    assert response.interestPicker is None

    # All sections must be visible.
    for section, _ in response.feeds.get_sections():
        assert section.isInitiallyVisible


@pytest.mark.parametrize("followed_count", list(range(7)))
def test_interest_picker_is_created(response, followed_count: int):
    """Test that the interest picker is created as expected, if enough sections are available."""
    section_count = 15
    response.feeds = generate_feed(section_count, followed_count=followed_count)
    apply_interest_picker(response)

    assert response.interestPicker is not None

    # The picker is ranked randomly, with different ranges depending on if any sections are followed
    min_picker_rank = 1 if followed_count == 0 else 2
    max_picker_rank = min_picker_rank + 2
    assert min_picker_rank <= response.interestPicker.receivedFeedRank <= max_picker_rank

    # Verify that the first MIN_INITIALLY_VISIBLE_SECTION_COUNT sections are visible.
    sections = response.feeds.get_sections()
    visible_sections = [section for section, _ in sections if section.isInitiallyVisible]
    assert len(visible_sections) == max(MIN_INITIALLY_VISIBLE_SECTION_COUNT, 1 + followed_count)

    # Verify that all followed sections are visible.
    for section, _ in sections:
        if section.isFollowed:
            assert section.isInitiallyVisible is True

    # Verify that receivedFeedRank (including on interestPicker) is numbered 0, 1, 2, etc.
    ranks = [section.receivedFeedRank for section, _ in sections]
    assert sorted(ranks) == [
        i for i in range(section_count + 1) if i != response.interestPicker.receivedFeedRank
    ]

    # Verify that the interest picker's sections include all sections not visible by default.
    hidden_section_ids = [
        section_id for section, section_id in sections if not section.isInitiallyVisible
    ]
    assert set([s.sectionId for s in response.interestPicker.sections]) == set(hidden_section_ids)
