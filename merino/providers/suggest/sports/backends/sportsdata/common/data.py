"""General Data Types for Sports"""

# from __future__ import annotations

import logging
import os

from abc import abstractmethod
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from enum import StrEnum
from typing import Any
from zoneinfo import ZoneInfo

from dynaconf.base import LazySettings
from httpx import AsyncClient
from pydantic import BaseModel

from merino.providers.suggest.sports import (
    LOGGING_TAG,
    TEAM_TTL_WEEKS,
    EVENT_TTL_WEEKS,
    utc_time_from_now,
)

from merino.cache.redis import RedisAdapter
from merino.cache.none import NoCacheAdapter
from merino.providers.suggest.sports.backends.sportsdata.common import GameStatus
from merino.providers.suggest.sports.backends.sportsdata.common.error import (
    SportsDataError,
)


# sportsdata.io's international-soccer feed returns the same "KOR" key for
# both Korea Republic and Curaçao, collapsing them into a single entry
# downstream (logo lookup, team caches, event dedup). Disambiguate by team
# name and remap Curaçao to its ISO 3166-1 alpha-3 code. Drop this entry
# when sportsdata fixes upstream.
_TEAM_KEY_OVERRIDES: dict[tuple[str, str], str] = {
    ("KOR", "Curaçao"): "CUW",
}

# Global Logger
logger = logging.getLogger(__name__)

SPORTSDATA_UTC = ZoneInfo("UTC")
SPORTSDATA_US_EASTERN = ZoneInfo("America/New_York")
SPORTSDATA_LEAGUE_NA_SPORTS = {"MLB", "NBA", "NHL", "NFL"}


def sportsdata_timezone_for_sport(sport: str) -> ZoneInfo:
    """Return the timezone SportsData uses for a sport's day-based endpoints."""
    if sport.upper() in SPORTSDATA_LEAGUE_NA_SPORTS:
        return SPORTSDATA_US_EASTERN
    return SPORTSDATA_UTC


def sportsdata_day_slug(kickoff: datetime, event_timezone: ZoneInfo) -> str:
    """Return the date path segment SportsData expects for a kickoff."""
    if kickoff.tzinfo is None:
        kickoff = kickoff.replace(tzinfo=timezone.utc)
    return kickoff.astimezone(event_timezone).strftime("%Y-%b-%d").upper()


def _parse_sportsdata_datetime(value: Any, source_timezone: ZoneInfo) -> datetime:
    """Parse a SportsData timestamp and normalize it to UTC."""
    parsed = datetime.fromisoformat(value)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=source_timezone)
    return parsed.astimezone(timezone.utc)


class Team(BaseModel):
    """Contain the truncated 'Team' information.

    This data is held in memory.
    """

    # Search terms for elastic search
    terms: str
    #  Team long name
    fullname: str
    # Team short name
    name: str
    # Team sport specific unique key
    key: str
    # Team ID
    id: int
    # Location of the team (city, state | country) if available
    locale: str | None
    # Alternate names for the team
    aliases: list[str]
    # Team colors (from primary to tertiary )
    colors: list[str]
    # Last update time.
    updated: datetime
    # Team Data expiration date:
    expiry: datetime
    # Country / Area
    country: str | None

    @classmethod
    def from_data(
        cls,
        team_data: dict[str, Any],
        term_filter: list[str],
        team_ttl: timedelta,
        normalized_terms: dict,
        areas: dict[int, Any] | None = None,
    ):
        """Convert the rich SportsData.io information set to the reduced info we need."""
        # build the list of terms we want to search:
        terms = set()
        for item in [
            "Name",
            "AreaName",
            "City",
            "FullName",
            "Nickname1",
            "Nickname2",
            "Nickname3",
        ]:
            candidate = team_data.get(item)
            if candidate:
                for word in candidate.split(" "):
                    lword = word.lower()
                    if word not in term_filter:
                        terms.add(lword)
        locale = " ".join([team_data.get("City") or "", team_data.get("AreaName") or ""]).strip()
        name = team_data["Name"]
        fullname = team_data.get("FullName") or f"{locale} {team_data['Name']}"
        logger.debug(f"{LOGGING_TAG} - Team: {fullname}")
        team_id = team_data.get(normalized_terms[SportTerms.TEAM_ID])
        if not team_id:
            logger.warning(f"{LOGGING_TAG}: No id found for team {team_data}")
            raise SportsDataError(
                f"No {normalized_terms[SportTerms.TEAM_ID]} found for {fullname}"
            )
        # WCS Find the country
        country = None
        if areas:
            country = areas.get(team_data.get(normalized_terms.get("AreaId", "AreaId"), 9999))
        raw_key = team_data["Key"]
        if country and country.get("aliases"):
            terms.add(country.get("aliases"))
        return cls(
            terms=" ".join(terms),
            key=_TEAM_KEY_OVERRIDES.get((raw_key, name), raw_key),
            id=team_id,
            fullname=fullname,
            name=name,
            locale=locale,
            aliases=list(
                filter(
                    lambda x: x is not None,
                    [
                        team_data.get("FullName"),
                        # Not all teams have nicknames,
                        team_data.get("Nickname1"),
                        team_data.get("Nickname2"),
                        team_data.get("Nickname3"),
                    ],
                )
            ),
            updated=datetime.now(),
            expiry=utc_time_from_now(team_ttl),
            colors=list(
                filter(
                    lambda x: x is not None,
                    [
                        team_data.get(normalized_terms[SportTerms.COLOR1]),
                        team_data.get(normalized_terms[SportTerms.COLOR2]),
                        team_data.get(normalized_terms[SportTerms.COLOR3]),
                        team_data.get(normalized_terms[SportTerms.COLOR4]),
                    ],
                )
            ),
            country=country,
        )

    def minimal(self) -> dict[str, Any]:
        """Return the very minimal version of the team info used in Events"""
        return dict(key=self.key, name=self.fullname, colors=self.colors, id=self.id)


