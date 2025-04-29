"""Module containing fixtures for curated recommendations"""

import random
import uuid
from copy import deepcopy

from pydantic import HttpUrl

from merino.curated_recommendations.protocol import Section, CuratedRecommendation, MIN_TILE_ID
from merino.curated_recommendations.corpus_backends.protocol import Topic
from merino.curated_recommendations.layouts import layout_4_medium


def generate_recommendations(
    length: int | None = None,
    item_ids: list[str] | None = None,
    time_sensitive_count: int | None = None,
) -> list[CuratedRecommendation]:
    """Create dummy recommendations for the tests below.

    @param length: Optionally, the number of items to generate. `length` or `item_ids` must be set.
    @param item_ids: Optionally, a list of item ids.
    @param time_sensitive_count: the number of items to make time-sensitive.
        If None (the default), then half of the recommendations will be time-sensitive.
    @return: A list of curated recommendations
    """
    recs = []

    if item_ids is not None:
        length = len(item_ids)
    elif length is not None:
        item_ids = [f"id:{i}" for i in range(length)]

    # Help the linter understand that length and item_ids are now set.
    assert length is not None
    assert item_ids is not None

    # If time_sensitive_count is not provided, default to half the length
    if time_sensitive_count is None:
        time_sensitive_count = length // 2

    # Randomly choose indices that will be time-sensitive
    time_sensitive_indices = random.sample(range(length), time_sensitive_count)

    for i, item_id in enumerate(item_ids):
        rec = CuratedRecommendation(
            corpusItemId=item_id,
            tileId=MIN_TILE_ID + random.randint(0, 101),
            receivedRank=i,
            scheduledCorpusItemId=str(uuid.uuid4()),
            url=HttpUrl("https://littlelarry.com/"),
            title="little larry",
            excerpt="is failing english",
            topic=random.choice(list(Topic)),
            publisher="cohens",
            isTimeSensitive=i in time_sensitive_indices,
            imageUrl=HttpUrl("https://placehold.co/600x400/"),
            iconUrl=None,
        )

        recs.append(rec)

    return recs


def generate_sections_feed(section_count: int, followed_count: int = 0) -> dict[str, Section]:
    """Create a sections dictionary populated with sections.

    Args:
        section_count (int): Number of sections to create.
        followed_count (int, optional): Number of sections to follow. Defaults to 0.

    Returns:
        dict[str, Section]: A dictionary of sections.
    """
    # Set top_stories_section first.
    sections = {
        "top_stories_section": Section(
            receivedFeedRank=0,
            recommendations=[],  # Dummy recommendations.
            title="Top Stories",
            layout=deepcopy(layout_4_medium),
        )
    }

    # Use topics to generate remaining sections.
    topics = list(Topic)[: section_count - 1]
    for i, topic in enumerate(topics):
        sections[topic.value] = Section(
            receivedFeedRank=i + 1,  # Ranks start after top_stories_section.
            recommendations=[],
            title=f"{topic.value.title()} Section",
            layout=deepcopy(layout_4_medium),
            isFollowed=(i < followed_count),
        )

    return sections
