"""Module containing fixtures for curated recommendations"""

from merino.curated_recommendations.protocol import Section
from merino.curated_recommendations.corpus_backends.protocol import Topic
from merino.curated_recommendations.layouts import layout_4_medium
from merino.curated_recommendations.protocol import CuratedRecommendationsFeed


def generate_sections_feed(
    section_count: int, followed_count: int = 0
) -> CuratedRecommendationsFeed:
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
