"""Handle incoming Sports related queries"""

from abc import abstractmethod
from dynaconf.base import LazySettings
from pydantic import HttpUrl
from typing import Protocol, cast


from merino.providers.suggest.sports.backends.sportsdata.protocol import SportSummary
from merino.providers.suggest.sports.backends.sportsdata.common.elastic import (
    SportsDataStore,
)

import logging
from datetime import datetime, timedelta, timezone
from merino.providers.suggest.sports import LOGGING_TAG
from merino.providers.suggest.sports.backends.sportsdata.common.sports import (
    # NFL,
    NHL,
    # NBA,
)
from merino.utils.http_client import create_http_client


class SportsDataProtocol(Protocol):
    """Protocol functions for Sports"""

    @abstractmethod
    async def shutdown(self) -> None:
        """Perform the shutdown steps"""


class SportsDataBackend(SportsDataProtocol):
    """Provide the methods specific to this provider for fulfilling the request"""

    data_store: SportsDataStore

    def __init__(
        self,
        settings: LazySettings,
        *args,
        store: SportsDataStore | None = None,
        **kwargs,
    ):
        super().__init__(*args, **kwargs)
        platform = settings.get("platform", "sports")
        event_map = settings.get("event_index", f"{platform}_event")
        self.data_store = store or SportsDataStore(
            dsn=settings.es.dsn,
            api_key=settings.es.api_key,
            languages=[lang for lang in settings.get("languages", ["en"])],
            platform=f"{{lang}}_{platform}",
            index_map={
                "event": cast(str, event_map),
            },
        )
        self.max_suggestions = settings.get("max_suggestions", 10)
        self.mix_sports = settings.get("mix_sports", True)
        self.settings = settings

    async def query(
        self,
        query_string: str | None = None,
        language_code: str = "en",
        score: float = 0.5,
        url: HttpUrl | None = None,
    ) -> list[SportSummary]:
        """Query the data store for terms and return a list of potential sporting events relevant to those terms.

        This relies on Elastic's internal tokenizer and full text search to scan the list of "terms" for matching results.
        Note that we would want to use elastic's term score as a multiplier for the returned suggestion score, since it would
        indicate how likely that suggestion matched the provided query.
        """
        # break the description into words
        if query_string:
            # This will build a list of events by sport.
            # There is an outstanding question about whether we
            # should mix events for sports
            # (e.g. prior NHL, current MLB, future NFL)
            events = await self.data_store.search_events(
                q=query_string, language_code=language_code, mix_sports=self.mix_sports
            )
            suggestions: list[SportSummary] = []
            for sport, events in events.items():
                if len(suggestions) > self.max_suggestions:
                    break
                # TODO: collect the es_score from the events, calculate an average, and
                # apply that as an adjustment value to the returned score value.
                # Waiting for guidance about what ranges to have scores.
                suggestions.append(
                    SportSummary.from_events(
                        sport=sport,
                        events=events,
                    )
                )
            return suggestions
        return []

    async def shutdown(self) -> None:
        """Politely shut down the datastore"""
        await self.data_store.shutdown()

    async def startup(self) -> None:
        """Perform any initialization functions here.

        NOTE: The Merino elastic search account is READ_ONLY
        The Airflow elastic search is READ_WRITE.

        """
        logger = logging.getLogger(__name__)
        # do we need to update the data?
        if await self.data_store.startup():
            updating = await self.data_store.query_meta("update")
            timestamp = (datetime.now(tz=timezone.utc) + timedelta(minutes=5)).timestamp()
            if not updating or (float(updating) < timestamp):
                await self.data_store.store_meta("update", str(timestamp))
                verify = await self.data_store.query_meta("update")
                # validate that we're the one doing the update.
                if float(verify or "0") != timestamp:
                    logger.info(f"{LOGGING_TAG} Update already in progress")
                    return
                logger.info(f"{LOGGING_TAG}Pre-populating data")
                client = create_http_client()
                # hardcode the sports for now:
                for sport in [
                    # NFL(settings=self.settings),
                    # NBA(settings=self.settings),
                    NHL(settings=self.settings),  # why NHL? Because the team is mostly Canadian.
                ]:
                    logger.info(f"{LOGGING_TAG} fetching {sport.name} teams...")
                    await sport.update_teams(client=client)
                    logger.info(f"{LOGGING_TAG} fetching {sport.name} events...")
                    await sport.update_events(client=client)
                    logger.info(f"{LOGGING_TAG} storing events for {sport.name}")
                    await self.data_store.store_events(sport, language_code="en")
