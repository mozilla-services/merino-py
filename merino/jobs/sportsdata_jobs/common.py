"""Commonly used functions for the SportsData.io functions"""

import logging
import json
import os
import time

from abc import abstractmethod
from datetime import datetime, timedelta
from enum import StrEnum
from dynaconf.base import Settings
from httpx import AsyncClient
from pydantic import BaseModel
from redis import ConnectionPool, ConnectionError, Redis, RedisError
from typing import Any
import typer

from merino.configs import settings
from merino.utils.http_client import create_http_client
from merino.jobs.sportsdata_jobs.data import Team, Event, DataStore
from merino.jobs.sportsdata_jobs.errors import SportDataError, SportDataWarning


DEFAULT_LOGGING_LEVEL = "INFO"
LOGGING_TAG = "⚾"

# INTERVAL PERIODS
ONE_MINUTE = 60
FIVE_MINUTES = ONE_MINUTE * 5  # for Standings
ONE_HOUR = ONE_MINUTE * 60
FOUR_HOURS = ONE_HOUR * 4  # For Team Profiles


# Enums
class GameStatus(StrEnum):
    """Enum of the normalized, valid, trackable game states.

    See https://support.sportsdata.io/hc/en-us/articles/14287629964567-Process-Guide-Game-Status
    """

    Scheduled = "scheduled"
    Delayed = "delayed"  # equivalent to "scheduled"
    Postponed = "postponed"  # equivalent to "scheduled"
    InProgress = "inprogress"
    Suspended = "suspended"  # equivalent to "inprogress"
    Cancelled = "cancelled"
    Final = "final"
    F_OT = "f/ot"  # Equivalent to "final"
    # other states can be ignored?

    @classmethod
    def is_final(cls, state: str) -> bool:
        return state.lower() in [cls.Final, cls.F_OT]

    @classmethod
    def is_scheduled(cls, state: str) -> bool:
        return state.lower() in [cls.Scheduled, cls.Delayed, cls.Postponed]

    @classmethod
    def is_in_progress(cls, state: str) -> bool:
        return state.lower() in [cls.InProgress, cls.Suspended]


async def fetch_data(client: AsyncClient, url: str) -> Any:
    response = await client.get(url)
    response.raise_for_status()
    return response.json()


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
    async def update(self, store: DataStore):
        """Update the data associated with this sport"""
        # once updated, remember to set the metadata to indicate last update time.


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
