"""Various suggested jobs and utilities for managing SportsData.io content.

See https://sportsdata.io/developers/integration-guide for details.

There are several tasks that should be performed on a regular basis, these are
broken out into `nightly`, and `update`, with a number of "plug-in"
elements to fetch and process the data appropriately. These three tasks are meant to be
called from a `cron` like function.

Per the recommendation of the team, these jobs will be invoked by AirFlow
(See `telemetry-airflow/dags/merino_jobs.py`). Per the documents, it is presumed that
AirFlow job manager will use the latest `merino` image (see
`docs/operations/jobs/dynamic-wiki-indexer.md`), and as such, the `merino.config.settings`
will be constructed and imported using the defined Environment and config file settings.

NOTE: `sport.update_teams(...)` will attempt to read a locally cached file (see
`settings.sportsdata.cache_dir`). The cache time on these files is
hardcoded in the calling function for now, but is based on the file creation time.

"""

import asyncio
import logging
import typer
from httpx import AsyncClient, Timeout
from dynaconf.base import LazySettings
from typing import cast

from aiodogstatsd import Client

from merino.configs import settings
from merino.utils.metrics import get_metrics_client
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
    # UCL,
    # MLB,
    # EPL,
)


class Options:
    """Application level options for the Sports importer"""

    def __init__(self, base_settings: LazySettings):
        """Local options"""
        # Currently no options to define.
        pass

    def get_command(self) -> typer.Typer:
        """Define the app name and help screen"""
        return typer.Typer(
            name="sports_data",
            help="Process SportsData.io content",
        )


class SportDataUpdater:
    """Fetch and update SportsData info"""

    # Collection of known sports
    sports: dict[str, Sport]
    store: SportsDataStore
    connect_timeout: int
    read_timeout: int
    # Copy of the general configuration
    # settings: LazySettings

    def __init__(
        self,
        settings: LazySettings,
        *args,
        store: SportsDataStore | None = None,
        **kwargs,
    ) -> None:
        if not settings.sports:
            raise SportsDataError("No sports defined")
        active_sports = [sport.strip().upper() for sport in settings.sports.split(",")]
        sport: Sport | None = None
        sports: dict[str, Sport] = {}
        platform = settings.get("platform", "sports")
        store = store or SportsDataStore(
            dsn=settings.es.dsn,
            api_key=settings.es.api_key,
            languages=[
                lang.strip().lower() for lang in settings.get("languages", "en").split(",")
            ],
            platform=f"{{lang}}_{platform}",
            index_map={
                "event": cast(
                    str,
                    settings.get("event_index", f"{platform}_event"),
                ),
            },
        )
        # We could be clever here, but we'd have to fight the style and type checkers.
        # Basically, you import the merino...sports module, then
        # `getattr[sys.modules["merino...sports"],sport_name](settings,api_key)`
        # which would allow you to not have to explicitly import and specify the sport class.
        for sport_name in active_sports:
            match sport_name:
                case "NFL":
                    sport = NFL(settings)
                case "NBA":
                    sport = NBA(settings)
                case "NHL":
                    sport = NHL(settings)
                # case "UCL":
                #    sport = UCL(settings)
                # case "MLB":
                #    sport = MLB(settings)
                # case "EPL":
                #    sport = EPL(settings)
                case _:
                    logging.warning(f"{LOGGING_TAG}⚠️ Ignoring sport {sport_name}")
                    continue
            sports[sport_name] = sport
        self.metrics = get_metrics_client()
        self.sports = sports
        self.store = store
        self.connect_timeout = settings.sportsdata.get("connect_timeout", 1)
        self.read_timeout = settings.sportsdata.get("read_timeout", 1)
        logging.debug(f"{LOGGING_TAG}: Starting up...")

    async def update(self, include_teams: bool = True, client: AsyncClient | None = None) -> bool:
        """Perform sport specific updates."""
        metrics = get_metrics_client()
        timeout = Timeout(
            3,
            connect=self.connect_timeout,
            read=self.read_timeout,
        )

        client = client or AsyncClient(timeout=timeout)

        for sport in self.sports.values():
            # Update the team information, this will try to use a query cache with a lifespan of 4 hours
            # which matches the recommended query period for SportsData.
            if include_teams:  # pragma: no cover
                with metrics.timeit("sports.time.load.team", tags={"sport": sport.name}):
                    await sport.update_teams(client=client)
            # Update the current and upcoming game schedules (using a cache with a lifespan of 5 minutes)
            with metrics.timeit("sports.time.update.events", tags={"sport": sport.name}):
                await sport.update_events(client=client)
            # Put the data in the shared storage for the live query.
            with metrics.timeit("sports.time.load.events", tags={"sport": sport.name}):
                await self.store.store_events(sport, language_code="en")
        await self.store.shutdown()
        return True

    async def nightly(self, client: AsyncClient | None = None) -> None:
        """Perform the nightly maintenance tasks"""
        # Fetch the meta data for the sport, this includes if the sport is "active"
        # as well as any upcoming events for the sport.
        logging.debug(f"{LOGGING_TAG} Nightly update...")
        await self.update(include_teams=True, client=client)
        await self.store.prune()


sports_settings = getattr(settings.providers, "sports", None)
if not sports_settings:
    raise SportsDataError(
        "Missing project configuration for `sports`. Did you create it under providers?"
    )
else:
    if not sports_settings.get("es"):
        sports_settings["es"] = {}
    if not sports_settings.es.get("api_key"):
        logging.warning(f"{LOGGING_TAG} No sport elasticsearch API key found, using alternate")
        sports_settings.es["api_key"] = settings.providers.wikipedia.es_api_key
    if not sports_settings.es.get("dsn"):
        logging.warning(f"{LOGGING_TAG} No sport elasticsearch DSN found, using alternative")
        sports_settings.es["dsn"] = settings.providers.wikipedia.es_url
app = Options(sports_settings).get_command()
cli = typer.Typer(
    name="fetch_sports",
    help="Commands to fetch and store sport information",
)
provider = SportDataUpdater(sports_settings)


@cli.command("nightly")
def nightly():
    """Perform the general nightly operations"""
    asyncio.run(provider.nightly())


@cli.command("update")
def update():
    """Perform the frequently required tasks (Approx once every 5 min)"""
    asyncio.run(provider.update())


if __name__ == "__main__":
    cli()
