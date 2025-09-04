"""Module for utils for Yelp."""

from datetime import datetime, timezone, timedelta


def get_day_of_week(long: float) -> int:
    """Retrieve day of week using longitude."""
    offset = long / 15.0
    approx_local_time = datetime.now(timezone.utc) + timedelta(hours=offset)
    return approx_local_time.weekday()
