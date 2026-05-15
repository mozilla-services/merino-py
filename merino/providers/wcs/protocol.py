"""World Cup Soccer match endpoint request and response models."""

from typing import Any

from pydantic import BaseModel, ConfigDict, Field, HttpUrl

from merino.providers.suggest.sports.backends.sportsdata.common.data import Event, Team
from merino.providers.suggest.sports.backends.sportsdata.protocol import build_query
from merino.providers.wcs.utils import get_team_colours
from merino.utils.logos import LogoCategory, load_manifest


# Stage does not always provide a CDN host override for the nations logo bucket.
# Pin WCS flag URLs to the production image bucket so stage and prod render the
# same assets.
_LOGO_HOST = "https://storage.googleapis.com/merino-images-prod"


def _icon(key: str) -> HttpUrl | None:
    """Return the nations flag URL for `key`, preferring SVG over PNG."""
    entry = load_manifest().get(LogoCategory.Nations, key)
    if not entry:
        return None
    if entry.svg:
        return HttpUrl(f"{_LOGO_HOST}/{entry.svg}")
    return HttpUrl(f"{_LOGO_HOST}/{entry.url}")


class TeamInfo(BaseModel):
    """A competing team."""

    key: str = Field(description="Abbreviated 3-letter team code, e.g. 'BRA'.")
    global_team_id: int = Field(description="Stable identifier for this team.")
    name: str = Field(description="Long form team name, e.g. 'Brazil'.")
    region: str = Field(description="ISO3 region designation; may differ from `name`.")
    colors: list[str] = Field(description="Branding colors, primary first.")
    icon_url: HttpUrl | None = Field(default=None, description="Team flag URL, if available.")
    group: str | None = Field(default=None, description="World Cup group name, if applicable.")
    eliminated: bool = Field(
        default=False, description="True once the team is out of the tournament."
    )

    @classmethod
    def from_team(
        cls,
        team: Team,
        *,
        group: str | None = None,
        eliminated: bool = False,
        region: str | None = None,
    ) -> "TeamInfo":
        """Build widget team info from a cached SportsData team."""
        return cls(
            key=team.key,
            global_team_id=team.id,
            name=team.name,
            region=region or team.country or team.key,
            colors=get_team_colours(team.key),
            icon_url=_icon(team.key),
            group=group,
            eliminated=eliminated,
        )

    @classmethod
    def from_event_team(
        cls,
        team: dict[str, Any],
        *,
        group: str | None = None,
    ) -> "TeamInfo":
        """Build widget team info from the compact team dict stored on events.

        The `group` argument is plumbed in from the parent event because the
        compact team dict does not carry a group of its own; the World Cup
        group is a per-event attribute.
        """
        key = str(team["key"])
        raw_icon_url = team.get("icon_url")
        return cls(
            key=key,
            global_team_id=int(team["id"]),
            name=str(team["name"]),
            region=str(team.get("region") or team.get("country") or key),
            colors=get_team_colours(key),
            icon_url=HttpUrl(raw_icon_url) if raw_icon_url else _icon(key),
            group=group,
            eliminated=bool(team.get("eliminated", False)),
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
    stage: str | None = Field(
        default=None,
        description="Tournament stage, e.g. 'Group Stage', 'Round of 32', 'Final'.",
    )
    status: str = Field(description="Game status: 'Scheduled', 'In Progress', 'Final', etc.")
    status_type: str = Field(description="UI status bucket, e.g. 'past', 'live', 'scheduled'.")
    query: str | None = Field(default=None, description="Optional click-through query.")
    sport: str = Field(default="soccer", description="Sport identifier.")

    @classmethod
    def from_event(cls, event: Event) -> "EventInfo":
        """Build widget event info from a cached SportsData event."""
        home_team = TeamInfo.from_event_team(event.home_team, group=event.group)
        away_team = TeamInfo.from_event_team(event.away_team, group=event.group)
        updated = event.updated or event.date
        return cls(
            date=event.date.isoformat(),
            global_event_id=event.id,
            home_team=home_team,
            away_team=away_team,
            period=event.period or "",
            home_score=event.home_score,
            away_score=event.away_score,
            home_extra=event.home_extra,
            away_extra=event.away_extra,
            home_penalty=event.home_penalty,
            away_penalty=event.away_penalty,
            clock=event.clock or "",
            updated=int(updated.timestamp()),
            stage=event.stage,
            status=event.status.as_str(),
            status_type=event.status.as_ui_status(),
            query=build_query(event.model_dump(mode="json")),
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

    Holds mocked live-endpoint events, sorted by `date` ascending.
    """

    matches: list[EventInfo]


class TeamsResponse(BaseModel):
    """Response payload for `GET /api/v1/wcs/teams`."""

    teams: list[TeamInfo]
