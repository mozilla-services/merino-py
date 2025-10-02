"""Stunt main for development and testing"""

import asyncio
import sys
from logging import Logger

from dynaconf.base import LazySettings
from httpx import AsyncClient, Timeout

# Reminder: this will instantiate `settings`
from merino.configs import settings
from merino.providers.suggest.sports import init_logs, LOGGING_TAG
from merino.providers.suggest.sports.backends.sportsdata.backend import (
    SportsDataBackend,
)
from merino.providers.suggest.sports.backends.sportsdata.common.elastic import (
    SportsDataStore,
)
from merino.providers.suggest.sports.backends.sportsdata.common.data import Sport
from merino.providers.suggest.sports.backends.sportsdata.common.sports import (
    FORCE_IMPORT,
)

# fool ruff into understanding that we really are importing this package.
_ = FORCE_IMPORT


async def main_loader(
    log: Logger,
    settings: LazySettings,
    build_indices: bool = False,
):
    """Be a simple "stunt" main process that fetches data to ensure that the load and retrieval
    functions work the way you'd expect
    """
    platform = settings.providers.sports.get("platform", "sports")
    event_store = SportsDataStore(
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
            "event": settings.providers.sports.get("event_index", f"{platform}_event"),
        },
        settings=settings,
    )

    log.debug(f"{LOGGING_TAG}: Building storage...")
    if build_indices:
        # Only call for test or dev builds.
        log.debug(f"{LOGGING_TAG}: Building indices...")
        await event_store.build_indexes(settings=settings, clear=False)
        await event_store.prune(expiry=1760473106)

    log.debug(f"{LOGGING_TAG}: Starting up...")
    my_sports: list[Sport] = []
    active_sports = [
        sport.strip().upper() for sport in settings.providers.sports.sports.split(",")
    ]
    for sport_name in active_sports:
        try:
            sport = getattr(
                sys.modules["merino.providers.suggest.sports.backends.sportsdata.common.sports"],
                sport_name.upper(),
            )(settings=settings)
            my_sports.append(sport)
        except AttributeError:
            print(f"Skipping {sport_name}")
            continue
    # Sadly, we can't instantiate the AsyncClient lower.
    timeout = Timeout(
        3,
        connect=settings.providers.sports.sportsdata.get("connect_timeout", 1),
        read=settings.providers.sports.sportsdata.get("read_timeout", 1),
    )
    client = AsyncClient(timeout=timeout)
    log.info(f"{LOGGING_TAG} Pruning data...")
    await event_store.prune()
    for sport in my_sports:
        await sport.update_teams(client=client)
        await sport.update_events(client=client)
        await event_store.store_events(sport, language_code="en")
    await event_store.shutdown()


async def main_query(log: Logger, settings: LazySettings):
    """Pretend we're a query function"""
    backend = SportsDataBackend(
        settings=settings,
    )
    res = await backend.query("Dallas")
    print(res)
    await backend.shutdown()


if __name__ == "__main__":
    log = init_logs()
    asyncio.run(main_loader(log=log, settings=settings, build_indices=True))
    asyncio.run(main_query(log=log, settings=settings))
