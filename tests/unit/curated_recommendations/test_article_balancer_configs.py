"""Tests for article balancer configuration constants."""

from dataclasses import replace

from merino.curated_recommendations.article_balancer import TopStoriesArticleBalancer
from merino.curated_recommendations.article_balancer_configs import (
    DEFAULT_TOP_STORIES_ARTICLE_BALANCER_CONFIG,
    TOP_STORIES_BALANCER_CONFIG_BY_SURFACE,
    get_top_stories_article_balancer_config,
)
from merino.curated_recommendations.corpus_backends.protocol import SurfaceId, Topic
from tests.unit.curated_recommendations.fixtures import generate_recommendations


def test_get_top_stories_article_balancer_config_returns_surface_config():
    """Return the configured balancer config for a section surface."""
    config = get_top_stories_article_balancer_config(SurfaceId.NEW_TAB_DE_DE)

    assert config is TOP_STORIES_BALANCER_CONFIG_BY_SURFACE[SurfaceId.NEW_TAB_DE_DE]
    assert (
        config.max_per_topic_ratio
        == DEFAULT_TOP_STORIES_ARTICLE_BALANCER_CONFIG.max_per_topic_ratio
    )
    assert config.min_per_topic_limit == 2
    assert config.government_max_override == 3
    assert config.max_per_publisher == 1
    assert config.publisher_enforcement_likelyhood == 0.85


def test_get_top_stories_article_balancer_config_falls_back_to_default():
    """Return the default config for surfaces without an explicit override."""
    config = get_top_stories_article_balancer_config(SurfaceId.NEW_TAB_ES_ES)

    assert config is DEFAULT_TOP_STORIES_ARTICLE_BALANCER_CONFIG
    assert config.max_per_publisher == 100
    assert config.publisher_enforcement_likelyhood == 0.0


def test_top_stories_article_balancer_accepts_custom_config():
    """A surface-specific config can raise the per-topic floor."""
    config = replace(DEFAULT_TOP_STORIES_ARTICLE_BALANCER_CONFIG, min_per_topic_limit=3)
    balancer = TopStoriesArticleBalancer(expected_num_articles=9, config=config)
    stories = generate_recommendations(
        item_ids=["a", "b", "c"],
        topics=[Topic.POLITICS, Topic.POLITICS, Topic.POLITICS],
        time_sensitive_count=0,
    )

    assert [balancer.add_story(story) for story in stories] == [True, True, True]
    assert [story.corpusItemId for story in balancer.get_stories()] == ["a", "b", "c"]


def test_top_stories_article_balancer_accepts_government_override():
    """A config can give government stories a topic limit separate from the default."""
    config = replace(DEFAULT_TOP_STORIES_ARTICLE_BALANCER_CONFIG, government_max_override=3)
    balancer = TopStoriesArticleBalancer(expected_num_articles=10, config=config)
    stories = generate_recommendations(
        item_ids=["a", "b", "c", "d"],
        topics=[Topic.POLITICS, Topic.POLITICS, Topic.POLITICS, Topic.POLITICS],
        time_sensitive_count=0,
    )

    assert [balancer.add_story(story) for story in stories] == [True, True, True, False]
    assert [story.corpusItemId for story in balancer.get_stories()] == ["a", "b", "c"]


def test_de_config_uses_default_topic_ratio_and_government_override():
    """The DE surface config uses the normal ratio but allows three government stories."""
    config = get_top_stories_article_balancer_config(SurfaceId.NEW_TAB_DE_DE)
    balancer = TopStoriesArticleBalancer(expected_num_articles=9, config=config)
    stories = generate_recommendations(
        item_ids=["a", "b", "c", "d", "e", "f", "g"],
        topics=[
            Topic.BUSINESS,
            Topic.BUSINESS,
            Topic.BUSINESS,
            Topic.POLITICS,
            Topic.POLITICS,
            Topic.POLITICS,
            Topic.POLITICS,
        ],
        time_sensitive_count=0,
    )

    assert [balancer.add_story(story) for story in stories] == [
        True,
        True,
        False,
        True,
        True,
        True,
        False,
    ]
    assert [story.corpusItemId for story in balancer.get_stories()] == ["a", "b", "d", "e", "f"]
