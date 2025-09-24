"""SportsData live query system"""

import logging
import os
import json
import hashlib

import pdb

from datetime import datetime, timedelta, timezone
from httpx import AsyncClient

from typing import Any

from merino.providers.suggest.sports import DEFAULT_LOGGING_LEVEL, LOGGING_TAG


async def get_data(
    client: AsyncClient,
    url: str,
    ttl: timedelta | None = None,
    cache_dir: str | None = None,
) -> Any:
    """Wrapper for commonly called remote data fetch"""
    # TODO: read from cache dir based on timestamp.
    cache_file = None
    if cache_dir:
        # painfully stupid cacher.
        # does not have to be super secure.
        hasher = hashlib.new("sha1")
        hasher.update(url.encode())
        hash = hasher.hexdigest()
        cache_file = os.path.join(cache_dir, f"{hash}.json")
        if os.path.exists(cache_file):
            if ttl:
                if os.path.getctime(cache_file) > (datetime.now() - ttl).timestamp():
                    logging.debug(f"{LOGGING_TAG}💾 Reading cache for {url}")
                    return json.load(open(cache_file, "r"))
            else:
                logging.debug(f"{LOGGING_TAG}💾 Reading perma-cache for {url}")
                return json.load(open(cache_file, "r"))
    response = await client.get(url)
    response.raise_for_status()
    response = response.json()
    if cache_file:
        logging.debug(f"{LOGGING_TAG}💾 Writing cache for {url}")
        json.dump(response, open(cache_file, "w"))
    return response


class SportSuggestion(dict):
    """Return a well structured Suggestion for the UA to process"""

    # Required fields.
    provider: str
    rating: float

    def as_suggestion(self) -> dict[str, Any]:
        return dict(
            provider=self.provider,
            rating=self.rating,
            # Return the random values we've collected as the "custom details"
            custom_details=dict(zip(self.keys(), self.values())),
        )
