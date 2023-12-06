# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

"""Load test."""

import asyncio
import csv
import gzip
import logging
import os
import socket
import struct
from itertools import chain
from random import choice, randint
from typing import Any

import faker
from elasticsearch import ApiError, Elasticsearch, ElasticsearchWarning, TransportError
from locust import HttpUser, events, task
from locust.exception import StopUser
from locust.runners import MasterRunner
from pydantic import BaseModel

from merino.providers.adm.backends.protocol import SuggestionContent
from merino.providers.adm.backends.remotesettings import (
    RemoteSettingsBackend,
    RemoteSettingsError,
)
from merino.providers.amo.addons_data import ADDON_KEYWORDS
from merino.providers.top_picks.backends.protocol import TopPicksData
from merino.providers.top_picks.backends.top_picks import TopPicksBackend, TopPicksError
from merino.utils.blocklists import TOP_PICKS_BLOCKLIST
from merino.utils.version import Version
from merino.web.models_v1 import SuggestResponse
from tests.load.common.client_info import DESKTOP_FIREFOX, LOCALES

# Type definitions
KintoRecords = list[dict[str, Any]]
QueriesList = list[list[str]]
IpRangeList = list[tuple[str, str]]

LOGGING_LEVEL = os.environ["LOAD_TESTS__LOGGING_LEVEL"]

logger = logging.getLogger("load_tests")
logger.setLevel(int(LOGGING_LEVEL))

# See https://mozilla-services.github.io/merino/api.html#suggest
SUGGEST_API: str = "/api/v1/suggest"
VERSION_API: str = "/__version__"

# Optional. A comma-separated list of any experiments or rollouts that are
# affecting the client's Suggest experience
CLIENT_VARIANTS: str = ""

# IP RANGE CSV FILES (GZIP)
# This test framework uses IP2Location LITE data available from
# https://lite.ip2location.com
CANADA_IP_ADDRESS_RANGES_GZIP: str = (
    "tests/load/data/ip2location_canada_ip_address_ranges.gz"
)
US_IP_ADDRESS_RANGES_GZIP: str = (
    "tests/load/data/ip2location_united_states_of_america_ip_address_ranges.gz"
)

# Configurations
# See Configuring Merino (https://mozilla-services.github.io/merino/ops.html)
MERINO_PROVIDERS__TOP_PICKS__TOP_PICKS_FILE_PATH: str | None = os.getenv(
    "MERINO_PROVIDERS__TOP_PICKS__TOP_PICKS_FILE_PATH"
)
MERINO_PROVIDERS__TOP_PICKS__QUERY_CHAR_LIMIT: int = int(
    os.getenv("MERINO_PROVIDERS__TOP_PICKS__QUERY_CHAR_LIMIT", 0)
)
MERINO_PROVIDERS__TOP_PICKS__FIREFOX_CHAR_LIMIT: int = int(
    os.getenv("MERINO_PROVIDERS__TOP_PICKS__FIREFOX_CHAR_LIMIT", 0)
)
MERINO_PROVIDERS__WIKIPEDIA__ES_URL: str | None = os.getenv(
    "MERINO_PROVIDERS__WIKIPEDIA__ES_URL"
)
MERINO_PROVIDERS__WIKIPEDIA__ES_API_KEY: str | None = os.getenv(
    "MERINO_PROVIDERS__WIKIPEDIA__ES_API_KEY"
)
MERINO_PROVIDERS__WIKIPEDIA__ES_INDEX: str | None = os.getenv(
    "MERINO_PROVIDERS__WIKIPEDIA__ES_INDEX"
)
MERINO_REMOTE_SETTINGS__SERVER: str | None = os.getenv(
    "MERINO_REMOTE_SETTINGS__SERVER", os.getenv("KINTO__SERVER_URL")
)
MERINO_REMOTE_SETTINGS__BUCKET: str | None = os.getenv(
    "MERINO_REMOTE_SETTINGS__BUCKET", os.getenv("KINTO__BUCKET")
)
MERINO_REMOTE_SETTINGS__COLLECTION: str | None = os.getenv(
    "MERINO_REMOTE_SETTINGS__COLLECTION", os.getenv("KINTO__COLLECTION")
)


# This will be populated on each worker
ADM_QUERIES: QueriesList = []
AMO_QUERIES: list[str] = []
IP_RANGES: IpRangeList = []
TOP_PICKS_QUERIES: QueriesList = []
WIKIPEDIA_QUERIES: list[str] = []


