"""Unit test for map_corpus_to_serp_topic."""

from zoneinfo import ZoneInfo
from datetime import datetime
import pytest
from freezegun import freeze_time

from merino.curated_recommendations.corpus_backends.corpus_api_backend import (
    CorpusApiBackend,
)
from pytest import LogCaptureFixture

from merino.curated_recommendations.corpus_backends.protocol import ScheduledSurfaceId


@pytest.mark.parametrize("topic", ["CORONAVIRUS"])
def test_map_corpus_to_serp_topic_return_none(topic):
    """Testing the map_to_corpus_serp_topic() method
    & ensuring topics that don't have a mapping return None.
    See for reference mapped topics: https://docs.google.com/document/d/1ICCHi1haxR-jIi_uZ3xQfPmphZm39MOmwQh0BRTXLHA/edit # noqa
    """
    assert CorpusApiBackend.map_corpus_topic_to_serp_topic(topic) is None


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
    assert CorpusApiBackend.map_corpus_topic_to_serp_topic(topic).value == mapped_topic


@pytest.mark.parametrize(
    "surface_id, timezone",
    [
        (ScheduledSurfaceId.NEW_TAB_EN_US, "America/New_York"),
        (ScheduledSurfaceId.NEW_TAB_EN_GB, "Europe/London"),
        (ScheduledSurfaceId.NEW_TAB_EN_INTL, "Asia/Kolkata"),
        (ScheduledSurfaceId.NEW_TAB_DE_DE, "Europe/Berlin"),
        (ScheduledSurfaceId.NEW_TAB_ES_ES, "Europe/Madrid"),
        (ScheduledSurfaceId.NEW_TAB_FR_FR, "Europe/Paris"),
        (ScheduledSurfaceId.NEW_TAB_IT_IT, "Europe/Rome"),
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
    tz = CorpusApiBackend.get_surface_timezone("foobar")  # type: ignore
    assert tz.key == "UTC"
    # Error was logged
    error_logs = [r for r in caplog.records if r.levelname == "ERROR"]
    assert len(error_logs) == 1
    assert "Failed to get timezone for foobar, so defaulting to UTC" in error_logs[0].message


@pytest.mark.parametrize(
    ("time_zone", "time_to_freeze", "expected_date"),
    [
        # The publishing day rolls over at 3:00am local time. At 2:59am, content from the previous day is requested.
        ("America/New_York", "2023-08-01 7:00:00", "2023-08-01"),  # 3:00am New York
        ("America/New_York", "2023-08-01 6:59:00", "2023-07-31"),  # 2:59am New York
        ("Asia/Kolkata", "2023-07-31 21:30:00", "2023-08-01"),  # 3:00am Kolkata
        ("Asia/Kolkata", "2023-07-31 21:29:00", "2023-07-31"),  # 2:59am Kolkata
        ("Europe/London", "2023-08-01 2:00:00", "2023-08-01"),  # 3:00am London
        ("Europe/London", "2023-08-01 1:59:00", "2023-07-31"),  # 3:00am London
        ("Europe/Berlin", "2023-08-01 1:00:00", "2023-08-01"),  # 3:00am Berlin
        ("Europe/Berlin", "2023-08-01 0:59:00", "2023-07-31"),  # 2:59am Berlin
        ("Europe/Madrid", "2023-08-01 1:00:00", "2023-08-01"),  # 3:00am Madrid
        ("Europe/Madrid", "2023-08-01 0:59:00", "2023-07-31"),  # 2:59am Madrid
        ("Europe/Paris", "2023-08-01 1:00:00", "2023-08-01"),  # 3:00am Paris
        ("Europe/Paris", "2023-08-01 0:59:00", "2023-07-31"),  # 2:59am Paris
        ("Europe/Rome", "2023-08-01 1:00:00", "2023-08-01"),  # 3:00am Rome
        ("Europe/Rome", "2023-08-01 0:59:00", "2023-07-31"),  # 2:59am Rome
    ],
)
def test_get_scheduled_surface_date(time_zone, time_to_freeze, expected_date):
    """Testing the get_scheduled_surface_date method & ensuring
    the correct date is returned for a scheduled surface.
    """
    with freeze_time(time_to_freeze, tz_offset=0):
        scheduled_surface_date = CorpusApiBackend.get_scheduled_surface_date(ZoneInfo(time_zone))
        assert scheduled_surface_date.strftime("%Y-%m-%d") == expected_date


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


@pytest.mark.parametrize("scheduled_surface_id", ["bad-scheduled-surface-id"])
def test_get_utm_source_return_none(scheduled_surface_id):
    """Testing the get_utm_source() method
    & ensuring ids that don't have utm_source return None.
    """
    assert CorpusApiBackend.get_utm_source(scheduled_surface_id) is None


@pytest.mark.parametrize(
    ("scheduled_surface_id", "expected_utm_source"),
    [
        (ScheduledSurfaceId.NEW_TAB_EN_US, "pocket-newtab-en-us"),
        (ScheduledSurfaceId.NEW_TAB_EN_GB, "pocket-newtab-en-gb"),
        (ScheduledSurfaceId.NEW_TAB_EN_INTL, "pocket-newtab-en-intl"),
        (ScheduledSurfaceId.NEW_TAB_DE_DE, "pocket-newtab-de-de"),
        (ScheduledSurfaceId.NEW_TAB_ES_ES, "pocket-newtab-es-es"),
        (ScheduledSurfaceId.NEW_TAB_FR_FR, "pocket-newtab-fr-fr"),
        (ScheduledSurfaceId.NEW_TAB_IT_IT, "pocket-newtab-it-it"),
    ],
)
def test_get_utm_source(scheduled_surface_id, expected_utm_source):
    """Testing the get_utm_source() method
    & ensuring correct utm_source is returned for a scheduled surface id.
    """
    assert CorpusApiBackend.get_utm_source(scheduled_surface_id) == expected_utm_source


@pytest.mark.parametrize(
    ("url", "utm_source", "expected_url"),
    [
        # add new utm_source
        (
            "https://getpocket.com/explore/item/example-article",
            "pocket-newtab-en-us",
            "https://getpocket.com/explore/item/example-article?utm_source=pocket-newtab-en-us",
        ),
        # add new utm_source with another query param present in url
        (
            "https://getpocket.com/explore/item/example-article?foo=bar",
            "pocket-newtab-en-gb",
            "https://getpocket.com/explore/item/example-article?foo=bar&utm_source=pocket-newtab-en-gb",
        ),
        # replace old utm_source with new one
        (
            "https://getpocket.com/explore/item/example-article?utm_source=old_source",
            "pocket-newtab-en-intl",
            "https://getpocket.com/explore/item/example-article?utm_source=pocket-newtab-en-intl",
        ),
        # replace old utm_source with new one & when another query param present in url
        (
            "https://getpocket.com/explore/item/example-article?utm_source=old_source&foo=bar",
            "pocket-newtab-de-de",
            "https://getpocket.com/explore/item/example-article?utm_source=pocket-newtab-de-de&foo=bar",
        ),
        # pass empty utm_source (when no mapping is found)
        (
            "https://getpocket.com/explore/item/example-article?foo=bar",
            "",
            "https://getpocket.com/explore/item/example-article?foo=bar&utm_source=",
        ),
    ],
)
def test_update_url_utm_source(url, utm_source, expected_url):
    """Testing the update_url_utm_source() method
    & ensuring url is updated correctly.
    """
    assert CorpusApiBackend.update_url_utm_source(url, utm_source) == expected_url
