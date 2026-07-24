"""Pub/Sub worker for processing search term submissions."""

import logging
import time

import google.cloud.pubsub_v1 as pubsub_v1
from google.cloud.pubsub_v1.subscriber.message import Message
from google.cloud.pubsub_v1.types import SubscriberOptions
from merino_common.models.suggest_logging import SearchTermsSubmission
from pydantic import ValidationError

from merino_fleece.emitter import emit_sanitized_query
from merino_fleece.sanitizer import sanitize_query

logger = logging.getLogger(__name__)

# Seconds to wait before reconnecting after a stream error.
DEFAULT_RECONNECT_DELAY_SECONDS = 5


def callback(message: Message) -> None:
    """Handle an incoming Pub/Sub message: sanitize then emit its search terms."""
    try:
        submission = SearchTermsSubmission.model_validate_json(message.data)
        for query in submission.search_terms:
            sanitized = sanitize_query(query)
            emit_sanitized_query(sanitized)
    except ValidationError:
        logger.exception("Dropping invalid message")
    # TODO: Any additional exception handling as needed if encounter
    # error during sanitization or emission, once methods are defined
    # Should be caught and `nacked` for redelivery if not fatal
    message.ack()


class FleeceQueueWorker:
    """Streaming-pull worker that consumes and processes search term submissions.

    Wraps a Pub/Sub `SubscriberClient` and blocks on a streaming pull until the
    subscription is cancelled via `stop` or an error interrupts the stream.

    Args:
        subscription_name: Fully-qualified Pub/Sub subscription path
            (``projects/{project}/subscriptions/{subscription}``) to consume from.
        restart_stream: When True, `start` rebuilds the client and reopens the
            pull after a stream error, looping until the process is terminated.
            When False, `start` returns on the first stream error.
        restart_backoff: Seconds to wait before reconnecting after a stream error.
    """

    def __init__(
        self,
        subscription_name: str,
        restart_stream: bool = True,
        restart_backoff: int = DEFAULT_RECONNECT_DELAY_SECONDS,
    ) -> None:
        self.subscription_name = subscription_name
        self.restart_stream = restart_stream
        self.restart_backoff = restart_backoff
        self._stopping = False
        self._connect()

    def start(self) -> None:
        """Consume messages, reconnecting after any stream error until stopped.

        Blocks on the streaming pull. When the stream errors and `restart_stream`
        is set, the client is rebuilt and the pull reopened after a short delay,
        looping indefinitely -- the worker is expected to run until the process is
        terminated (e.g. a Kubernetes SIGTERM/SIGKILL).
        """
        logger.debug(
            "Listening for messages",
            extra={"subscription_name": self.subscription_name},
        )
        while True:
            errored = self._process_messages()
            # Restart on error, if not stopped manually and restart behavior is enabled
            if not errored or not self.restart_stream or self._stopping:
                return
            time.sleep(self.restart_backoff)
            self.restart()

    def stop(self) -> None:
        """Cancel the streaming pull, draining in-flight callbacks before shutdown."""
        self._stopping = True
        self._future.cancel()

    def restart(self) -> None:
        """Rebuild the subscriber and streaming pull after the client has closed.

        A closed `SubscriberClient` cannot be reused, so a fresh client and
        streaming pull future are created. No-op if the subscriber is still open.
        """
        if not self.subscriber.closed:
            logger.warning("Ignored attempt to restart open subscription; must be closed first.")
            return
        self._connect()

    def _connect(self) -> None:
        """Create a fresh subscriber client and open a streaming pull."""
        self.subscriber = pubsub_v1.SubscriberClient(
            subscriber_options=SubscriberOptions(enable_open_telemetry_tracing=True)
        )
        self._future = self.subscriber.subscribe(
            self.subscription_name,
            callback=callback,
            await_callbacks_on_shutdown=True,
        )

    def _process_messages(self) -> bool:
        """Block on the streaming pull until it is cancelled or raises.

        Returns True if the stream terminated because of an error, or False if it
        stopped cleanly (e.g. via `stop`).
        """
        errored = False
        with self.subscriber:
            try:
                # result() blocks indefinitely when timeout=None until cancel
                self._future.result(timeout=None)
            except Exception:
                logger.exception("Encountered exception during message streaming")
                self._future.cancel()
                errored = True
        return errored
