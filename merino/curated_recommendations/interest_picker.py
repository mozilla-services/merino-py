"""Module for the New Tab 'interest picker' component that allows users to follow
sections.
"""

import random
from merino.curated_recommendations.protocol import (
    InterestPickerSection,
    InterestPicker,
    SectionWithID,
)

MIN_INITIALLY_VISIBLE_SECTION_COUNT = 3  # Minimum number of sections shown by default.
MIN_INTEREST_PICKER_COUNT = 8  # Minimum number of items in the interest picker.


def create_interest_picker(sections: list[SectionWithID]) -> InterestPicker | None:
    """Process feed sections and set the interest picker.

    Returns a tuple of the updated feed and the constructed InterestPicker, or None.
    """
    sections = sorted(sections, key=lambda s: s.section.receivedFeedRank)
    _set_section_initial_visibility(
        sections, MIN_INITIALLY_VISIBLE_SECTION_COUNT, MIN_INTEREST_PICKER_COUNT
    )
    picker = _build_picker(sections, MIN_INTEREST_PICKER_COUNT)
    if picker is not None:
        _renumber_sections(sections, picker.receivedFeedRank)
    return picker


def _set_section_initial_visibility(
    sections: list[SectionWithID],
    min_visible: int,
    min_picker: int,
) -> None:
    """Mark first min_visible and followed sections as visible; else hide."""
    visible_count = 0
    for s in sections:
        if s.section.isFollowed or visible_count < min_visible:
            s.section.isInitiallyVisible = True
            visible_count += 1
        else:
            s.section.isInitiallyVisible = False
    invisible = sum(1 for s in sections if not s.section.isInitiallyVisible)
    if invisible < min_picker:
        for s in sections:
            s.section.isInitiallyVisible = True


def _get_interest_picker_rank(
    sections: list[SectionWithID],
) -> int:
    """Return a random rank for the interest picker."""
    if any(s.section.isFollowed for s in sections):
        return random.randint(2, 4)
    return random.randint(1, 3)


def _renumber_sections(
    sections: list[SectionWithID],
    picker_rank: int,
) -> None:
    """Renumber section ranks, leaving a gap for the interest picker."""
    new_rank = 0
    for s in sections:
        if new_rank == picker_rank:
            # Skip the rank for the interest picker.
            new_rank += 1
        s.section.receivedFeedRank = new_rank
        new_rank += 1


def _build_picker(
    sections: list[SectionWithID],
    min_picker_sections: int,
) -> InterestPicker | None:
    """Create an InterestPicker if enough sections are eligible, by not being visible initially."""
    picker_sections = [s for s in sections if not s.section.isInitiallyVisible]
    if len(picker_sections) < min_picker_sections:
        return None
    picker_rank = _get_interest_picker_rank(sections)
    return InterestPicker(
        receivedFeedRank=picker_rank,
        title="Follow topics to personalize your feed",
        subtitle=(
            "We will bring you personalized content, all while respecting your privacy. "
            "You'll have powerful control over what content you see and what you don't."
        ),
        sections=[InterestPickerSection(sectionId=s.ID) for s in picker_sections],
    )
