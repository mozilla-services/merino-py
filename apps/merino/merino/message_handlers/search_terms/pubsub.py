"""Pub/Sub backup channel for search terms that fail direct submission to merino-fleece."""

import asyncio

from google.auth.credentials import AnonymousCredentials
from google.cloud.pubsub_v1 import PublisherClient
from opentelemetry import metrics

from merino.configs import settings
from merino_common.models.suggest_logging import (
    SearchTermsSubmission,
    SuggestRequestParams,
)
from merino_common.utils.query_processing.pii_detect import PIIType, basic_detect

_meter = metrics.get_meter("merino.message_handlers.search_terms.pubsub")
_publish_counter = _meter.create_counter(
    name="pubsub.publish.count",
    unit="{search_term}",
    description="Search terms published to the Pub/Sub backup channel, labeled by outcome.",
)
_filtered_counter = _meter.create_counter(
    name="pubsub.filtered.count",
    unit="{search_term}",
    description="Search terms dropped by basic sanitization before publishing to Pub/Sub.",
)


def create_publisher_client() -> PublisherClient:
    """Create a Pub/Sub publisher client."""
    if settings.runtime.skip_gcp_client_auth:
        return PublisherClient()
    return PublisherClient(credentials=AnonymousCredentials())  # type: ignore[no-untyped-call]


def _is_publishable(term: SuggestRequestParams) -> bool:
    """Return whether a term is safe to persist (has a non-email, non-numeric query)."""
    return term.query is not None and basic_detect(term.query) == PIIType.NON_PII


class PubSubClient:
    """Publishes search terms to a Pub/Sub topic as a backup when direct submission fails.

    Email and numeric queries are dropped before publishing (basic sanitization) so no
    highly sensitive data is persisted in the queue; merino-fleece consumes the surviving
    terms and performs full sanitization once it recovers.
    """

    def __init__(self, publisher: PublisherClient, topic: str) -> None:
        self.publisher = publisher
        self.topic = topic

    async def publish(self, search_terms: list[SuggestRequestParams]) -> None:
        """Publish a batch of search terms to the backup topic."""
        sanitized = [term for term in search_terms if _is_publishable(term)]
        dropped = len(search_terms) - len(sanitized)
        if dropped:
            _filtered_counter.add(dropped)
        if not sanitized:
            return

        data = SearchTermsSubmission(search_terms=sanitized).model_dump_json().encode("utf-8")
        try:
            future = self.publisher.publish(self.topic, data)
            await asyncio.to_thread(future.result)
        except Exception:
            _publish_counter.add(len(sanitized), {"outcome": "error"})
            raise
        _publish_counter.add(len(sanitized), {"outcome": "success"})

    def close(self) -> None:
        """Release the publisher client's transport."""
        self.publisher.transport.close()
