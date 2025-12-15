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
import sys
from time import time
from datetime import datetime, timedelta, timezone
from httpx import AsyncClient
from dynaconf.base import LazySettings
from typing import cast

from aiodogstatsd import Client

from merino.configs import settings
from merino.providers.suggest.sports import LOGGING_TAG
from merino.providers.suggest.sports.backends.sportsdata.common.data import Sport
from merino.providers.suggest.sports.backends.sportsdata.common.error import (
    SportsDataError,
)
from merino.providers.suggest.sports.backends.sportsdata.common.elastic import (
    SportsDataStore,
    ElasticCredentials,
)
from merino.providers.suggest.sports.backends.sportsdata.common.sports import (
    NFL,
    NBA,
    NHL,
    # UCL,
    # MLB,
    # EPL,
)
from merino.utils.http_client import create_http_client


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
        store: SportsDataStore,
        connect_timeout: int = 1,
        read_timeout: int = 1,
        *args,
        **kwargs,
    ) -> None:
        logger = logging.getLogger(__name__)
        logger.info(f"{LOGGING_TAG} Python: {sys.version}")
        active_sports = [sport.strip().upper() for sport in settings.sports]
        sport: Sport | None = None
        sports: dict[str, Sport] = {}
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
                    logger.warning(f"{LOGGING_TAG}⚠️ Ignoring sport {sport_name}")
                    continue
            sports[sport_name] = sport
        self.sports = sports
        self.store = store
        self.connect_timeout = connect_timeout
        self.read_timeout = read_timeout
        logger.debug(f"{LOGGING_TAG}: Starting up...")

    async def update(self, include_teams: bool = True, client: AsyncClient | None = None) -> bool:
        """Perform sport specific updates."""
        logger = logging.getLogger(__name__)
        logger.debug(f"{LOGGING_TAG} Initializing database")
        await self.store.startup()
        await self.store.build_indexes()
        client = create_http_client(
            connect_timeout=self.connect_timeout, request_timeout=self.read_timeout
        )

        for sport in self.sports.values():
            # Update the team information, this will try to use a query cache with a lifespan of 4 hours
            # which matches the recommended query period for SportsData.
            if include_teams:  # pragma: no cover
                start = time()
                await sport.update_teams(client=client)
                logger.info(
                    f"""{LOGGING_TAG} sports.time.update.team: ["sport": {sport.name}] = {time() - start}"""
                )
            # Update the current and upcoming game schedules (using a cache with a lifespan of 5 minutes)
            start = time()
            await sport.update_events(client=client)
            logger.info(
                f"""{LOGGING_TAG} sports.time.update.event: ["sport": {sport.name}] = {time() - start}"""
            )
            # Put the data in the shared storage for the live query.
            start = time()
            await self.store.store_events(sport, language_code="en")
            logger.info(
                f"""{LOGGING_TAG} sports.time.load.events ["sport": {sport.name}] = {time() - start}"""
            )
        await self.store.shutdown()
        return True

    async def nightly(self, client: AsyncClient | None = None) -> None:
        """Perform the nightly maintenance tasks"""
        logger = logging.getLogger(__name__)
        logger.debug(f"{LOGGING_TAG} Initializing database")
        await self.store.startup()
        # Drop the prior indexes: Note, this may lose older games.
        await self.store.build_indexes(clear=True)

        # Fetch the meta data for the sport, this includes if the sport is "active"
        # as well as any upcoming events for the sport.
        logger.debug(f"{LOGGING_TAG} Nightly update...")
        await self.update(include_teams=True, client=client)
        await self.store.prune()
        await self.store.shutdown()

    async def initialize(self) -> None:
        """Initialize the ElasticSearch data store"""
        await self.store.startup()
        await self.store.build_indexes(clear=True)

    async def quick_update(self, client: AsyncClient | None = None) -> None:
        """Perform a 'quick' update for events that changed recently"""
        logger = logging.getLogger(__name__)
        logger.debug(f"{LOGGING_TAG} starting database")
        start = time()
        await self.store.startup()
        try:
            last_update = datetime.fromisoformat(await self.store.query_meta("last_update"))
        except Exception as ex:
            logger.error(f"{LOGGING_TAG} quick_update date error {ex}")
            last_update = datetime.now(tz=timezone.utc) - timedelta(minutes=5)
        client = create_http_client(
            connect_timeout=self.connect_timeout, request_timeout=self.read_timeout
        )
        for sport in self.sports.values():
            start = time()
            await sport.update_events(client=client, allow_no_teams=True)
            logger.info(
                f"""{LOGGING_TAG} sports.time.quick_update.event ["sport": {sport.name}] = {time() - start}"""
            )
            start = time()
            await self.store.update_events(sport, language_code="en", last_update=last_update)
            logger.info(
                f"""{LOGGING_TAG} sports.time.quick_update.update ["sport": {sport.name}] = {time() - start}"""
            )
        await self.store.shutdown()


logger = logging.getLogger(__name__)
sports_settings = settings.providers.sports
# If there are no explicit elastic search values defined for sports,
# use the existing wikipedia values.
# NOTE: eventually, this will be replaced when the elasticsearch code
# is moved to `/utils`
elastic_credentials = ElasticCredentials(settings=settings)
app = Options(sports_settings).get_command()
cli = typer.Typer(
    name="fetch_sports",
    help="Commands to fetch and store sport information",
)
name = sports_settings.get("platform", "sports")
platform = f"{name}-{{lang}}"
event_map = sports_settings.get("event_index", f"{platform}-event")
meta_map = sports_settings.get("meta_index", f"{name}-meta")
provider = None
if elastic_credentials.validate():
    try:
        store = SportsDataStore(
            credentials=elastic_credentials,
            platform=platform,
            languages=[lang for lang in sports_settings.get("languages", ["en"])],
            index_map={"event": event_map},
        )
        provider = SportDataUpdater(
            settings=sports_settings,
            store=store,
            connect_timeout=sports_settings.get("connect_timeout"),
            read_timeout=sports_settings.get("read_timeout"),
        )
    except Exception as ex:
        # except SportsDataError as ex:
        logger.error(f"{LOGGING_TAG} Sports Unavailable: {ex}")
else:
    logger.error(f"{LOGGING_TAG} Sports Unavailable: Missing Elasticsearch Credentials:")


@cli.command("initialize")
def initialize():  # pragma: no cover
    """Build the indexes and initialize the ES tables"""
    if provider:
        asyncio.run(provider.initialize(sports_settings))
    else:
        logger.error("Sports provider unavailable.")


@cli.command("nightly")
def nightly():  # pragma: no cover
    """Perform the general nightly operations"""
    if provider:
        asyncio.run(provider.nightly())
    else:
        logger.error("Sports provider unavailable.")


@cli.command("update")
def update():  # pragma: no cover
    """Perform the frequently required tasks (Approx once every 5 min)"""
    if provider:
        asyncio.run(provider.update())
    else:
        logger.error("Sports provider unavailable.")


@cli.command("quickup")
def quick_update():  # pragma: no cover
    """Perform a 'quick' update, which only changes scores & status for known sport events that changed recently"""
    if provider:
        asyncio.run(provider.quick_update())
    else:
        logger.error("Sports provider unavailable")


if __name__ == "__main__":
    cli()
