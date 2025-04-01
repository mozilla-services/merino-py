"""Unit tests for ScheduledCorpusBackend in merino/curated_recommendations/corpus_backends/scheduled_corpus_backend.py"""

from datetime import datetime
from zoneinfo import ZoneInfo
import pytest
from freezegun import freeze_time
from merino.curated_recommendations.corpus_backends.scheduled_corpus_backend import (
    ScheduledCorpusBackend,
)
from merino.curated_recommendations.corpus_backends.protocol import ScheduledSurfaceId
from pytest import LogCaptureFixture


@pytest.mark.parametrize(
    "surface_id, timezone_str",
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
def test_get_surface_timezone(surface_id, timezone_str, caplog: LogCaptureFixture):
    """Testing get_surface_timezone method ensuring correct timezone is returned for a scheduled surface."""
    tz = ScheduledCorpusBackend.get_surface_timezone(surface_id)
    assert tz.key == timezone_str
    # No warnings or errors were logged.
    assert not any(r for r in caplog.records if r.levelname in ("WARNING", "ERROR", "CRITICAL"))


@pytest.mark.parametrize(
    "time_zone, time_to_freeze, expected_date",
    [
        ("America/New_York", "2023-08-01 7:00:00", "2023-08-01"),
        ("America/New_York", "2023-08-01 6:59:00", "2023-07-31"),
        ("Asia/Kolkata", "2023-07-31 21:30:00", "2023-08-01"),
        ("Asia/Kolkata", "2023-07-31 21:29:00", "2023-07-31"),
        ("Europe/London", "2023-08-01 2:00:00", "2023-08-01"),
        ("Europe/London", "2023-08-01 1:59:00", "2023-07-31"),
        ("Europe/Berlin", "2023-08-01 1:00:00", "2023-08-01"),
        ("Europe/Berlin", "2023-08-01 0:59:00", "2023-07-31"),
        ("Europe/Madrid", "2023-08-01 1:00:00", "2023-08-01"),
        ("Europe/Madrid", "2023-08-01 0:59:00", "2023-07-31"),
        ("Europe/Paris", "2023-08-01 1:00:00", "2023-08-01"),
        ("Europe/Paris", "2023-08-01 0:59:00", "2023-07-31"),
        ("Europe/Rome", "2023-08-01 1:00:00", "2023-08-01"),
        ("Europe/Rome", "2023-08-01 0:59:00", "2023-07-31"),
    ],
)
def test_get_scheduled_surface_date(time_zone, time_to_freeze, expected_date):
    """Testing get_scheduled_surface_date method ensuring the correct date is returned for a scheduled surface."""
    with freeze_time(time_to_freeze, tz_offset=0):
        scheduled_surface_date = ScheduledCorpusBackend.get_scheduled_surface_date(
            ZoneInfo(time_zone)
        )
        assert scheduled_surface_date.strftime("%Y-%m-%d") == expected_date


@freeze_time("2012-01-14 00:00:00", tz_offset=0)
def test_get_expiration_time():
    """Testing the generation of expiration times."""
    times = [ScheduledCorpusBackend.get_expiration_time() for _ in range(10)]
    min_expected_time = datetime(2012, 1, 14, 0, 0, 50)
    max_expected_time = datetime(2012, 1, 14, 0, 1, 10)
    assert all(min_expected_time <= t <= max_expected_time for t in times)
    assert len(set(times)) == len(times)
