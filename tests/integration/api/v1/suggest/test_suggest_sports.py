"""Integration tests for the Wikipedia provider."""

from typing import Any

import pytest
from fastapi.testclient import TestClient
from freezegun import freeze_time
from pytest_mock import MockerFixture

from merino.configs import settings
from merino.exceptions import BackendError
from merino.providers.suggest.sports.backends.sportsdata.backend import SportsDataBackend
from merino.providers.suggest.sports.provider import SportsDataProvider


@pytest.fixture(name="backend_mock")
def fixture_backend_mock(mocker: MockerFixture) -> Any:
    """Create a SportsDataBackend mock for circuit breaker tests,
    to allow mid-test behavior changes (from fail to recovery)
    """
    backend = mocker.AsyncMock(spec=SportsDataBackend)
    backend.shutdown = mocker.AsyncMock()
    return backend


@pytest.fixture(name="providers")
def fixture_providers(backend_mock: Any, statsd_mock: Any) -> dict[str, SportsDataProvider]:
    """Define the Sports provider backed by a mock for circuit breaker tests."""
    return {
        "sports": SportsDataProvider(
            backend=backend_mock,
            metrics_client=statsd_mock,
            enabled_by_default=True,
            intent_words=["test"],
        )
    }


def test_circuit_breaker_with_backend_error_sports(
    client: TestClient,
    backend_mock: Any,
    mocker: MockerFixture,
) -> None:
    """Verify that the sports provider behaves as expected when its circuit breaker is triggered."""
    query = "test+manchester+united"
    backend_mock.query.side_effect = BackendError("Elasticsearch failure")

    with freeze_time("2025-04-11") as freezer:
        # trip the breaker by hitting the failing endpoint `threshold` times
        for _ in range(settings.providers.sports.circuit_breaker_failure_threshold):
            _ = client.get(f"/api/v1/suggest?providers=sports&q={query}")

        # after open, subsequent calls should be short-circuited and not touch the backend
        spy = mocker.spy(backend_mock, "query")
        for _ in range(settings.providers.sports.circuit_breaker_failure_threshold):
            _ = client.get(f"/api/v1/suggest?providers=sports&q={query}")
        spy.assert_not_called()

        # advance time past recovery timeout to allow half-open
        freezer.tick(settings.providers.sports.circuit_breaker_recover_timeout_sec + 1.0)

        # restore normal backend behavior and ensure a successful pass closes the breaker
        backend_mock.query.side_effect = None
        backend_mock.query.return_value = []

        response = client.get(f"/api/v1/suggest?providers=sports&q={query}")
        assert response.status_code == 200
        spy.assert_called_once()  # half-open allowed a trial call through

        # subsequent requests should also succeed (breaker back to closed)
        for _ in range(settings.providers.sports.circuit_breaker_failure_threshold):
            response = client.get(f"/api/v1/suggest?providers=sports&q={query}")
            assert response.status_code == 200
