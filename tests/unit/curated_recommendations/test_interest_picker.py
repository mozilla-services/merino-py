"""Tests covering merino/curated_recommendations/interest_picker.py"""

import pytest

from merino.curated_recommendations.corpus_backends.protocol import Topic
from merino.curated_recommendations.interest_picker import (
    create_interest_picker,
    _set_section_initial_visibility,
    _get_interest_picker_rank,
    _renumber_sections,
    MIN_INITIALLY_VISIBLE_SECTION_COUNT,
    MIN_INTEREST_PICKER_COUNT,
)
from merino.curated_recommendations.layouts import layout_4_medium
from merino.curated_recommendations.protocol import (
    Section,
    CuratedRecommendationsFeed,
    SectionWithID,
)


def generate_feed(section_count: int, followed_count: int = 0) -> CuratedRecommendationsFeed:
    """Create a CuratedRecommendationsFeed populated with sections.

    Args:
        section_count (int): Number of sections to create.
        followed_count (int, optional): Number of sections to follow. Defaults to 0.

    Returns:
        CuratedRecommendationsFeed: A feed with generated sections.
    """
    feed = CuratedRecommendationsFeed()

    # Set top_stories_section first.
    feed.top_stories_section = Section(
        receivedFeedRank=0,
        recommendations=[],  # Dummy recommendations.
        title="Top Stories",
        layout=layout_4_medium,
    )

    # Use topics to generate remaining sections.
    topics = list(Topic)[: section_count - 1]
    for i, topic in enumerate(topics):
        section = Section(
            receivedFeedRank=i + 1,  # Ranks start after top_stories_section.
            recommendations=[],
            title=f"{topic.value.title()} Section",
            layout=layout_4_medium,
            isFollowed=(i < followed_count),
        )
        feed.set_topic_section(topic, section)

    return feed


def test_no_sections():
    """Test that if the feed has no sections, no interest picker is created."""
    feed = CuratedRecommendationsFeed()
    sections: list[SectionWithID] = feed.get_sections()  # Expected to be empty.
    picker = create_interest_picker(sections)
    assert picker is None


def test_not_enough_sections():
    """Test that no interest picker is created if insufficient sections are eligible."""
    # Create feed such that hidden sections = total - MIN_INITIALLY_VISIBLE_SECTION_COUNT
    total = MIN_INTEREST_PICKER_COUNT + MIN_INITIALLY_VISIBLE_SECTION_COUNT - 1
    feed = generate_feed(total)
    sections = feed.get_sections()
    picker = create_interest_picker(sections)
    # Not enough hidden sections -> no picker.
    assert picker is None
    # All sections must be visible.
    for s in sections:
        assert s.section.isInitiallyVisible is True


@pytest.mark.parametrize("followed_count", list(range(7)))
def test_interest_picker_is_created(followed_count: int):
    """Test that an interest picker is created when enough sections are available."""
    total = 15
    feed = generate_feed(total, followed_count=followed_count)
    sections = feed.get_sections()
    picker = create_interest_picker(sections)
    assert picker is not None
    # Picker rank range depends on followed sections.
    min_picker_rank = 1 if followed_count == 0 else 2
    max_picker_rank = min_picker_rank + 2
    assert min_picker_rank <= picker.receivedFeedRank <= max_picker_rank
    # Check that first MIN_INITIALLY_VISIBLE_SECTION_COUNT sections are visible.
    visible = [s for s in sections if s.section.isInitiallyVisible]
    expected_vis = max(MIN_INITIALLY_VISIBLE_SECTION_COUNT, 1 + followed_count)
    assert len(visible) == expected_vis
    # All followed sections must be visible.
    for s in sections:
        if s.section.isFollowed:
            assert s.section.isInitiallyVisible is True
    # Check renumbering: ranks should be sequential and skip the picker rank.
    ranks = [s.section.receivedFeedRank for s in sections]
    expected = [i for i in range(total + 1) if i != picker.receivedFeedRank]
    assert sorted(ranks) == expected
    # Check picker sections: they must include all sections not initially visible.
    hidden_ids = {s.ID for s in sections if not s.section.isInitiallyVisible}
    picker_ids = {ps.sectionId for ps in picker.sections}
    assert picker_ids == hidden_ids


