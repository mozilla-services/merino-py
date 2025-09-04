"""Various suggested jobs and utilities for managing SportsData.io content.

See https://sportsdata.io/developers/integration-guide for details.

There are several tasks that should be performed on a regular basis, these are
broken out into `nightly`, `hourly` and `10minute`, with a number of "plug-in"
elements to fetch and process the data appropriately. These three tasks are meant to be
called from a `cron` like function. These will require access to a centralized data
storage system (and will presume a Redis-like storage system)

"""

"""Perform nightly data fetch and cleanup"""

import asyncio
import logging
import typer
from datetime import datetime, timedelta
from httpx import AsyncClient
from dynaconf.base import Settings
from pydantic import BaseModel

from merino.jobs.sportsdata_jobs.common import (
    init_logs,
    DataStore,
    Sport,
    SportDataError,
    LOGGING_TAG,
    # NFL,
    # MLB,
    NBA,
    NHL,
    EPL,
    UCL,
)
from merino.configs import settings

LOGGING_TAG = "⚾"
UPDATE_PERIOD = 4 * 60 * 60  # Four hours


class Options:

    def __init__(self, base_settings: Settings):
        logger.debug(f"{LOGGING_TAG} Defining Options")
        # Currently no options to define.
        pass

    def get_command(self) -> typer.Typer:
        """Define the app name and help screen"""
        return typer.Typer(
            name="sports_data",
            help="Process SportsData.io content",
        )


class SportDataUpdater(BaseModel):
    # HTTP Client for fetching Data.
    client: AsyncClient
    # Data Storage backend
    store: DataStore
    # Collection of known sports
    sports: dict[str, Sport]
    # Copy of the general configuration
    settings: Settings

    def __init__(self, settings: Settings, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self.client = AsyncClient()
        self.store = DataStore(settings)
        if not settings.sports:
            raise SportDataError("No sports defined")

        for sport_name in [
            sport.strip().upper() for sport in settings.sports.split(",")
        ]:
            match sport_name:
                # case "NFL":
                #    sport = NFL(settings, self.store)
                # case "MLB":
                #    sport = MLB(settings, self.store)
                case "NBA":
                    sport = NBA(settings, self.store)
                case "NHL":
                    sport = NHL(settings, self.store)
                case "EPL":
                    sport = EPL(settings, self.store)
                case "UCL":
                    sport = UCL(settings, self.store)
                case _:
                    logger.warning(f"{LOGGING_TAG}⚠️ Ignoring sport {sport_name}")
                    continue
            self.sports[sport_name] = sport

    async def update(self) -> bool:
        """Perform sport specific updates."""
        for sport in self.sports.values():
            sport.update(self.store)

    async def refresh_sport(self, sport_name: str, force: bool = False):
        """Refresh the fetched sport data if needed."""
        # Does the stored data require refreshing?
        try:
            sport = await self.store.fetch(sport_name)
            if stored:
                if force or datetime.fromtimestamp(
                    stored["updated"]
                ) <= datetime.now() - timedelta(seconds=0 - UPDATE_PERIOD):
                    logging.debug(f"{LOGGING_TAG} Updating {sport_name}")
                    return
        except:
            logging.debug(f"{LOGGING_TAG}: Refreshing data for {self.name}")
        return True

    async def nightly(self) -> None:
        """Perform the nightly maintenance tasks"""
        for sport in self.sports:
            # Fetch the meta data for the sport, this includes if the sport is "active"
            # as well as any upcoming events for the sport.
            await sport.update()

    async def hourly(self) -> None:
        """Perform the hourly maintenance tasks"""
        for sport in self.sports:
            if not sport.is_active:
                continue
            await sport.poll_data()


logger = init_logs()
sports_settings = getattr(settings.providers, "sportsdata", None)
if not sports_settings:
    raise SportDataError(
        "Missing project configuration for `sportsdata`. Did you create it under providers?"
    )

app = Options(sports_settings).get_command()
provider = SportDataUpdater(sports_settings)


@app.command("nightly")
def nightly():
    """Perform the general nightly operations"""
    asyncio.run(provider.nightly())


@app.command("hourly")
def hourly():
    """Perform the hourly operations"""
    asyncio.run(provider.hourly())


if __name__ == "__main__":
    app()
