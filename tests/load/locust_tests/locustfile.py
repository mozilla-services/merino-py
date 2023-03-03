# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

"""Load test."""

import asyncio
import logging
import os
from random import choice, randint
from typing import Any, Tuple

import faker
from locust import HttpUser, events, task
from locust.clients import HttpSession
from locust.runners import MasterRunner
from pydantic import BaseModel

from merino.providers.adm.backends.protocol import SuggestionContent
from merino.providers.adm.backends.remotesettings import (
    RemoteSettingsBackend,
    RemoteSettingsError,
)
from merino.providers.top_picks.backends.protocol import TopPicksData
from merino.providers.top_picks.backends.top_picks import TopPicksBackend, TopPicksError
from tests.load.locust_tests.client_info import DESKTOP_FIREFOX, LOCALES
from tests.load.locust_tests.suggest_models import ResponseContent

# Type definitions
KintoRecords = list[dict[str, Any]]
QueriesList = list[list[str]]

LOGGING_LEVEL = os.environ["LOAD_TESTS__LOGGING_LEVEL"]

logger = logging.getLogger("load_tests")
logger.setLevel(int(LOGGING_LEVEL))

# See https://mozilla-services.github.io/merino/api.html#suggest
SUGGEST_API: str = "/api/v1/suggest"

# Optional. A comma-separated list of any experiments or rollouts that are
# affecting the client's Suggest experience
CLIENT_VARIANTS: str = ""

# See RemoteSettingsGlobalSettings in
# https://github.com/mozilla-services/merino/blob/main/merino-settings/src/lib.rs
KINTO__SERVER_URL = os.environ["KINTO__SERVER_URL"]

# See default values in RemoteSettingsConfig in
# https://github.com/mozilla-services/merino/blob/main/merino-settings/src/providers.rs
KINTO__BUCKET = os.environ["KINTO__BUCKET"]
KINTO__COLLECTION = os.environ["KINTO__COLLECTION"]

# See Ops - TOP PICKS
# https://github.com/mozilla-services/merino-py/blob/main/docs/ops.md#top-picks-provider
MERINO_PROVIDERS__TOP_PICKS__TOP_PICKS_FILE_PATH: str = os.environ[
    "MERINO_PROVIDERS__TOP_PICKS__TOP_PICKS_FILE_PATH"
]
MERINO_PROVIDERS__TOP_PICKS__QUERY_CHAR_LIMIT: int = int(
    int(os.environ["MERINO_PROVIDERS__TOP_PICKS__QUERY_CHAR_LIMIT"])
)
MERINO_PROVIDERS__TOP_PICKS__FIREFOX_CHAR_LIMIT: int = int(
    int(os.environ["MERINO_PROVIDERS__TOP_PICKS__FIREFOX_CHAR_LIMIT"])
)

# This will be populated on each worker
ADM_QUERIES: QueriesList = []
TOP_PICKS_QUERIES: QueriesList = []
WIKIPEDIA_QUERIES: QueriesList = []


@events.test_start.add_listener
def on_locust_test_start(environment, **kwargs):
    """Download suggestions from Kinto and store suggestions on workers."""
    if not isinstance(environment.runner, MasterRunner):
        return

    query_data: QueryData = QueryData()
    try:
        query_data.adm, query_data.wikipedia = get_adm_queries(
            server=KINTO__SERVER_URL, collection=KINTO__COLLECTION, bucket=KINTO__BUCKET
        )

        logger.info(f"Download {len(query_data.adm)} queries for AdM")
        logger.info(f"Download {len(query_data.wikipedia)} queries for Wikipedia")

        query_data.top_picks = get_top_picks_queries(
            top_picks_file_path=MERINO_PROVIDERS__TOP_PICKS__TOP_PICKS_FILE_PATH,
            query_char_limit=MERINO_PROVIDERS__TOP_PICKS__QUERY_CHAR_LIMIT,
            firefox_char_limit=MERINO_PROVIDERS__TOP_PICKS__FIREFOX_CHAR_LIMIT,
        )

        logger.info(f"Download {len(query_data.top_picks)} queries for Top Picks")

    except (TopPicksError, RemoteSettingsError, ValueError):
        logger.error("Failed to gather query data. Stopping Test!")
        quit(1)

    for worker in environment.runner.clients:
        environment.runner.send_message(
            "store_suggestions", dict(query_data), client_id=worker
        )


def get_adm_queries(
    server: str, collection: str, bucket: str
) -> Tuple[QueriesList, QueriesList]:
    """Get query strings for use in testing the AdM Provider.

    Args:
        server: Server URL of the Kinto instance containing suggestions
        collection: Kinto bucket with the suggestions
        bucket: Kinto collection with the suggestions
    Returns:
        Tuple[QueriesList, QueriesList]: Lists of queries to use with the ADM provider
    Raises:
        ValueError: If 'server', 'collection' or 'bucket' parameters are None or
                    empty.
        BackendError: Failed request to Remote Settings.
    """
    backend: RemoteSettingsBackend = RemoteSettingsBackend(server, collection, bucket)
    content: SuggestionContent = asyncio.run(backend.fetch())

    adm_query_dict: dict[int, list[str]] = {}
    wikipedia_query_dict: dict[int, list[str]] = {}
    for query, (result_id, fkw_index) in content.suggestions.items():
        result: dict[str, Any] = content.results[result_id]
        if result["advertiser"] == "Wikipedia":
            wikipedia_query_dict.setdefault(result_id, []).append(query)
        else:
            adm_query_dict.setdefault(result_id, []).append(query)

    return list(adm_query_dict.values()), list(wikipedia_query_dict.values())


