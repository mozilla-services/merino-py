"""Configuration constants for curated recommendation article balancers."""

from collections.abc import Callable, Collection
from dataclasses import dataclass, replace

from merino.curated_recommendations.corpus_backends.protocol import SurfaceId, Topic
from merino.curated_recommendations.protocol import ITEM_SUBTOPIC_FLAG, CuratedRecommendation


@dataclass(frozen=True)
class ArticleBalancerConfig:
    """Configuration for an ArticleBalancer instance."""

    max_topical_ratio: float
    max_evergreen_ratio: float
    max_per_topic_ratio: float
    max_subtopic_ratio: float
    max_blocked_topics_ratio: float
    evergreen_topics: Collection[Topic]
    subtopic_checker: Callable[[CuratedRecommendation], bool]
    min_per_topic_limit: int = 0
    min_subtopic_limit: int = 0
    blocked_topics_multiplier: int = 1


BALANCER_MAX_TOPICAL = 0.75
BALANCER_MAX_EVERGREEN = 0.4

BALANCER_MAX_PER_TOPIC = 0.2
BALANCER_MAX_SUBTOPIC = 0.1
MAX_BLOCKED_TOPICS = 0.0  # 0.1 effectively means 0 when num articles < 10.

EVERGREEN_TOPICS = frozenset(
    {
        Topic.FOOD,
        Topic.SELF_IMPROVEMENT,
        Topic.PERSONAL_FINANCE,
        Topic.PARENTING,
        Topic.HOME,
    }
)

DEFAULT_TOP_STORIES_ARTICLE_BALANCER_CONFIG = ArticleBalancerConfig(
    max_topical_ratio=BALANCER_MAX_TOPICAL,
    max_evergreen_ratio=BALANCER_MAX_EVERGREEN,
    max_per_topic_ratio=BALANCER_MAX_PER_TOPIC,
    max_subtopic_ratio=BALANCER_MAX_SUBTOPIC,
    max_blocked_topics_ratio=MAX_BLOCKED_TOPICS,
    evergreen_topics=EVERGREEN_TOPICS,
    subtopic_checker=lambda rec: rec.in_experiment(ITEM_SUBTOPIC_FLAG),
    min_per_topic_limit=2,
    min_subtopic_limit=1,
    blocked_topics_multiplier=3,
)

# Surface IDs are the locale-normalized key Merino uses for corpus content.
TOP_STORIES_BALANCER_CONFIG_BY_SURFACE: dict[SurfaceId, ArticleBalancerConfig] = {
    SurfaceId.NEW_TAB_DE_DE: replace(
        DEFAULT_TOP_STORIES_ARTICLE_BALANCER_CONFIG,
        min_per_topic_limit=3,
    ),
}


def get_top_stories_article_balancer_config(surface_id: SurfaceId) -> ArticleBalancerConfig:
    """Return the Top Stories/Popular Today balancer config for a surface."""
    # Future experiment-specific overrides should be selected here once the experiment id
    # is threaded into this function.
    return TOP_STORIES_BALANCER_CONFIG_BY_SURFACE.get(
        surface_id, DEFAULT_TOP_STORIES_ARTICLE_BALANCER_CONFIG
    )
