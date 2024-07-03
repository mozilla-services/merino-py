"""Unit test for map_corpus_to_serp_topic."""

from zoneinfo import ZoneInfo
import pytest
from freezegun import freeze_time

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


@pytest.mark.parametrize(
    ("surface_id", "time_to_freeze", "expected_date"),
    [
        # The publishing day rolls over at 3:00am local time. At 2:59am, content from the previous day is requested.
        ("America/New_York", "2023-08-01 7:00:00", "2023-08-01"),  # 3:00am New York
        ("America/New_York", "2023-08-01 6:59:00", "2023-07-31"),  # 2:59am New York
        ("Asia/Kolkata", "2023-08-01 7:00:00", "2023-08-01"),  # 3:00am Kolkata
        ("Asia/Kolkata", "2023-07-31 21:29:00", "2023-07-31"),  # 2:59am Kolkata
        ("Europe/London", "2023-08-01 7:00:00", "2023-08-01"),  # 3:00am London
        ("Europe/London", "2023-08-01 6:59:00", "2023-07-31"),  # 3:00am London
        ("Europe/Berlin", "2023-08-01 7:00:00", "2023-08-01"),  # 3:00am Berlin
        ("Europe/Berlin", "2023-08-01 6:59:00", "2023-07-31"),  # 2:59am Berlin
        ("Europe/Madrid", "2023-08-01 7:00:00", "2023-08-01"),  # 3:00am Madrid
        ("Europe/Madrid", "2023-08-01 6:59:00", "2023-07-31"),  # 2:59am Madrid
        ("Europe/Paris", "2023-08-01 7:00:00", "2023-08-01"),  # 3:00am Paris
        ("Europe/Paris", "2023-08-01 6:59:00", "2023-07-31"),  # 2:59am Paris
        ("Europe/Rome", "2023-08-01 7:00:00", "2023-08-01"),  # 3:00am Rome
        ("Europe/Rome", "2023-08-01 6:59:00", "2023-07-31"),  # 2:59am Rome
    ],
)
def test_get_scheduled_surface_date(surface_id, time_to_freeze, expected_date):
    """Testing the get_scheduled_surface_date method & ensuring
    the correct date is returned for a scheduled surface.
    """
    with freeze_time(time_to_freeze, tz_offset=0):
        assert (
            CorpusApiBackend.get_scheduled_surface_date(ZoneInfo("America/New_York")).strftime(
                "%Y-%m-%d"
            )
            == expected_date
        )  # noqa
