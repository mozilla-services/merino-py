"""Tests covering merino/curated_recommendations/interest_picker.py"""

import pytest

from merino.curated_recommendations.corpus_backends.protocol import Topic
from merino.curated_recommendations.interest_picker import (
    create_interest_picker,
    MIN_INITIALLY_VISIBLE_SECTION_COUNT,
    MIN_INTEREST_PICKER_COUNT,
)
from merino.curated_recommendations.layouts import layout_4_medium
from merino.curated_recommendations.protocol import Section, CuratedRecommendationsFeed


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


def test_no_sections():
    """Test that if the feed has no sections, no interest picker is created."""
    feed, interest_picker = create_interest_picker(CuratedRecommendationsFeed())
    assert interest_picker is None


def test_not_enough_sections():
    """Test that the interest picker is not shown if insufficient sections are available."""
    # Create 10 sections. With MIN_INITIALLY_VISIBLE_SECTION_COUNT = 3, there will be 10 - 3 = 7 sections
    # eligible for the interest picker, which is less than the min of 8.
    section_count = MIN_INTEREST_PICKER_COUNT + MIN_INITIALLY_VISIBLE_SECTION_COUNT - 1
    feed, interest_picker = create_interest_picker(generate_feed(section_count))

    # Interest picker should not be created.
    assert interest_picker is None

    # All sections must be visible.
    for section, _ in feed.get_sections():
        assert section.isInitiallyVisible is True


@pytest.mark.parametrize("followed_count", list(range(7)))
def test_interest_picker_is_created(followed_count: int):
    """Test that the interest picker is created as expected, if enough sections are available."""
    section_count = 15
    feed = generate_feed(section_count, followed_count=followed_count)
    feed, interest_picker = create_interest_picker(feed)

    assert interest_picker is not None

    # The picker is ranked randomly, with different ranges depending on if any sections are followed
    min_picker_rank = 1 if followed_count == 0 else 2
    max_picker_rank = min_picker_rank + 2
    assert min_picker_rank <= interest_picker.receivedFeedRank <= max_picker_rank

    # Verify that the first MIN_INITIALLY_VISIBLE_SECTION_COUNT sections are visible.
    sections = feed.get_sections()
    visible_sections = [section for section, _ in sections if section.isInitiallyVisible]
    assert len(visible_sections) == max(MIN_INITIALLY_VISIBLE_SECTION_COUNT, 1 + followed_count)

    # Verify that all followed sections are visible.
    for section, _ in sections:
        if section.isFollowed:
            assert section.isInitiallyVisible is True

    # Verify that receivedFeedRank (including on interestPicker) is numbered 0, 1, 2, etc.
    ranks = [section.receivedFeedRank for section, _ in sections]
    expected_ranks = [i for i in range(section_count + 1) if i != interest_picker.receivedFeedRank]
    assert sorted(ranks) == expected_ranks

    # Verify that the interest picker's sections include all sections not visible by default.
    hidden_section_ids: list[str | None] = [
        section_id for section, section_id in sections if not section.isInitiallyVisible
    ]
    picker_ids = [s.sectionId for s in interest_picker.sections]
    assert set(picker_ids) == set(hidden_section_ids)
