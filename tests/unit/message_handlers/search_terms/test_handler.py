# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

"""Unit tests for the search term submission message handler."""

from collections.abc import Callable

import httpx
import pytest
from pytest_mock import MockerFixture

from merino.configs import settings
from merino.message_handlers import search_terms
from merino.message_handlers.search_terms import MessageHandler, get_message_handler
from merino.message_handlers.search_terms.errors import FleeceError
from merino.message_handlers.search_terms.fleece import FleeceClient
from merino.message_handlers.search_terms.pubsub import PubSubClient
from merino.utils.featureflags import FeatureFlags
from merino_common.models.suggest_logging import SearchTermsSubmission, SuggestRequestParams

Params = Callable[[str], SuggestRequestParams]


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
async def test_put_before_start_raises(params: Params) -> None:
    """Test that enqueuing before start raises a clear error."""
    handler = MessageHandler(on_batch=_noop)
    with pytest.raises(RuntimeError, match="not running"):
        handler.put(params("firefox"))


@pytest.mark.asyncio
async def test_queued_items_are_drained_on_shutdown(params: Params) -> None:
    """Test that buffered search terms are processed before the handler stops."""
    processed: list[SuggestRequestParams] = []

    async def capture(batch: list[SuggestRequestParams]) -> None:
        processed.extend(batch)

    handler = MessageHandler(on_batch=capture)
    await handler.start()

    handler.put(params("apple"))
    handler.put(params("orange"))

    await handler.stop()

    assert {p.query for p in processed} == {"apple", "orange"}


@pytest.mark.asyncio
async def test_default_sink_creates_and_closes_fleece_client(mocker: MockerFixture) -> None:
    """Test that with no override, the handler creates a FleeceClient and closes it on stop."""
    http_client = mocker.AsyncMock(spec=httpx.AsyncClient)
    create_http_client = mocker.patch(
        "merino.message_handlers.search_terms.handler.create_http_client",
        return_value=http_client,
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
async def test_start_skips_pubsub_when_topic_unset(mocker: MockerFixture) -> None:
    """Test that no Pub/Sub client is built when no backup topic is configured."""
    mocker.patch(
        "merino.message_handlers.search_terms.handler.create_http_client",
        return_value=mocker.AsyncMock(spec=httpx.AsyncClient),
    )
    mocker.patch.object(settings.message_handler, "pubsub_topic", "")

    handler = MessageHandler()
    await handler.start()

    assert handler._pubsub is None
    await handler.stop()


@pytest.mark.asyncio
async def test_backup_publishes_batch_to_pubsub(mocker: MockerFixture, params: Params) -> None:
    """Test that the error-path adapter forwards the failed batch to the Pub/Sub client."""
    handler = MessageHandler()
    pubsub = mocker.AsyncMock(spec=PubSubClient)
    handler._pubsub = pubsub

    batch = [params("apple")]
    await handler._backup(batch, FleeceError("boom"))

    pubsub.publish.assert_awaited_once_with(batch)


@pytest.mark.asyncio
async def test_failed_submission_falls_back_to_pubsub(
    mocker: MockerFixture, params: Params
) -> None:
    """Test that a failed direct submission routes the batch to the Pub/Sub backup channel."""
    http_client = mocker.AsyncMock(spec=httpx.AsyncClient)
    http_client.post.side_effect = httpx.ConnectError("fleece down")
    mocker.patch(
        "merino.message_handlers.search_terms.handler.create_http_client",
        return_value=http_client,
    )
    publisher = mocker.MagicMock()
    publisher.publish.return_value.result.return_value = "message-id"
    mocker.patch(
        "merino.message_handlers.search_terms.handler.create_publisher_client",
        return_value=publisher,
    )
    mocker.patch.object(settings.message_handler, "pubsub_topic", "projects/p/topics/t")

    handler = MessageHandler()
    await handler.start()
    handler.put(params("apple"))
    await handler.stop()

    publisher.publish.assert_called_once()
    topic, data = publisher.publish.call_args.args
    assert topic == "projects/p/topics/t"
    submission = SearchTermsSubmission.model_validate_json(data)
    assert [term.query for term in submission.search_terms] == ["apple"]


@pytest.mark.asyncio
async def test_stop_closes_pubsub_client(mocker: MockerFixture) -> None:
    """Test that stopping the handler closes the Pub/Sub client."""
    handler = MessageHandler()
    pubsub = mocker.MagicMock(spec=PubSubClient)
    handler._pubsub = pubsub

    await handler.stop()

    pubsub.close.assert_called_once()
    assert handler._pubsub is None


@pytest.mark.asyncio
async def test_module_start_stop_manage_singleton(mocker: MockerFixture) -> None:
    """Test that the module-level wrappers start and stop the shared singleton."""
    mocker.patch(
        "merino.message_handlers.search_terms.handler.create_http_client",
        return_value=mocker.AsyncMock(spec=httpx.AsyncClient),
    )
    assert get_message_handler() is search_terms.message_handler

    await search_terms.start()
    assert search_terms.message_handler.is_running()

    await search_terms.stop()
    assert not search_terms.message_handler.is_running()


@pytest.mark.asyncio
async def test_start_regular_services_wires_message_handler(mocker: MockerFixture) -> None:
    """Test that regular startup starts the handler and registers its drain when enabled."""
    import merino.main as main

    mocker.patch.object(FeatureFlags, "is_enabled", return_value=True)
    mocker.patch("merino.providers.suggest.init_providers", new=mocker.AsyncMock())
    mocker.patch("merino.providers.manifest.init_provider", new=mocker.AsyncMock())
    mocker.patch("merino.providers.rss.init_providers", new=mocker.AsyncMock())
    mocker.patch("merino.curated_recommendations.init_provider", new=mocker.MagicMock())
    mocker.patch("merino.providers.games.init_providers", new=mocker.AsyncMock())
    start_mock = mocker.patch.object(search_terms, "start", new=mocker.AsyncMock())

    cleanup_callbacks: list = []
    await main._start_regular_services(cleanup_callbacks)

    start_mock.assert_awaited_once()
    assert search_terms.stop in cleanup_callbacks


@pytest.mark.asyncio
async def test_start_regular_services_skips_handler_when_disabled(mocker: MockerFixture) -> None:
    """Test that the handler is not started when submission is disabled."""
    import merino.main as main

    mocker.patch.object(FeatureFlags, "is_enabled", return_value=False)
    mocker.patch("merino.providers.suggest.init_providers", new=mocker.AsyncMock())
    mocker.patch("merino.providers.manifest.init_provider", new=mocker.AsyncMock())
    mocker.patch("merino.providers.rss.init_providers", new=mocker.AsyncMock())
    mocker.patch("merino.curated_recommendations.init_provider", new=mocker.MagicMock())
    mocker.patch("merino.providers.games.init_providers", new=mocker.AsyncMock())
    start_mock = mocker.patch.object(search_terms, "start", new=mocker.AsyncMock())

    cleanup_callbacks: list = []
    await main._start_regular_services(cleanup_callbacks)

    start_mock.assert_not_awaited()
    assert search_terms.stop not in cleanup_callbacks
