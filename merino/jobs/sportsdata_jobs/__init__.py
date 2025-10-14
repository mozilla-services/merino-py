"""Various suggested jobs and utilities for managing SportsData.io content.

See https://sportsdata.io/developers/integration-guide for details.

There are several tasks that should be performed on a regular basis, these are
broken out into `nightly`, `hourly` and `5minute`, with a number of "plug-in"
elements to fetch and process the data appropriately. These three tasks are meant to be
called from a `cron` like function.

NOTE: `sport.update_teams(...)` will attempt to read a locally cached file (see
`settings.providers.sports.sportsdata.cache_dir`). The cache time on these files is
hardcoded in the calling function for now, but is based on the file creation time.

    * Add tests (unit and integration)
    * Address TODOs
    * Document


"""

import asyncio
import typer
from httpx import AsyncClient, Timeout
from dynaconf.base import LazySettings
from pydantic import BaseModel
from typing import cast

from merino.configs import settings
from merino.providers.suggest.sports import init_logs, LOGGING_TAG
from merino.providers.suggest.sports.backends.sportsdata.common.data import Sport
from merino.providers.suggest.sports.backends.sportsdata.common.elastic import (
    SportsDataStore,
)
from merino.providers.suggest.sports.backends.sportsdata.common.error import (
    SportsDataError,
)
from merino.providers.suggest.sports.backends.sportsdata.common.sports import (
    NFL,
    NBA,
    NHL,
    # MLB,
    # EPL,
    # UCL,
)


class Options:
    """Application level options for the Sports importer"""

    def __init__(self, base_settings: LazySettings):
        """Local options"""
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
    """Fetch and update SportsData info"""

    # HTTP Client for fetching Data.
    client: AsyncClient
    # Data Storage backend
    store: SportsDataStore
    # Collection of known sports
    sports: dict[str, Sport]
    # Copy of the general configuration
    settings: LazySettings

    def __init__(self, settings: LazySettings, *args, **kwargs) -> None:
        log = init_logs()
        super().__init__(*args, **kwargs)
        if not settings.sports:
            raise SportsDataError("No sports defined")
        self.log = log
        log.debug(f"{LOGGING_TAG}: Starting up...")
        platform = settings.providers.sports.get("platform", "sports")
        active_sports = [
            sport.strip().upper() for sport in settings.providers.sports.sports.split(",")
        ]
        self.store = SportsDataStore(
            dsn=settings.providers.sports.es.dsn,
            api_key=settings.providers.sports.es.api_key,
            languages=[
                lang.strip().lower()
                for lang in settings.providers.sports.get("languages", "en").split(",")
            ],
            platform=f"{{lang}}_{platform}",
            index_map={
                # "meta": settings.providers.sports.get(
                #     "meta_index", f"{self.platform}_meta"
                # ),
                # "team": settings.providers.sports.get(
                #     "team_index", f"{self.platform}_team"
                # ),
                "event": cast(
                    str,
                    settings.providers.sports.get("event_index", f"{platform}_event"),
                ),
            },
            settings=settings,
        )
        sport: Sport | None = None
        # We could be clever here, but we'd have to fight the style and type checkers.
        # Basically, you import the merino...sports module, then
        # `getattr[sys.modules["merino...sports"],sport_name](settings,api_key)`
        # which would allow you to not have to explicitly import and specify the sport class.
        for sport_name in active_sports:
            match sport_name:
                case "NFL":
                    sport = NFL(settings=settings)
                # case "MLB":
                #    sport = MLB(settings, self.store)
                case "NBA":
                    sport = NBA(settings, self.store)
                case "NHL":
                    sport = NHL(settings, self.store)
                # case "EPL":
                #    sport = EPL(settings, self.store)
                # case "UCL":
                #    sport = UCL(settings=settings)
                case _:
                    logger.warning(f"{LOGGING_TAG}⚠️ Ignoring sport {sport_name}")
                    continue
            self.sports[sport_name] = sport

    async def update(self) -> bool:
        """Perform sport specific updates."""
        timeout = Timeout(
            3,
            connect=self.settings.providers.sports.sportsdata.get("connect_timeout", 1),
            read=settings.providers.sports.sportsdata.get("read_timeout", 1),
        )
        client = AsyncClient(timeout=timeout)
        for sport in self.sports.values():
            # Update the team information, this will try to use a query cache with a lifespan of 4 hours
            # which matches the recommended query period for SportsData.
            await sport.update_teams(client=client)
            # Update the current and upcoming game schedules (using a cache with a lifespan of 5 minutes)
            await sport.update_events(client=client)
            # Put the data in the shared storage for the live query.
            await self.store.store_events(sport, language_code="en")
        await self.store.shutdown()
        return True

    async def nightly(self) -> None:
        """Perform the nightly maintenance tasks"""
        for sport in self.sports.values():
            # Fetch the meta data for the sport, this includes if the sport is "active"
            # as well as any upcoming events for the sport.
            await self.update()
        await self.store.prune()

    async def hourly(self) -> None:
        """Perform the hourly maintenance tasks"""
        await self.update()


logger = init_logs()
sports_settings = getattr(settings.providers, "sportsdata", None)
if not sports_settings:
    raise SportsDataError(
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