class Event(BaseModel):
    """Root model for a Sporting Event (e.g. a game or match)"""

    # Reference to the associated Sport (DO NOT SERIALIZE!)
    sport: str
    # Event Unique Identifier (for elastic)
    id: int
    # list of searchable terms for this event.
    terms: str
    # Event UTC start time
    date: datetime
    # The original date string (used for debugging)
    original_date: str | None
    # minimal team info for home
    home_team: dict[str, Any]
    # minimal team info for home
    away_team: dict[str, Any]
    # Score for the "Home" team
    home_score: int | None
    # Score for the "Away" team
    away_score: int | None
    # Status of the game
    status: GameStatus
    # UTC timestamp when to expire an event.
    expiry: datetime
    # UTC of last event update
    updated: datetime | None
    # Final period of the game: "Regular", "ExtraTime", "PenaltyShootout", etc.
    period: str | None = None
    # Points scored in extra play
    home_extra: int | None = None
    away_extra: int | None = None
    # Points scored in penalty play
    home_penalty: int | None = None
    away_penalty: int | None = None
    # Play time, with additions when provided by the feed.
    clock: str | None = None
    # Optional stage, e.g. "Group", "Round of 32"
    stage: str | None = None
    # Tournament metadata used by WCS widget team state.
    round_id: int | None = None
    season_type: int | None = None
    group: str | None = None
    winner: str | None = None
    is_closed: bool | None = None

    def key(self) -> str:
        """Generate semi-unique key for this event"""
        return f"{self.sport}:{self.home_team['key']}:{self.away_team['key']}".lower()

    def serialize(self) -> dict[str, Any]:
        """Condition Event for JSON serialization. This converts dates from datetime and
        skips potentially blank items.
        """
        result = {
            "sport": self.sport,
            "id": self.id,
            "home_score": self.home_score,
            "away_score": self.away_score,
            "status": str(self.status),
            "date": self.date.isoformat(),
            "expiry": self.expiry.isoformat(),
        }
        optional_fields = (
            "period",
            "home_extra",
            "away_extra",
            "home_penalty",
            "away_penalty",
            "clock",
            "stage",
            "round_id",
            "season_type",
            "group",
            "winner",
            "is_closed",
        )
        for field_name in optional_fields:
            value = getattr(self, field_name)
            if value is not None:
                result[field_name] = value
        # This may be a quick_update, meaning these values could be blank
        # Do not destructively overwrite them!
        if self.terms:
            result["terms"] = self.terms
        if self.home_team:
            result["home_team"] = self.home_team
        if self.away_team:
            result["away_team"] = self.away_team
        if self.original_date:
            # NOTE: original_date is stored as a string value.
            result["original_date"] = self.original_date
        if self.updated:
            result["updated"] = self.updated.isoformat()
        return result


