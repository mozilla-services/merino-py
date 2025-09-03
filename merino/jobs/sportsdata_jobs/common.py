"""Commonly used functions for the SportsData.io functions"""

import logging
import json
import os
import time

from abc import abstractmethod
from datetime import datetime, timedelta
from dynaconf.base import Settings
from httpx import AsyncClient
from pydantic import BaseModel
from redis import ConnectionPool, ConnectionError, Redis, RedisError
from typing import Any
import typer

from merino.configs import settings
from merino.utils.http_client import create_http_client
from merino.jobs.sportsdata_jobs.data import Team, Event


DEFAULT_LOGGING_LEVEL = "INFO"
LOGGING_TAG = "⚾"

# INTERVAL PERIODS
ONE_MINUTE = 60
FIVE_MINUTES = ONE_MINUTE * 5  # for Standings
ONE_HOUR = ONE_MINUTE * 60
FOUR_HOURS = ONE_HOUR * 4  # For Team Profiles


class SportDataError(BaseException):
    message: str

    def __init__(self, message: str):
        self.message = message

    def __str__(self):
        name = type(self).__name__
        return f"{name}: {self.message}"


async def fetch_data(client: AsyncClient, url: str) -> Any:
    response = await client.get(url)
    response.raise_for_status()
    return response.json()


class DataStore:
    pool: ConnectionPool
    data: dict[str, Any] | None

    def __init__(self, settings: Settings) -> None:
        try:
            self.client = ConnectionPool().from_url(settings.dsn)
            # TODO: fetch the meta data from the client and deser it into a dict.
            self.data = dict(is_active=False)
        except AttributeError as ex:
            logging.warning(f"{LOGGING_TAG}⚠️ Could not create DataStore pool: {ex}")
            raise SportDataError(f"No Connection Pool: {ex}")
        logging.info(f"{LOGGING_TAG} Connected to datastore {settings.sports.dsn}")

    async def active_sports(self) -> [str]:
        if self.data:
            return self.data.get("active", [])
        return []

    async def store_active_sports(self, sports: list[tuple[str, int]]):
        """store a list of active sports.

        `sports` should be a list of tuples of the sport id ("MLB", "NFL", etc) and the
        UTC timestamp for when the sport should be considered no longer "active". The
        sport will be automatically removed at that timestamp.
        """
        pass

    async def store_team_keywords(self, team: Team):
        """store the keywords to be associated with the sport.

        TODO: Make this specific to the Team?

        this will HSETEX {lowercase, normalized city | team name} {sport} {team_id}
        """
        # store all words: city, team name (remember to store combo names as individual words)
        pass

    async def store_event(self, event: Event):
        """Store the event as event:team:team"""

    async def store(self, data: dict[str, Any]):
        """Store the supplied data into our Datastore"""

    async def get_team(self, word):
        """Scan the keywords to see if we have a match for either a city or team"""


class Sport(BaseModel):
    api_key: str
    name: str
    http_client: AsyncClient
    teams: dict[str, Team]
    base_url: str

    def __init__(self, settings: Settings, *args, **kwargs):
        super().__init__(key=settings.get("key"), *args, **kwargs)
        self.base_url = settings.get(
            "base_url",
            default=f"https://api.sportsdata.io/v3/{self.name.lower()}/scores/json/",
        )

    @abstractmethod
    async def update(self, settings: Settings, store: DataStore):
        """Update the data associated with this sport"""


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


def init_logs() -> logging.Logger:
    """Initialize logging based on `PYTHON_LOG` environ)"""
    level = getattr(
        logging, os.environ.get("PYTHON_LOG", DEFAULT_LOGGING_LEVEL).upper(), None
    )
    logging.basicConfig(level=level)
    return logging.getLogger(__name__)


## TODO:
# add updater?


class NFL(Sport):
    """National Football League"""

    store: DataStore

    def __init__(self, *args, **kwargs):
        super().__init__(name="NFL", *args, **kwargs)

    async def update(self, settings: Settings, store: DataStore):
        """NFL requires a nightly "Timeframe" lookup."""
        logging.debug(f"{LOGGING_TAG} Getting timeframe for {self.name} ")
        URL = f"{self.base_url}/Timeframes/current?key={self.api_key}"
        response = await self.http_client.get(url=URL)
        response.raise_for_status()
        data = json.loads(response.content)
        # TODO: parse this out to get the current week and games.
        # see: https://sportsdata.io/developers/api-documentation/nfl#timeframesepl

    def event_ttl(self):
        return timedelta(days=7)


class MLB(Sport):
    """Major League Baseball"""

    store: DataStore

    def __init__(self, *args, **kwargs):
        super().__init__(name="MLB", *args, **kwargs)

    async def update(self, store: DataStore):
        # TODO: Fill in update
        pass

        return timedelta(days=3)

    def event_ttl(self):
        pass


class NBA(Sport):
    """National Basketball Association"""

    store: DataStore

    def __init__(self, *args, **kwargs):
        super().__init__(name="NBA", *args, **kwargs)

    async def update(self, store: DataStore):
        # TODO: Fill in update
        pass

        return timedelta(days=3)

    def event_ttl(self):
        pass


class NHL(Sport):
    """Major Hockey League"""

    store: DataStore

    def __init__(self, *args, **kwargs):
        super().__init__(name="NHL", *args, **kwargs)

    async def update(self, store: DataStore):
        # TODO: Fill in update
        pass

        return timedelta(days=3)

    def event_ttl(self):
        pass


