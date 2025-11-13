"""Sport info provider"""

import logging
from abc import abstractmethod
from datetime import datetime, timedelta, timezone
import os
from typing import Final


LOGGING_TAG: Final[str] = "⚾"
DEFAULT_LOGGING_LEVEL = "DEBUG"
UPDATE_PERIOD_SECS = 60 * 60 * 4  # Four hours

# The URL field in the returned suggestion is ignored. Use
# a generic space-holder for this value for this provider.
IGNORED_SUGGESTION_URL: Final[str] = "https://merino.services.mozilla.com"
BASE_SUGGEST_SCORE: float = 0.5
PROVIDER_ID: Final[str] = "sports"

DEFAULT_TRIGGER_WORDS = [
    "vs",
    "game",
    "match",
    "fixtures",
    "schedule",
    "play",
    "upcoming",
    "score",
    "result",
    "final",
    "live",
    "today",
    "v",
]


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
