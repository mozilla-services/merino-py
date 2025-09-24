"""Data Types for Sports"""

# from __future__ import annotations

import json
import logging

from abc import abstractmethod
from datetime import datetime, timedelta, timezone
from typing import Any, Final

from dynaconf.base import LazySettings
from httpx import AsyncClient
from pydantic import BaseModel

from merino.configs import settings
from merino.providers.suggest.sports import (
    LOGGING_TAG,
    TEAM_TTL_WEEKS,
    EVENT_TTL_WEEKS,
    ttl_from_now,
)

from merino.providers.suggest.sports.backends.sportsdata.common import (
    GameStatus,
)

UTC_TIME_FORMAT: Final[str] = "%Y-%m-%dT%H:%M:%S"


class SportDate:
    instance: datetime
    """Return the current date in SportsData compliant format"""

    def __init__(self):
        self.instance = datetime.now()
        pass

    def __str__(self) -> str:
        return self.instance.strftime("%Y-%b-%d")

    def parse(self, parse: str):
        self.instance = datetime.strptime(parse, "%Y-%b-%d")


# TODO: refactor up to `.../sports`?
class Team(BaseModel):
    # Search terms for elastic search
    terms: str
    #  Team long name
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
    ttl: int

    def as_str(self) -> str:
        """Serialize to JSON string"""
        return json.dumps(self)

    @classmethod
    def from_data(
        cls, team_data: dict[str, Any], term_filter: list[str], team_ttl: timedelta
    ):
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
        logging.debug(f"{LOGGING_TAG} - Team: {team_data.get("Name")}")
        return cls(
            terms=" ".join(terms),
            key=team_data["Key"],
            name=team_data.get("FullName", team_data["Name"]),
            locale=" ".join(
                [team_data.get("City", ""), team_data.get("AreaName", "")]
            ).strip(),
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
            ttl=ttl_from_now(team_ttl),
            colors=list(
                filter(
                    lambda x: x is not None,
                    [
                        # Some Teams use "ClubColor#"
                        team_data.get("PrimaryColor"),
                        team_data.get("SecondaryColor"),
                        team_data.get("TertiaryColor"),
                        team_data.get("QuaternaryColor"),
                    ],
                )
            ),
        )

    def minimal(self) -> dict[str, Any]:
        """Return the minimal version of the team info used in Events"""
        return dict(key=self.key, name=self.name, colors=self.colors)


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
    # How long to retain an event in seconds
    ttl: int

    def suggest_text(self, away: Team, home: Team) -> str:
        """TODO: Event suggest format as JSON"""
        text = f"{away.name} at {home.name}"
        match self.status:
            case GameStatus.Scheduled | GameStatus.Delayed:
                text = f"{text} starts {self.date}"
            case GameStatus.Final | GameStatus.F_OT:
                text = f"{text} Final score: {self.away_score} - {self.home_score}"
            case _:
                text = f"{text} {self.status.as_str()}: {self.away_score} - {self.home_score}"
        return text

    def as_json(self) -> dict[str, Any]:
        return dict(
            terms=self.terms,
            sport=self.sport,
            id=self.id,
            date=int(self.date.timestamp()),
            home_team=self.home_team,
            away_team=self.away_team,
            home_score=self.home_score,
            away_score=self.away_score,
            status=self.status.as_str(),
            ttl=self.ttl,
        )


class Sport(BaseModel):
    """Root Model for Sport data"""

    api_key: str
    name: str
    teams: dict[str, Team]
    events: list[Event]
    base_url: str
    event_ttl: timedelta
    team_ttl: timedelta
    # Commented because Pydantic does not know how to generate a core schema
    # http_client: AsyncClient
    # event_store: ElasticDataStore
    term_filter: list[str]
    cache_dir: str | None

    def __init__(self, settings: LazySettings, *args, **kwargs):
        logging.debug(f"{LOGGING_TAG} In sport")
        # Set defaults for overrides
        if "event_ttl" not in kwargs:
            kwargs.update(
                {
                    "event_ttl": timedelta(
                        weeks=settings.providers.sports.get(
                            "event_ttl_weeks", EVENT_TTL_WEEKS
                        )
                    )
                }
            )
        if "team_ttl" not in kwargs:
            kwargs.update(
                {
                    "team_ttl": timedelta(
                        weeks=settings.providers.sports.get(
                            "team_ttl_weeks", TEAM_TTL_WEEKS
                        )
                    )
                }
            )
        if "term_filter" not in kwargs:
            kwargs.update({"term_filter": []})
        super().__init__(
            *args,
            **kwargs,
        )

    def gen_key(self, key: str) -> str:
        return f"{self.name.lower()}:{key.lower()}"

    @abstractmethod
    def get_team(self, key: str) -> Team:
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

    def load_events_from_source(self, data: list[dict[str, Any]]) -> list["Event"]:
        """ "Scan the list of events for any event within the 'current' window.

        This presumes that we are receiving data that complies with the SportsData.io
        `Team` data dictionary (See https://sportsdata.io/developers/data-dictionary/nfl#team)

        If we ever have a different data provider, this will need to be moved to the
        SportData provider class.

        """
        self.events = []
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
            # TODO: put this in Event.from_data()?
            date = datetime.fromisoformat(event_description["DateTimeUTC"]).replace(
                tzinfo=timezone.utc
            )
            # Ignore any events that are outside of the event interest window.
            if not start_window <= date <= end_window:
                continue
            home_team = self.teams[event_description["HomeTeam"]]
            away_team = self.teams[event_description["AwayTeam"]]
            terms = f"event {home_team.terms} vs {away_team.terms} game match "
            event = Event(
                sport=self.name,
                id=event_description["GlobalGameID"],
                terms=terms,
                date=datetime.strptime(
                    event_description["DateTimeUTC"], UTC_TIME_FORMAT
                ),
                home_team=home_team.minimal(),
                away_team=away_team.minimal(),
                home_score=event_description["HomeScore"],
                away_score=event_description["AwayScore"],
                status=GameStatus.from_str(event_description["Status"]),
                ttl=ttl_from_now(self.event_ttl),
            )
            self.events.append(event)
        return self.events
