"""Unit tests for the merino-fleece PII detection client."""

from typing import Any

import httpx
import pytest
from pytest import LogCaptureFixture
from pytest_mock import MockerFixture

from merino.configs import settings
from merino.utils.query_processing import fleece_client as fleece_module
from merino.utils.query_processing.fleece_client import (
    FleeceClient,
    get_fleece_client,
    init_fleece_client,
    shutdown_fleece_client,
)


@pytest.fixture(name="fleece")
def fixture_fleece() -> FleeceClient:
    """Create a FleeceClient."""
    return FleeceClient(
        http_client=httpx.AsyncClient(base_url="http://test-fleece"),
        pii_path="/api/v1/pii",
    )


def _response(json_body: Any, status_code: int = 200) -> httpx.Response:
    """Build an httpx.Response for the PII endpoint."""
    return httpx.Response(
        status_code=status_code,
        json=json_body,
        request=httpx.Request("GET", "http://test-fleece/api/v1/pii?q=test"),
    )


@pytest.mark.asyncio
@pytest.mark.parametrize(["pii", "expected"], [(True, True), (False, False)])
async def test_detect_pii_parses_flag(
    mocker: MockerFixture, fleece: FleeceClient, pii: bool, expected: bool
) -> None:
    """Test that detect_pii returns the boolean `pii` field from the fleece response."""
    mocker.patch.object(httpx.AsyncClient, "get", return_value=_response({"pii": pii}))

    assert await fleece.detect_pii("barack obama") is expected
    await fleece.shutdown()


@pytest.mark.asyncio
async def test_detect_pii_safe_returns_result_and_times(
    mocker: MockerFixture, fleece: FleeceClient, statsd_mock: Any
) -> None:
    """Test that detect_pii_safe returns the detected value and records the duration metric."""
    mocker.patch.object(httpx.AsyncClient, "get", return_value=_response({"pii": True}))

    assert await fleece.detect_pii_safe("barack obama", statsd_mock) is True
    statsd_mock.timeit.assert_called_once_with("fleece.pii.detect_duration")
    await fleece.shutdown()


@pytest.mark.asyncio
async def test_detect_pii_safe_fails_open_on_http_error(
    mocker: MockerFixture,
    fleece: FleeceClient,
    statsd_mock: Any,
    caplog: LogCaptureFixture,
) -> None:
    """Test that http error returns False and emits an error metric."""
    mocker.patch.object(
        httpx.AsyncClient, "get", side_effect=httpx.ConnectError("connection refused")
    )

    assert await fleece.detect_pii_safe("barack obama", statsd_mock) is False
    statsd_mock.increment.assert_called_once_with("fleece.pii.error", tags={"reason": "http"})
    assert any("merino-fleece request failed" in r.message for r in caplog.records)
    await fleece.shutdown()


@pytest.mark.asyncio
async def test_detect_pii_safe_fails_open_on_bad_response(
    mocker: MockerFixture, fleece: FleeceClient, statsd_mock: Any
) -> None:
    """Test that a response missing the `pii` key returns False and emits a response error metric."""
    mocker.patch.object(httpx.AsyncClient, "get", return_value=_response({"unexpected": 1}))

    assert await fleece.detect_pii_safe("barack obama", statsd_mock) is False
    statsd_mock.increment.assert_called_once_with("fleece.pii.error", tags={"reason": "response"})
    await fleece.shutdown()


@pytest.mark.asyncio
async def test_init_disabled_when_url_base_empty(mocker: MockerFixture) -> None:
    """Test that init_fleece_client is a no-op (client stays None) when url_base is empty."""
    mocker.patch.object(settings.fleece, "url_base", "")
    init_fleece_client()

    assert get_fleece_client() is None


@pytest.mark.asyncio
async def test_init_and_shutdown_lifecycle(mocker: MockerFixture) -> None:
    """Test that init builds the singleton when url_base is set; shutdown clears it."""
    mocker.patch.object(settings.fleece, "url_base", "http://test-fleece")
    init_fleece_client()
    try:
        client = get_fleece_client()
        assert isinstance(client, FleeceClient)
        # The singleton is reused across get() calls.
        assert get_fleece_client() is client
    finally:
        await shutdown_fleece_client()

    assert get_fleece_client() is None
    assert fleece_module._fleece_client is None


@pytest.mark.asyncio
async def test_shutdown_is_idempotent() -> None:
    """Test that shutdown_fleece_client is safe to call when no client is initialized."""
    await shutdown_fleece_client()
    assert get_fleece_client() is None
