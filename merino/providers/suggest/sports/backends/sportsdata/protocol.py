"""Protocol for sport suggestion backends."""

from typing import Any
from datetime import datetime, timezone

from merino.providers.suggest.base import BaseModel


class SportTeamDetails(BaseModel):
    """Data about the specific Sport team."""

    key: str  # Sport unique abbreviated identifier (e.g. "SFG", "DAL", etc)
    name: str  # Full name of the team
    colors: list[str]  # list of hex colors from primary to quaternary
    score: int | None  # Current score (if available)


def build_query(event: dict[str, Any]) -> str:
    """Build the search query from the event information"""
    date = datetime.fromtimestamp(event["date"]).strftime("%d %b %Y")
    return f"{event.get("sport")} {event.get("away_team",{}).get("name","")} at {event.get("home_team", {}).get("name", "")} {date}"


class SportEventDetails(BaseModel):
    """Data about the specific Sport event."""

    sport: str  # Sport Name ("NFL", "NHL", "NBA", etc.)
    query: str  # Click search query for this event.
    date: str  # UTC timestamp for the game
    home_team: SportTeamDetails  # Home Team details
    away_team: SportTeamDetails  # Away Team details
    event_status: str  # Long form event status. ("Scheduled", "Final - Overtime", etc.)
    status: str  # UI display status ("past", "live", "scheduled")

    @classmethod
    def from_event_dict(cls, event: dict[str, Any]):
        """Create an instance of SportEventDetails from a provided Event dictionary

        This presumes that it's reading a json loaded sport Event that was returned by elastic search.
        """
        status = event["event_status"]
        return cls(
            sport=event["sport"],
            query=build_query(event),
            date=datetime.fromtimestamp(event["date"], tz=timezone.utc).isoformat(),
            home_team=SportTeamDetails(
                key=event.get("home_team", {}).get("key"),
                name=event.get("home_team", {}).get("name"),
                colors=event.get("home_team", {}).get("colors"),
                score=event.get("home_score"),
            ),
            away_team=SportTeamDetails(
                key=event.get("away_team", {}).get("key"),
                name=event.get("away_team", {}).get("name"),
                colors=event.get("away_team", {}).get("colors"),
                score=event.get("away_score"),
            ),
            event_status=event["status"],
            status=str(status.status_type()),
        )


class SportSummary(BaseModel):
    """SportsData Suggest Specific fields"""

    sport: str
    values: list[SportEventDetails]

    @classmethod
    def from_events(cls, sport: str, events: dict[str, Any]):
        """Create a SportSuggestDetails instance off the returned result of a Sports query.

        This presumes that the query returns elements for the previous, current, and next events (as appropriate)
        """
        previous = current = next = None
        if events.get("previous"):
            previous = SportEventDetails.from_event_dict(events["previous"])
        if events.get("current"):
            previous = None
            current = SportEventDetails.from_event_dict(events["current"])
        if events.get("next"):
            next = SportEventDetails.from_event_dict(events["next"])
        # Note, each event result contains a "score" which is the returned ES score.
        # This may be used as an adjustment to the returned score for the suggestion.
        # Higher "scores" have a greater match against the provided search term.
        return cls(sport=sport, values=[e for e in [previous, current, next] if e is not None])
