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
    cache_file = None
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
                        logging.debug(f"{LOGGING_TAG}💾 Reading cache for {url}")
                        return json.load(open(cache_file, "r"))
                else:
                    logging.debug(f"{LOGGING_TAG}💾 Reading perma-cache for {url}")
                    return json.load(open(cache_file, "r"))
            except PermissionError:
                logging.warning(f"{LOGGING_TAG} Unable to read cache {cache_file}")
                pass
    logging.debug(f"{LOGGING_TAG} fetching data from {url}")
    response = await client.get(url)
    response.raise_for_status()
    response = response.json()
    if cache_file:
        logging.debug(f"{LOGGING_TAG}💾 Writing cache for {url}")
        try:
            json.dump(response, open(cache_file, "w"))
        except PermissionError:
            logging.warning(f"{LOGGING_TAG} Unable to write cache {cache_file}")
            pass
    return response


# class SportSuggestion(BaseModel):
#    """Return a well structured Suggestion for the UA to process
#    A returned suggestion will be a set of minimized event data for a
#    given sport (e.g. for `NFL` there could be a "previous" entry indicating
#    the final score of any previously finished games, a "current" entry
#    indicating the state and score of any in play games, and a "next" entry
#    indicating the time that a future game will be played.
#    Note that any "current" game (a game in progress) overrides the "previous"
#    per UA design.
#    An example would be:
#    ```
#    {
#        "NFL": {
#            "previous": {
#                "sport": "NFL",
#                "id": 19127,
#                "date": 1759130400,
#                "home_team": {
#                    "key": "DAL",
#                    "name": "Dallas Cowboys",
#                    "colors": [
#                    "002244",
#                    "B0B7BC",
#                    "00338D",
#                    "ADD9CE"
#                    ]
#                },
#                "away_team": {
#                    "key": "GB",
#                    "name": "Green Bay Packers",
#                    "colors": [
#                    "203731",
#                    "FFB612",
#                    "FFFFFF"
#                    ]
#                },
#                "home_score": 40,
#                "away_score": 40,
#                "status": "Final - Over Time",
#                "expiry": 1760390110
#            },
#            "next": {
#                "sport": "NFL",
#                "id": 19135,
#                "date": 1759708800,
#                "home_team": {
#                    "key": "NYJ",
#                    "name": "New York Jets",
#                    "colors": [
#                    "115740",
#                    "FFFFFF",
#                    "000000"
#                    ]
#                },
#                "away_team": {
#                    "key": "DAL",
#                    "name": "Dallas Cowboys",
#                    "colors": [
#                    "002244",
#                    "B0B7BC",
#                    "00338D",
#                    "ADD9CE"
#                    ]
#                },
#                "home_score": null,
#                "away_score": null,
#                "status": "Scheduled",
#                "expiry": 1760390110
#            }
#        }
#    }
#    ```
#    """
#
#    # Required fields.
#    provider: str
#    rating: float
#
#    @classmethod
#    def from_events(
#        cls,
#        sport_name: str,
#        query: str,
#        rating: float = 0,
#        events: dict = {},
#    ):
#        """Return a Suggestion for a given sport based on the query results."""
#        custom_details = CustomDetails(sports=SportSummary.from_events(events=events))
#        return SportSuggestion()
#
