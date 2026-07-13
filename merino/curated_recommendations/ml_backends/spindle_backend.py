"""Spindle backend.

Talks to the Content-ML Spindle service to find near-duplicate stories using
text and image embeddings. Results are cached per-surface and exposed to the
ranking pipeline via the `SimilarStoriesProtocol`.
"""

import logging

import aiodogstatsd
from httpx import AsyncClient, HTTPError
from pydantic import BaseModel, Field

from merino.curated_recommendations.corpus_backends.protocol import CorpusItem, SurfaceId
from merino.curated_recommendations.ml_backends.protocol import (
    SimilarStoriesProtocol,
    SpindleBackendProtocol,
)
from merino.utils.http_client import create_http_client

logger = logging.getLogger(__name__)


SIMILAR_STORIES_TEXT_API_PATH = "/find_similar_stories"
SIMILAR_STORIES_IMAGE_API_PATH = "/find_similar_images"

LOCALE_FOR_SURFACE: dict[SurfaceId, str] = {
    SurfaceId.NEW_TAB_EN_US: "en_US",
    SurfaceId.NEW_TAB_DE_DE: "de_DE",
}

METRIC_NAMESPACE = "recommendation.spindle"


class SimilarStoriesTextItem(BaseModel):
    """Text payload entry sent to /find_similar_stories."""

    corpus_item_id: str
    title: str
    excerpt: str


class SimilarStoriesImageItem(BaseModel):
    """Image payload entry sent to /find_similar_images."""

    corpus_item_id: str
    image_url: str


class FindSimilarStoriesRequest(BaseModel):
    """Request body for /find_similar_stories."""

    items: list[SimilarStoriesTextItem]
    threshold: float = Field(0.8, ge=0.0, le=1.0)
    language: str = Field("en", min_length=2, max_length=10)


class FindSimilarImagesRequest(BaseModel):
    """Request body for /find_similar_images."""

    items: list[SimilarStoriesImageItem]
    threshold: float = Field(0.8, ge=0.0, le=1.0)
    locale: str = Field("en_US", min_length=2, max_length=10)


class FindSimilarResponse(BaseModel):
    """Response body for /find_similar_stories (and the text-only fields of images)."""

    similar: dict[str, list[str]]
    model_version: str
    threshold: float
    language: str | None = None
    locale: str | None = None
    num_items: int
    num_pairs: int


class SimilarStoriesInfo(SimilarStoriesProtocol):
    """Sparse undirected adjacency over corpus item ids.

    Built from the `similar` dict returned by Spindle. `neighbors(id)` is the
    primary access pattern used by the article balancer.
    """

    def __init__(self, similar: dict[str, list[str]] | None = None):
        """Build from Spindle's adjacency dict; absent keys map to empty neighbor lists."""
        self._neighbors: dict[str, set[str]] = {}
        if similar:
            for a, group in similar.items():
                for b in group:
                    if a == b:
                        continue
                    self._neighbors.setdefault(a, set()).add(b)
                    self._neighbors.setdefault(b, set()).add(a)

    def neighbors(self, corpus_item_id: str) -> list[str]:
        """Return ids that are near-duplicates of `corpus_item_id`."""
        return list(self._neighbors.get(corpus_item_id, ()))

    def __len__(self) -> int:
        """Return the count of items that have at least one neighbor."""
        return len(self._neighbors)

    def __contains__(self, corpus_item_id: str) -> bool:
        """Whether the id has any known neighbors."""
        return corpus_item_id in self._neighbors


