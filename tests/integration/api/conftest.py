# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

"""Module for test configurations for the integration test directory."""

from logging import LogRecord
from typing import Iterator, Generator

import pytest
import orjson
from starlette.testclient import TestClient
from aiodogstatsd import Client as AioDogstatsdClient
from merino.utils.gcs.gcs_uploader import GcsUploader
from contextlib import nullcontext
from merino.curated_recommendations.fakespot_backend.protocol import (
    FakespotFeed,
    FakespotProduct,
    FAKESPOT_DEFAULT_CATEGORY_NAME,
    FAKESPOT_HEADER_COPY,
    FAKESPOT_FOOTER_COPY,
    FakespotCTA,
    FAKESPOT_CTA_COPY,
    FAKESPOT_CTA_URL,
)
from merino.main import app
from merino.utils.log_data_creators import RequestSummaryLogDataModel
from merino.middleware import ScopeKey
from tests.integration.api.types import RequestSummaryLogDataFixture


class NoOpMetricsClient(AioDogstatsdClient):
    """No-op metrics client for test usage that inherits from aiodogstatsd.Client."""

    def increment(self, *args, **kwargs):
        """Do nothing instead of sending a metric increment."""
        pass

    def gauge(self, *args, **kwargs):
        """Do nothing instead of sending a metric gauge."""
        pass

    def timeit(self, *args, **kwargs):
        """Return a no-op context manager instead of timing."""
        return nullcontext()


@pytest.fixture(scope="function")
def gcp_uploader(gcs_storage_client, gcs_storage_bucket) -> GcsUploader:
    """Return a custom test gcs uploader"""
    return GcsUploader(
        destination_gcp_project=gcs_storage_client.project,
        destination_bucket_name=gcs_storage_bucket.name,
        destination_cdn_hostname="",
    )


@pytest.fixture(name="client")
def fixture_test_client() -> TestClient:
    """Return a FastAPI TestClient instance.

    Note that this will NOT trigger event handlers (i.e. `startup` and `shutdown`) for
    the app, see: https://fastapi.tiangolo.com/advanced/testing-events/
    """
    return TestClient(app)


@pytest.fixture(name="client_with_metrics")
def fixture_client_with_metrics() -> Generator[TestClient, None, None]:
    """Create test client with NoOpMetricsClient in request scope."""

    async def asgi_wrapper(scope, receive, send):
        scope[ScopeKey.METRICS_CLIENT] = NoOpMetricsClient()
        await app(scope, receive, send)

    with TestClient(asgi_wrapper) as client:
        yield client


@pytest.fixture(name="client_with_events")
def fixture_test_client_with_events() -> Iterator[TestClient]:
    """Return a FastAPI TestClient instance.

    This test client will trigger event handlers (i.e. `startup` and `shutdown`) for
    the app, see: https://fastapi.tiangolo.com/advanced/testing-events/
    """
    with TestClient(app) as client:
        yield client


@pytest.fixture(name="extract_request_summary_log_data")
def fixture_extract_request_summary_log_data() -> RequestSummaryLogDataFixture:
    """Return a function that will extract the extra log data from a captured
    "request.summary" log record
    """

    def extract_request_summary_log_data(
        record: LogRecord,
    ) -> RequestSummaryLogDataModel:
        return RequestSummaryLogDataModel(
            errno=record.__dict__["errno"],
            time=record.__dict__["time"],
            agent=record.__dict__["agent"],
            path=record.__dict__["path"],
            method=record.__dict__["method"],
            lang=record.__dict__["lang"],
            querystring=record.__dict__["querystring"],
            code=record.__dict__["code"],
        )

    return extract_request_summary_log_data


def fakespot_feed() -> FakespotFeed:
    """Open JSON file for mocked fakespot products & return constructed Fakespot feed"""
    with open("tests/data/fakespot_products.json", "rb") as f:
        fakespot_products_json_data = orjson.loads(f.read())

        fakespot_products = []
        for product in fakespot_products_json_data:
            fakespot_products.append(
                FakespotProduct(
                    id=product["id"],
                    title=product["title"],
                    category=product["category"],
                    imageUrl=product["imageUrl"],
                    url=product["url"],
                )
            )
    return FakespotFeed(
        products=fakespot_products,
        defaultCategoryName=FAKESPOT_DEFAULT_CATEGORY_NAME,
        headerCopy=FAKESPOT_HEADER_COPY,
        footerCopy=FAKESPOT_FOOTER_COPY,
        cta=FakespotCTA(ctaCopy=FAKESPOT_CTA_COPY, url=FAKESPOT_CTA_URL),
    )
