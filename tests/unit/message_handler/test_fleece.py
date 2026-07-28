# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

"""Unit tests for the merino-fleece search terms client."""

import httpx
import pytest
from pytest_mock import MockerFixture

from merino.configs import settings
from merino.message_handler.errors import FleeceError
from merino.message_handler.fleece import FleeceClient
from merino_common.models.suggest_logging import SuggestRequestParams


def _params(query: str) -> SuggestRequestParams:
    """Build a minimal SuggestRequestParams for a given query."""
    return SuggestRequestParams(
        query=query,
        code=200,
        rid="rid",
        client_variants="",
        requested_providers="",
        browser="Firefox",
        os_family="macos",
        form_factor="desktop",
    )


@pytest.mark.asyncio
async def test_submit_posts_batch_as_submission(mocker: MockerFixture) -> None:
    """Test that a successful submit POSTs the batch to the search terms endpoint."""
    request = httpx.Request("POST", "http://fleece/api/v1/search-terms")
    http_client = mocker.AsyncMock(spec=httpx.AsyncClient)
    http_client.post.return_value = httpx.Response(201, request=request)

    client = FleeceClient(http_client=http_client)
    await client.submit([_params("apple"), _params("orange")])

    http_client.post.assert_awaited_once()
    args, kwargs = http_client.post.call_args
    assert args[0] == settings.fleece.search_terms_path
    assert [term["query"] for term in kwargs["json"]["search_terms"]] == ["apple", "orange"]


@pytest.mark.asyncio
async def test_submit_raises_fleece_error_on_bad_status(mocker: MockerFixture) -> None:
    """Test that a non-2xx response is wrapped in a FleeceError."""
    request = httpx.Request("POST", "http://fleece/api/v1/search-terms")
    http_client = mocker.AsyncMock(spec=httpx.AsyncClient)
    http_client.post.return_value = httpx.Response(500, request=request)

    client = FleeceClient(http_client=http_client)
    with pytest.raises(FleeceError, match="unexpected status 500"):
        await client.submit([_params("apple")])


@pytest.mark.asyncio
async def test_submit_raises_fleece_error_on_transport_error(mocker: MockerFixture) -> None:
    """Test that a transport error (e.g. timeout/connection failure) is wrapped in a FleeceError."""
    http_client = mocker.AsyncMock(spec=httpx.AsyncClient)
    http_client.post.side_effect = httpx.ConnectError("connection refused")

    client = FleeceClient(http_client=http_client)
    with pytest.raises(FleeceError, match="Failed to submit search terms"):
        await client.submit([_params("apple")])


@pytest.mark.asyncio
async def test_close_closes_http_client(mocker: MockerFixture) -> None:
    """Test that closing the client closes the underlying HTTP client."""
    http_client = mocker.AsyncMock(spec=httpx.AsyncClient)

    client = FleeceClient(http_client=http_client)
    await client.close()

    http_client.aclose.assert_awaited_once()
