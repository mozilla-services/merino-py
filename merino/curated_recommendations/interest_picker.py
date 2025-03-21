"""Module for the New Tab 'interest picker' component that allows users to follow sections."""

import random
from merino.curated_recommendations.protocol import (
    InterestPickerSection,
    InterestPicker,
    Section,
)

MIN_INITIALLY_VISIBLE_SECTION_COUNT = 3  # Minimum number of sections shown by default.
MIN_INTEREST_PICKER_COUNT = 8  # Minimum number of items in the interest picker.


def create_interest_picker(sections: dict[str, Section]) -> InterestPicker | None:
    """Process feed sections and set the interest picker.

    Returns a tuple of the updated feed and the constructed InterestPicker, or None.
    """
    _set_section_initial_visibility(
        sections, MIN_INITIALLY_VISIBLE_SECTION_COUNT, MIN_INTEREST_PICKER_COUNT
    )
    picker = _build_picker(sections, MIN_INTEREST_PICKER_COUNT)
    if picker is not None:
        _renumber_sections(sections, picker.receivedFeedRank)
    return picker


def _set_section_initial_visibility(
    sections: dict[str, Section],
    min_visible: int,
    min_picker: int,
) -> None:
    """Make the first min_visible and followed sections by receivedFeedRank visible; else hide."""
    sorted_sections = sorted(sections.values(), key=lambda s: s.section.receivedFeedRank)

    visible_count = 0
    for section in sorted_sections:
        if section.isFollowed or visible_count < min_visible:
            section.isInitiallyVisible = True
            visible_count += 1
        else:
            section.isInitiallyVisible = False
    invisible_count = sum(1 for section in sorted_sections if not section.isInitiallyVisible)
    if invisible_count < min_picker:
        for section in sections.values():
            section.isInitiallyVisible = True


def _get_interest_picker_rank(
    sections: dict[str, Section],
) -> int:
    """Return a random rank for the interest picker."""
    if any(s.isFollowed for s in sections.values()):
        return random.randint(2, 4)
    return random.randint(1, 3)


def _renumber_sections(
    sections: dict[str, Section],
    picker_rank: int,
) -> None:
    """Renumber section ranks, leaving a gap for the interest picker."""
    new_rank = 0
    for s in sections.values():
        if new_rank == picker_rank:
            # Skip the rank for the interest picker.
            new_rank += 1
        s.section.receivedFeedRank = new_rank
        new_rank += 1


def _build_picker(
    sections: dict[str, Section],
    min_picker_sections: int,
) -> InterestPicker | None:
    """Create an InterestPicker if enough sections are eligible, by not being visible initially."""
    picker_sections = {key: section for key, section in sections if not section.isInitiallyVisible}
    if len(picker_sections) < min_picker_sections:
        return None
    picker_rank = _get_interest_picker_rank(sections)
    return InterestPicker(
        receivedFeedRank=picker_rank,
        title="Follow topics to fine-tune your feed",
        sections=[
            InterestPickerSection(sectionId=section_id) for section_id, _ in picker_sections
        ],
    )
