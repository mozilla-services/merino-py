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
import copy
import logging
import signal
import typer
import sys
from time import monotonic, time
from datetime import datetime, timedelta, timezone
from httpx import AsyncClient
from dynaconf.base import LazySettings
from typing import TYPE_CHECKING
from sentry_sdk.crons import monitor

if TYPE_CHECKING:
    from sentry_sdk._types import MonitorConfig

from merino.configs import settings
from merino.cache.redis import RedisAdapter, create_redis_clients
from merino.cache.none import NoCacheAdapter

from merino.providers.suggest.sports import LOGGING_TAG, UPDATE_PERIOD_SECS
from merino.providers.suggest.sports.backends.sportsdata.common.data import Sport
from merino.providers.suggest.sports.backends.sportsdata.common.elastic import (
    SportsDataStore,
    ElasticCredentials,
)
from merino.providers.suggest.sports.backends.sportsdata.common._metrics import (
    wcs_job_state_counter,
)
from merino.providers.suggest.sports.backends.sportsdata.common.sports import (
    NFL,
    NBA,
    NHL,
    MLB,
    UCL,
    WCS,
    # EPL,
)
from merino.utils.http_client import create_http_client
from merino.utils.metrics import get_metrics_client


# Sentry monitor config for WCS cron jobs
wcs_monitor_config: "MonitorConfig" = {
    "schedule": {"type": "crontab", "value": "*/3 * * * *"},
    # If an expected check-in doesn't come in `checkin_margin`
    # minutes, it'll be considered missed
    "checkin_margin": 1,
    # The check-in is allowed to run for `max_runtime` minutes
    # before it's considered failed
    "max_runtime": 3,
    # It'll take `failure_issue_threshold` consecutive failed
    # check-ins to create an issue
    "failure_issue_threshold": 2,
    # It'll take `recovery_threshold` OK check-ins to resolve
    # an issue
    "recovery_threshold": 3,
}


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
    client: AsyncClient
    cache: RedisAdapter | NoCacheAdapter

    # Copy of the general configuration
    # settings: LazySettings

    def __init__(
        self,
        settings: LazySettings,
        store: SportsDataStore,
        connect_timeout: int = 1,
        read_timeout: int = 1,
        cache: RedisAdapter | NoCacheAdapter = NoCacheAdapter(),
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
                case "UCL":
                    sport = UCL(settings)
                case "MLB":
                    sport = MLB(settings)
                case "WCS":
                    sport = WCS(settings, cache=cache)
                # case "EPL":
                #    sport = EPL(settings)
                case _:
                    logger.warning(f"{LOGGING_TAG}⚠️ Ignoring sport {sport_name}")
                    continue
            sports[sport_name] = sport
        self.sports = sports
        self.store = store
        self.cache = cache
        self.connect_timeout = connect_timeout
        self.read_timeout = read_timeout
        self.client = create_http_client(
            connect_timeout=self.connect_timeout, request_timeout=self.read_timeout
        )
        logger.debug(f"{LOGGING_TAG}: Starting up...")

    async def update_data(
        self, include_teams: bool = True, client: AsyncClient | None = None
    ) -> bool:
        """Perform sport specific updates."""
        logger = logging.getLogger(__name__)
        logger.debug(f"{LOGGING_TAG} Initializing database")
        await self.store.startup()

        for sport in self.sports.values():
            # Update the team information, this will try to use a query cache with a lifespan of 4 hours
            # which matches the recommended query period for SportsData.
            if include_teams:  # pragma: no cover
                start = time()
                await sport.update_teams(client=self.client)
                logger.info(
                    f"""{LOGGING_TAG} sports.time.update.team: ["sport": {sport.name}] = {time() - start}"""
                )
            # Update the current and upcoming game schedules (using a cache with a lifespan of 5 minutes)
            start = time()
            await sport.update_events(client=self.client)
            logger.info(
                f"""{LOGGING_TAG} sports.time.update.event: ["sport": {sport.name}] = {time() - start}"""
            )
            # Put the data in the shared storage for the live query.
            start = time()
            await self.store.store_events(sport, language_code="en")
            logger.info(
                f"""{LOGGING_TAG} sports.time.load.events ["sport": {sport.name}] = {time() - start}"""
            )
        return True

    async def nightly(self) -> None:
        """Perform the nightly maintenance tasks"""
        logger = logging.getLogger(__name__)
        logger.debug(f"{LOGGING_TAG} Initializing database")
        await self.store.startup()

        # Fetch the meta data for the sport, this includes if the sport is "active"
        # as well as any upcoming events for the sport.
        logger.debug(f"{LOGGING_TAG} Nightly update...")
        await self.update_data(include_teams=True)
        await self.store.prune()
        await self.store.shutdown()

    async def initialize(self) -> None:
        """Initialize the ElasticSearch data store
        Intended for local or test bootstrapping;
        Indices should be managed by terraform in deployed environments.
        """
        await self.store.startup()
        await self.store.build_indexes(clear=True)

    async def quick_update(self) -> None:
        """Perform a 'quick' update for events that changed recently"""
        logger = logging.getLogger(__name__)
        logger.debug(f"{LOGGING_TAG} starting database")
        await self.store.startup()
        default_prior_update = datetime.now(tz=timezone.utc) - timedelta(
            seconds=UPDATE_PERIOD_SECS
        )
        try:
            last_update_str = (
                await self.store.query_meta("last_update") or default_prior_update.isoformat()
            )
            last_update = datetime.fromisoformat(last_update_str)
        except Exception as ex:
            logger.error(f"{LOGGING_TAG} quick_update date error {ex}")
            last_update = datetime.now(tz=timezone.utc) - timedelta(seconds=UPDATE_PERIOD_SECS)
        for sport in self.sports.values():
            start = time()
            await sport.update_events(client=self.client)
            logger.info(
                f"""{LOGGING_TAG} sports.time.quick_update.event ["sport": {sport.name}] = {time() - start}"""
            )
            start = time()
            await self.store.update_events(sport, language_code="en", last_update=last_update)
            logger.info(
                f"""{LOGGING_TAG} sports.time.quick_update.update ["sport": {sport.name}] = {time() - start}"""
            )
        await self.store.shutdown()

    async def update(self) -> None:
        """Perform just a data update"""
        logger = logging.getLogger(__name__)
        logger.debug(f"{LOGGING_TAG} Initializing database")
        await self.store.startup()
        await self.update_data()
        await self.store.shutdown()

    async def update_widget(self) -> None:
        """Fetch widget based info and store into the cache"""
        # we only deal with WCS for now.
        sport = self.sports.get("WCS")
        if sport is None:
            return
        await self.store.startup()
        await sport.init_cache(client=self.client, force=True)  # type: ignore
        if not sport.teams:
            await sport.update_teams(client=self.client)
        await sport.cache_teams()  # type: ignore

    async def update_and_cache_wcs(self) -> None:
        """Update Elasticsearch data and refresh the widget cache."""
        sport = self.sports.get("WCS")
        if sport is None:
            return
        with monitor(monitor_slug="wcs-etl", monitor_config=wcs_monitor_config):
            # TODO: Ensure errors bubble up to caller or are otherwise elevated
            # so we can track success/fail here
            await self.store.startup()
            try:
                # NOTE: Widget data must be done first, otherwise there may
                # be missing data like no terms aliases, due to mutable internal
                # state which depends on ordering of calls in the WCS class
                await self.update_widget()
                await self.update_data()
            finally:
                await self.store.shutdown()

    async def run_wcs_loop(self, interval_sec: float, stop_event: asyncio.Event) -> None:
        """Continuously refresh WCS Elasticsearch data and widget cache.

        Intended for a long-lived pod rather than a k8s CronJob: the store, cache,
        and HTTP clients built in `__init__` are reused across every iteration
        instead of being recreated per run. Each iteration is wrapped so a
        transient provider error is logged and counted but does not stop the loop
        (which would otherwise crash the pod). The loop exits cleanly once
        `stop_event` is set, so callers can wire it to SIGTERM for rolling restarts.
        """
        logger = logging.getLogger(__name__)
        # `startup()` is idempotent; open the store once and keep it for the
        # lifetime of the loop rather than reconnecting every iteration.
        await self.store.startup()
        try:
            while not stop_event.is_set():
                started = monotonic()
                wcs_job_state_counter.add(1, {"job_state": "started"})
                try:
                    # Widget data must be refreshed before event data; see the
                    # ordering note on `update_and_cache_wcs`.
                    await self.update_widget()
                    await self.update_data()
                    wcs_job_state_counter.add(1, {"job_state": "succeeded"})
                except Exception as ex:
                    logger.error(f"{LOGGING_TAG} WCS loop iteration failed: {ex}")
                    wcs_job_state_counter.add(1, {"job_state": "failed"})
                finally:
                    logger.info(
                        "wcs loop iteration finished",
                        extra={"elapsed_sec": monotonic() - started},
                    )
                # Cancellable sleep: wake immediately if a shutdown signal arrives
                # mid-gap rather than blocking for the full interval.
                try:
                    await asyncio.wait_for(stop_event.wait(), timeout=interval_sec)
                except asyncio.TimeoutError:
                    pass
        finally:
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
            metrics_client=get_metrics_client(),
        )
        cache = (
            RedisAdapter(
                *create_redis_clients(
                    settings.redis.wcs_server,
                    settings.redis.wcs_replica,
                    settings.redis.max_connections,
                    settings.redis.socket_connect_timeout_sec,
                    settings.redis.socket_timeout_sec,
                )
            )
            if sports_settings.get("cache") == "redis"
            else NoCacheAdapter()
        )
        provider = SportDataUpdater(
            settings=sports_settings,
            store=store,
            cache=cache,
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
    """Build the indexes and initialize the ES tables
    For local and test use only; indices are managed by
    terraform in deployed environments.
    """
    if provider:
        asyncio.run(provider.initialize())
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
        asyncio.run(provider.update_data())
    else:
        logger.error("Sports provider unavailable.")


@cli.command("update-widget")
def update_widget():  # pragma: no cover
    """Update widget based info"""
    if provider:
        asyncio.run(provider.update_widget())
    else:
        logger.error("Sports provider unavailable.")


@cli.command("update-and-cache-wcs")
def update_and_cache_wcs():  # pragma: no cover
    """Update Elasticsearch data and refresh the widget cache for WCS (only)."""
    if store and cache:
        wcs_only_settings = copy.copy(sports_settings)
        wcs_only_settings.sports = ["WCS"]
        wcs_provider = SportDataUpdater(
            settings=wcs_only_settings,
            store=store,
            cache=cache,
            connect_timeout=sports_settings.get("connect_timeout"),
            read_timeout=sports_settings.get("read_timeout"),
        )
        started = monotonic()
        try:
            asyncio.run(wcs_provider.update_and_cache_wcs())
        finally:
            logger.info(
                "update-and-cache-wcs finished",
                extra={"elapsed_sec": monotonic() - started},
            )
    else:
        logger.error("Sports provider unavailable.")


@cli.command("run-wcs-loop")
def run_wcs_loop(interval_sec: float = 60.0):  # pragma: no cover
    """Continuously refresh WCS data on a long-lived pod (not a CronJob).

    Builds the WCS updater once and loops until SIGTERM/SIGINT. Override the gap
    between iterations with `--interval-sec`; otherwise `providers.sports.
    wcs_loop_interval_sec` is used.
    """
    if not (store and cache):
        logger.error("Sports provider unavailable.")
        raise typer.Exit(code=1)
    wcs_only_settings = copy.copy(sports_settings)
    wcs_only_settings.sports = ["WCS"]
    wcs_provider = SportDataUpdater(
        settings=wcs_only_settings,
        store=store,
        cache=cache,
        connect_timeout=sports_settings.get("connect_timeout"),
        read_timeout=sports_settings.get("read_timeout"),
    )

    async def _main() -> None:
        stop_event = asyncio.Event()
        loop = asyncio.get_running_loop()
        for sig in (signal.SIGTERM, signal.SIGINT):
            loop.add_signal_handler(sig, stop_event.set)
        logger.info("Starting WCS loop", extra={"interval_sec": interval_sec})
        await wcs_provider.run_wcs_loop(interval_sec=interval_sec, stop_event=stop_event)

    asyncio.run(_main())


@cli.command("quick_update")
def quick_update():  # pragma: no cover
    """Perform a 'quick' update, which only changes scores & status for known sport events that changed recently"""
    if provider:
        asyncio.run(provider.quick_update())
    else:
        logger.error("Sports provider unavailable")


if __name__ == "__main__":
    cli()
