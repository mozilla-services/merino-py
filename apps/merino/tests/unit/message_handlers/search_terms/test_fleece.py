# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

"""Unit tests for the merino-fleece search terms client."""

import asyncio
import json
from collections.abc import Callable

import httpx
import pytest
from pytest_mock import MockerFixture

from merino.configs import settings
from merino.message_handlers.search_terms import fleece
from merino.message_handlers.search_terms.errors import FleeceError
from merino.message_handlers.search_terms.fleece import FleeceClient
from merino_common.models.suggest_logging import SuggestRequestParams
from tests.unit.message_handlers.search_terms.conftest import SUBMITTED_AT_ISO

Params = Callable[[str], SuggestRequestParams]


@pytest.mark.asyncio
async def test_submit_posts_batch_as_submission(mocker: MockerFixture, params: Params) -> None:
    """Test that a successful submit POSTs the batch to the search terms endpoint."""
    request = httpx.Request("POST", "http://fleece/api/v1/search-terms")
    http_client = mocker.AsyncMock(spec=httpx.AsyncClient)
    http_client.post.return_value = httpx.Response(201, request=request)

    client = FleeceClient(http_client=http_client)
    await client.submit([params("apple"), params("orange")])

    http_client.post.assert_awaited_once()
    args, kwargs = http_client.post.call_args
    assert args[0] == settings.fleece.search_terms_path
    assert [term["query"] for term in kwargs["json"]["search_terms"]] == ["apple", "orange"]


@pytest.mark.asyncio
async def test_submit_posts_submitted_at_as_json_encodable_string(
    mocker: MockerFixture, params: Params
) -> None:
    """Test that the submission timestamp is posted as a UTC ISO string.

    The body must be JSON-encodable as dumped: httpx encodes the `json=` kwarg itself
    and raises TypeError on a raw datetime, which the model's field serializer prevents.
    """
    request = httpx.Request("POST", "http://fleece/api/v1/search-terms")
    http_client = mocker.AsyncMock(spec=httpx.AsyncClient)
    http_client.post.return_value = httpx.Response(201, request=request)

    client = FleeceClient(http_client=http_client)
    await client.submit([params("apple")])

    body = http_client.post.call_args.kwargs["json"]
    assert body["search_terms"][0]["submitted_at"] == SUBMITTED_AT_ISO
    json.dumps(body)  # raises TypeError if any value is not JSON-encodable


@pytest.mark.asyncio
async def test_submit_raises_fleece_error_on_bad_status(
    mocker: MockerFixture, params: Params
) -> None:
    """Test that a non-2xx response is wrapped in a FleeceError."""
    request = httpx.Request("POST", "http://fleece/api/v1/search-terms")
    http_client = mocker.AsyncMock(spec=httpx.AsyncClient)
    http_client.post.return_value = httpx.Response(500, request=request)

    client = FleeceClient(http_client=http_client)
    with pytest.raises(FleeceError, match="unexpected status 500"):
        await client.submit([params("apple")])


@pytest.mark.asyncio
async def test_submit_raises_fleece_error_on_transport_error(
    mocker: MockerFixture, params: Params
) -> None:
    """Test that a transport error (e.g. timeout/connection failure) is wrapped in a FleeceError."""
    http_client = mocker.AsyncMock(spec=httpx.AsyncClient)
    http_client.post.side_effect = httpx.ConnectError("connection refused")

    client = FleeceClient(http_client=http_client)
    with pytest.raises(FleeceError, match="Failed to submit search terms"):
        await client.submit([params("apple")])


@pytest.mark.asyncio
async def test_submit_records_success_outcome(mocker: MockerFixture, params: Params) -> None:
    """Test that a successful submission is recorded as a success in the duration histogram."""
    histogram = mocker.patch.object(fleece, "_submit_duration_histogram")
    request = httpx.Request("POST", "http://fleece/api/v1/search-terms")
    http_client = mocker.AsyncMock(spec=httpx.AsyncClient)
    http_client.post.return_value = httpx.Response(201, request=request)

    client = FleeceClient(http_client=http_client)
    await client.submit([params("apple")])

    assert histogram.record.call_args.args[1] == {"outcome": "success"}


@pytest.mark.asyncio
async def test_submit_records_error_outcome_on_bad_status(
    mocker: MockerFixture, params: Params
) -> None:
    """Test that a failed submission is recorded as an error in the duration histogram."""
    histogram = mocker.patch.object(fleece, "_submit_duration_histogram")
    transport = httpx.MockTransport(lambda request: httpx.Response(503))

    async with httpx.AsyncClient(base_url="http://fleece", transport=transport) as http_client:
        client = FleeceClient(http_client=http_client)
        with pytest.raises(FleeceError):
            await client.submit([params("apple")])

    assert histogram.record.call_args.args[1] == {"outcome": "error"}


@pytest.mark.asyncio
async def test_submit_records_error_outcome_on_closed_client(
    mocker: MockerFixture, params: Params
) -> None:
    """Test that a submission on a closed HTTP client is recorded as an error.

    httpx raises a bare RuntimeError, not an HTTPError, when the client is closed, so the
    failure escapes `except HTTPError`.
    """
    histogram = mocker.patch.object(fleece, "_submit_duration_histogram")
    transport = httpx.MockTransport(lambda request: httpx.Response(201))
    http_client = httpx.AsyncClient(base_url="http://fleece", transport=transport)
    await http_client.aclose()

    client = FleeceClient(http_client=http_client)
    with pytest.raises(RuntimeError, match="the client has been closed"):
        await client.submit([params("apple")])

    assert histogram.record.call_args.args[1] == {"outcome": "error"}


@pytest.mark.asyncio
async def test_submit_records_error_outcome_on_cancellation(
    mocker: MockerFixture, params: Params
) -> None:
    """Test that a cancelled submission is recorded as an error in the duration histogram.

    A cancelled request raises `asyncio.CancelledError`, a BaseException that escapes
    `except HTTPError` too.
    """
    histogram = mocker.patch.object(fleece, "_submit_duration_histogram")
    in_flight = asyncio.Event()

    async def hang(request: httpx.Request) -> httpx.Response:
        """Block the request until the submitting task is cancelled."""
        in_flight.set()
        await asyncio.Event().wait()
        raise AssertionError("unreachable: the request is cancelled while waiting")

    transport = httpx.MockTransport(hang)

    async with httpx.AsyncClient(base_url="http://fleece", transport=transport) as http_client:
        client = FleeceClient(http_client=http_client)
        task = asyncio.create_task(client.submit([params("apple")]))
        await in_flight.wait()
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task

    assert histogram.record.call_args.args[1] == {"outcome": "error"}


@pytest.mark.asyncio
async def test_close_closes_http_client(mocker: MockerFixture) -> None:
    """Test that closing the client closes the underlying HTTP client."""
    http_client = mocker.AsyncMock(spec=httpx.AsyncClient)

    client = FleeceClient(http_client=http_client)
    await client.close()

    http_client.aclose.assert_awaited_once()