def get_top_picks_queries(
    top_picks_file_path: str, query_char_limit: int, firefox_char_limit: int
) -> QueriesList:
    """Get query strings for use in testing the Top Picks Provider.

    Args:
        top_picks_file_path: File path to the json file of domains
        query_char_limit: The minimum character limit set for long domain suggestion
                          indexing
        firefox_char_limit: The minimum character limit set for short domain suggestion
                            indexing
    Returns:
        QueriesList: List of queries to use with the Top Picks provider
    Raises:
        ValueError: If the top picks file path is not specified
        TopPicksError: If the top picks file path cannot be opened or decoded
    """
    backend: TopPicksBackend = TopPicksBackend(
        top_picks_file_path, query_char_limit, firefox_char_limit
    )
    data: TopPicksData = asyncio.run(backend.fetch())

    def add_queries(index: dict[str, list[int]], queries: dict[int, list[str]]):
        for query, result_ids in index.items():
            for result_id in result_ids:
                queries.setdefault(result_id, []).append(query)

    query_dict: dict[int, list[str]] = {}
    add_queries(data.short_domain_index, query_dict)
    add_queries(data.primary_index, query_dict)
    add_queries(data.secondary_index, query_dict)

    return list(query_dict.values())


def store_suggestions(environment, msg, **kwargs):
    """Modify the module scoped list with suggestions in-place."""
    logger.info("store_suggestions: Storing %d suggestions", len(msg.data))

    query_data: QueryData = QueryData(**msg.data)

    ADM_QUERIES[:] = query_data.adm
    TOP_PICKS_QUERIES[:] = query_data.top_picks
    WIKIPEDIA_QUERIES[:] = query_data.wikipedia


@events.init.add_listener
def on_locust_init(environment, **kwargs):
    """Register a message on worker nodes."""
    if not isinstance(environment.runner, MasterRunner):
        environment.runner.register_message("store_suggestions", store_suggestions)


def request_suggestions(
    client: HttpSession, query: str, providers: str | None = None
) -> None:
    """Request suggestions from Merino for the given query string.

    Args:
        client: An HTTP session client
        query: Query string
        providers: Optional. A comma-separated list of providers to use for this request
    """
    params: dict[str, Any] = {"q": query}

    if CLIENT_VARIANTS:
        params = {**params, "client_variants": CLIENT_VARIANTS}

    if providers:
        params = {**params, "providers": providers}

    headers: dict[str, str] = {  # nosec
        "Accept-Language": choice(LOCALES),
        "User-Agent": choice(DESKTOP_FIREFOX),
    }

    with client.get(
        url=SUGGEST_API,
        params=params,
        headers=headers,
        catch_response=True,
        # group all requests under the 'name' entry
        name=f"{SUGGEST_API}{(f'?providers={providers}' if providers else '')}",
    ) as response:
        # This contextmanager returns a response that provides the ability to
        # manually control if an HTTP request should be marked as successful or
        # a failure in Locust's statistics
        if response.status_code != 200:
            response.failure(f"{response.status_code=}, expected 200, {response.text=}")
            return

        # Create a pydantic model instance for validating the response content
        # from Merino. This will raise an Exception if the response is missing
        # fields which will be reported as a failure in Locust's statistics.
        ResponseContent(**response.json())


class QueryData(BaseModel):
    """Class that holds query data for targeting Merino providers"""

    adm: QueriesList = []
    top_picks: QueriesList = []
    wikipedia: QueriesList = []


class MerinoUser(HttpUser):
    """User that sends requests to the Merino API."""

    def on_start(self):
        """Instructions to execute for each simulated user when they start."""
        # Create a Faker instance for generating random suggest queries
        self.faker = faker.Faker(locale="en-US", providers=["faker.providers.lorem"])

        # By this time suggestions are expected to be stored on the worker
        logger.debug(
            f"user will be sending queries based on the following number of "
            f"stored suggestions: "
            f"adm: {len(ADM_QUERIES)}, "
            f"top picks: {len(TOP_PICKS_QUERIES)},"
            f"wikipedia: {len(WIKIPEDIA_QUERIES)}"
        )

        return super().on_start()

    @task(weight=10)
    def adm_suggestions(self) -> None:
        """Send multiple requests for AdM queries."""
        queries: list[str] = choice(ADM_QUERIES + WIKIPEDIA_QUERIES)  # nosec
        providers: str = "adm"

        for query in queries:
            request_suggestions(self.client, query, providers)

    @task(weight=10)
    def dynamic_wikipedia_suggestions(self) -> None:
        """Send multiple requests for Dynamic Wikipedia queries."""
        # TODO Replace query source with ElasticSearch Source, not RemoteSettings
        queries: list[str] = choice(WIKIPEDIA_QUERIES)  # nosec
        providers: str = "wikipedia"

        for query in queries:
            request_suggestions(self.client, query, providers)

    @task(weight=70)
    def faker_suggestions(self) -> None:
        """Send multiple requests for random queries."""
        # This produces a query between 2 and 4 random words
        full_query = " ".join(self.faker.words(nb=randint(2, 4)))  # nosec

        for query in [full_query[: i + 1] for i in range(len(full_query))]:
            # Send multiple requests for the entire query, but skip spaces
            if query.endswith(" "):
                continue

            request_suggestions(self.client, query)

    @task(weight=10)
    def top_picks_suggestions(self) -> None:
        """Send multiple requests for Top Picks queries."""
        queries: list[str] = choice(TOP_PICKS_QUERIES)  # nosec
        providers: str = "top_picks"

        for query in queries:
            request_suggestions(self.client, query, providers)

    @task(weight=0)
    def wikifruit_suggestions(self) -> None:
        """Send multiple requests for random WikiFruit queries."""
        # These queries are supported by the WikiFruit provider
        for fruit in ("apple", "banana", "cherry"):
            request_suggestions(self.client, fruit)
