"""General Data Types for Sports"""

# from __future__ import annotations

import json
import logging

from abc import abstractmethod
from datetime import datetime, timedelta, timezone
from typing import Any
from zoneinfo import ZoneInfo

from dynaconf.base import LazySettings
from httpx import AsyncClient
from pydantic import BaseModel

from merino.utils.metrics import get_metrics_client
from merino.providers.suggest.sports import (
    LOGGING_TAG,
    TEAM_TTL_WEEKS,
    EVENT_TTL_WEEKS,
    utc_time_from_now,
)

from merino.providers.suggest.sports.backends.sportsdata.common import (
    GameStatus,
)


class SportDate(BaseModel):
    """Return the current date in SportsData compliant format.

    Some requests to SportsData use a Y-M-D formatted timestamp as a URL parameter.
    """

    instance: datetime

    def __init__(self, *args, **kwargs):
        """Instantiate using an optional instance time.

        mypy will fail to recognize `__init__()` as typed, see
        https://github.com/python/mypy/issues/5502
        """
        instance = kwargs.get("instance", datetime.now(tz=timezone.utc))
        kwargs["instance"] = instance.replace(
            hour=0, minute=0, second=0, microsecond=0, tzinfo=timezone.utc
        )
        super().__init__(*args, **kwargs)

    def __str__(self) -> str:
        return self.instance.strftime("%Y-%b-%d")

    @classmethod
    def parse(cls, parse: str):
        """Convert string into self."""
        return cls(instance=datetime.strptime(parse, "%Y-%b-%d"))


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
    # Location of the team (city, state | country) if available
    locale: str | None
    # Alternate names for the team
    aliases: list[str]
    # Team colors (from primary to tertiary )
    colors: list[str]
    # Last update time.
    updated: datetime
    # Team Data expiration date:
    expiry: int

    def as_str(self) -> str:
        """Serialize to JSON string"""
        return json.dumps(self)

    @classmethod
    def from_data(cls, team_data: dict[str, Any], term_filter: list[str], team_ttl: timedelta):
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
                for word in list(candidate.split(" ")):
                    lword = word.lower()
                    if word not in term_filter:
                        terms.add(lword)
        locale = " ".join([team_data.get("City") or "", team_data.get("AreaName") or ""]).strip()
        name = team_data["Name"]
        fullname = team_data.get("FullName") or f"{locale} {team_data["Name"]}"
        logging.debug(f"{LOGGING_TAG} - Team: {fullname}")
        return cls(
            terms=" ".join(terms),
            key=team_data["Key"],
            fullname=fullname.encode("utf8"),
            name=name.encode("utf8"),
            locale=locale.encode("utf8"),
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
                        # Some Teams use "ClubColor#"
                        team_data.get("PrimaryColor", team_data.get("ClubColor1")),
                        team_data.get("SecondaryColor", team_data.get("ClubColor2")),
                        team_data.get("TertiaryColor", team_data.get("ClubColor3")),
                        team_data.get("QuaternaryColor", team_data.get("ClubColor4")),
                    ],
                )
            ),
        )

    def minimal(self) -> dict[str, Any]:
        """Return the very minimal version of the team info used in Events"""
        return dict(key=self.key, name=self.fullname, colors=self.colors)


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
    original_date: str
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
    expiry: int

    def suggest_title(self) -> str:
        """Event suggest title"""
        return f"{self.away_team["name"]} at {self.home_team["name"]}"

    def suggest_description(self) -> str:
        """Return a formatted description text for the suggestion result."""
        match self.status:
            case GameStatus.Scheduled | GameStatus.Delayed:
                text = f"starts at {self.date}"
            case GameStatus.Final | GameStatus.F_OT:
                text = f"Final score: {self.away_score} - {self.home_score}"
            case _:
                text = f"{self.status.as_str()}: {self.away_score} - {self.home_score}"
        return text

    def as_json(self) -> str:
        """Provide the data as a minimal JSON structure without the terms"""
        return json.dumps(
            dict(
                # terms=self.terms,
                sport=self.sport,
                id=self.id,
                date=int(self.date.timestamp()),
                home_team=self.home_team,
                away_team=self.away_team,
                home_score=self.home_score,
                away_score=self.away_score,
                status=self.status.as_str(),
                expiry=self.expiry,
            )
        )

    def key(self) -> str:
        """Generate semi-unique key for this event"""
        return f"{self.sport}:{self.home_team["key"]}:{self.away_team["key"]}".lower()


