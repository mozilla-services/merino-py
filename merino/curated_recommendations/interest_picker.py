"""Module for the New Tab 'interest picker' component that allows users to follow sections."""

import random

from merino.curated_recommendations.protocol import (
    CuratedRecommendationsFeed,
    InterestPickerSection,
    InterestPicker,
)


MIN_INITIALLY_VISIBLE_SECTION_COUNT = 3  # Minimum number of sections that are shown by default.
MIN_INTEREST_PICKER_COUNT = 8  # Minimum number of items in the interest picker.


def create_interest_picker(
    feed: CuratedRecommendationsFeed,
) -> tuple[CuratedRecommendationsFeed, InterestPicker | None]:
    """Set the interest picker on the given feed.

    This method processes the sections in the feed to determine which sections
    should be initially visible and which should be hidden. It sets `isInitiallyVisible` to True
    for the first `MIN_INITIALLY_VISIBLE_SECTION_COUNT` sections and for followed sections.
    It then checks if there are at least MIN_INTEREST_PICKER_COUNT hidden sections available.
    If there are not enough hidden sections, all sections are made visible and no interest
    picker is created. Otherwise, the hidden sections are added to the interestPicker.sections.

    Args:
        feed (CuratedRecommendationsFeed): The feed containing sections.

    Returns:
        tuple[CuratedRecommendationsFeed, InterestPicker | None]:
            A tuple where the first element is the updated feed and the second element is the
            constructed InterestPicker. If there are not enough hidden sections, the InterestPicker
            is not created and None is returned as the second element.
    """
    # Get all available sections sorted by the order in which they should be shown.
    sections = sorted(feed.get_sections(), key=lambda tup: tup[0].receivedFeedRank)

    _set_is_initially_visible(sections)

    picker_sections = [
        (section, section_id)
        for (section, section_id) in sections
        if not section.isInitiallyVisible
    ]

    # If there are not enough hidden sections, then show all sections without an interest picker.
    if len(picker_sections) < MIN_INTEREST_PICKER_COUNT:
        for section, _ in sections:
            section.isInitiallyVisible = True
        return feed, None

    interest_picker_rank = _get_interest_picker_rank(sections)
    _renumber_sections(sections, interest_picker_rank)

    interest_picker = InterestPicker(
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
    return feed, interest_picker


def _set_is_initially_visible(sections: list[tuple]) -> None:
    """Set initial visibility for sections.

    Marks the first MIN_INITIALLY_VISIBLE_SECTION_COUNT and followed sections as visible;
    others are hidden.
    """
    visible_count = 0
    for section, _ in sections:
        if section.isFollowed or visible_count < MIN_INITIALLY_VISIBLE_SECTION_COUNT:
            section.isInitiallyVisible = True
            visible_count += 1
        else:
            section.isInitiallyVisible = False


def _get_interest_picker_rank(sections: list[tuple]) -> int:
    """Return a randomized rank for the interest picker.

    If any section is followed, choose a random int in [2, 4]; otherwise, in [1, 3].
    """
    if any(section.isFollowed for section, _ in sections):
        return random.randint(2, 4)
    return random.randint(1, 3)


def _renumber_sections(sections: list[tuple], picker_rank: int) -> None:
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
