"""Stunt main for development and testing"""

import asyncio
import sys
from datetime import datetime
from logging import Logger

from dynaconf.base import LazySettings
from httpx import AsyncClient, Timeout

# Reminder: this will instantiate `settings`
from merino.configs import settings
from merino.middleware.geolocation import Location
from merino.providers.suggest.base import SuggestionRequest
from merino.providers.suggest.sports import init_logs, LOGGING_TAG
from merino.providers.suggest.sports.provider import SportsDataProvider
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
from merino.utils.metrics import get_metrics_client

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
    provider = SportsDataProvider(
        backend=SportsDataBackend(settings=settings),
        metrics_client=get_metrics_client(),
        base_score=settings.providers.sports.score,
        name="test_sports_provider_id",
        enabled_by_default=True,
    )
    sreq = SuggestionRequest(query="Dallas", geolocation=Location())
    start = datetime.now()
    res = await provider.query(sreq=sreq)
    log.debug(f"{LOGGING_TAG}⏰ query: {datetime.now()-start}")
    print("## Output >>> ")
    print("===\n".join([rr.model_dump_json(indent=2) for rr in res]))

    await provider.shutdown()


if __name__ == "__main__":
    log = init_logs()
    # Perform the "load" job. This would normally be handled by a merino job function
    # This can be commented out once it's been run once, if you want to test query speed.

    # asyncio.run(main_loader(log=log, settings=settings, build_indices=True))

    # Perform a query and return the results.
    settings.providers.sports.mix_sports = True
    asyncio.run(main_query(log=log, settings=settings))