class SportTerms(StrEnum):
    """Define enums for normalized field names"""

    GAME_ID = "GameID"
    AWAY_TEAM_ID = "AwayTeamID"
    AWAY_TEAM_KEY = "AwayTeamKey"
    AWAY_TEAM_SCORE = "AwayTeamScore"
    HOME_TEAM_ID = "HomeTeamID"
    HOME_TEAM_KEY = "HomeTeamKey"
    HOME_TEAM_SCORE = "HomeTeamScore"
    TEAM_ID = "TeamID"
    COLOR1 = "PrimaryColor"
    COLOR2 = "SecondaryColor"
    COLOR3 = "TertiaryColor"
    COLOR4 = "QuaternaryColor"


SportNormalizedTerms: dict[SportTerms, str] = {
    SportTerms.GAME_ID: "GameID",  # This value _MUST_ match between the Schedule and Sport if both are used.
    SportTerms.AWAY_TEAM_ID: "AwayTeamID",
    SportTerms.AWAY_TEAM_KEY: "AwayTeam",
    SportTerms.AWAY_TEAM_SCORE: "AwayTeamScore",
    SportTerms.HOME_TEAM_ID: "HomeTeamID",
    SportTerms.HOME_TEAM_KEY: "HomeTeam",
    SportTerms.HOME_TEAM_SCORE: "HomeTeamScore",
    SportTerms.TEAM_ID: "TeamID",
    SportTerms.COLOR1: "PrimaryColor",
    SportTerms.COLOR2: "SecondaryColor",
    SportTerms.COLOR3: "TertiaryColor",
    SportTerms.COLOR4: "QuaternaryColor",
}


@dataclass(frozen=True)
class SportsDataEventRow:
    """Normalized fields from a SportsData schedule or score row."""

    game_id: int
    status: GameStatus
    home_team_id: int | None
    away_team_id: int | None
    home_team_key: str | None
    away_team_key: str | None
    home_score: int | None
    away_score: int | None
    kickoff: datetime
    original_date: str | None
    updated: datetime | None
    raw: dict[str, Any]

    @classmethod
    def from_event_description(
        cls,
        event_description: dict[str, Any],
        normalized_terms: dict[SportTerms, str],
        event_timezone: ZoneInfo,
    ) -> "SportsDataEventRow":
        """Normalize shared SportsData schedule and score fields."""
        game_id = event_description.get(normalized_terms[SportTerms.GAME_ID])
        if game_id is None:
            raise SportsDataError(f"No game id found for event: {event_description}")

        kickoff, original_date = cls._kickoff_at(event_description, event_timezone)
        return cls(
            game_id=game_id,
            status=GameStatus.parse(event_description["Status"]),
            home_team_id=event_description.get(normalized_terms[SportTerms.HOME_TEAM_ID]),
            away_team_id=event_description.get(normalized_terms[SportTerms.AWAY_TEAM_ID]),
            home_team_key=event_description.get(normalized_terms[SportTerms.HOME_TEAM_KEY]),
            away_team_key=event_description.get(normalized_terms[SportTerms.AWAY_TEAM_KEY]),
            home_score=event_description.get(normalized_terms[SportTerms.HOME_TEAM_SCORE]),
            away_score=event_description.get(normalized_terms[SportTerms.AWAY_TEAM_SCORE]),
            kickoff=kickoff,
            original_date=original_date,
            updated=cls._updated_at(event_description, event_timezone),
            raw=event_description,
        )

    @staticmethod
    def _kickoff_at(
        event_description: dict[str, Any], event_timezone: ZoneInfo
    ) -> tuple[datetime, str | None]:
        """Return the event kickoff, preferring SportsData's UTC field."""
        source_day = event_description.get("Day")
        if event_description.get("DateTimeUTC"):
            raw_utc_date = event_description["DateTimeUTC"]
            return _parse_sportsdata_datetime(
                raw_utc_date, SPORTSDATA_UTC
            ), source_day or raw_utc_date
        if event_description.get("DateTime"):
            raw_date = event_description["DateTime"]
            return _parse_sportsdata_datetime(raw_date, event_timezone), source_day or raw_date
        raise TypeError("SportsData event has no DateTimeUTC or DateTime")

    @staticmethod
    def _updated_at(
        event_description: dict[str, Any], event_timezone: ZoneInfo
    ) -> datetime | None:
        """Return the SportsData row update timestamp as UTC."""
        raw_updated_utc = event_description.get("UpdatedUtc") or event_description.get(
            "UpdatedUTC"
        )
        if raw_updated_utc:
            return _parse_sportsdata_datetime(raw_updated_utc, SPORTSDATA_UTC)

        raw_updated = event_description.get("Updated") or event_description.get("LastUpdated")
        if raw_updated:
            return _parse_sportsdata_datetime(raw_updated, event_timezone)
        return None