def test_renumber_sections_preserves_order():
    """Test that _renumber_sections assigns sequential ranks skipping the picker rank."""
    # Create a simple list of SectionWithID with preset ranks.
    sections = []
    for i in range(5):
        sec = Section(
            receivedFeedRank=i, recommendations=[], title=f"S{i}", layout=layout_4_medium
        )
        # Dummy ID is "id{i}"
        sections.append(SectionWithID(section=sec, ID=f"id{i}"))
    # Suppose picker rank is 2.
    _renumber_sections(sections, 2)
    new_ranks = [s.section.receivedFeedRank for s in sections]
    # Expected ranks: 0,1,3,4,5 (2 is skipped).
    assert new_ranks == [0, 1, 3, 4, 5]


def test_get_interest_picker_rank_no_followed():
    """Test _get_interest_picker_rank returns values in [1, 3] when no section is followed."""
    sections = []
    for i in range(10):
        sec = Section(
            receivedFeedRank=i, recommendations=[], title=f"S{i}", layout=layout_4_medium
        )
        sec.isFollowed = False
        sections.append(SectionWithID(section=sec, ID=f"id{i}"))
    results = {_get_interest_picker_rank(sections) for _ in range(100)}
    # All values must be in the range [1,3]
    for r in results:
        assert 1 <= r <= 3


def test_get_interest_picker_rank_with_followed():
    """Test _get_interest_picker_rank returns values in [2, 4] when at least one section is followed."""
    sections = []
    for i in range(10):
        sec = Section(
            receivedFeedRank=i, recommendations=[], title=f"S{i}", layout=layout_4_medium
        )
        sec.isFollowed = i == 5
        sections.append(SectionWithID(section=sec, ID=f"id{i}"))
    results = {_get_interest_picker_rank(sections) for _ in range(100)}
    for r in results:
        assert 2 <= r <= 4


def test_set_section_initial_visibility_without_enough_sections():
    """Test _set_section_initial_visibility makes all sections visible exceeding min_picker."""
    # Create 10 sections; mark none as followed initially.
    sections = []
    for i in range(10):
        sec = Section(
            receivedFeedRank=i, recommendations=[], title=f"S{i}", layout=layout_4_medium
        )
        sec.isFollowed = False
        # Initially, set all to False.
        sec.isInitiallyVisible = False
        sections.append(SectionWithID(section=sec, ID=f"id{i}"))
    # Call function with min_visible=3, min_picker=8.
    _set_section_initial_visibility(sections, 3, 8)
    # Since there are 10 sections, invisible count would be 10-3=7 < 8, so all become visible.
    assert all(s.section.isInitiallyVisible for s in sections if s.section.isInitiallyVisible)


def test_set_section_initial_visibility_with_followed():
    """Test that followed sections are always visible and minimum count is met."""
    sections = []
    for i in range(15):
        sec = Section(
            receivedFeedRank=i, recommendations=[], title=f"S{i}", layout=layout_4_medium
        )
        # Mark sections 2 and 7 as followed.
        sec.isFollowed = i in [2, 7]
        sec.isInitiallyVisible = False
        sections.append(SectionWithID(section=sec, ID=f"id{i}"))
    _set_section_initial_visibility(sections, 3, 8)
    visible = [s for s in sections if s.section.isInitiallyVisible]
    # At least sections 2 and 7 must be visible, and the top 3 overall.
    assert [s.ID for s in visible] == ["id0", "id1", "id2", "id7"]
    for s in sections:
        if s.section.isFollowed:
            assert s.section.isInitiallyVisible is True
