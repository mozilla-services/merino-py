# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

"""Load test."""

import asyncio
import logging
import os
from random import choice, randint
from typing import Any

import faker
from elasticsearch import ApiError, Elasticsearch, ElasticsearchWarning, TransportError
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
from merino.web.models_v1 import SuggestResponse
from tests.load.locust_tests.client_info import DESKTOP_FIREFOX, LOCALES

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

# See Ops - Remote Settings
# https://github.com/mozilla-services/merino-py/blob/main/docs/ops.md#remote_settings
MERINO_REMOTE_SETTINGS__SERVER: str | None = os.getenv(
    "MERINO_REMOTE_SETTINGS__SERVER", os.getenv("KINTO__SERVER_URL")
)
MERINO_REMOTE_SETTINGS__BUCKET: str | None = os.getenv(
    "MERINO_REMOTE_SETTINGS__BUCKET", os.getenv("KINTO__BUCKET")
)
MERINO_REMOTE_SETTINGS__COLLECTION: str | None = os.getenv(
    "MERINO_REMOTE_SETTINGS__COLLECTION", os.getenv("KINTO__COLLECTION")
)

# See Ops - TOP PICKS
# https://github.com/mozilla-services/merino-py/blob/main/docs/ops.md#top-picks-provider
MERINO_PROVIDERS__TOP_PICKS__TOP_PICKS_FILE_PATH: str | None = os.getenv(
    "MERINO_PROVIDERS__TOP_PICKS__TOP_PICKS_FILE_PATH"
)
MERINO_PROVIDERS__TOP_PICKS__QUERY_CHAR_LIMIT: int = int(
    os.getenv("MERINO_PROVIDERS__TOP_PICKS__QUERY_CHAR_LIMIT", 0)
)
MERINO_PROVIDERS__TOP_PICKS__FIREFOX_CHAR_LIMIT: int = int(
    os.getenv("MERINO_PROVIDERS__TOP_PICKS__FIREFOX_CHAR_LIMIT", 0)
)

# See Ops - Wikipedia Dynamic Match Provider
# https://github.com/mozilla-services/merino-py/blob/main/docs/ops.md#wikipedia-dynamic-match-provider
MERINO_PROVIDERS__WIKIPEDIA__ES_URL: str | None = os.getenv(
    "MERINO_PROVIDERS__WIKIPEDIA__ES_URL"
)
MERINO_PROVIDERS__WIKIPEDIA__ES_API_KEY: str | None = os.getenv(
    "MERINO_PROVIDERS__WIKIPEDIA__ES_API_KEY"
)
MERINO_PROVIDERS__WIKIPEDIA__ES_INDEX: str | None = os.getenv(
    "MERINO_PROVIDERS__WIKIPEDIA__ES_INDEX"
)


# This will be populated on each worker
ADM_QUERIES: QueriesList = []
TOP_PICKS_QUERIES: QueriesList = []
WIKIPEDIA_QUERIES: list[str] = []


