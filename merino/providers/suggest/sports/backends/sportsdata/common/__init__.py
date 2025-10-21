"""Common data definitions for SportsData.io information"""

from enum import StrEnum


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
    Canceled = "canceled"
    Final = "final"
    F_OT = "f/ot"  # Equivalent to "final"
    F_SO = "f/so"  # Equivalent to "final"
    Forfeit = "forfeit"
    NotNecessary = "notnecessary"
    Unknown = "unknown"
    # other states can be ignored?

    @classmethod
    def parse(cls, state: str) -> "GameStatus":
        """Instantiate from a string"""
        try:
            return cls(state.lower())
        except ValueError:
            # Handle our custom strings
            match state.lower():
                case "in progress":
                    return GameStatus.InProgress
                case "final - over time":
                    return GameStatus.F_OT
                case "final - shoot out":
                    return GameStatus.F_SO
                case "not necessary":
                    return GameStatus.NotNecessary
                case _:
                    return GameStatus.Unknown

    def is_final(self) -> bool:
        """Return if this is the final result"""
        return self in [GameStatus.Final, GameStatus.F_OT, GameStatus.F_SO]

    def is_scheduled(self) -> bool:
        """Return if the game is still pending"""
        return self in [GameStatus.Scheduled, GameStatus.Delayed, GameStatus.Postponed]

    def is_in_progress(self) -> bool:
        """Return if the game is currently in progress in some form"""
        return self in [GameStatus.InProgress, GameStatus.Suspended]

    def status_type(self) -> "GameStatus":
        """Minimal type of status
        0 = Unknown
        1 = Final
        2 = Current
        3 = Scheduled
        """
        if self.is_final():
            return GameStatus.Final
        if self.is_in_progress():
            return GameStatus.InProgress
        if self.is_scheduled():
            return GameStatus.Scheduled
        return GameStatus.Unknown

    def as_ui_status(self) -> str:
        """Return the UI preferred status label"""
        match self.status_type():
            case GameStatus.Final:
                return "past"
            case GameStatus.InProgress:
                return "live"
            case GameStatus.Scheduled:
                return "scheduled"
            case _:
                return "unknown"

    def as_str(self) -> str:
        """Return self as a somewhat prettier formatted string
        NOTE: For int'l this should probably return a lookup code.
        """
        match self:
            case GameStatus.InProgress:
                return "In Progress"
            case GameStatus.F_OT:
                return "Final - Over Time"
            case GameStatus.F_SO:
                return "Final - Shoot Out"
            case GameStatus.NotNecessary:
                return "Not Necessary"
            case GameStatus.Unknown:
                return ""
            case _:
                return self.name.capitalize()
