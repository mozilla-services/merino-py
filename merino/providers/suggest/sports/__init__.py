"""Sport info provider"""

from abc import abstractmethod
from datetime import datetime, timedelta, timezone
from typing import Final

from merino.configs import settings

LOGGING_TAG: Final[str] = "⚾"
DEFAULT_LOGGING_LEVEL = "DEBUG"
# How frequently do we expect the "update" job to run?
# This will impact some things like the `quick-update` function
UPDATE_PERIOD_SECS = 60 * 5  # Five minutes

# The URL field in the returned suggestion is ignored. Use
# a generic space-holder for this value for this provider.
IGNORED_SUGGESTION_URL: Final[str] = "https://merino.services.mozilla.com"
BASE_SUGGEST_SCORE: float = 0.5
PROVIDER_ID: Final[str] = settings.providers.sports.type

DEFAULT_INTENT_WORDS = [
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


def utc_time_from_now(delta: timedelta) -> datetime:
    """Return the timestamp of the period from now"""
    return datetime.now(tz=timezone.utc) + delta
