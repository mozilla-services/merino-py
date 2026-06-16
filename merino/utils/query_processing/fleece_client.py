"""Client for the merino-fleece PII detection service."""

import logging

from aiodogstatsd import Client as MetricsClient
from httpx import AsyncClient, HTTPError

from merino.configs import settings
from merino.utils.http_client import create_http_client

logger = logging.getLogger(__name__)


class FleeceClient:
    """HTTP client for the merino-fleece PII detection endpoint."""

    http_client: AsyncClient
    pii_path: str

    def __init__(self, http_client: AsyncClient, pii_path: str) -> None:
        """Initialize the client with an HTTP client and the PII endpoint path."""
        self.http_client = http_client
        self.pii_path = pii_path

    async def detect_pii(self, query: str) -> bool:
        """Return whether merino-fleece flags `query` as containing PII."""
        response = await self.http_client.post(self.pii_path, json={"q": query})
        response.raise_for_status()
        return bool(response.json()["pii"])

    async def detect_pii_safe(self, query: str, metrics_client: MetricsClient) -> bool:
        """Detect PII, recording duration and returns False on error."""
        with metrics_client.timeit("fleece.pii.detect_duration"):
            try:
                return await self.detect_pii(query)
            except HTTPError as exc:
                logger.warning("merino-fleece request failed: %s", exc)
                metrics_client.increment("fleece.pii.error", tags={"reason": "http"})
                return False
            except (KeyError, ValueError) as exc:
                logger.warning("merino-fleece returned an unexpected response: %s", exc)
                metrics_client.increment("fleece.pii.error", tags={"reason": "response"})
                return False

    async def shutdown(self) -> None:
        """Close the underlying HTTP client."""
        await self.http_client.aclose()


_fleece_client: FleeceClient | None = None


def init_fleece_client() -> None:
    """Build the FleeceClient singleton from settings; no-op if url_base is unset."""
    global _fleece_client
    if not settings.fleece.url_base:
        logger.info("merino-fleece url_base not configured; PII detection disabled")
        return
    _fleece_client = FleeceClient(
        http_client=create_http_client(
            base_url=settings.fleece.url_base,
            connect_timeout=settings.fleece.connect_timeout_sec,
            request_timeout=settings.fleece.request_timeout_sec,
        ),
        pii_path=settings.fleece.pii_path,
    )


async def shutdown_fleece_client() -> None:
    """Close and drop the FleeceClient singleton. Call once at shutdown."""
    global _fleece_client
    if _fleece_client is not None:
        await _fleece_client.shutdown()
        _fleece_client = None


def get_fleece_client() -> FleeceClient | None:
    """Return the FleeceClient singleton, or None when the feature is disabled."""
    return _fleece_client
