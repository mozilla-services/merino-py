"""Balancers for curated recommendation articles."""

from collections import defaultdict
from dataclasses import dataclass
import math
from typing import Callable, Collection

from merino.curated_recommendations.corpus_backends.protocol import Topic
from merino.curated_recommendations.prior_backends.engagment_rescaler import (
    ITEM_SUBTOPIC_FLAG, ITEM_EDITORIAL_SECTION_FLAG
)
from merino.curated_recommendations.protocol import CuratedRecommendation


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
    blocked_checker: Callable[[CuratedRecommendation], bool]
    min_per_topic_limit: int = 0
    min_subtopic_limit: int = 0
    blocked_topics_multiplier: int = 1


class ArticleBalancer:
    """Balance articles by multiple criteria."""

    def __init__(self, expected_num_articles: int, config: ArticleBalancerConfig) -> None:
        """Initialize limits for target number of articles."""
        self.config = config
        self.article_list: list[CuratedRecommendation] = []
        self.feature_counts: defaultdict[str, int] = defaultdict(int)
        self.num_expected = 0
        self.evergreen_topics = set(config.evergreen_topics)
        self.subtopic_checker = config.subtopic_checker
        self.blocked_checker = config.blocked_checker
        self.set_limits_for_expected_articles(expected_num_articles)

    def set_limits_for_expected_articles(self, expected_num_articles: int):
        """Update limits for expected number of articles."""
        if self.num_expected == expected_num_articles:
            return
        if self.num_expected > expected_num_articles:
            raise Exception("Limits can only be raised")
        self.num_expected = expected_num_articles
        self.max_topical = math.ceil(self.config.max_topical_ratio * expected_num_articles)
        self.max_evergreen = math.ceil(self.config.max_evergreen_ratio * expected_num_articles)
        self.max_per_topic = max(
            self.config.min_per_topic_limit,
            math.ceil(self.config.max_per_topic_ratio * expected_num_articles),
        )
        self.max_subtopic = max(
            self.config.min_subtopic_limit,
            math.ceil(self.config.max_subtopic_ratio * expected_num_articles),
        )

        # We round down here to be conservative in blocking topics in initial list, but relax
        # for extra stories or for personalization.
        self.max_blocked_topics = self.config.blocked_topics_multiplier * math.floor(
            self.config.max_blocked_topics_ratio * expected_num_articles
        )

    def _is_evergreen(self, topic: Topic | None):
        """Return true if topic is an Evergreen style topic."""
        return topic in self.evergreen_topics

    def _is_subtopic(self, rec: CuratedRecommendation) -> bool:
        """Return true if item is in a subtopic."""
        return self.subtopic_checker(rec)

    def is_blocked_rec(self, rec: CuratedRecommendation) -> bool:
        """Return true if topic is a blocked topic."""
        return self.blocked_checker(rec)

    def _update_stats(self, info_dict, rec: CuratedRecommendation):
        """Update passed dictionary with new stats to reflect the article added."""
        if (topic := rec.topic) is not None:
            info_dict[topic.value] += 1
        if self._is_evergreen(rec.topic):
            info_dict["evergreen"] += 1
        else:
            info_dict["topical"] += 1
        if self._is_subtopic(rec):
            info_dict["is_subtopic"] += 1
        if self.is_blocked_rec(rec):
            info_dict["blocked_topics"] += 1

    def _does_meet_spec(self, info_dict) -> bool:
        """Return true if passed spec meets requirements of the balancer."""
        if info_dict.get("evergreen", 0) > self.max_evergreen:
            return False
        if info_dict.get("topical", 0) > self.max_topical:
            return False
        if info_dict.get("is_subtopic", 0) > self.max_subtopic:
            return False
        if info_dict.get("blocked_topics", 0) > self.max_blocked_topics:
            return False
        for topic in Topic:
            if info_dict.get(topic.value, 0) > self.max_per_topic:
                return False
        return True

    def add_story(self, rec: CuratedRecommendation) -> bool:
        """Add story if it meets requirements. Return true if story added."""
        provisional_stats = self.feature_counts.copy()
        self._update_stats(provisional_stats, rec)
        if self._does_meet_spec(provisional_stats):
            self.article_list.append(rec)
            self.feature_counts = provisional_stats
            return True
        return False

    def add_stories(self, stories_to_add: list[CuratedRecommendation], limit: int):
        """Add additional stories from stories_to_add up to total limit
        Return tuple with discarded stories and remaining ones. Selected stories
        are added to the class.
        """
        discarded_stories = []
        num_stories_consumed = 0
        for story in stories_to_add:
            if len(self.article_list) >= limit:
                break
            if not self.add_story(story):
                discarded_stories.append(story)
            num_stories_consumed += 1
        return discarded_stories, stories_to_add[num_stories_consumed:]

    def get_stories(self) -> list[CuratedRecommendation]:
        """Get story list."""
        return self.article_list


BALANCER_MAX_TOPICAL = 0.75
BALANCER_MAX_EVERGREEN = 0.4

BALANCER_MAX_PER_TOPIC = 0.2
BALANCER_MAX_SUBTOPIC = 0.1
MAX_BLOCKED_TOPICS = 0.1  # This effectively means 0 when num articles < 10, which is typical (non personalized) case

EVERGREEN_TOPICS = {
    Topic.FOOD,
    Topic.SELF_IMPROVEMENT,
    Topic.PERSONAL_FINANCE,
    Topic.PARENTING,
    Topic.HOME,
}


def _is_top_stories_blocked(rec: CuratedRecommendation) -> bool:
    return (
        rec.topic == (Topic.SPORTS or Topic.ARTS) and rec.in_experiment(ITEM_SUBTOPIC_FLAG)
    ) or rec.topic == Topic.GAMING


class TopStoriesArticleBalancer(ArticleBalancer):
    """Balancer configured for top stories."""

    def __init__(self, expected_num_articles: int) -> None:
        super().__init__(
            expected_num_articles=expected_num_articles,
            config=ArticleBalancerConfig(
                max_topical_ratio=BALANCER_MAX_TOPICAL,
                max_evergreen_ratio=BALANCER_MAX_EVERGREEN,
                max_per_topic_ratio=BALANCER_MAX_PER_TOPIC,
                max_subtopic_ratio=BALANCER_MAX_SUBTOPIC,
                max_blocked_topics_ratio=MAX_BLOCKED_TOPICS,
                evergreen_topics=EVERGREEN_TOPICS,
                subtopic_checker=lambda rec: rec.in_experiment(
                    ITEM_SUBTOPIC_FLAG
                ),
                blocked_checker=_is_top_stories_blocked,
                min_per_topic_limit=2,
                min_subtopic_limit=1,
                blocked_topics_multiplier=3,
            ),
        )
