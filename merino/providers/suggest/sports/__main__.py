"""Stunt main for development and testing"""

import asyncio

import os
import logging
import sys
from datetime import datetime
from logging import Logger

from dynaconf.base import LazySettings

# Reminder: this will instantiate `settings`
from merino.configs import settings

from merino.middleware.geolocation import Location
from merino.providers.suggest.base import SuggestionRequest
from merino.providers.suggest.sports import (
    LOGGING_TAG,
    DEFAULT_TRIGGER_WORDS,
)
from merino.providers.suggest.sports.provider import SportsDataProvider
from merino.providers.suggest.sports.backends.sportsdata.backend import (
    SportsDataBackend,
)
from merino.providers.suggest.sports.backends.sportsdata.common.elastic import (
    ElasticCredentials,
    SportsDataStore,
)
from merino.providers.suggest.sports.backends.sportsdata.common.data import Sport
from merino.providers.suggest.sports.backends.sportsdata.common.sports import (
    FORCE_IMPORT,
)
from merino.utils.metrics import get_metrics_client
from merino.utils.http_client import create_http_client

# fool ruff into understanding that we really are importing this package.
_ = FORCE_IMPORT


# Set this value to `False` to prevent the loader functions
# RUN_LOADER = False
RUN_LOADER = True


async def main_loader(
    log: Logger,
    settings: LazySettings,
    credentials: ElasticCredentials,
    platform: str,
    event_map: str,
) -> list[str]:
    """Be a simple "stunt" main process that fetches data to ensure that the load and retrieval
    functions work the way you'd expect
    """
    log.debug(f"{LOGGING_TAG}: Building storage...")
    store = SportsDataStore(
        credentials=credentials,
        platform=platform,
        languages=[lang for lang in settings.get("languages", ["en"])],
        index_map={"event": event_map},
    )
    await store.startup()
    await store.prune()

    log.debug(f"{LOGGING_TAG}: Starting up...")
    my_sports: list[Sport] = []
    active_sports = [sport.upper().strip() for sport in settings.sports]
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
    client = create_http_client(
        connect_timeout=settings.sportsdata.get("connect_timeout", 1),
        request_timeout=settings.sportsdata.get("read_timeout", 1),
    )
    await store.prune()
    team_names: set[str] = set()
    for sport in my_sports:
        await sport.update_teams(client=client)
        for team in sport.teams.values():
            team_names.add(team.name.lower())
        await sport.update_events(client=client)
        await store.store_events(sport, language_code="en")
    await store.shutdown()
    reply: list[str] = list(team_names)
    reply.sort()
    return reply


async def main_query(
    log: Logger,
    credentials: ElasticCredentials,
    platform: str,
    event_map: str,
    settings: LazySettings,
):
    """Pretend we're a query function"""
    trigger_words = [
        word.lower().strip() for word in settings.get("trigger_words", DEFAULT_TRIGGER_WORDS)
    ]
    if not credentials.validate():
        print("Failure")
    store = SportsDataStore(
        credentials=credentials,
        platform=platform,
        languages=[lang for lang in settings.get("languages", ["en"])],
        index_map={"event": event_map},
    )
    backend = SportsDataBackend(store=store, settings=settings)
    provider = SportsDataProvider(
        backend=backend,
        metrics_client=get_metrics_client(),
        name="test_sports_provider_id",
        trigger_words=trigger_words,
        enabled_by_default=True,
    )
    await provider.initialize()
    sreq = SuggestionRequest(query="Jets game", geolocation=Location())
    start = datetime.now()
    res = await provider.query(sreq=sreq)
    log.debug(f"{LOGGING_TAG}⏱ query [{(datetime.now()-start).microseconds}μs]")
    print("## Output >>> ")

    print("===\n".join([rr.model_dump_json(indent=2) for rr in res]))

    await provider.shutdown()


if __name__ == "__main__":
    logging.basicConfig(level=getattr(logging, os.environ.get("PYTHON_LOG", "info").upper()))
    log = logging.getLogger(__name__)
    # Perform the "load" job. This would normally be handled by a merino job function
    # This can be commented out once it's been run once, if you want to test query speed.
    name = "sports"
    platform = f"{name}-{{lang}}"
    event_map = settings.providers.sports.get("event_index", f"{platform}-event")
    meta_map = settings.providers.sports.get("meta_index", f"{name}-meta")
    try:
        credentials = ElasticCredentials(settings=settings)
    except (Exception, BaseException) as ex:
        log.error(f"Could not get credentials {ex}")
        raise ex

    if RUN_LOADER:
        team_names = asyncio.run(
            main_loader(
                log=log,
                credentials=credentials,
                settings=settings.providers.sports,
                platform=platform,
                event_map=event_map,
            )
        )

    # Perform a query and return the results.
    asyncio.run(
        main_query(
            log=log,
            credentials=credentials,
            platform=platform,
            event_map=event_map,
            settings=settings.providers.sports,
        )
    )

    # Dump out the accumulated team names
    # Ideal World: This should go into some common data storage engine and be pulled regularly by
    # the suggest server.
    # `json.dumps()` converts these to non-UTF8 values.
    if os.environ.get("DUMP_GROUPS"):
        print("[")
        for name in team_names[:-1]:
            print(f'  "{name.lower().encode("utf8")!r}",')
        print(f'  "{team_names[-1].lower().encode("utf8")!r}"')
        print("]")