class Sport:
    """Root Model for Sport data"""

    api_key: str
    name: str
    teams: dict[int, Team] = {}
    events: dict[int, Event] = {}
    base_url: str
    event_ttl: timedelta
    team_ttl: timedelta
    # While it's possible to include `AsyncClient` as a property of this
    # class, I prefer passing it as a discrete parameter to the calls for mocking
    # and ownership reasons.
    term_filter: list[str] = []
    cache_dir: str | None
    cache: RedisAdapter | NoCacheAdapter
    # Each sport may use a different term for these values.
    # You should prefer to use the `Global*` version when possible, but not all sports
    # provide that value, nor do all returned data sets.
    # This array is used by both Schedule and Score lookups.
    normalized_terms: dict = {}

    def __init__(
        self,
        settings: LazySettings,
        base_url: str,
        name: str,
        cache_dir: str | None = None,
        cache: RedisAdapter | NoCacheAdapter = NoCacheAdapter(),
        api_key: str | None = None,
        event_ttl: timedelta | None = None,
        team_ttl: timedelta | None = None,
        term_filter: list[str] = [],
        **kwargs,
    ):
        logger.debug(f"{LOGGING_TAG} In sport")
        # Set defaults for overrides
        # NOTE: This also handles a potential typo in the AirFlow environment variable name.
        # See https://mozilla-hub.atlassian.net/browse/DISCO-3802
        self.api_key = (
            api_key
            or settings.sportsdata.get("api_key")
            or os.environ.get("MERINO_PROVIDERS__SPORTS__SPORTSDATA_API_KEY")
            or ""
        )
        logger.info(f"{LOGGING_TAG} SportsData API Key: {self.api_key[:4] or 'None'}")
        self.base_url = base_url
        self.name = name
        self.teams = {}
        self.events = {}
        self.event_ttl = event_ttl or timedelta(
            weeks=settings.sportsdata.get("event_ttl_weeks", EVENT_TTL_WEEKS)
        )
        self.team_ttl = team_ttl or timedelta(weeks=settings.get("team_ttl_weeks", TEAM_TTL_WEEKS))
        self.term_filter = term_filter
        self.cache_dir = cache_dir
        self.cache = cache
        self.normalized_terms = SportNormalizedTerms.copy()

    @abstractmethod
    async def get_team(self, id: int) -> Team | None:
        """Return the team based on the id provided"""

    @abstractmethod
    async def get_season(self, client: AsyncClient):
        """Fetch the current season"""

    @abstractmethod
    async def update_teams(self, client: AsyncClient):
        """Update team information and store in common storage (usually called nightly)"""

    @abstractmethod
    async def update_events(self, client: AsyncClient):
        """Fetch the list of current and upcoming events for this sport"""

    def load_teams_from_source(self, data: list[dict[str, Any]]) -> dict[int, Team]:
        """Create the Team entries from the data source

        This presumes that we are receiving data that complies with the SportsData.io
        `Team` data dictionary (See https://sportsdata.io/developers/data-dictionary/nfl#team)

        If we ever have a different data provider, this will need to be moved to the
        SportData provider class.
        """
        for team_data in data:
            try:
                team = Team.from_data(
                    team_data=team_data,
                    term_filter=self.term_filter,
                    team_ttl=self.team_ttl,
                    normalized_terms=self.normalized_terms,
                )
                self.teams[team.id] = team
            except SportsDataError:
                pass
        return self.teams

    def load_scores_from_source(
        self,
        data: list[dict[str, Any]],
        event_timezone: ZoneInfo = ZoneInfo("UTC"),
    ) -> dict[int, "Event"]:
        """Scan score rows and update or create events in the interest window."""
        for event_description in data:
            row = self.event_row_from_source(event_description, event_timezone)
            if row is None or self.skip_event_row(row):
                continue

            if row.game_id in self.events:
                event = self.events[row.game_id]
                self.apply_score_update(event, row)
            else:
                # Some Sports may not pull Schedules first
                logger.warning(
                    f"{LOGGING_TAG} Adding game...{row.away_team_key} at {row.home_team_key} :: {row.status}"
                )
                new_event = self.event_from_row(row)
                if new_event is not None:
                    self.events[new_event.id] = new_event

        return self.events

    def team_minimal(self, team: Team) -> dict[str, Any]:
        """Return the very minimal version of the team info used in Events"""
        return dict(key=team.key, name=team.fullname, colors=team.colors, id=team.id)

    def load_schedules_from_source(
        self, data: list[dict[str, Any]], event_timezone: ZoneInfo = ZoneInfo("UTC")
    ) -> dict[int, "Event"]:
        """Scan schedule rows and store events in the interest window."""
        for event_description in data:
            row = self.event_row_from_source(event_description, event_timezone)
            if row is None or self.skip_event_row(row):
                continue

            event = self.event_from_row(row)
            if event is not None:
                self.events[event.id] = event
        return self.events

    def event_row_from_source(
        self, event_description: dict[str, Any], event_timezone: ZoneInfo
    ) -> SportsDataEventRow | None:
        """Return a normalized event row or skip invalid SportsData input."""
        try:
            return SportsDataEventRow.from_event_description(
                event_description=event_description,
                normalized_terms=self.normalized_terms,
                event_timezone=event_timezone,
            )
        except SportsDataError as ex:
            self._log_invalid_event_row("sports.error.invalid_event", ex)
        except (TypeError, ValueError) as ex:
            self._log_invalid_event_row("sports.error.no_date", ex)
        except KeyError as ex:
            self._log_invalid_event_row("sports.error.invalid_event", ex)
        return None

    def _log_invalid_event_row(self, metric: str, error: BaseException) -> None:
        """Log a skipped SportsData row with the closest known reason."""
        logger.info(f"""{LOGGING_TAG}📈 {metric} ["sport" = "{self.name}"]""")
        logger.debug(f"{LOGGING_TAG} {self.name} invalid event row skipped: {error}")

    def skip_event_row(self, row: SportsDataEventRow) -> bool:
        """Return whether an event row should not be considered for ingestion."""
        return row.status in [GameStatus.NotNecessary, GameStatus.Canceled]

    def event_from_row(self, row: SportsDataEventRow) -> Event | None:
        """Create an Event from a normalized row when teams and dates are usable."""
        if not self.row_in_event_window(row):
            return None

        teams = self.teams_for_row(row)
        if teams is None:
            return None
        home_team, away_team = teams

        return Event(
            sport=self.name,
            id=row.game_id,
            terms=f"{home_team.terms} {away_team.terms}",
            date=row.kickoff,
            original_date=row.original_date,
            home_team=self.team_minimal(home_team),
            away_team=self.team_minimal(away_team),
            home_score=row.home_score,
            away_score=row.away_score,
            status=row.status,
            expiry=utc_time_from_now(self.event_ttl),
            updated=row.updated,
            **self.event_details(row.raw),
        )

    def row_in_event_window(self, row: SportsDataEventRow) -> bool:
        """Return whether a row kickoff falls inside this sport's interest window."""
        start_window = datetime.now(tz=timezone.utc) - self.event_ttl
        end_window = datetime.now(tz=timezone.utc) + self.event_ttl
        return start_window <= row.kickoff <= end_window

    def teams_for_row(self, row: SportsDataEventRow) -> tuple[Team, Team] | None:
        """Return the home and away teams for a normalized SportsData row."""
        if not row.home_team_id or not row.away_team_id:
            log = (
                logger.debug
                if row.home_team_id is None and row.away_team_id is None
                else logger.warning
            )
            log(
                f"{LOGGING_TAG} Could not find team id for '{row.home_team_key}' vs '{row.away_team_key}' for {self.name}: {row.raw}"
            )
            return None

        home_team = self.teams.get(row.home_team_id)
        away_team = self.teams.get(row.away_team_id)
        if not home_team or not away_team:
            logger.warning(
                f"{LOGGING_TAG} Could not find team info for '{row.home_team_key}' vs '{row.away_team_key}' for {self.name}: {row.raw}"
            )
            return None
        return home_team, away_team

    def apply_score_update(self, event: Event, row: SportsDataEventRow) -> None:
        """Apply score fields and source freshness from a normalized score row."""
        event.home_score = row.home_score
        event.away_score = row.away_score
        event.status = row.status
        event.updated = row.updated
        for field, value in self.event_details(row.raw).items():
            # Skip Nones so partial score payloads do not clobber schedule details.
            if value is not None:
                setattr(event, field, value)

    def updated_at(
        self, event_description: dict[str, Any], event_timezone: ZoneInfo
    ) -> datetime | None:
        """Return the event update timestamp, preferring the UTC field when available."""
        return SportsDataEventRow._updated_at(event_description, event_timezone)

    def event_details(self, event_description: dict[str, Any]) -> dict[str, Any]:
        """Return optional fields to merge into an `Event`.

        Most sports only need the common score fields. Subclasses can override this
        when a feed exposes widget-specific details, such as WCS clock and penalty data.
        """
        return {}
