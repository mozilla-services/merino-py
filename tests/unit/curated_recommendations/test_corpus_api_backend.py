"""Unit test for map_corpus_to_serp_topic."""

import pytest

from merino.curated_recommendations.corpus_backends.corpus_api_backend import (
    map_corpus_topic_to_serp_topic,
    CorpusApiBackend,
)
from pytest import LogCaptureFixture


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


@pytest.mark.parametrize(
    "surface_id, timezone",
    [
        ("NEW_TAB_EN_US", "America/New_York"),
        ("NEW_TAB_EN_GB", "Europe/London"),
        ("NEW_TAB_EN_INTL", "Asia/Kolkata"),
        ("NEW_TAB_DE_DE", "Europe/Berlin"),
        ("NEW_TAB_ES_ES", "Europe/Madrid"),
        ("NEW_TAB_FR_FR", "Europe/Paris"),
        ("NEW_TAB_IT_IT", "Europe/Rome"),
    ],
)
def test_get_surface_timezone(surface_id, timezone, caplog: LogCaptureFixture):
    """Testing get_surface_timezone method & ensuring correct
    timezone is returned for a scheduled surface.
    """
    tz = CorpusApiBackend.get_surface_timezone(surface_id)
    assert timezone == tz.key
    # No warnings or errors were logged.
    assert not any(r for r in caplog.records if r.levelname in ("WARNING", "ERROR", "CRITICAL"))


def test_get_surface_timezone_bad_input(caplog: LogCaptureFixture):
    """Testing get_surface_timezone method & ensuring if
    a bad input is provided, UTC is returned.
    """
    # Should default to UTC if bad input
    tz = CorpusApiBackend.get_surface_timezone("foobar")
    assert tz.key == "UTC"
    # Error was logged
    error_logs = [r for r in caplog.records if r.levelname == "ERROR"]
    assert len(error_logs) == 1
    assert "Failed to get timezone for foobar, so defaulting to UTC" in error_logs[0].message
