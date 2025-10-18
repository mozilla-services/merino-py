"""Sport info provider"""

import logging
from abc import abstractmethod
from datetime import datetime, timedelta, timezone
import os
from typing import Final


LOGGING_TAG: Final[str] = "⚾"
DEFAULT_LOGGING_LEVEL = "DEBUG"
UPDATE_PERIOD_SECS = 60 * 60 * 4  # Four hours

# Retain team information for 2 years
# DeltaTime only understands weeks, so use 52*2
TEAM_TTL_WEEKS = 52 * 2
EVENT_TTL_WEEKS = 2

# INTERVAL PERIODS
ONE_MINUTE = 60
FIVE_MINUTES = ONE_MINUTE * 5  # for Standings
ONE_HOUR = ONE_MINUTE * 60
FOUR_HOURS = ONE_HOUR * 4  # For Team Profiles


def utc_time_from_now(delta: timedelta) -> int:
    """Return the timestamp of the period from now"""
    return int((datetime.now(tz=timezone.utc) + delta).timestamp())


def init_logs(level: str | None = None) -> logging.Logger:
    """Initialize logging based on `PYTHON_LOG` environ)"""
    # be very verbose because `mypy` does not understand
    # `None or x.get(label, CONST_STR_VALUE)` does not produce a None value.
    if not level:
        level = os.environ.get("PYTHON_LOG", DEFAULT_LOGGING_LEVEL)
    level = getattr(logging, level.upper())
    logging.basicConfig(level=level)
    return logging.getLogger(__name__)
