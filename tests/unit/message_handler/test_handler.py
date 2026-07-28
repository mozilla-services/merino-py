# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

"""Unit tests for the search term submission message handler."""

import httpx
import pytest
from pytest_mock import MockerFixture

from merino import message_handler as message_handler_module
from merino.message_handler import MessageHandler, get_message_handler
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


async def _noop(batch: list[SuggestRequestParams]) -> None:
    """No-op batch callback for isolating lifecycle from the fleece sink."""


@pytest.mark.asyncio
async def test_start_stop_lifecycle() -> None:
    """Test that the handler starts a running queue and stops it cleanly."""
    handler = MessageHandler(on_batch=_noop)
    assert not handler.is_running()

    await handler.start()
    assert handler.is_running()

    await handler.stop()
    assert not handler.is_running()


@pytest.mark.asyncio
async def test_start_is_idempotent() -> None:
    """Test that a second start while running does not replace the queue."""
    handler = MessageHandler(on_batch=_noop)
    await handler.start()
    queue = handler._queue

    await handler.start()

    assert handler._queue is queue
    await handler.stop()


@pytest.mark.asyncio
async def test_stop_without_start_is_noop() -> None:
    """Test that stopping a handler that never started does not raise."""
    handler = MessageHandler(on_batch=_noop)
    await handler.stop()
    assert not handler.is_running()


@pytest.mark.asyncio
async def test_put_before_start_raises() -> None:
    """Test that enqueuing before start raises a clear error."""
    handler = MessageHandler(on_batch=_noop)
    with pytest.raises(RuntimeError, match="not running"):
        handler.put(_params("firefox"))


@pytest.mark.asyncio
async def test_queued_items_are_drained_on_shutdown() -> None:
    """Test that buffered search terms are processed before the handler stops."""
    processed: list[SuggestRequestParams] = []

    async def capture(batch: list[SuggestRequestParams]) -> None:
        processed.extend(batch)

    handler = MessageHandler(on_batch=capture)
    await handler.start()

    handler.put(_params("apple"))
    handler.put(_params("orange"))

    await handler.stop()

    assert {params.query for params in processed} == {"apple", "orange"}


@pytest.mark.asyncio
async def test_default_sink_creates_and_closes_fleece_client(mocker: MockerFixture) -> None:
    """Test that with no override, the handler creates a FleeceClient and closes it on stop."""
    http_client = mocker.AsyncMock(spec=httpx.AsyncClient)
    create_http_client = mocker.patch(
        "merino.message_handler.handler.create_http_client", return_value=http_client
    )

    handler = MessageHandler()
    await handler.start()

    create_http_client.assert_called_once()
    # Read through a local so mypy does not narrow handler._client (stop() clears it).
    client = handler._client
    assert isinstance(client, FleeceClient)
    assert handler.is_running()

    await handler.stop()

    http_client.aclose.assert_awaited_once()
    assert handler._client is None
    assert not handler.is_running()


@pytest.mark.asyncio
async def test_module_start_stop_manage_singleton(mocker: MockerFixture) -> None:
    """Test that the module-level wrappers start and stop the shared singleton."""
    mocker.patch(
        "merino.message_handler.handler.create_http_client",
        return_value=mocker.AsyncMock(spec=httpx.AsyncClient),
    )
    assert get_message_handler() is message_handler_module.message_handler

    await message_handler_module.start()
    assert message_handler_module.message_handler.is_running()

    await message_handler_module.stop()
    assert not message_handler_module.message_handler.is_running()


@pytest.mark.asyncio
async def test_start_regular_services_wires_message_handler(mocker: MockerFixture) -> None:
    """Test that regular service startup starts the message handler and registers its drain."""
    import merino.main as main

    mocker.patch("merino.providers.suggest.init_providers", new=mocker.AsyncMock())
    mocker.patch("merino.providers.manifest.init_provider", new=mocker.AsyncMock())
    mocker.patch("merino.providers.rss.init_providers", new=mocker.AsyncMock())
    mocker.patch("merino.curated_recommendations.init_provider", new=mocker.MagicMock())
    mocker.patch("merino.providers.games.init_providers", new=mocker.AsyncMock())
    start_mock = mocker.patch.object(message_handler_module, "start", new=mocker.AsyncMock())

    cleanup_callbacks: list = []
    await main._start_regular_services(cleanup_callbacks)

    start_mock.assert_awaited_once()
    assert message_handler_module.stop in cleanup_callbacks
