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
from locust import HttpUser, events, task
from locust.clients import HttpSession
from locust.runners import MasterRunner

from merino.providers.adm.backends.remotesettings import (
    KintoSuggestion,
    RemoteSettingsBackend,
)
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

# This will be populated on each worker and
ADM_QUERIES: QueriesList = []
WIKIPEDIA_QUERIES: QueriesList = []


@events.test_start.add_listener
def on_locust_test_start(environment, **kwargs):
    """Download suggestions from Kinto and store suggestions on workers."""
    if not isinstance(environment.runner, MasterRunner):
        return

    suggestions: list[KintoSuggestion] = asyncio.run(get_rs_suggestions())

    logger.info("download_suggestions: Downloaded %d suggestions", len(suggestions))

    data: dict[str, QueriesList] = {"adm": [], "wikipedia": []}
    for suggestion in suggestions:
        match suggestion.advertiser:
            case "Wikipedia":
                data["wikipedia"].append(suggestion.keywords)
            case _:
                data["adm"].append(suggestion.keywords)

    for worker in environment.runner.clients:
        environment.runner.send_message("store_suggestions", data, client_id=worker)


async def get_rs_suggestions() -> list[KintoSuggestion]:
    """Get suggestions from Remote Settings.

    Returns:
        list[KintoSuggestion]: List of Remote Settings suggestion data
    Raises:
        BackendError: Failed request to Remote Settings
    """
    rs_backend: RemoteSettingsBackend = RemoteSettingsBackend(
        server=KINTO__SERVER_URL, collection=KINTO__COLLECTION, bucket=KINTO__BUCKET
    )
    attachment_url: str = await rs_backend.get_attachment_host()
    records: KintoRecords = await rs_backend.get_records()
    return await rs_backend.get_suggestions(attachment_url, records)


def store_suggestions(environment, msg, **kwargs):
    """Modify the module scoped list with suggestions in-place."""
    logger.info("store_suggestions: Storing %d suggestions", len(msg.data))
    ADM_QUERIES[:] = msg.data.get("adm")
    WIKIPEDIA_QUERIES[:] = msg.data.get("wikipedia")


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


class MerinoUser(HttpUser):
    """User that sends requests to the Merino API."""

    def on_start(self):
        """Instructions to execute for each simulated user when they start."""
        # Create a Faker instance for generating random suggest queries
        self.faker = faker.Faker(locale="en-US", providers=["faker.providers.lorem"])

        # By this time suggestions are expected to be stored on the worker
        logger.debug(
            "user will be sending queries based on the %d stored suggestions",
            (len(ADM_QUERIES) + len(WIKIPEDIA_QUERIES)),
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
        # TODO Replace query source with ElasticSearch Source, not RemoteSettings
        queries: list[str] = choice(WIKIPEDIA_QUERIES)  # nosec
        providers: str = "wikipedia"  # TODO double check providers name

        for query in queries:
            request_suggestions(self.client, query, providers)

    @task(weight=10)
    def wikipedia_suggestions(self) -> None:
        """Send multiple requests for Wikipedia queries."""
        queries: list[str] = choice(WIKIPEDIA_QUERIES)  # nosec
        providers: str = "adm"

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

    @task(weight=0)
    def wikifruit_suggestions(self) -> None:
        """Send multiple requests for random WikiFruit queries."""
        # These queries are supported by the WikiFruit provider
        for fruit in ("apple", "banana", "cherry"):
            request_suggestions(self.client, fruit)
