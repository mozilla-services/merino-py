"""Module for the New Tab 'interest picker' component that allows users to follow sections."""

import random

from merino.curated_recommendations.protocol import (
    CuratedRecommendationsFeed,
    InterestPickerSection,
    InterestPicker,
    Section,
    SectionWithID
)


MIN_INITIALLY_VISIBLE_SECTION_COUNT = 3  # Minimum number of sections that are shown by default.
MIN_INTEREST_PICKER_COUNT = 8  # Minimum number of items in the interest picker.


def main(
    feed: CuratedRecommendationsFeed,
) -> tuple[list[SectionWithID], InterestPicker | None]:
    # Get all available sections sorted by the order in which they should be shown.
    sections = sort_sections(feed.get_sections())

    # set initial visibility for sections
    sections = set_section_initial_visibility(sections, MIN_INITIALLY_VISIBLE_SECTION_COUNT, MIN_INTEREST_PICKER_COUNT)

    # see if we can create an interest picker based on section visibility
    interest_picker = create_interest_picker(sections, MIN_INTEREST_PICKER_COUNT)

    # if we were able to create an interest picker, re-order the sections
    if interest_picker:
        sections = _renumber_sections(sections, interest_picker.receivedFeedRank)

    return sections, interest_picker


def sort_sections(sections: list[SectionWithID]) -> list[SectionWithID]:
    return sorted(sections, key=lambda tup: tup.section.receivedFeedRank)

def set_section_initial_visibility(
    sections: list[SectionWithID],
    min_initially_visible_count: int,
    min_interest_picker_count: int
) -> list[tuple[Section, str]]:
    visible_count = 0

    # make sure all followed sections are initially visible
    # and make sure we have at least min_initially_visible_count sections initially visible
    for section, _ in sections:
        if section.isFollowed or visible_count < min_initially_visible_count:
            section.isInitiallyVisible = True
            visible_count += 1
        else:
            section.isInitiallyVisible = False

    # now see if we have enough non-initially visible sections to even display the interest picker
    invisible_count = 0

    for section, _ in sections:
        if not section.isInitiallyVisible:
            invisible_count += 1

    # if we don't have enough invisible sections to satisfy making an interest picker, then
    # set all sections to initially visible
    if invisible_count < min_interest_picker_count:
        for section, _ in sections:
            section.isInitiallyVisible = True

    return sections

def create_interest_picker(
    sections: list[SectionWithID],
    min_interest_picker_count: int       
) -> InterestPicker | None:
    picker_sections = [
        (section, section_id)
        for (section, section_id) in sections
        if not section.isInitiallyVisible
    ]

    if len(picker_sections) >= min_interest_picker_count:
        interest_picker_rank = _get_interest_picker_rank(sections)

        return InterestPicker(
            receivedFeedRank=interest_picker_rank,
            title="Follow topics to personalize your feed",
            subtitle=(
                "We will bring you personalized content, all while respecting your privacy. "
                "You'll have powerful control over what content you see and what you don't."
            ),
            sections=[
                InterestPickerSection(sectionId=section_id) for _, section_id in picker_sections
            ],
        )
    else:
        return None
    
def _renumber_sections(sections: list[SectionWithID], picker_rank: int) -> list[SectionWithID]:
    """Renumber section ranks, leaving a gap for the interest picker.

    Increments ranks by 1 so that the section after the picker has rank picker_rank+1.
    """
    new_rank = 0
    for section, _ in sections:
        if new_rank == picker_rank:
            # Skip the rank for the interest picker.
            new_rank += 1
        section.receivedFeedRank = new_rank
        new_rank += 1

    return sections


def _get_interest_picker_rank(sections: list[SectionWithID]) -> int:
    """Return a randomized rank for the interest picker.

    If any section is followed, choose a random int in [2, 4]; otherwise, in [1, 3].
    """
    if any(section.isFollowed for section, _ in sections):
        return random.randint(2, 4)
    return random.randint(1, 3)