class SpindleBackend(SpindleBackendProtocol):
    """HTTP client for the Content-ML Spindle service."""

    def __init__(
        self,
        base_url: str,
        request_timeout: float,
        metrics_client: aiodogstatsd.Client,
        http_client: AsyncClient | None = None,
        api_key: str | None = None,
    ) -> None:
        """Build the backend; an existing `http_client` may be injected for tests."""
        self.base_url = base_url
        self.metrics_client = metrics_client
        self.http_client = http_client or create_http_client(
            base_url=base_url,
            request_timeout=request_timeout,
            max_connections=5,
        )
        self._text_info: dict[SurfaceId, SimilarStoriesInfo] = {}
        self._image_info: dict[SurfaceId, SimilarStoriesInfo] = {}
        self._api_key = api_key

    def _language_for_surface(self, surface: SurfaceId) -> str | None:
        parts = surface.value.split("_")
        if len(parts) < 3:
            return None
        return parts[2].lower()

    def _locale_for_surface(self, surface: SurfaceId) -> str | None:
        return LOCALE_FOR_SURFACE.get(surface)

    async def refresh_duplicate_item_info(
        self,
        items: list[CorpusItem],
        surface: SurfaceId,
        threshold: float = 0.7,
    ) -> None:
        """Refresh both text and image similarity caches for `surface`.

        Each call is best-effort: failures are logged and leave the previously
        cached values in place.
        """
        if not items:
            return
        deduped_items = list({item.corpusItemId: item for item in items}.values())
        await self._refresh_text(deduped_items, surface, threshold)

        # Refresh images will be rolled out as soon as GPU inference is verified
        # await self._refresh_image(deduped_items, surface, threshold)

    async def _refresh_text(
        self, items: list[CorpusItem], surface: SurfaceId, threshold: float
    ) -> None:
        language = self._language_for_surface(surface)
        if language is None:
            return
        request = FindSimilarStoriesRequest(
            items=[
                SimilarStoriesTextItem(
                    corpus_item_id=item.corpusItemId,
                    title=item.title,
                    excerpt=item.excerpt,
                )
                for item in items
            ],
            threshold=threshold,
            language=language,
        )
        response = await self._post(
            path=SIMILAR_STORIES_TEXT_API_PATH,
            json_body=request.model_dump(),
            metric_subname="text",
        )
        if response is not None:
            self._text_info[surface] = SimilarStoriesInfo(response.similar)

    async def _refresh_image(
        self, items: list[CorpusItem], surface: SurfaceId, threshold: float
    ) -> None:
        locale = self._locale_for_surface(surface)
        if locale is None:
            return
        image_items = [
            SimilarStoriesImageItem(
                corpus_item_id=item.corpusItemId,
                image_url=str(item.imageUrl),
            )
            for item in items
            if item.imageUrl is not None
        ]
        if not image_items:
            return
        request = FindSimilarImagesRequest(
            items=image_items,
            threshold=threshold,
            locale=locale,
        )
        response = await self._post(
            path=SIMILAR_STORIES_IMAGE_API_PATH,
            json_body=request.model_dump(),
            metric_subname="image",
        )
        if response is not None:
            self._image_info[surface] = SimilarStoriesInfo(response.similar)

    async def _post(
        self,
        path: str,
        json_body: dict,
        metric_subname: str,
    ) -> FindSimilarResponse | None:
        """POST to Spindle, emit metrics, and return a parsed response or None on failure."""
        metric_base = f"{METRIC_NAMESPACE}.{metric_subname}"
        try:
            with self.metrics_client.timeit(f"{metric_base}.timing"):
                res = await self.http_client.post(
                    path, json=json_body, headers={"X-Spindle-Auth": self._api_key or ""}
                )
            self.metrics_client.increment(f"{metric_base}.status_codes.{res.status_code}")
            res.raise_for_status()
            return FindSimilarResponse.model_validate(res.json())
        except HTTPError as e:
            self.metrics_client.increment(f"{metric_base}.error")
            logger.warning("Spindle %s call failed: %s", path, e)
            return None
        except Exception as e:
            self.metrics_client.increment(f"{metric_base}.error")
            logger.warning("Spindle %s response could not be parsed: %s", path, e)
            return None

    def get_similar_stories_text(self, surface: SurfaceId) -> SimilarStoriesInfo | None:
        """Return cached text-similarity for `surface`, or None if not yet populated."""
        return self._text_info.get(surface)

    def get_similar_stories_image(self, surface: SurfaceId) -> SimilarStoriesInfo | None:
        """Return cached image-similarity for `surface`, or None if not yet populated."""
        return self._image_info.get(surface)


class DummySpindleBackend(SpindleBackendProtocol):
    """No-op backend used when Spindle is disabled or unreachable."""

    async def refresh_duplicate_item_info(
        self,
        items: list[CorpusItem],
        surface: SurfaceId,
        threshold: float = 0.8,
    ) -> None:
        """No-op."""
        return None

    def get_similar_stories_text(self, surface: SurfaceId) -> SimilarStoriesInfo | None:
        """Return None — the dummy backend has no cache."""
        return None

    def get_similar_stories_image(self, surface: SurfaceId) -> SimilarStoriesInfo | None:
        """Return None — the dummy backend has no cache."""
        return None
