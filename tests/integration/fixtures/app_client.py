"""Fixture for the merino FastAPI app client object"""

import logging

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from aiodogstatsd import Client
from merino.middleware import ScopeKey
from typing import Generator

logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)


class NoOpMetricsClient(Client):
    """Create a no-op metrics client for test usage.

    This class inherits from `aiodogstatsd.Client`, but overrides `increment` and
    `timeit` so they do nothing. This prevents KeyErrors or real metric calls in tests.
    """

    def increment(self, *args, **kwargs):
        """Do nothing instead of sending a metric increment."""
        pass

    def gauge(self, *args, **kwargs):
        """Do nothing instead of sending a metric gauge."""
        pass

    def timeit(self, *args, **kwargs):
        """Return a no-op context manager instead of timing anything."""
        from contextlib import nullcontext

        return nullcontext()


@pytest.fixture(scope="module")
def test_app() -> FastAPI:
    """Test FastAPI app object"""
    test_app = FastAPI()
    return test_app


@pytest.fixture(scope="module")
def client_with_metrics(test_app) -> Generator[TestClient, None, None]:
    """Wrap `test_app` in an ASGI function that inserts a
    NoOpMetricsClient into the request scope, so that any endpoint referencing
    `request.scope[ScopeKey.METRICS_CLIENT]` won't crash.
    """

    async def asgi_wrapper(scope, receive, send):
        """Insert NoOpMetricsClient into the scope, then call the real app."""
        scope[ScopeKey.METRICS_CLIENT] = NoOpMetricsClient()
        await test_app(scope, receive, send)

    with TestClient(asgi_wrapper) as client:
        yield client