@events.test_start.add_listener
def on_locust_test_start(environment, **kwargs) -> None:
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

        query_data.amo = get_amo_queries()

        logger.info(f"Download {len(query_data.amo)} queries for AMO")

        query_data.top_picks = get_top_picks_queries(
            top_picks_file_path=MERINO_PROVIDERS__TOP_PICKS__TOP_PICKS_FILE_PATH,
            query_char_limit=MERINO_PROVIDERS__TOP_PICKS__QUERY_CHAR_LIMIT,
            firefox_char_limit=MERINO_PROVIDERS__TOP_PICKS__FIREFOX_CHAR_LIMIT,
            domain_blocklist=TOP_PICKS_BLOCKLIST,
        )

        logger.info(f"Download {len(query_data.top_picks)} queries for Top Picks")

        query_data.wikipedia = get_wikipedia_queries(
            url=MERINO_PROVIDERS__WIKIPEDIA__ES_URL,
            api_key=MERINO_PROVIDERS__WIKIPEDIA__ES_API_KEY,
            index=MERINO_PROVIDERS__WIKIPEDIA__ES_INDEX,
        )

        logger.info(f"Download {len(query_data.wikipedia)} queries for Wikipedia")

        query_data.ip_ranges = get_ip_ranges(
            ip_range_files=[CANADA_IP_ADDRESS_RANGES_GZIP, US_IP_ADDRESS_RANGES_GZIP]
        )

        logger.info(
            f"Download {len(query_data.ip_ranges)} IP ranges for X-Forward-For headers"
        )
    except (
        ApiError,
        ElasticsearchWarning,
        OSError,
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


def get_adm_queries(
    server: str | None, collection: str | None, bucket: str | None
) -> QueriesList:
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


def get_amo_queries() -> list[str]:
    """Get query strings for use in testing the AMO provider.

    Returns:
        List[str]: List of full query strings to use with the AMO provider
    """
    return list(
        set(map(lambda x: x.lower(), chain.from_iterable(ADDON_KEYWORDS.values())))
    )


def get_top_picks_queries(
    top_picks_file_path: str | None,
    query_char_limit: int,
    firefox_char_limit: int,
    domain_blocklist: set[str],
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
        top_picks_file_path, query_char_limit, firefox_char_limit, domain_blocklist
    )
    data: TopPicksData = asyncio.run(backend.fetch())  # type: ignore [assignment]
    # `type: ignore` is necessary to avoid confusing mypy as in the local context of load tests,
    # we won't risk returning `None` from a local fetch.

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


def get_ip_ranges(ip_range_files: list[str]) -> IpRangeList:
    """Get IP address ranges for use when testing with the 'X-Forwarded-For' headers.

    Args:
        ip_range_files: List of gzip CSV files containing IP address ranges
    Returns:
        IpRangeList: List of IP string tuples indicating the beginning and end of IP
                     address ranges
    Raises:
        OSError: If an IP range file cannot be opened or read
    """
    ip_ranges: list[tuple[str, str]] = []
    for ip_range_file in ip_range_files:
        with gzip.open(ip_range_file, mode="rt") as csv_file:
            for row in csv.DictReader(csv_file, delimiter=","):
                begin_ip_address: str = row["Begin IP Address"]
                end_ip_address: str = row["End IP Address"]
                ip_ranges.append((begin_ip_address, end_ip_address))
    return ip_ranges


def store_suggestions(environment, msg, **kwargs) -> None:
    """Modify the module scoped list with suggestions in-place."""
    logger.info("store_suggestions: Storing %d suggestions", len(msg.data))

    query_data: QueryData = QueryData(**msg.data)

    ADM_QUERIES[:] = query_data.adm
    AMO_QUERIES[:] = query_data.amo
    IP_RANGES[:] = query_data.ip_ranges
    TOP_PICKS_QUERIES[:] = query_data.top_picks
    WIKIPEDIA_QUERIES[:] = query_data.wikipedia


@events.init.add_listener
def on_locust_init(environment, **kwargs):
    """Register a message on worker nodes."""
    if not isinstance(environment.runner, MasterRunner):
        environment.runner.register_message("store_suggestions", store_suggestions)


class QueryData(BaseModel):
    """Class that holds query data for targeting Merino providers"""

    adm: QueriesList = []
    amo: list[str] = []
    ip_ranges: IpRangeList = []
    top_picks: QueriesList = []
    wikipedia: list[str] = []


class MerinoUser(HttpUser):
    """User that sends requests to the Merino API."""

    def on_start(self) -> Any:
        """Instructions to execute for each simulated user when they start."""
        # Check that the Merino 'Host' is available
        version: Version | None = self._request_version()
        if not version:
            logger.error(
                "The Merino version information was unavailable. Verify that "
                "the Merino 'Host' is reachable."
            )
            raise StopUser()
        logger.debug(f"User will execute queries against Merino: {version.commit}")

        # Create a Faker instance for generating random suggest queries
        self.faker = faker.Faker(locale="en-US", providers=["faker.providers.lorem"])

        # By this time suggestions are expected to be stored on the worker
        logger.debug(
            f"user will be sending queries based on the following number of "
            f"stored suggestions: "
            f"adm: {len(ADM_QUERIES)}, "
            f"amo: {len(AMO_QUERIES)}, "
            f"top picks: {len(TOP_PICKS_QUERIES)},"
            f"wikipedia: {len(WIKIPEDIA_QUERIES)}"
        )

        return super().on_start()

    @task(weight=2)
    def adm_suggestions(self) -> None:
        """Send multiple requests for AdM queries."""
        queries: list[str] = choice(ADM_QUERIES)  # nosec
        providers: str = "adm"

        for query in queries:
            self._request_suggestions(query, providers)

    @task(weight=2)
    def amo_suggestions(self) -> None:
        """Send a request for AMO. AMO matches work with matching the first keyword
        and then prefix on subsequent words.
        """
        phrase: str = choice(AMO_QUERIES)  # nosec
        providers: str = "amo"

        first_word: str = phrase.split()[0]
        self._request_suggestions(first_word, providers)
        for i in range(len(first_word), len(phrase) + 1):
            self._request_suggestions(phrase[:i], providers)

    @task(weight=2)
    def dynamic_wikipedia_suggestions(self) -> None:
        """Send multiple requests for Dynamic Wikipedia queries."""
        full_query: str = choice(WIKIPEDIA_QUERIES)  # nosec
        providers: str = "wikipedia"

        queries: list[str] = [full_query[:x] for x in range(2, (len(full_query) + 1))]
        for query in queries:
            self._request_suggestions(query, providers)

    @task(weight=2)
    def faker_suggestions(self) -> None:
        """Send multiple requests for random queries."""
        # This produces a query between 2 and 4 random words
        full_query = " ".join(self.faker.words(nb=randint(2, 4)))  # nosec

        for query in [full_query[: i + 1] for i in range(len(full_query))]:
            # Send multiple requests for the entire query, but skip spaces
            if query.endswith(" "):
                continue

            self._request_suggestions(query)

    @task(weight=2)
    def top_picks_suggestions(self) -> None:
        """Send multiple requests for Top Picks queries."""
        queries: list[str] = choice(TOP_PICKS_QUERIES)  # nosec
        providers: str = "top_picks"

        for query in queries:
            self._request_suggestions(query, providers)

    @task(weight=90)
    def weather_suggestions(self) -> None:
        """Send multiple requests for Weather queries."""
        # Firefox will do local keyword matching to trigger weather suggestions
        # sending an empty query to Merino.
        query: str = ""
        providers: str = "accuweather"
        headers: dict[str, str] = {
            "X-Forwarded-For": self._get_ip_from_range(*choice(IP_RANGES))  # nosec
        }

        self._request_suggestions(query, providers, headers)

    @staticmethod
    def _get_ip_from_range(begin_ip_address: str, end_ip_address: str) -> str:
        # Convert the begin and end IP address values to integers. Randomly chose an
        # integer within the range and convert the integer back to an IP string.
        start: int = struct.unpack(">I", socket.inet_aton(begin_ip_address))[0]
        stop: int = struct.unpack(">I", socket.inet_aton(end_ip_address))[0]
        return socket.inet_ntoa(struct.pack(">I", randint(start, stop)))  # nosec

    def _request_suggestions(
        self,
        query: str,
        providers: str | None = None,
        headers: dict[str, str] | None = None,
    ) -> None:
        """Request suggestions from Merino for the given query string.

        Args:
            query: Query string
            providers: Optional. A comma-separated list of providers to use for this request
            headers: Optional. A dictionary of header key value pairs
        Raises:
            ValidationError: Response data is not as expected.
        """
        params: dict[str, Any] = {"q": query}

        if CLIENT_VARIANTS:
            params = {**params, "client_variants": CLIENT_VARIANTS}

        if providers:
            params = {**params, "providers": providers}

        default_headers: dict[str, str] = {
            "Accept-Language": choice(LOCALES),  # nosec
            "User-Agent": choice(DESKTOP_FIREFOX),  # nosec
        }

        with self.client.get(
            url=SUGGEST_API,
            params=params,
            headers=((default_headers | headers) if headers else default_headers),
            catch_response=True,
            # group all requests under the 'name' entry
            name=f"{SUGGEST_API}{(f'?providers={providers}' if providers else '')}",
        ) as response:
            if response.status_code == 0:
                # Do not classify as failure
                #
                # 0: The HttpSession catches any requests.RequestException thrown by
                #    Session (caused by connection errors, timeouts or similar), instead
                #    returning a dummy Response object with status_code set to 0 and
                #    content set to None.
                logger.warning("Received a response with a status code of 0.")
                response.success()
                return

            # This contextmanager returns a response that provides the ability to
            # manually control if an HTTP request should be marked as successful or
            # a failure in Locust's statistics
            if response.status_code != 200:
                response.failure(
                    f"{response.status_code=}, expected 200, {response.text=}"
                )
                return

            # Create a pydantic model instance for validating the response content
            # from Merino. This will raise a ValidationError if the response is missing
            # fields which will be reported as a failure in Locust's statistics.
            SuggestResponse(**response.json())

    def _request_version(self) -> Version | None:
        """Request version information from Merino.

        Returns:
            Version | None: Merino version information or None
        Raises:
            ValidationError: Response data is not as expected.
        """
        headers: dict[str, str] = {
            "Accept-Language": choice(LOCALES),  # nosec
            "User-Agent": choice(DESKTOP_FIREFOX),  # nosec
        }
        with self.client.get(
            url=VERSION_API, headers=headers, catch_response=True
        ) as response:
            if response.status_code != 200:
                response.failure(
                    f"{response.status_code=}, expected 200, {response.text=}"
                )
                return None
            return Version(**response.json())
