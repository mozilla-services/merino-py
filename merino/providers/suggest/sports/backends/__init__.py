"""SportsData live query system"""

import logging
import os
import json
import hashlib
from typing import Any

from datetime import datetime, timedelta
from httpx import AsyncClient

from merino.providers.suggest.sports import LOGGING_TAG


async def get_data(
    client: AsyncClient,
    url: str,
    ttl: timedelta | None = None,
    cache_dir: str | None = None,
) -> Any:
    """Fetch data from the provider. This may pull from the local cache or from the remote site depending on the
    `ttl` for the local cache.

    """
    logger = logging.getLogger(__name__)
    cache_file = None
    # TODO: Convert to using a GCS bucket?
    if cache_dir:
        # painfully stupid cacher.
        # does not have to be super secure.
        hasher = hashlib.new("sha1", usedforsecurity=False)
        hasher.update(url.encode())
        hash = hasher.hexdigest()
        cache_file = os.path.join(cache_dir, f"{hash}.json")
        if os.path.exists(cache_file):
            try:
                if ttl:
                    if os.path.getctime(cache_file) > (datetime.now() - ttl).timestamp():
                        logger.debug(f"{LOGGING_TAG}💾 Reading cache for {url}")
                        with open(cache_file, "r") as cache:
                            return json.load(cache)
                else:
                    logger.debug(f"{LOGGING_TAG}💾 Reading perma-cache for {url}")
                    with open(cache_file, "r") as cache:
                        return json.load(cache)
            except PermissionError:
                logger.warning(f"{LOGGING_TAG} Unable to read cache {cache_file}")
                pass
            except ValueError:
                # possible read on a closed file.
                pass
    logger.debug(f"{LOGGING_TAG} fetching data from {url}")
    response = await client.get(url)
    response.raise_for_status()
    response = response.json()
    if cache_file:
        logger.debug(f"{LOGGING_TAG}💾 Writing cache for {url}")
        try:
            with open(cache_file, "w") as cache:
                json.dump(response, cache)
        except PermissionError:
            logger.warning(f"{LOGGING_TAG} Unable to write cache {cache_file}")
            pass
        except TypeError:
            # Could not serialize the response, possibly due to it being a mock.
            logger.warning(f"{LOGGING_TAG} Unable to serialize response for {url}")
            pass
    return response
