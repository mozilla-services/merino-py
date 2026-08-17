"""The message handler for asynchronous search term submission."""

from collections.abc import Awaitable, Callable

from merino.configs import settings
from merino.message_handlers.search_terms.fleece import FleeceClient
from merino.message_handlers.search_terms.pubsub import (
    PubSubClient,
    create_publisher_client,
)
from merino_common.utils.http_client import create_http_client
from merino_common.models.suggest_logging import SuggestRequestParams
from merino_common.utils.async_batch_queue import AsyncBatchQueue

# identifier used to tag the queue's metrics.
QUEUE_ID = "search_term_submission"


class MessageHandler:
    """Buffers search terms and submits them to merino-fleece in batches.

    Args:
        on_batch: async callback for each batch. Defaults to submitting to merino-fleece
            via a ``FleeceClient``; override only in tests.
    """

    def __init__(
        self,
        on_batch: (Callable[[list[SuggestRequestParams]], Awaitable[object]] | None) = None,
    ) -> None:
        self._on_batch = on_batch
        self._client: FleeceClient | None = None
        self._pubsub: PubSubClient | None = None
        self._queue: AsyncBatchQueue[SuggestRequestParams] | None = None

    async def start(self) -> None:
        """Build the queue (and default fleece client) and start its background task."""
        if self._queue is not None:
            return
        on_batch = self._on_batch
        on_error: Callable[[list[SuggestRequestParams], Exception], Awaitable[object]] | None = (
            None
        )
        if on_batch is None:
            self._client = FleeceClient(
                http_client=create_http_client(
                    base_url=settings.fleece.url_base,
                    connect_timeout=settings.message_handler.connect_timeout_sec,
                    request_timeout=settings.message_handler.collection_delay_sec / 2,
                )
            )
            on_batch = self._client.submit
            # fall back to the Pub/Sub backup channel on submission failure when configured.
            if settings.message_handler.pubsub_topic:
                self._pubsub = PubSubClient(
                    publisher=create_publisher_client(),
                    topic=settings.message_handler.pubsub_topic,
                )
                on_error = self._backup
        queue: AsyncBatchQueue[SuggestRequestParams] = AsyncBatchQueue(
            on_batch=on_batch,
            on_error=on_error,
            queue_id=QUEUE_ID,
            max_batch_size=settings.message_handler.max_batch_size,
            collection_delay_s=settings.message_handler.collection_delay_sec,
            shutdown_deadline_s=settings.message_handler.shutdown_deadline_sec,
            max_queue_size=settings.message_handler.max_queue_size,
        )
        await queue.start()
        self._queue = queue

    async def stop(self) -> None:
        """Drain the queue, then close the fleece client.

        Buffered terms are processed before the client closes (bounded by the shutdown
        deadline).
        """
        if self._queue is not None:
            await self._queue.stop()
            self._queue = None
        if self._client is not None:
            await self._client.close()
            self._client = None
        if self._pubsub is not None:
            self._pubsub.close()
            self._pubsub = None

    async def _backup(self, batch: list[SuggestRequestParams], exc: Exception) -> None:
        """Publish a failed batch to the Pub/Sub backup channel (the queue's error path)."""
        if self._pubsub is not None:
            await self._pubsub.publish(batch)

    def put(self, message: SuggestRequestParams) -> None:
        """Enqueue a search term for asynchronous processing.

        Raises:
            RuntimeError: If the handler has not been started.
        """
        if self._queue is None:
            raise RuntimeError("The message handler is not running")
        self._queue.put(message)

    def is_running(self) -> bool:
        """Return whether the message handler's queue is running."""
        return self._queue is not None and self._queue.is_running()
