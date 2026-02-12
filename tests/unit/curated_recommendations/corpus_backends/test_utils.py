"""Unit tests for utility functions in merino/curated_recommendations/corpus_backends/utils.py"""

from unittest.mock import MagicMock

import pytest
from pydantic import HttpUrl

from merino.curated_recommendations.corpus_backends.protocol import SurfaceId
from merino.curated_recommendations.corpus_backends.utils import build_corpus_item
from merino.curated_recommendations.corpus_backends.utils import (
    map_corpus_topic_to_serp_topic,
    get_utm_source,
    update_url_utm_source,
)
from merino.providers.manifest import Provider


@pytest.mark.parametrize("topic", ["CORONAVIRUS"])
def test_map_corpus_to_serp_topic_return_none(topic):
    """Test that topics without a mapping return None."""
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
        (SurfaceId.NEW_TAB_EN_US, "firefox-newtab-en-us"),
        (SurfaceId.NEW_TAB_EN_GB, "firefox-newtab-en-gb"),
        (SurfaceId.NEW_TAB_EN_CA, "firefox-newtab-en-ca"),
        (SurfaceId.NEW_TAB_EN_INTL, "firefox-newtab-en-intl"),
        (SurfaceId.NEW_TAB_DE_DE, "firefox-newtab-de-de"),
        (SurfaceId.NEW_TAB_ES_ES, "firefox-newtab-es-es"),
        (SurfaceId.NEW_TAB_FR_FR, "firefox-newtab-fr-fr"),
        (SurfaceId.NEW_TAB_IT_IT, "firefox-newtab-it-it"),
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


class TestBuildCorpusItem:
    """Tests covering build_corpus_item"""

    sample_item = {
        "id": "item1",
        "title": "Test Title",
        "excerpt": "Test excerpt",
        "topic": "BUSINESS",
        "publisher": "TestPublisher",
        "isTimeSensitive": False,
        "imageUrl": "https://example.com/image.png",
        "url": "https://example.com/page",
    }

    @staticmethod
    def get_mock_icon_url(url):
        """Generate a dummy icon image url"""
        return f"https://dummy.icon/{url.replace('https://', '')}"

    @pytest.fixture
    def mock_manifest_provider(self):
        """Provide a get_icon_url method that returns a valid URL.
        The method returns a URL in the format:
            https://dummy.icon/<original_url_without_https://>
        """
        dummy = MagicMock(spec=Provider)
        dummy.get_icon_url.side_effect = TestBuildCorpusItem.get_mock_icon_url
        return dummy

    def test_build_corpus_item_with_utm(self, mock_manifest_provider):
        """When a valid utm_source is provided the URL should be updated and the manifest provider
        should be called with the updated URL.
        """
        utm_source = "firefox-newtab-en-us"
        corpus_item = self.sample_item.copy()
        result = build_corpus_item(corpus_item, mock_manifest_provider, utm_source)

        expected_url = update_url_utm_source(corpus_item["url"], utm_source)
        assert result.url == HttpUrl(expected_url)
        assert result.iconUrl == HttpUrl(self.get_mock_icon_url(expected_url))
        mapped_topic = map_corpus_topic_to_serp_topic(corpus_item["topic"])
        assert mapped_topic is not None
        assert result.topic == mapped_topic

    def test_build_corpus_item_without_utm(self, mock_manifest_provider):
        """When utm_source is None the URL should not be updated."""
        utm_source = None
        corpus_item = self.sample_item.copy()
        result = build_corpus_item(corpus_item, mock_manifest_provider, utm_source)

        expected_url = corpus_item["url"]
        assert result.url == HttpUrl(expected_url)
        assert result.iconUrl == HttpUrl(self.get_mock_icon_url(expected_url))

    def test_build_corpus_item_unmapped_topic(self, mock_manifest_provider):
        """If the corpus item's topic does not have a corresponding mapping,
        the returned CorpusItem should have a topic of None.
        """
        corpus_item = self.sample_item.copy()
        corpus_item["topic"] = "UNKNOWN"  # Unmapped topic.
        result = build_corpus_item(corpus_item, mock_manifest_provider, utm_source=None)

        expected_url = corpus_item["url"]
        assert result.topic is None
        assert result.url == HttpUrl(expected_url)
        assert result.iconUrl == HttpUrl(self.get_mock_icon_url(expected_url))

    def test_build_corpus_item_empty_utm(self, mock_manifest_provider):
        """If an empty string is provided as utm_source, the URL should be updated accordingly."""
        utm_source = ""
        corpus_item = self.sample_item.copy()
        result = build_corpus_item(corpus_item, mock_manifest_provider, utm_source)

        expected_url = update_url_utm_source(corpus_item["url"], utm_source)
        assert result.url == HttpUrl(expected_url)
        assert result.iconUrl == HttpUrl(self.get_mock_icon_url(expected_url))
