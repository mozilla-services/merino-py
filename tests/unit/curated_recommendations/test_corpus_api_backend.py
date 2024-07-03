"""Unit test for map_corpus_to_serp_topic."""

from datetime import datetime

import pytest
from freezegun import freeze_time

from merino.curated_recommendations.corpus_backends.corpus_api_backend import (
    map_corpus_topic_to_serp_topic,
    CorpusApiBackend,
)


@pytest.mark.parametrize("topic", ["PARENTING", "CORONAVIRUS", "GAMING", "CAREER", "EDUCATION"])
def test_map_corpus_to_serp_topic_return_none(topic):
    """Testing the map_to_corpus_serp_topic() method
    & ensuring topics that don't have a mapping return None.
    See for reference mapped topics: https://docs.google.com/document/d/1ICCHi1haxR-jIi_uZ3xQfPmphZm39MOmwQh0BRTXLHA/edit # noqa
    """
    assert map_corpus_topic_to_serp_topic(topic) is None


@pytest.mark.parametrize(
    "topic, mapped_topic",
    [
        ("ENTERTAINMENT", "arts"),
        ("BUSINESS", "business"),
        ("SCIENCE", "education"),
        ("PERSONAL_FINANCE", "finance"),
        ("FOOD", "food"),
        ("POLITICS", "government"),
        ("HEALTH_FITNESS", "health"),
        ("SELF_IMPROVEMENT", "society"),
        ("SPORTS", "sports"),
        ("TECHNOLOGY", "tech"),
        ("TRAVEL", "travel"),
    ],
)
def test_map_corpus_to_serp_topic(topic, mapped_topic):
    """Testing the map_to_corpus_serp_topic() method & ensuring topics are mapped correctly.
    See for reference mapped topics:
    https://docs.google.com/document/d/1ICCHi1haxR-jIi_uZ3xQfPmphZm39MOmwQh0BRTXLHA/edit
    """
    assert map_corpus_topic_to_serp_topic(topic) == mapped_topic


@freeze_time("2012-01-14 00:00:00", tz_offset=0)
def test_get_expiration_time():
    """Testing the generation of expiration times"""
    times = [CorpusApiBackend.get_expiration_time() for _ in range(10)]

    # Assert that times are within the expected range
    min_expected_time = datetime(2012, 1, 14, 0, 0, 50)
    max_expected_time = datetime(2012, 1, 14, 0, 1, 10)
    assert all(min_expected_time <= t <= max_expected_time for t in times)

    # Assert that all returned times are different
    assert len(set(times)) == len(times)
