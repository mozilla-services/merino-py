"""General Data Types for Sports"""

# from __future__ import annotations

import logging
import os

from abc import abstractmethod
from datetime import datetime, timedelta, timezone
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

from merino.providers.suggest.sports.backends.sportsdata.common import (
    GameStatus,
)

from merino.providers.suggest.sports.backends.sportsdata.common.error import (
    SportsDataError,
)


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

    @classmethod
    def from_data(cls, team_data: dict[str, Any], term_filter: list[str], team_ttl: timedelta):
        """Convert the rich SportsData.io information set to the reduced info we need."""
        logger = logging.getLogger(__name__)
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
        fullname = team_data.get("FullName") or f"{locale} {team_data["Name"]}"
        logger.debug(f"{LOGGING_TAG} - Team: {fullname}")
        id = team_data.get("GlobalTeamID", team_data.get("GlobalTeamId"))
        if not id:
            logger.warning(f"{LOGGING_TAG}: No id found for team {team_data}")
            raise SportsDataError(f"No GlobalTeamID found for {fullname}")
        return cls(
            terms=" ".join(terms),
            key=team_data["Key"],
            id=id,
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

    def suggest_title(self) -> str:
        """Event suggest title"""
        return f"{self.away_team["name"]} at {self.home_team["name"]}"

    def key(self) -> str:
        """Generate semi-unique key for this event"""
        return f"{self.sport}:{self.home_team["key"]}:{self.away_team["key"]}".lower()


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

    def __init__(
        self,
        settings: LazySettings,
        base_url: str,
        name: str,
        cache_dir: str | None = None,
        api_key: str | None = None,
        event_ttl: timedelta | None = None,
        team_ttl: timedelta | None = None,
        term_filter: list[str] = [],
        **kwargs,
    ):
        logger = logging.getLogger(__name__)
        logger.debug(f"{LOGGING_TAG} In sport")
        # Set defaults for overrides
        # NOTE: This also handles a potential typo in the AirFlow environment variable name.
        # See https://mozilla-hub.atlassian.net/browse/DISCO-3802
        self.api_key = api_key or settings.sportsdata.get(
            "api_key", os.environ.get("MERINO_PROVIDERS__SPORTS__SPORTSDATA_API_KEY")
        )
        logger.info(f"{LOGGING_TAG} SportsData API Key: {self.api_key[:4] or "None"}")
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

    def gen_key(self, key: str) -> str:
        """Generate the internal sport:team key for unique lookup and storage."""
        return f"{self.name.lower()}:{key.lower()}"

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
                )
                self.teams[team.id] = team
            except SportsDataError:
                pass
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
        logger = logging.getLogger(__name__)
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
            home_id = event_description.get("GlobalHomeTeamID") or event_description.get(
                "GlobalHomeTeamId"
            )
            away_id = event_description.get("GlobalAwayTeamID") or event_description.get(
                "GlobalAwayTeamId"
            )
            home_name = event_description.get("HomeTeam") or event_description.get(
                "HomeTeamKey", "UNDEFINED_HOME"
            )
            away_name = event_description.get("AwayTeam") or event_description.get(
                "AwayTeamKey", "UNDEFINED_AWAY"
            )
            if not home_id or not away_id:
                logger.warning(
                    f"{LOGGING_TAG} Could not find team id for '{home_name}' vs '{away_name}' for {self.name}: {event_description}"
                )
                continue
            home_team = self.teams.get(home_id)
            away_team = self.teams.get(away_id)
            if not home_team or not away_team:
                logger.warning(
                    f"{LOGGING_TAG} Could not find team info for '{home_name}' vs '{away_name}' for {self.name}: {event_description}"
                )
            try:
                if "DateTimeUTC" in event_description:
                    date = datetime.fromisoformat(event_description["DateTimeUTC"]).replace(
                        tzinfo=timezone.utc
                    )
                else:
                    date = datetime.fromisoformat(event_description["DateTime"]).replace(
                        tzinfo=event_timezone
                    )
            # There have been incidents where an event returns "None" as a date value.
            # We should ignore that event, and allow processing to continue, but note
            # the error in case we need to escalate the problem.
            except TypeError:
                # It's possible to salvage this game by examining the other fields like "Day" or "Updated",
                # but if there's an error, it's probably wise to ignore this.
                logger.info(f"""{LOGGING_TAG}📈 sports.error.no_date ["sport" = "{self.name}"]""")
                continue
            # Ignore any events that are outside of the event interest window.
            if not start_window <= date <= end_window:
                continue
            terms = f"{home_team.terms} {away_team.terms}"
            updated = None
            # All "Updated" fields are always in ET.
            if event_description.get("Updated"):
                updated = datetime.fromisoformat(event_description["Updated"]).replace(
                    tzinfo=event_timezone
                )
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
                updated=updated,
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
        # Sample raw event
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
        logger = logging.getLogger(__name__)
        start_window = datetime.now(tz=timezone.utc) - self.event_ttl
        end_window = datetime.now(tz=timezone.utc) + self.event_ttl
        for event_description in data:
            # US sports use "(Away|Home)Team", Soccer uses "(Away|Home)TeamKey"
            home_id = event_description.get("HomeTeamID") or event_description.get("HomeTeamId")
            away_id = event_description.get("AwayTeamID") or event_description.get("AwayTeamId")
            if not home_id or not away_id:
                logger.warning(f"{LOGGING_TAG} Could not find team for event: {event_description}")
                continue
            home_team = self.teams.get(home_id)
            away_team = self.teams.get(away_id)
            if not home_team or not away_team:
                logger.warning(
                    f"{LOGGING_TAG} Could not find team info for event: {event_description}"
                )
                continue
            id = event_description.get("GlobalGameID") or event_description["GameId"]
            status = GameStatus.parse(event_description["Status"])
            # Ignore cancelled games.
            if status == GameStatus.Canceled:
                # Cancelled games have no UTC time stamp, so we can't know how recent they were.
                continue
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
                logger.info(f"""{LOGGING_TAG}📈 sports.error.no_date ["sport" = "{self.name}"]""")
                logger.debug(
                    f"{LOGGING_TAG} {self.name} Event {id} between {home_team.key} and {away_team.key} has no time, skipping [{ex}]"
                )
                continue
            # Ignore any events that are outside of the event interest window.
            if not start_window <= date <= end_window:
                continue
            terms = f"{home_team.terms} {away_team.terms}"
            # All "Updated" fields are always in ET.
            updated = None
            if event_description.get("Updated"):
                updated = datetime.fromisoformat(event_description["Updated"]).replace(
                    tzinfo=event_timezone
                )

            event = Event(
                sport=self.name,
                id=id,
                terms=terms,
                date=date,
                original_date=event_description.get(
                    "DateTimeUTC", event_description.get("DateTime")
                ),
                home_team=home_team.minimal(),
                away_team=away_team.minimal(),
                home_score=event_description["HomeTeamScore"],
                away_score=event_description["AwayTeamScore"],
                status=GameStatus.parse(event_description["Status"]),
                expiry=utc_time_from_now(self.event_ttl),
                updated=updated,
            )
            self.events[event.id] = event
        return self.events