class EPL(Sport):
    """English Premier League"""

    store: DataStore

    def __init__(self, *args, **kwargs):
        super().__init__(name="EPL", *args, **kwargs)
        # EPL is a league beneath the general "soccer" sport.
        self.base_url = f"https://api.sportsdata.io/v4/soccer/scores/json"

    async def update(self, store: DataStore):
        """Fetch and update the Team Standing information."""
        # TODO: Fill in update
        # fetch the Standings data: (5 min interval)
        """

        """
        standings_url = f"{self.base_url}/Standings/{self.name}?key={self.api_key}"
        response = await self.http_client.get(standings_url)
        response.raise_for_status()
        raw_data = response.json()
        for round in raw_data:
            pass
        return

    def event_ttl(self):
        pass


class UCL(Sport):
    """English Premier League"""

    store: DataStore

    def __init__(self, *args, **kwargs):
        super().__init__(name="MLS", *args, **kwargs)

    def team_key(self, short: str) -> str:
        return f"{self.name.lower()}:{short.lower()}"

    async def get_teams(self):
        """fetch the Standings data: (4 hour interval)"""
        # https://api.sportsdata.io/v4/soccer/scores/json/Teams/ucl?key=
        # Sample:
        """
        [
        {
            "TeamId": 509,
            "AreaId": 68,
            "VenueId": 2,
            "Key": "ARS",
            "Name": "Arsenal FC",
            "FullName": "Arsenal Football Club ",
            "Active": true,
            "AreaName": "England",
            "VenueName": "Emirates Stadium",
            "Gender": "Male",
            "Type": "Club",
            "Address": null,
            "City": null,
            "Zip": null,
            "Phone": null,
            "Fax": null,
            "Website": "http://www.arsenal.com",
            "Email": null,
            "Founded": 1886,
            "ClubColor1": "Red",
            "ClubColor2": "White",
            "ClubColor3": null,
            "Nickname1": "The Gunners",
            "Nickname2": null,
            "Nickname3": null,
            "WikipediaLogoUrl": "https://upload.wikimedia.org/wikipedia/en/5/53/Arsenal_FC.svg",
            "WikipediaWordMarkUrl": null,
            "GlobalTeamId": 90000509
        },
        ...
        ]
        """
        url = f"{self.base_url}/Teams/{self.name}?key={self.api_key}"
        data = await fetch_data(self.http_client, url)
        for team_data in data:
            team = Team(
                key=self.team_key(team_data.get("Key")),
                name=team_data.get("Name"),
                locale=" ".join(
                    [team_data.get("City"), team_data.get("AreaName")]
                ).strip(),
                aliases=list(
                    filter(
                        lambda x: x is not None,
                        [
                            team_data.get("FullName"),
                            team_data.get("Nickname1"),
                            team_data.get("Nickname2"),
                            team_data.get("Nickname3"),
                        ],
                    )
                ),
                updated=datetime.now(),
                colors=list(
                    filter(
                        lambda x: x is not None,
                        [
                            team_data.get("ClubColor1"),
                            team_data.get("ClubColor2"),
                            team_data.get("ClubColor3"),
                        ],
                    )
                ),
            )

    async def get_events(self):
        """Fetch the events for this sport. (5min interval)"""
        # Sample:
        """
        [
        {
            "GameId": 79507,
            "RoundId": 1499,
            "Season": 2025,
            "SeasonType": 3,
            "Group": null,
            "AwayTeamId": 587,
            "HomeTeamId": 2776,
            "VenueId": 9953,
            "Day": "2024-07-09T00:00:00",
            "DateTime": "2024-07-09T15:30:00",
            "Status": "Final",
            "Week": null,
            "Winner": "HomeTeam",
            "VenueType": "Home Away",
            "AwayTeamKey": "HJK",
            "AwayTeamName": "Helsingin JK",
            "AwayTeamCountryCode": "FIN",
            "AwayTeamScore": 0,
            "AwayTeamScorePeriod1": 0,
            "AwayTeamScorePeriod2": 0,
            "AwayTeamScoreExtraTime": null,
            "AwayTeamScorePenalty": null,
            "HomeTeamKey": "PAN",
            "HomeTeamName": "FK Panevėžys",
            "HomeTeamCountryCode": "LTU",
            "HomeTeamScore": 3,
            "HomeTeamScorePeriod1": 1,
            "HomeTeamScorePeriod2": 2,
            "HomeTeamScoreExtraTime": null,
            "HomeTeamScorePenalty": null,
            "Updated": "2024-07-10T05:46:08",
            "UpdatedUtc": "2024-07-10T09:46:08",
            "GlobalGameId": 90079507,
            "GlobalAwayTeamId": 90000587,
            "GlobalHomeTeamId": 90002776,
            "IsClosed": true,
            "PlayoffAggregateScore": null
        },
        """
        url = f"{self.base_url}/Teams/{self.name}?key={self.api_key}"
        data = await fetch_data(self.http_client, url)
        start_window = datetime.now() - timedelta(days=-7)
        end_window = datetime.now() + timedelta(days=7)
        for raw in data:
            event_date = datetime.fromisoformat(raw.get("DateTime"))
            if start_window <= event_date <= end_window:
                event = Event(
                    sport=self,
                    date=event_date,
                    home_team=self.team_key(raw.get("HomeTeamKey")),
                    away_team=self.team_key(raw.get("AwayTeamKey")),
                    home_score=int(raw.get("HomeTeamScore")),
                    away_score=int(raw.get("AwayTeamScore")),
                    status=raw.get("status"),
                )

    async def update(self):
        """Fetch and update the Team information."""
        await self.get_teams()
        await self.get_events()

        return timedelta(days=3)

    def event_ttl(self):
        pass
