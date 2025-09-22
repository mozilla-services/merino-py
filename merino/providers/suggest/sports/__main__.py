"""Stunt main for development and testing"""

import asyncio
import pdb

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
    pdb.set_trace()
    search_store = ElasticDataStore(settings=settings)
    log.debug(f"{LOGGING_TAG}: Starting up...")
    pdb.set_trace()
    sport = NFL(settings)
    pdb.set_trace()
    await sport.update_teams()
    pdb.set_trace()
    await sport.update_events()
    pdb.set_trace()
    res = await search_store.search(q="Giants vs dodgers", language_code="en")
    pdb.set_trace()
    print(res)


if __name__ == "__main__":
    asyncio.run(main())
