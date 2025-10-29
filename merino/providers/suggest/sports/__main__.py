"""Stunt main for development and testing"""

import asyncio

import os
import sys
from datetime import datetime
from logging import Logger

from dynaconf.base import LazySettings

# Reminder: this will instantiate `settings`
from merino.configs import settings

from merino.middleware.geolocation import Location
from merino.providers.suggest.base import SuggestionRequest
from merino.providers.suggest.sports import (
    init_logs,
    LOGGING_TAG,
    DEFAULT_TRIGGER_WORDS,
)
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
from merino.utils.http_client import create_http_client

# fool ruff into understanding that we really are importing this package.
_ = FORCE_IMPORT


async def main_loader(
    log: Logger,
    settings: LazySettings,
    build_indices: bool = False,
) -> list[str]:
    """Be a simple "stunt" main process that fetches data to ensure that the load and retrieval
    functions work the way you'd expect
    """
    platform = settings.get("platform", "sports")
    event_store = SportsDataStore(
        dsn=settings.es.dsn,
        api_key=settings.es.api_key,
        languages=[lang.lower().strip() for lang in settings.get("languages", ["en"])],
        platform=f"{{lang}}_{platform}",
        index_map={
            # "meta": settings.get(
            #     "meta_index", f"{self.platform}_meta"
            # ),
            # "team": settings.get(
            #     "team_index", f"{self.platform}_team"
            # ),
            "event": settings.get("event_index", f"{platform}_event"),
        },
    )

    log.debug(f"{LOGGING_TAG}: Building storage...")
    if build_indices:
        # Only call for test or dev builds.
        log.debug(f"{LOGGING_TAG}: Building indices...")
        await event_store.build_indexes(clear=False)
        await event_store.prune(expiry=1760473106)

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
    await event_store.prune()
    team_names: set[str] = set()
    for sport in my_sports:
        await sport.update_teams(client=client)
        for team in sport.teams.values():
            team_names.add(team.name.lower())
        await sport.update_events(client=client)
        await event_store.store_events(sport, language_code="en")
    await event_store.shutdown()
    reply: list[str] = list(team_names)
    reply.sort()
    return reply


async def main_query(log: Logger, settings: LazySettings):
    """Pretend we're a query function"""
    trigger_words = [
        word.lower().strip() for word in settings.get("trigger_words", DEFAULT_TRIGGER_WORDS)
    ]
    backend = SportsDataBackend(settings=settings)
    await backend.startup()

    provider = SportsDataProvider(
        backend=backend,
        metrics_client=get_metrics_client(),
        name="test_sports_provider_id",
        trigger_words=trigger_words,
        enabled_by_default=True,
    )
    sreq = SuggestionRequest(query="Jets game", geolocation=Location())
    start = datetime.now()
    res = await provider.query(sreq=sreq)
    log.debug(f"{LOGGING_TAG}⏱ query [{(datetime.now()-start).microseconds}μs]")
    print("## Output >>> ")

    print("===\n".join([rr.model_dump_json(indent=2) for rr in res]))

    await provider.shutdown()


if __name__ == "__main__":
    log = init_logs()
    # Perform the "load" job. This would normally be handled by a merino job function
    # This can be commented out once it's been run once, if you want to test query speed.

    team_names = asyncio.run(
        main_loader(log=log, settings=settings.providers.sports, build_indices=True)
    )

    # Perform a query and return the results.
    asyncio.run(main_query(log=log, settings=settings.providers.sports))

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
