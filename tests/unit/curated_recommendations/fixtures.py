"""Module containing fixtures for curated recommendations"""

import random
import uuid
from copy import deepcopy

from pydantic import HttpUrl

from merino.curated_recommendations.protocol import Section, CuratedRecommendation, MIN_TILE_ID
from merino.curated_recommendations.corpus_backends.protocol import Topic
from merino.curated_recommendations.layouts import layout_4_medium


def generate_recommendations(item_ids: list[str]) -> list[CuratedRecommendation]:
    """Create dummy recommendations."""
    recs = []
    for item_id in item_ids:
        rec = CuratedRecommendation(
            corpusItemId=str(uuid.uuid4()),
            tileId=MIN_TILE_ID + random.randint(0, 101),
            receivedRank=random.randint(0, 101),
            scheduledCorpusItemId=item_id,
            url=HttpUrl("https://littlelarry.com/"),
            title="little larry",
            excerpt="is failing english",
            topic=random.choice(list(Topic)),
            publisher="cohens",
            isTimeSensitive=False,
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
