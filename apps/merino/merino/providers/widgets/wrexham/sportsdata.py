"""SportsDataIO backend for the Wrexham widget, and converters from SportsDataIO responses
to the widget models.
"""

import logging
from datetime import UTC, datetime

from httpx import AsyncClient, HTTPError
from pydantic import BaseModel, HttpUrl, TypeAdapter, ValidationError, field_validator

from merino.configs import settings
from merino.exceptions import BackendError
from merino.providers.widgets.wrexham.protocol import (
    WREXHAM_TEAM_ID,
    Competition,
    Match,
    MatchPeriod,
    MatchStatus,
    Standing,
    Team,
)
from merino.utils.logos import LogoCategory, get_logo_url

logger = logging.getLogger(__name__)

API_KEY_HEADER: str = settings.providers.sports.sportsdata.api_auth_header

# SportsDataIO `SeasonType` of regular-season rounds (play-off rounds are 3, "postseason").
REGULAR_SEASON = 1

# SportsDataIO statuses that MatchStatus doesn't include, and the MatchStatus used for each.
_STATUS_ALIASES: dict[str, MatchStatus] = {
    "Start Delay": MatchStatus.Delayed,
    "Rain Delay": MatchStatus.Delayed,
    "Awarded": MatchStatus.Final,
}


class SportsDataBackendError(BackendError):
    """Error fetching or parsing SportsDataIO data."""


class SportsDataGame(BaseModel):
    """The SportsDataIO game fields used by the widget."""

    GameId: int
    # Null for some games, e.g. cancelled or awarded early-round cup games with no kickoff time.
    DateTime: datetime | None
    Status: str | None
    Period: str | None
    # Display clock during play, e.g. "90+3". Empty before kickoff and after the match.
    ClockDisplay: str | None
    # Teams are null when unknown, e.g. for a cup game cancelled before the draw.
    GlobalHomeTeamId: int | None
    GlobalAwayTeamId: int | None
    HomeTeamName: str | None
    AwayTeamName: str | None
    HomeTeamScore: int | None
    AwayTeamScore: int | None
    HomeTeamScorePenalty: int | None
    AwayTeamScorePenalty: int | None
    UpdatedUtc: datetime | None


class SportsDataStanding(BaseModel):
    """The SportsDataIO standing fields used by the widget."""

    GlobalTeamID: int
    ShortName: str
    Scope: str
    Order: int
    Games: int
    GoalsDifferential: int
    Points: int


class SportsDataRound(BaseModel):
    """A SportsDataIO competition round, as returned by `Schedule` and `Standings`."""

    SeasonType: int
    Games: list[SportsDataGame]
    Standings: list[SportsDataStanding]

    @field_validator("Games", mode="before")
    @classmethod
    def _null_as_empty(cls, value: object) -> object:
        """Treat a null collection as an empty one."""
        return [] if value is None else value

    @field_validator("Standings", mode="before")
    @classmethod
    def _total_rows_only(cls, value: object) -> object:
        """Keep only the overall table's rows, treating a null collection as an empty one.

        Rows are dropped before they're validated, so an incomplete row in a table we don't
        serve can't fail the whole response.
        """
        if not isinstance(value, list):
            return [] if value is None else value
        # Each round has three tables, one per `Scope`: `Total` counts all matches, `Home`
        # only home matches and `Away` only away matches. The widget shows the league table,
        # which is the `Total` one; it's also the only one whose `Order` is the league position.
        return [row for row in value if isinstance(row, dict) and row.get("Scope") == "Total"]


_games_adapter = TypeAdapter(list[SportsDataGame])
_rounds_adapter = TypeAdapter(list[SportsDataRound])


def _as_utc(value: datetime) -> datetime:
    """Mark a naive SportsDataIO UTC time as UTC."""
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)


def team_logo_url(global_team_id: int, fallback_logo_url: HttpUrl) -> HttpUrl:
    """Return the team's logo URL, or the fallback URL if it has none."""
    return get_logo_url(LogoCategory.Soccer, str(global_team_id)) or fallback_logo_url


