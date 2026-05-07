"""World Cup Soccer match endpoint request and response models."""

from typing import Any

from pydantic import BaseModel, ConfigDict, Field, HttpUrl
import webcolors

from merino.providers.suggest.sports.backends.sportsdata.common.data import Team, Event
from merino.utils.logos import get_logo_url, LogoCategory


def as_hex_color(color_name: str) -> str:
    """Convert the sportsdata color name to a hex value"""
    return str(
        webcolors.rgb_to_hex(
            webcolors.html5_parse_legacy_color(color_name.replace(" ", "").lower())
        )
    )


class TeamInfo(BaseModel):
    """A competing team."""

    key: str = Field(description="Abbreviated 3-letter team code, e.g. 'BRA'.")
    global_team_id: int = Field(description="Stable identifier for this team.")
    name: str = Field(description="Long form team name, e.g. 'Brazil'.")
    region: str = Field(description="ISO3 region designation; may differ from `name`.")
    colors: list[str] = Field(description="Branding colors, primary first.")
    icon_url: HttpUrl | None = Field(default=None, description="Team flag URL, if available.")
    eliminated: bool = Field(description="True once the team is out of the tournament.")

    @classmethod
    def from_Team(cls, team: Team):
        """Convert a Team to the widget TeamInfo"""
        colors = map(lambda color: as_hex_color(color), team.colors)
        return cls(
            key=team.key,
            global_team_id=team.id,
            name=team.name,
            region=team.country,
            colors=colors,
            icon_url=get_logo_url(LogoCategory.Nations, team.key),
            eliminated=team.eliminated,
        )

    @classmethod
    def from_Team_dict(cls, team: dict[str, Any]):
        """Build a TeamInfo from the minimized team dictionary stored in an Event record"""
        colors: list[str] = list(map(lambda color: as_hex_color(color), team.get("colors", [])))
        url = None
        if team.get("key"):
            url = get_logo_url(LogoCategory.Nations, team.get("key"))
        return cls(
            key=team.get("key"),
            global_team_id=team.get("id"),
            name=team.get("name"),
            region=team.get("region"),
            colors=colors,
            icon_url=url,
            eliminated=team.get("eliminated", False),
        )


class EventInfo(BaseModel):
    """A single match event."""

    date: str = Field(description="UTC ISO datetime for the start of the event.")
    global_event_id: int = Field(description="Stable identifier for this event.")
    home_team: TeamInfo
    away_team: TeamInfo
    period: str = Field(description="Period descriptor: '1', '2', 'Extra', etc.")
    home_score: int | None
    away_score: int | None
    home_extra: int | None
    away_extra: int | None
    home_penalty: int | None
    away_penalty: int | None
    clock: str = Field(description="Elapsed minutes; extra time as '90+3'.")
    updated: int = Field(description="UTC unix timestamp of the last record update.")
    status: str = Field(description="Game status: 'Scheduled', 'In Progress', 'Final', etc.")
    status_type: str = Field(description="Simplified status: 'past' | 'live' | 'scheduled'.")
    query: str | None = Field(default=None, description="Optional click-through query.")
    sport: str = Field(default="soccer", description="Sport identifier.")

    @classmethod
    def from_Event(cls, event: Event):
        """Generate a widget event descriptor record from a suggest Event"""
        home_team = TeamInfo.from_Team_dict(event.home_team)
        away_team = TeamInfo.from_Team_dict(event.away_team)
        updated = None
        if event.updated:
            updated = event.updated.isoformat()

        cls(
            date=event.date.isoformat(),
            global_event_id=event.id,
            home_team=home_team,
            away_team=away_team,
            period=event.period,
            home_score=event.home_score,
            away_score=event.away_score,
            home_extra=event.home_extra,
            away_extra=event.away_extra,
            home_penalty=event.home_penalty,
            away_penalty=event.away_penalty,
            clock=event.clock,
            updated=updated,
            status=event.status.as_str(),
            status_type=event.status.as_ui_status(),
            # This should probably use the same construct as suggest, but I don't think we've
            # resolved what it should be, so manually construct it here.
            query=f"{event.sport} {event.away_team.get('region')} {event.away_team.get('name')} vs {event.home_team.get('region')} {event.home_team.get('name')} {event.date}",
            sport=event.sport,
        )


class MatchesResponse(BaseModel):
    """Response payload for `GET /api/v1/wcs/matches`.

    Each bucket is sorted by `EventInfo.date` ascending. `next_` is aliased to
    `next` on the wire; populate by either name in Python.
    """

    model_config = ConfigDict(populate_by_name=True)

    previous: list[EventInfo]
    current: list[EventInfo]
    next_: list[EventInfo] = Field(alias="next")


class LiveMatchesResponse(BaseModel):
    """Response payload for `GET /api/v1/wcs/live`.

    Holds events with `status_type == "live"`, sorted by `date` ascending.
    """

    matches: list[EventInfo]


class TeamsResponse(BaseModel):
    """Response payload for `GET /api/v1/wcs/teams`."""

    teams: list[TeamInfo]
