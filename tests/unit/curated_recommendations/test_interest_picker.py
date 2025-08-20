"""Tests covering merino/curated_recommendations/interest_picker.py"""

from random import shuffle

import pytest

from merino.curated_recommendations.interest_picker import (
    create_interest_picker,
    _set_section_initial_visibility,
    _get_interest_picker_rank,
    _renumber_sections,
    MIN_INITIALLY_VISIBLE_SECTION_COUNT,
    MIN_INTEREST_PICKER_COUNT,
)
from merino.curated_recommendations.layouts import layout_4_medium
from merino.curated_recommendations.protocol import Section
from tests.unit.curated_recommendations.fixtures import generate_sections_feed


def test_no_sections():
    """Test that if the feed has no sections, no interest picker is created."""
    assert create_interest_picker(sections={}) is None


def test_not_enough_sections():
    """Test that no interest picker is created if insufficient sections are eligible."""
    # Create feed such that hidden sections = total - MIN_INITIALLY_VISIBLE_SECTION_COUNT
    total = MIN_INTEREST_PICKER_COUNT + MIN_INITIALLY_VISIBLE_SECTION_COUNT - 1
    sections = generate_sections_feed(total)
    picker = create_interest_picker(sections)
    # Not enough hidden sections -> no picker.
    assert picker is None
    # All sections must be visible.
    for s in sections.values():
        assert s.isInitiallyVisible is True


@pytest.mark.parametrize("followed_count", list(range(7)))
def test_interest_picker_is_created(followed_count: int):
    """Test that an interest picker is created as expected, if enough sections are available."""
    total = 15
    sections = generate_sections_feed(total, followed_count=followed_count)
    original_order = list(sections.keys())

    picker = create_interest_picker(sections)
    assert picker is not None

    # Picker has expected title string and no subtitle.
    assert picker.title == "Follow topics to fine-tune your experience"
    assert picker.subtitle is None

    # Picker rank range depends on followed sections.
    min_picker_rank = 1 if followed_count == 0 else 2
    max_picker_rank = min_picker_rank + 2
    assert min_picker_rank <= picker.receivedFeedRank <= max_picker_rank

    # Check that first MIN_INITIALLY_VISIBLE_SECTION_COUNT sections are visible.
    visible = [s for s in sections.values() if s.isInitiallyVisible]
    expected_vis = max(MIN_INITIALLY_VISIBLE_SECTION_COUNT, 1 + followed_count)
    assert len(visible) == expected_vis

    # All followed sections must be visible.
    for s in sections.values():
        if s.isFollowed:
            assert s.isInitiallyVisible is True

    # Check renumbering: ranks should be sequential and skip the picker rank.
    ranks = [s.receivedFeedRank for s in sections.values()]
    expected = [i for i in range(len(sections) + 1) if i != picker.receivedFeedRank]
    assert sorted(ranks) == expected

    # Check picker sections: they must include all sections not initially visible.
    hidden_ids = {key for key, s in sections.items() if not s.isInitiallyVisible}
    picker_ids = {ps.sectionId for ps in picker.sections}
    assert picker_ids == hidden_ids

    # Assert that the order of sections is preserved from before calling create_interest_picker.
    new_order = [
        key for key, s in sorted(sections.items(), key=lambda item: item[1].receivedFeedRank)
    ]
    assert new_order == original_order


def test_renumber_sections_preserves_order_skips_picker_rank():
    """Test that _renumber_sections preserves original order and skips the picker rank."""
    sections = {}
    for i in range(5):
        sec = Section(
            receivedFeedRank=i, recommendations=[], title=f"S{i}", layout=layout_4_medium
        )
        sections[f"id{i}"] = sec
    # Capture original section insertion order
    section_ids_original_order = list(sections.keys())
    # Suppose picker rank is 2.
    _renumber_sections(sections, 2)
    # Get new_ranks in original order
    new_ranks = [sections[s].receivedFeedRank for s in section_ids_original_order]

    # Expected ranks: 0,1,3,4,5 (2 is skipped).
    assert new_ranks == [0, 1, 3, 4, 5]

    # Verify that sorting by new rank preserves original ordering of section keys
    new_order = [s for s, _ in sorted(sections.items(), key=lambda item: item[1].receivedFeedRank)]
    assert new_order == section_ids_original_order


@pytest.mark.parametrize(
    "followed, expected_ranks",
    [
        (False, {1, 2, 3}),
        (True, {2, 3}),
    ],
)
def test_get_interest_picker_rank_param(followed: bool, expected_ranks: set[int]):
    """Test _get_interest_picker_rank returns proper values based on followed status."""
    sections = {}
    for i in range(10):
        sec = Section(
            receivedFeedRank=i, recommendations=[], title=f"S{i}", layout=layout_4_medium
        )
        sec.isFollowed = (i == 5) if followed else False
        sections[f"id{i}"] = sec
    actual_ranks = {_get_interest_picker_rank(sections) for _ in range(100)}
    assert actual_ranks == expected_ranks


def test_set_section_initial_visibility_without_enough_sections():
    """Test _set_section_initial_visibility makes all sections visible exceeding min_picker."""
    # Create 10 sections; mark none as followed initially.
    sections = {}
    for i in range(10):
        sec = Section(
            receivedFeedRank=i, recommendations=[], title=f"S{i}", layout=layout_4_medium
        )
        sec.isFollowed = False
        # Initially, set all to False.
        sec.isInitiallyVisible = False
        sections[f"id{i}"] = sec
    # Call function with min_visible=3, min_picker=8.
    _set_section_initial_visibility(sections, 3, 8)
    # Since there are 10 sections, invisible count would be 10-3=7 < 8, so all become visible.
    assert all(s.isInitiallyVisible for s in sections.values())


def test_set_section_initial_visibility_with_followed():
    """Test that followed sections are always visible and minimum count is met."""
    sections = {}
    for i in range(15):
        sec = Section(
            receivedFeedRank=i, recommendations=[], title=f"S{i}", layout=layout_4_medium
        )
        # Mark sections 2 and 7 as followed.
        sec.isFollowed = i in [2, 7]
        sec.isInitiallyVisible = False
        sections[f"id{i}"] = sec
    # Randomize the order by shuffling keys.
    keys = list(sections.keys())
    shuffle(keys)
    sections = {k: sections[k] for k in keys}

    _set_section_initial_visibility(sections, 3, 8)
    visible_ids = {k for k, s in sections.items() if s.isInitiallyVisible}

    # Expected: top 3 by receivedFeedRank (id0, id1, id2) and followed section id7.
    expected_visible = {"id0", "id1", "id2", "id7"}
    assert visible_ids == expected_visible
    for s in sections.values():
        if s.isFollowed:
            assert s.isInitiallyVisible is True
