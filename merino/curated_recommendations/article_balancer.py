"""Balancers for curated recommendation articles."""

from collections import Counter, defaultdict
import math
import random

from merino.curated_recommendations.corpus_backends.protocol import Topic
from merino.curated_recommendations.article_balancer_configs import (
    ArticleBalancerConfig,
    DEFAULT_TOP_STORIES_ARTICLE_BALANCER_CONFIG,
)
from merino.curated_recommendations.protocol import CuratedRecommendation


class ArticleBalancer:
    """Balance articles by multiple criteria.

    Topic and aggregate counters use the controlled feature_counts namespace.
    Publisher counters are tracked separately because publisher names are arbitrary
    external strings and can collide with topic values or aggregate keys like "evergreen".
    """

    def __init__(self, expected_num_articles: int, config: ArticleBalancerConfig) -> None:
        """Initialize limits for target number of articles."""
        self.config = config
        self.article_list: list[CuratedRecommendation] = []
        self.feature_counts: defaultdict[str, int] = defaultdict(int)
        self.publisher_counts: Counter[str] = Counter()
        self.enforce_publisher = True
        self.num_expected = 0
        self.evergreen_topics = set(config.evergreen_topics)
        self.subtopic_checker = config.subtopic_checker
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
        self.max_per_publisher = self.config.max_per_publisher

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

    def _max_for_topic(self, topic: Topic) -> int:
        """Return the max article count for a topic, including configured topic overrides."""
        if topic == Topic.POLITICS and self.config.government_max_override is not None:
            return self.config.government_max_override
        return self.max_per_topic

    def is_blocked_rec(self, rec: CuratedRecommendation) -> bool:
        """Return true if topic is a blocked topic."""
        return rec.is_story_blocked_for_top_stories()

    def _update_stats(
        self,
        info_dict: defaultdict[str, int],
        publisher_counts: Counter[str],
        rec: CuratedRecommendation,
    ):
        """Update passed dictionary with new stats to reflect the article added.

        Publisher names are arbitrary external strings, so they are counted separately
        from topic and aggregate counters to prevent namespace collisions.
        """
        publisher_counts[rec.publisher] += 1
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

    def _does_meet_spec(
        self, info_dict: defaultdict[str, int], publisher_counts: Counter[str]
    ) -> bool:
        """Return true if passed spec meets requirements of the balancer."""
        if info_dict.get("evergreen", 0) > self.max_evergreen:
            return False
        if info_dict.get("topical", 0) > self.max_topical:
            return False
        if info_dict.get("is_subtopic", 0) > self.max_subtopic:
            return False
        if info_dict.get("blocked_topics", 0) > self.max_blocked_topics:
            return False
        if self.enforce_publisher and publisher_counts:
            _publisher, count = publisher_counts.most_common(1)[0]
            if count > self.max_per_publisher:
                return False
        for topic in Topic:
            if info_dict.get(topic.value, 0) > self._max_for_topic(topic):
                return False
        return True

    def add_story(self, rec: CuratedRecommendation) -> bool:
        """Add story if it meets requirements. Return true if story added."""
        provisional_stats = self.feature_counts.copy()
        provisional_publisher_counts = self.publisher_counts.copy()
        self._update_stats(provisional_stats, provisional_publisher_counts, rec)
        if self._does_meet_spec(provisional_stats, provisional_publisher_counts):
            self.article_list.append(rec)
            self.feature_counts = provisional_stats
            self.publisher_counts = provisional_publisher_counts
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


class TopStoriesArticleBalancer(ArticleBalancer):
    """Balancer configured for top stories."""

    def __init__(
        self,
        expected_num_articles: int,
        config: ArticleBalancerConfig | None = None,
    ) -> None:
        resolved_config = config or DEFAULT_TOP_STORIES_ARTICLE_BALANCER_CONFIG
        super().__init__(
            expected_num_articles=expected_num_articles,
            config=resolved_config,
        )
        self.enforce_publisher = random.random() < resolved_config.publisher_enforcement_likelyhood
