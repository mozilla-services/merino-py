"""Unit tests for Yelp Utils."""

import pytest
from freezegun import freeze_time

from merino.providers.suggest.yelp.backends.utils import get_day_of_week


@pytest.mark.parametrize(
    "label,utc_str,expected_weekday",
    [
        # 2025-09-03 is a Weds. Offset from lon -123 is ~ -8h.
        ("Wed_0005_UTC_prev_day", "2025-09-03 00:05:00", 1),  # ~Tues
        ("Wed_0600_UTC_prev_day", "2025-09-03 06:00:00", 1),  # ~Tues
        ("Wed_1200_UTC_same_day", "2025-09-03 12:00:00", 2),  # ~Wed
        ("Thurs_0600_UTC_still_wed", "2025-09-04 06:00:00", 2),  # ~Wed
    ],
)
def test_weekday_by_utc_with_lon(label, utc_str, expected_weekday):
    """Test get weekday by utc and lon."""
    with freeze_time(utc_str, tz_offset=0):
        assert get_day_of_week(-123.0) == expected_weekday
