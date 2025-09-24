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
    def from_str(cls, state: str):
        return cls(state.lower())

    def is_final(self) -> bool:
        return self in [GameStatus.Final, GameStatus.F_OT]

    def is_scheduled(self) -> bool:
        return self in [GameStatus.Scheduled, GameStatus.Delayed, GameStatus.Postponed]

    def is_in_progress(self) -> bool:
        return self in [GameStatus.InProgress, GameStatus.Suspended]

    def as_str(self) -> str:
        """As a somewhat prettier formatted string
        NOTE: For int'l this should probably return a lookup code.
        """

        match self:
            case GameStatus.InProgress:
                return "In Progress "
            case GameStatus.F_OT:
                return "Final - Over Time"
            case _:
                return self.name.capitalize()
