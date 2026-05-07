"""World Cup Soccer match endpoint request and response models."""

from pydantic import BaseModel, ConfigDict, Field, HttpUrl

from merino.providers.suggest.sports.backends.sportsdata.common.data import Event


class TeamInfo(BaseModel):
    """A competing team."""

    key: str = Field(description="Abbreviated 3-letter team code, e.g. 'BRA'.")
    global_team_id: int = Field(description="Stable identifier for this team.")
    name: str = Field(description="Long form team name, e.g. 'Brazil'.")
    region: str = Field(description="ISO3 region designation; may differ from `name`.")
    colors: list[str] = Field(description="Branding colors, primary first.")
    icon_url: HttpUrl | None = Field(default=None, description="Team flag URL, if available.")
    eliminated: bool = Field(description="True once the team is out of the tournament.")


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
        # TODO: generate home and away teams from the provided, minimized dictionaries
        # home_team = TeamInfo.from_Team_dict(event.home_team)
        # away_team = TeamInfo.from_Team_dict(event.away_team)
        team = TeamInfo(
            key="UNK", global_team_id=0, name="TBD", region="UNK", colors=[], eliminated=True
        )
        updated = None
        if event.updated:
            updated = event.updated.isoformat()

        cls(
            date=event.date.isoformat(),
            global_event_id=event.id,
            home_team=team,
            away_team=team,
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
