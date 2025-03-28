"""Unit tests for utility functions in merino/curated_recommendations/corpus_backends/utils.py"""

import pytest

from merino.curated_recommendations.corpus_backends.utils import (
    map_corpus_topic_to_serp_topic,
    get_utm_source,
    update_url_utm_source,
)
from merino.curated_recommendations.corpus_backends.protocol import ScheduledSurfaceId, Topic

@pytest.mark.parametrize("topic", ["CORONAVIRUS"])
def test_map_corpus_to_serp_topic_return_none(topic):
    """Testing map_corpus_topic_to_serp_topic() method ensuring topics that don't have a mapping return None."""
    assert map_corpus_topic_to_serp_topic(topic) is None

@pytest.mark.parametrize(
    "topic, mapped_topic",
    [
        ("ENTERTAINMENT", "arts"),
        ("EDUCATION", "education"),
        ("GAMING", "hobbies"),
        ("PARENTING", "society-parenting"),
        ("BUSINESS", "business"),
        ("SCIENCE", "education-science"),
        ("PERSONAL_FINANCE", "finance"),
        ("FOOD", "food"),
        ("POLITICS", "government"),
        ("HEALTH_FITNESS", "health"),
        ("HOME", "home"),
        ("SELF_IMPROVEMENT", "society"),
        ("SPORTS", "sports"),
        ("TECHNOLOGY", "tech"),
        ("TRAVEL", "travel"),
    ],
)
def test_map_corpus_to_serp_topic(topic, mapped_topic):
    """Testing map_corpus_topic_to_serp_topic() method ensuring topics are mapped correctly."""
    result = map_corpus_topic_to_serp_topic(topic)
    assert result is not None
    assert result.value == mapped_topic

@pytest.mark.parametrize("scheduled_surface_id", ["bad-scheduled-surface-id"])
def test_get_utm_source_return_none(scheduled_surface_id):
    """Testing get_utm_source() method ensuring ids that don't have a mapping return None."""
    assert get_utm_source(scheduled_surface_id) is None

@pytest.mark.parametrize(
    ("scheduled_surface_id", "expected_utm_source"),
    [
        (ScheduledSurfaceId.NEW_TAB_EN_US, "firefox-newtab-en-us"),
        (ScheduledSurfaceId.NEW_TAB_EN_GB, "firefox-newtab-en-gb"),
        (ScheduledSurfaceId.NEW_TAB_EN_INTL, "firefox-newtab-en-intl"),
        (ScheduledSurfaceId.NEW_TAB_DE_DE, "firefox-newtab-de-de"),
        (ScheduledSurfaceId.NEW_TAB_ES_ES, "firefox-newtab-es-es"),
        (ScheduledSurfaceId.NEW_TAB_FR_FR, "firefox-newtab-fr-fr"),
        (ScheduledSurfaceId.NEW_TAB_IT_IT, "firefox-newtab-it-it"),
    ],
)
def test_get_utm_source(scheduled_surface_id, expected_utm_source):
    """Testing get_utm_source() method ensuring correct utm_source is returned for a scheduled surface id."""
    assert get_utm_source(scheduled_surface_id) == expected_utm_source

@pytest.mark.parametrize(
    ("url", "utm_source", "expected_url"),
    [
        (
            "https://getpocket.com/explore/item/example-article",
            "firefox-newtab-en-us",
            "https://getpocket.com/explore/item/example-article?utm_source=firefox-newtab-en-us",
        ),
        (
            "https://getpocket.com/explore/item/example-article?foo=bar",
            "firefox-newtab-en-gb",
            "https://getpocket.com/explore/item/example-article?foo=bar&utm_source=firefox-newtab-en-gb",
        ),
        (
            "https://getpocket.com/explore/item/example-article?utm_source=old_source",
            "firefox-newtab-en-intl",
            "https://getpocket.com/explore/item/example-article?utm_source=firefox-newtab-en-intl",
        ),
        (
            "https://getpocket.com/explore/item/example-article?utm_source=old_source&foo=bar",
            "firefox-newtab-de-de",
            "https://getpocket.com/explore/item/example-article?utm_source=firefox-newtab-de-de&foo=bar",
        ),
        (
            "https://getpocket.com/explore/item/example-article?foo=bar",
            "",
            "https://getpocket.com/explore/item/example-article?foo=bar&utm_source=",
        ),
    ],
)
def test_update_url_utm_source(url, utm_source, expected_url):
    """Testing update_url_utm_source() method ensuring URL is updated correctly."""
    assert update_url_utm_source(url, utm_source) == expected_url