def to_match(
    game: SportsDataGame, competition: Competition, fallback_logo_url: HttpUrl
) -> Match | None:
    """Convert a SportsDataIO game to a match.

    Returns None if either team, the kickoff time, the status or the update time is unknown,
    and also logs a warning if the game status isn't one we support.
    """
    home_id, away_id = game.GlobalHomeTeamId, game.GlobalAwayTeamId
    home_name, away_name = game.HomeTeamName, game.AwayTeamName
    kickoff, updated_at = game.DateTime, game.UpdatedUtc
    if (
        home_id is None
        or away_id is None
        or home_name is None
        or away_name is None
        or kickoff is None
        or updated_at is None
        or game.Status is None
    ):
        logger.debug("Skipping incomplete SportsDataIO game", extra={"game_id": game.GameId})
        return None

    if game.Status in _STATUS_ALIASES:
        status = _STATUS_ALIASES[game.Status]
    elif game.Status in MatchStatus:
        status = MatchStatus(game.Status)
    else:
        logger.warning(
            "Skipping SportsDataIO game with unsupported status",
            extra={"game_id": game.GameId, "status": game.Status},
        )
        return None

    # SportsDataIO sends a period even before kickoff, but we only return one once the
    # match has started.
    period = None
    if game.HomeTeamScore is not None and game.Period is not None and game.Period in MatchPeriod:
        period = MatchPeriod(game.Period)

    # Only send the clock while the match is being played. It's null at half-time, and when
    # play is suspended or delayed
    clock = (game.ClockDisplay or None) if status is MatchStatus.InProgress else None

    return Match(
        id=game.GameId,
        competition=competition,
        kickoff=_as_utc(kickoff),
        home_team=Team(
            id=home_id, name=home_name, logo_url=team_logo_url(home_id, fallback_logo_url)
        ),
        away_team=Team(
            id=away_id, name=away_name, logo_url=team_logo_url(away_id, fallback_logo_url)
        ),
        period=period,
        status=status,
        clock=clock,
        home_score=game.HomeTeamScore,
        away_score=game.AwayTeamScore,
        home_penalty_score=game.HomeTeamScorePenalty,
        away_penalty_score=game.AwayTeamScorePenalty,
        updated_at=_as_utc(updated_at),
    )


def to_wrexham_matches(
    games: list[SportsDataGame], competition: Competition, fallback_logo_url: HttpUrl
) -> list[Match]:
    """Convert the Wrexham games to matches, earliest kickoff first. Other games are dropped."""
    matches = [
        match
        for game in games
        if WREXHAM_TEAM_ID in (game.GlobalHomeTeamId, game.GlobalAwayTeamId)
        and (match := to_match(game, competition, fallback_logo_url)) is not None
    ]
    return sorted(matches, key=lambda match: match.kickoff)


def to_standings(rounds: list[SportsDataRound], fallback_logo_url: HttpUrl) -> list[Standing]:
    """Convert the overall table of the latest regular-season round that has one, ordered by
    position. Play-off rounds are ignored, so the final regular-season table is served during
    the play-offs.

    Returns an empty list if no regular-season round has a table.
    """
    for round in reversed(rounds):
        if round.SeasonType != REGULAR_SEASON:
            continue
        # Only `Total` rows are kept when the response is parsed.
        rows = round.Standings
        if rows:
            return [
                Standing(
                    position=row.Order,
                    team=Team(
                        id=row.GlobalTeamID,
                        name=row.ShortName,
                        logo_url=team_logo_url(row.GlobalTeamID, fallback_logo_url),
                    ),
                    played=row.Games,
                    goal_difference=row.GoalsDifferential,
                    points=row.Points,
                )
                for row in sorted(rows, key=lambda row: row.Order)
            ]
    return []


class SportsDataBackend:
    """Fetches Wrexham matches and league standings from SportsDataIO.

    Each call makes a single request; failures are not retried.
    """

    http_client: AsyncClient
    api_key: str
    fallback_logo_url: HttpUrl

    def __init__(self, http_client: AsyncClient, api_key: str, fallback_logo_url: HttpUrl) -> None:
        self.http_client = http_client
        self.api_key = api_key
        self.fallback_logo_url = fallback_logo_url

    async def fetch_schedule(self, competition: Competition, season: int) -> list[Match]:
        """Return the season's Wrexham matches in the competition, earliest first."""
        rounds = await self._get(f"Schedule/{competition.id}/{season}", _rounds_adapter)
        games = [game for round in rounds for game in round.Games]
        return to_wrexham_matches(games, competition, self.fallback_logo_url)

    async def fetch_live_matches(self, competition: Competition) -> list[Match]:
        """Return today's (UTC) Wrexham matches in the competition."""
        today = datetime.now(UTC).date().isoformat()
        games = await self._get(f"GamesByDate/{competition.id}/{today}", _games_adapter)
        return to_wrexham_matches(games, competition, self.fallback_logo_url)

    async def fetch_standings(self, competition: Competition, season: int) -> list[Standing]:
        """Return the competition's latest table for the season."""
        rounds = await self._get(f"Standings/{competition.id}/{season}", _rounds_adapter)
        return to_standings(rounds, self.fallback_logo_url)

    async def shutdown(self) -> None:
        """Close the HTTP client."""
        await self.http_client.aclose()

    async def _get[T](self, path: str, adapter: TypeAdapter[T]) -> T:
        """Fetch and validate a SportsDataIO response."""
        try:
            response = await self.http_client.get(path, headers={API_KEY_HEADER: self.api_key})
            response.raise_for_status()
            return adapter.validate_json(response.content)
        except HTTPError as ex:
            # The message carries the URL, which never includes the key (it's in a header).
            raise SportsDataBackendError(f"SportsDataIO request failed: {ex}") from ex
        except ValidationError as ex:
            raise SportsDataBackendError(
                f"Invalid SportsDataIO response for {path}: {ex.error_count()} errors"
            ) from ex
