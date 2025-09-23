"""Stunt main for development and testing"""

import asyncio
import pdb

from httpx import AsyncClient, Timeout
from merino.configs import settings
from merino.providers.suggest.sports import init_logs, LOGGING_TAG
from merino.providers.suggest.sports.backends.sportsdata.common.data import (
    NFL,
    ElasticDataStore,
)


# Create a simple 'stunt' main process that fetches data to ensure that the load and retrieval
# functions work the way you'd expect.
async def main():
    log = init_logs()
    event_store = ElasticDataStore(settings=settings)
    # Only call for test or dev builds.
    await event_store.build_indexes(settings=settings)
    log.debug(f"{LOGGING_TAG}: Starting up...")
    sport = NFL(
        settings,
        event_store=event_store,
        api_key=settings.providers.sports.sportsdata.api_key,
    )
    # Sadly, we can't instantiate the AsyncClient lower.
    timeout = Timeout(
        3,
        connect=settings.providers.sports.sportsdata.get("connect_timeout", 1),
        read=settings.providers.sports.sportsdata.get("read_timeout", 1),
    )
    client = AsyncClient(timeout=timeout)
    pdb.set_trace()
    await sport.update_teams(http_client=client)
    pdb.set_trace()
    await sport.update_events(http_client=client)
    pdb.set_trace()
    res = await event_store.search(q="Giants vs dodgers", language_code="en")
    pdb.set_trace()
    print(res)


if __name__ == "__main__":
    asyncio.run(main())
