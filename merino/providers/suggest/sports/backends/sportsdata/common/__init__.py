"""Common data fetch functions for SportsData.io information"""

import logging
import os
from datetime import datetime, timedelta, timezone

from enum import StrEnum
from typing import Any


# Enums
class GameStatus(StrEnum):
    """Enum of the normalized, valid, trackable game states.

    See https://support.sportsdata.io/hc/en-us/articles/14287629964567-Process-Guide-Game-Status
    """

    Scheduled = "scheduled"
    Delayed = "delayed"  # equivalent to "scheduled"
    Postponed = "postponed"  # equivalent to "scheduled"
    InProgress = "inprogress"
    Suspended = "suspended"  # equivalent to "inprogress"
    Cancelled = "cancelled"
    Final = "final"
    F_OT = "f/ot"  # Equivalent to "final"
    # other states can be ignored?

    @classmethod
    def is_final(cls, state: str) -> bool:
        return state.lower() in [cls.Final, cls.F_OT]

    @classmethod
    def is_scheduled(cls, state: str) -> bool:
        return state.lower() in [cls.Scheduled, cls.Delayed, cls.Postponed]

    @classmethod
    def is_in_progress(cls, state: str) -> bool:
        return state.lower() in [cls.InProgress, cls.Suspended]

    def as_str(self) -> str:
        """As a somewhat prettier formatted string
        NOTE: For int'l this should probably return a lookup code.
        """

        match self:
            case GameStatus.Scheduled:
                return "scheduled"
            case GameStatus.Delayed:
                return "delayed"
            case GameStatus.Postponed:
                return "postponed"
            case GameStatus.InProgress:
                return "in progress"
            case GameStatus.Suspended:
                return "suspended"
            case GameStatus.Cancelled:
                return "cancelled"
            case GameStatus.Final:
                return "final"
            case GameStatus.F_OT:
                return "Final - Over Time"
