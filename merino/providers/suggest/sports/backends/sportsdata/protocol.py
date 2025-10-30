"""Protocol for sport suggestion backends."""

from typing import Any
from datetime import datetime, timezone

from merino.providers.suggest.base import BaseModel
from merino.providers.suggest.sports.backends.sportsdata.common import GameStatus


class SportTeamDetail(BaseModel):
    """Data about the specific Sport team."""

    key: str  # Sport unique abbreviated identifier (e.g. "SFG", "DAL", etc)
    name: str  # Full name of the team
    colors: list[str]  # list of hex colors from primary to quaternary
    score: int | None  # Current score (if available)


def build_query(event: dict[str, Any]) -> str:
    """Build the search query from the event information"""
    date = datetime.fromtimestamp(event["date"]).strftime("%d %b %Y")
    return f"""{event.get("sport")} {event.get("away_team",{}).get("name","")} at {event.get("home_team", {}).get("name", "")} {date}"""


class SportEventDetail(BaseModel):
    """Data about the specific Sport event."""

    sport: str  # Sport Name ("NFL", "NHL", "NBA", etc.)
    query: str  # Click search query for this event.
    date: str  # UTC timestamp for the game
    home_team: SportTeamDetail  # Home Team details
    away_team: SportTeamDetail  # Away Team details
    status: str  # Long form event status. ("Scheduled", "Final - Overtime", etc.)
    status_type: str  # UI display status ("past", "live", "scheduled")

    @classmethod
    def from_event_dict(cls, event: dict[str, Any]):
        """Create an instance of SportEventDetails from a provided Event dictionary

        This presumes that it's reading a json loaded sport Event that was returned by elastic search.
        """
        status: GameStatus = event["event_status"]
        return cls(
            sport=event["sport"],
            query=build_query(event),
            date=datetime.fromtimestamp(event["date"], tz=timezone.utc).isoformat(),
            home_team=SportTeamDetail(
                key=event.get("home_team", {}).get("key"),
                name=event.get("home_team", {}).get("name"),
                colors=event.get("home_team", {}).get("colors"),
                score=event.get("home_score"),
            ),
            away_team=SportTeamDetail(
                key=event.get("away_team", {}).get("key"),
                name=event.get("away_team", {}).get("name"),
                colors=event.get("away_team", {}).get("colors"),
                score=event.get("away_score"),
            ),
            status=str(status.as_str()),
            status_type=str(status.as_ui_status()),
        )


class SportEventDetails(BaseModel):
    """Return a set of Sports Results in a decollated manner.

    This presumes that results can be from mixed sports, and that there
    is only one level of structure to the result. If you want to do
    multiple sport results that are collated, you probably want to
    look at SportSummary and returning a list of those.
    """

    values: list[SportEventDetail]

    def __init__(self, summary: "SportSummary"):
        super().__init__(values=summary.values)


class SportSummary(BaseModel):
    """SportsData Suggest Specific fields"""

    sport: str
    values: list[SportEventDetail]

    @classmethod
    def from_events(cls, sport: str, events: dict[str, Any]):
        """Create a SportSuggestDetails instance off the returned result of a Sports query.

        This presumes that the query returns elements for the previous, current, and next events (as appropriate)
        """
        previous = current = next = None
        if events.get("previous"):
            previous = SportEventDetail.from_event_dict(events["previous"])
        if events.get("current"):
            previous = None
            current = SportEventDetail.from_event_dict(events["current"])
        if events.get("next"):
            next = SportEventDetail.from_event_dict(events["next"])
        # Note, each event result contains a "score" which is the returned ES score.
        # This may be used as an adjustment to the returned score for the suggestion.
        # Higher "scores" have a greater match against the provided search term.
        return cls(sport=sport, values=[e for e in [previous, current, next] if e is not None])
