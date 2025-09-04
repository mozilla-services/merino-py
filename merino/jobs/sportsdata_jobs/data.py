"""Sport Data constructs. These are used by both `job` and `suggest`"""

import json
import logging
from datetime import datetime, timedelta

from dynaconf.base import LazySettings
from pydantic import BaseModel
from redis import ConnectionPool, ConnectionError, Redis, RedisError
from typing import Any

from merino.utils.http_client import create_http_client
from merino.jobs.sportsdata_jobs.common import SportDate, SportDataError, SportDataWarning, DataStore, GameStatus
from merino.providers.suggest.sports import LOGGING_TAG


class Sport(BaseModel):
    """Wrapper class for often used sport data"""

    store: DataStore
    name: str
    is_active: bool
    season_start: SportDate | None
    season_end: SportDate | None
    updated: datetime

    def __init__(
        self,
        name: str,
        store: DataStore,
        api_key: str,
        is_active=False,
        updated: datetime = datetime.fromordinal(1),
    ):
        self.name = name
        self.store = store
        self.api_key = api_key
        self.is_active = is_active
        self.http_client = create_http_client(base_url="")
        self.updated = updated

    @classmethod
    def parse(cls, store: DataStore, string: str):
        parsed = json.loads(string)
        self = cls(
            store=store,
            name=parsed.get("name"),
            is_active=parsed.get("is_active"),
            api_key=parsed.get("api_key"),
            updated=parsed.get("updated"),
        )
        return self

    def as_str(self) -> str:
        return json.dumps(
            dict(
                name=self.name,
                api_key=self.api_key,
                is_active=self.is_active,
                updated=self.updated.isoformat(),
            )
        )

    async def poll_data(self):
        """More frequent refresh data for this sport"""

    async def events(self) -> None:
        """Get list of current and upcoming events"""
        logging.debug(f"{LOGGING_TAG} Getting timeframe for {self.name} ")
        URL = f"https://api.sportsdata.io/v3/{self.name.lower()}/scores/json/Timeframes/current?key={self.api_key}"
        response = await self.http_client.get(url=URL)
        response.raise_for_status()
        data = json.loads(response.content)
        # TODO: store the timeframe data

    async def get_teams(self) -> None:
        URL = f"https://api.sportsdata.io/v3/{self.name.lower()}/scores/json/teams?key={self.api_key}"
        response = await self.http_client.get(url=URL)
        response.raise_for_status()
        data = json.loads(response.content)
        # TODO: store the timeframe data


class Team(BaseModel):
    name: str
    key: str
    locale: str | None
    aliases: list[str]
    colors: list[str] | None
    updated: datetime

    @classmethod
    def parse(cls, sport: Sport, serialized: str):
        """Deserialize from JSON string"""
        struct = json.loads(serialized)
        if not sport.name == struct.get("key").split(":")[0]
        return cls(
            name=struct.get("name"),
            key=struct.get("key"),
            locale=struct.get("locale"),
            aliases=struct.get("aliases"),
            colors=struct.get("colors"),
            updated=struct.get("updated"),
        )

    def as_str(self) -> str:
        """Serialize to JSON string"""
        return json.dumps(self)


class Event(BaseModel):
    sport: Sport
    date: datetime
    # the team key for the home team
    home_team: str
    # the team key for the away team
    away_team: str
    home_score: int
    away_score: int
    # enum: "Pending", "Final"
    status: GameStatus

    @classmethod
    def parse(cls, sport: Sport, serialized: str):
        """Deserialize from JSON string"""
        parsed = json.loads(serialized)
        sport_name = parsed.get("sport_name")
        if sport_name != sport.name:
            raise SportDataError(
                f"Conflicting team name found in storage: {sport_name}"
            )
        try:
            status = GameStatus(parsed.get("status"))
        except ValueError as ex:
            logging.debug(f"""{LOGGING_TAG}⚠️ Unknown status: {parsed.get("status")}, ignoring""")
            raise SportDataWarning("Unknown game status, ignoring")
        self = cls(
            sport=sport,
            date=parsed.get("date"),
            home_team=parsed.get("home_team"),
            away_team=parsed.get("away_team"),
            home_score=parsed.get("home_score"),
            away_score=parsed.get("away_score"),
            status=GameStatus(parsed.get("status")),
        )
        return self

    def as_str(self) -> str:
        """Serialize to JSON string"""
        return json.dumps(self)

    def suggest_text(self, away:Team, home:Team) -> str:
        text = f"{away.name} at {home.name}"
        match self.status:
            case "Upcoming":
                text = f"{text} starts {self.date}"
            case "Final":
                text = f"{text} Final score: {self.away_score} - {self.home_score}"
            case _:
                text = f"{text} currently {self.away_score} - {self.home_score}"
        return text