class Sport(BaseModel):
    """Root Model for Sport data"""

    api_key: str
    name: str
    teams: dict[str, Team] = {}
    events: dict[int, Event] = {}
    base_url: str
    event_ttl: timedelta
    team_ttl: timedelta
    # Commented because Pydantic does not know how to generate a core schema
    # client: AsyncClient
    # _lock: asyncio.Lock = asyncio.Lock() # Used for local cache management
    term_filter: list[str] = []
    cache_dir: str | None

    def __init__(self, settings: LazySettings, *args, **kwargs):
        logging.debug(f"{LOGGING_TAG} In sport")
        # Set defaults for overrides
        if "api_key" not in kwargs:
            kwargs.update({"api_key": settings.sportsdata.get("api_key")})
        if "event_ttl" not in kwargs:
            kwargs.update(
                {"event_ttl": timedelta(weeks=settings.get("event_ttl_weeks", EVENT_TTL_WEEKS))}
            )
        if "team_ttl" not in kwargs:
            kwargs.update(
                {"team_ttl": timedelta(weeks=settings.get("team_ttl_weeks", TEAM_TTL_WEEKS))}
            )
        if "term_filter" not in kwargs:
            kwargs.update({"term_filter": []})
        super().__init__(
            *args,
            **kwargs,
        )

    def gen_key(self, key: str) -> str:
        """Generate the internal sport:team key for unique lookup and storage."""
        return f"{self.name.lower()}:{key.lower()}"

    @abstractmethod
    async def get_team(self, key: str) -> Team | None:
        """Return the team based on the key provided"""

    @abstractmethod
    async def update_teams(self, client: AsyncClient):
        """Update team information and store in common storage (usually called nightly)"""

    @abstractmethod
    async def update_events(self, client: AsyncClient):
        """Fetch the list of current and upcoming events for this sport"""

    def load_teams_from_source(self, data: list[dict[str, Any]]) -> dict[str, Team]:
        """Create the Team entries from the data source

        This presumes that we are receiving data that complies with the SportsData.io
        `Team` data dictionary (See https://sportsdata.io/developers/data-dictionary/nfl#team)

        If we ever have a different data provider, this will need to be moved to the
        SportData provider class.
        """
        for team_data in data:
            team = Team.from_data(
                team_data=team_data,
                term_filter=self.term_filter,
                team_ttl=self.team_ttl,
            )
            self.teams[team.key] = team
        return self.teams

    def load_scores_from_source(
        self, data: list[dict[str, Any]], event_timezone: ZoneInfo = ZoneInfo("UTC")
    ) -> dict[int, "Event"]:
        """Scan the list of Event scores for any event within the 'current' window.

        This presumes that we are receiving data that complies with the SportsData.io
        `ScoreBasic` data dictionary (See https://sportsdata.io/developers/data-dictionary/nfl#scorebasic)

        If we ever have a different data provider, this will need to be moved to the
        SportData provider class.

        """
        if not self.events:
            self.events = {}
        """
        [
            {'Quarter': None,
             'TimeRemaining': None,
             'QuarterDescription': '',
             'GameEndDateTime': None,
             'AwayScore': None,
             'HomeScore': None,
             'GameID': 19047,
             'GlobalGameID': 19047,
             'ScoreID': 19047,
             'GameKey': '202510428',
             'Season': 2025,
             'SeasonType': 1,
             'Status': 'Scheduled',
             'Canceled': False,
             'Date': '2025-09-28T09:30:00',
             'Day': '2025-09-28T00:00:00',
             'DateTime': '2025-09-28T09:30:00',
             'DateTimeUTC': '2025-09-28T13:30:00',
             'AwayTeam': 'MIN',
             'HomeTeam': 'PIT',
             'GlobalAwayTeamID': 20,
             'GlobalHomeTeamID': 28,
             'AwayTeamID': 20,
             'HomeTeamID': 28,
             'StadiumID': 90,
             'Closed': False,
             'LastUpdated': '2025-09-24T12:03:59',
             'IsClosed': False,
             'Week': 4},
             ...
             ]
        """
        start_window = datetime.now(tz=timezone.utc) - self.event_ttl
        end_window = datetime.now(tz=timezone.utc) + self.event_ttl
        for event_description in data:
            try:
                home_team = self.teams[
                    event_description.get("HomeTeam") or event_description["HomeTeamKey"]
                ]
                away_team = self.teams[
                    event_description.get("AwayTeam") or event_description["AwayTeamKey"]
                ]
            except Exception as ex:
                import pdb

                pdb.set_trace()
                print(ex)
            try:
                if "DateTimeUTC" in event_description:
                    date = datetime.fromisoformat(event_description["DateTimeUTC"]).replace(
                        tzinfo=timezone.utc
                    )
                else:
                    date = datetime.fromisoformat(event_description["DateTime"]).replace(
                        tzinfo=event_timezone
                    )
            except TypeError as ex:
                # It's possible to salvage this game by examining the other fields like "Day" or "Updated",
                # but if there's an error, it's probably wise to ignore this.
                # note: declaring a `self.metrics_client` causes a circular dependency.
                get_metrics_client().increment("sports.error.no_date", tags={"sport": self.name})
                logging.debug(
                    f"{LOGGING_TAG} {self.name} Event {id} between {home_team.key} and {away_team.key} has no time, skipping [{ex}]"
                )
                continue
            # Ignore any events that are outside of the event interest window.
            if not start_window <= date <= end_window:
                continue
            terms = f"{home_team.terms} {away_team.terms}"
            event = Event(
                sport=self.name,
                id=event_description["GlobalGameID"],
                terms=terms,
                date=date,
                original_date=event_description["DateTimeUTC"],
                home_team=home_team.minimal(),
                away_team=away_team.minimal(),
                home_score=event_description.get("HomeTeamScore")
                or event_description.get("HomeScore"),
                away_score=event_description.get("AwayTeamScore")
                or event_description.get("AwayScore"),
                status=GameStatus.parse(event_description["Status"]),
                expiry=utc_time_from_now(self.event_ttl),
            )
            self.events[event.id] = event
        return self.events

    def load_schedules_from_source(
        self, data: list[dict[str, Any]], event_timezone: ZoneInfo = ZoneInfo("UTC")
    ) -> dict[int, "Event"]:
        """Scan the list of Scheduled events, storing any in the current interest window.
        (Note: this is very similar to `load_scores_from_source` with some minor
        differences in the source data.)

        This presumes that we are receiving data that complies with the SportsData.io
        `ScheduleBasic` Data dictionary (See https://sportsdata.io/developers/data-dictionary/nhl#schedulebasic)

        """
        if not self.events:
            self.events = {}
        """
        [
            {"GameID":23869,
             "Season":2026,
             "SeasonType":2,
             "Status":"Final",
             "Day":"2025-09-21T00:00:00",
             "DateTime":"2025-09-21T21:30:00",
             "Updated":"2025-09-29T04:10:57",
             "IsClosed":true,
             "AwayTeam":"UTA",
             "HomeTeam":"COL",
             "StadiumID":9,
             "AwayTeamScore":2,
             "HomeTeamScore":3,
             "GlobalGameID":30023869,
             "GlobalAwayTeamID":30000041,
             "GlobalHomeTeamID":30000019,
             "GameEndDateTime":"2025-09-22T00:10:17",
             "NeutralVenue":false,
             "DateTimeUTC":"2025-09-22T01:30:00",
             "AwayTeamID":41,
             "HomeTeamID":19,
             "SeriesInfo":null
             },
             ...
             ]
        ]"""
        start_window = datetime.now(tz=timezone.utc) - self.event_ttl
        end_window = datetime.now(tz=timezone.utc) + self.event_ttl
        for event_description in data:
            # US sports use "(Away|Home)Team", Soccer uses "(Away|Home)TeamKey"
            home_team = self.teams[
                event_description.get("HomeTeamKey") or event_description["HomeTeam"]
            ]
            away_team = self.teams[
                event_description.get("AwayTeamKey") or event_description["AwayTeam"]
            ]
            id = event_description.get("GlobalGameID") or event_description["GameId"]
            try:
                if "DateTimeUTC" in event_description:
                    date = datetime.fromisoformat(event_description["DateTimeUTC"]).replace(
                        tzinfo=timezone.utc
                    )
                else:
                    date = datetime.fromisoformat(event_description["DateTime"]).replace(
                        tzinfo=event_timezone
                    )
            except TypeError as ex:
                # It's possible to salvage this game by examining the other fields like "Day" or "Updated",
                # but if there's an error, it's probably wise to ignore this.
                # note: declaring a `self.metrics_client` causes a circular dependency.
                get_metrics_client().increment("sports.error.no_date", tags={"sport": self.name})
                logging.debug(
                    f"{LOGGING_TAG} {self.name} Event {id} between {home_team.key} and {away_team.key} has no time, skipping [{ex}]"
                )
                continue
            status = GameStatus.parse(event_description["Status"])
            # Ignore cancelled games.
            if status == GameStatus.Canceled:
                # Cancelled games have no UTC time stamp, so we can't know how recent they were.
                continue
            # Ignore any events that are outside of the event interest window.
            if not start_window <= date <= end_window:
                continue
            terms = f"{home_team.terms} {away_team.terms}"
            event = Event(
                sport=self.name,
                id=id,
                terms=terms,
                date=datetime.strptime(event_description["DateTimeUTC"], "%Y-%m-%dT%H:%M:%S"),
                original_date=event_description["DateTimeUTC"],
                home_team=home_team.minimal(),
                away_team=away_team.minimal(),
                home_score=event_description["HomeTeamScore"],  # Differs
                away_score=event_description["AwayTeamScore"],  # Differs
                status=GameStatus.parse(event_description["Status"]),
                expiry=utc_time_from_now(self.event_ttl),
            )
            self.events[event.id] = event
        return self.events