@events.test_start.add_listener
def on_locust_test_start(environment, **kwargs):
    """Download suggestions from Kinto and store suggestions on workers."""
    if not isinstance(environment.runner, MasterRunner):
        return

    query_data: QueryData = QueryData()
    try:
        query_data.adm = get_adm_queries(
            server=MERINO_REMOTE_SETTINGS__SERVER,
            collection=MERINO_REMOTE_SETTINGS__COLLECTION,
            bucket=MERINO_REMOTE_SETTINGS__BUCKET,
        )

        logger.info(f"Download {len(query_data.adm)} queries for AdM")

        query_data.top_picks = get_top_picks_queries(
            top_picks_file_path=MERINO_PROVIDERS__TOP_PICKS__TOP_PICKS_FILE_PATH,
            query_char_limit=MERINO_PROVIDERS__TOP_PICKS__QUERY_CHAR_LIMIT,
            firefox_char_limit=MERINO_PROVIDERS__TOP_PICKS__FIREFOX_CHAR_LIMIT,
        )

        logger.info(f"Download {len(query_data.top_picks)} queries for Top Picks")

        query_data.wikipedia = get_wikipedia_queries(
            url=MERINO_PROVIDERS__WIKIPEDIA__ES_URL,
            api_key=MERINO_PROVIDERS__WIKIPEDIA__ES_API_KEY,
            index=MERINO_PROVIDERS__WIKIPEDIA__ES_INDEX,
        )

        logger.info(f"Download {len(query_data.wikipedia)} queries for Wikipedia")

    except (
        ApiError,
        ElasticsearchWarning,
        RemoteSettingsError,
        TopPicksError,
        TransportError,
        ValueError,
    ):
        logger.error("Failed to gather query data. Stopping Test!")
        quit(1)

    for worker in environment.runner.clients:
        environment.runner.send_message(
            "store_suggestions", dict(query_data), client_id=worker
        )


def get_adm_queries(server: str, collection: str, bucket: str) -> QueriesList:
    """Get query strings for use in testing the AdM Provider.

    Args:
        server: Server URL of the Kinto instance containing suggestions
        collection: Kinto bucket with the suggestions
        bucket: Kinto collection with the suggestions
    Returns:
        QueriesList: List of queries to use with the ADM provider
    Raises:
        ValueError: If 'server', 'collection' or 'bucket' parameters are None or
                    empty.
        BackendError: Failed request to Remote Settings.
    """
    backend: RemoteSettingsBackend = RemoteSettingsBackend(server, collection, bucket)
    content: SuggestionContent = asyncio.run(backend.fetch())

    adm_query_dict: dict[int, list[str]] = {}
    for query, (result_id, fkw_index) in content.suggestions.items():
        adm_query_dict.setdefault(result_id, []).append(query)

    return list(adm_query_dict.values())


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


def get_wikipedia_queries(
    url: str | None, api_key: str | None, index: str | None
) -> list[str]:
    """Get query strings for use in testing the Wikipedia Provider.

    Args:
        url: The URL for the Elasticsearch cluster
        api_key: The base64 key used to authenticate on the Elasticsearch cluster
        index: A comma-separated list of index names to search; use `_all` or empty
               string to perform the operation on all indices
    Returns:
        List[str]: List of full query strings to use with the Wikipedia provider
    Raises:
        ApiError: Error triggered from an HTTP response that isn’t 2XX
        TransportError: Error triggered by an error occurring before an HTTP response
                        arrives
        ElasticsearchWarning: Warning that is raised when a deprecated option or
                              incorrect usage is flagged via the ‘Warning’ HTTP header
    """
    with Elasticsearch(url, api_key=api_key) as client:
        response = client.search(index=index, size=10000)  # maximum size

    query_list: list[str] = []
    for hit in response["hits"]["hits"]:
        full_query: str = hit["_source"]["title"]
        query_list.append(full_query)

    return query_list


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
    Raises:
        ValidationError: Response data is not as expected.
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
        # from Merino. This will raise a ValidationError if the response is missing
        # fields which will be reported as a failure in Locust's statistics.
        SuggestResponse(**response.json())


class QueryData(BaseModel):
    """Class that holds query data for targeting Merino providers"""

    adm: QueriesList = []
    top_picks: QueriesList = []
    wikipedia: list[str] = []


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
        queries: list[str] = choice(ADM_QUERIES)  # nosec
        providers: str = "adm"

        for query in queries:
            request_suggestions(self.client, query, providers)

    @task(weight=10)
    def dynamic_wikipedia_suggestions(self) -> None:
        """Send multiple requests for Dynamic Wikipedia queries."""
        full_query: str = choice(WIKIPEDIA_QUERIES)  # nosec
        providers: str = "wikipedia"

        queries: list[str] = [full_query[:x] for x in range(2, (len(full_query) + 1))]
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
