"""Unit tests for the Spindle ML backend."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import aiodogstatsd
import pytest
from httpx import AsyncClient, HTTPError, Request, Response
from pydantic import HttpUrl

from merino.curated_recommendations.corpus_backends.protocol import CorpusItem, SurfaceId
from merino.curated_recommendations.ml_backends.spindle_backend import (
    SIMILAR_STORIES_IMAGE_API_PATH,
    SIMILAR_STORIES_TEXT_API_PATH,
    DummySpindleBackend,
    SimilarStoriesInfo,
    SpindleBackend,
)


def _item(corpus_id: str, image: str | None = None) -> CorpusItem:
    return CorpusItem(
        corpusItemId=corpus_id,
        url=HttpUrl(f"https://example.com/{corpus_id}"),
        title=f"Title_{corpus_id}",
        excerpt=f"Excerpt_{corpus_id}",
        topic="education",
        publisher=f"Pub_{corpus_id}",
        isTimeSensitive=False,
        imageUrl=HttpUrl(image or f"https://example.com/img/{corpus_id}.jpg"),
    )


def _ok_response(body: dict) -> Response:
    return Response(status_code=200, json=body, request=Request("POST", "http://x/"))


def _make_backend(
    http_client: AsyncClient,
    metrics_client: aiodogstatsd.Client | None = None,
) -> SpindleBackend:
    return SpindleBackend(
        base_url="http://localhost:8001",
        request_timeout=1.0,
        metrics_client=metrics_client or MagicMock(spec=aiodogstatsd.Client),
        http_client=http_client,
    )


class TestSimilarStoriesInfo:
    """SimilarStoriesInfo edge cases."""

    def test_empty(self):
        """No similar dict yields no neighbors and zero length."""
        info = SimilarStoriesInfo()
        assert info.neighbors("anything") == []
        assert len(info) == 0
        assert "anything" not in info

    def test_neighbors_are_symmetric(self):
        """A -> B from the wire payload should also expose B -> A locally."""
        info = SimilarStoriesInfo({"a": ["b", "c"]})
        assert set(info.neighbors("a")) == {"b", "c"}
        assert info.neighbors("b") == ["a"]
        assert info.neighbors("c") == ["a"]

    def test_self_reference_is_ignored(self):
        """Spindle should not return self in its own neighbor list; if it does, skip it."""
        info = SimilarStoriesInfo({"a": ["a", "b"]})
        assert info.neighbors("a") == ["b"]


class TestSpindleBackendRefresh:
    """Behavior of refresh_duplicate_item_info."""

    @pytest.mark.asyncio
    async def test_unsupported_surface_skips_http(self):
        """A surface with no language mapping should not hit the network."""
        http_client = MagicMock(spec=AsyncClient)
        http_client.post = AsyncMock()
        backend = _make_backend(http_client)
        await backend.refresh_duplicate_item_info([_item("a")], SurfaceId.NEW_TAB_DE_DE)
        http_client.post.assert_not_called()

    @pytest.mark.asyncio
    async def test_empty_items_skips_http(self):
        """No items in -> no HTTP traffic out."""
        http_client = MagicMock(spec=AsyncClient)
        http_client.post = AsyncMock()
        backend = _make_backend(http_client)
        await backend.refresh_duplicate_item_info([], SurfaceId.NEW_TAB_EN_US)
        http_client.post.assert_not_called()

    @pytest.mark.asyncio
    async def test_success_populates_text_and_image_info(self):
        """Successful response should populate both text and image caches with symmetric pairs."""
        http_client = MagicMock(spec=AsyncClient)
        text_payload = {
            "similar": {"a": ["b"]},
            "model_version": "text-v1",
            "threshold": 0.85,
            "language": "en",
            "num_items": 2,
            "num_pairs": 1,
        }
        image_payload = {
            "similar": {"a": ["c"]},
            "model_version": "img-v1",
            "threshold": 0.85,
            "locale": "en_US",
            "num_items": 2,
            "num_pairs": 1,
        }

        async def fake_post(path: str, json: dict) -> Response:
            if path == SIMILAR_STORIES_TEXT_API_PATH:
                return _ok_response(text_payload)
            if path == SIMILAR_STORIES_IMAGE_API_PATH:
                return _ok_response(image_payload)
            raise AssertionError(f"unexpected path {path}")

        http_client.post = AsyncMock(side_effect=fake_post)

        metrics = MagicMock(spec=aiodogstatsd.Client)
        backend = _make_backend(http_client, metrics_client=metrics)
        await backend.refresh_duplicate_item_info(
            [_item("a"), _item("b"), _item("c")], SurfaceId.NEW_TAB_EN_US
        )

        text_info = backend.get_similar_stories_text(SurfaceId.NEW_TAB_EN_US)
        image_info = backend.get_similar_stories_image(SurfaceId.NEW_TAB_EN_US)
        assert text_info is not None
        assert image_info is not None
        assert text_info.neighbors("a") == ["b"]
        assert text_info.neighbors("b") == ["a"]
        assert image_info.neighbors("a") == ["c"]

        # Status-code metric should have fired for each endpoint.
        increment_calls = [c.args[0] for c in metrics.increment.call_args_list]
        assert "recommendation.spindle.text.status_codes.200" in increment_calls
        assert "recommendation.spindle.image.status_codes.200" in increment_calls
        # Timing metric should have been used.
        timing_calls = [c.args[0] for c in metrics.timeit.call_args_list]
        assert "recommendation.spindle.text.timing" in timing_calls
        assert "recommendation.spindle.image.timing" in timing_calls

    @pytest.mark.asyncio
    async def test_http_error_does_not_raise_and_leaves_cache_alone(self):
        """A 5xx from Spindle should be swallowed and the previous cache preserved."""
        http_client = MagicMock(spec=AsyncClient)

        async def fake_post(path: str, json: dict) -> Response:
            raise HTTPError("boom")

        http_client.post = AsyncMock(side_effect=fake_post)
        metrics = MagicMock(spec=aiodogstatsd.Client)
        backend = _make_backend(http_client, metrics_client=metrics)

        await backend.refresh_duplicate_item_info([_item("a")], SurfaceId.NEW_TAB_EN_US)

        assert backend.get_similar_stories_text(SurfaceId.NEW_TAB_EN_US) is None
        assert backend.get_similar_stories_image(SurfaceId.NEW_TAB_EN_US) is None
        increment_calls = [c.args[0] for c in metrics.increment.call_args_list]
        assert "recommendation.spindle.text.error" in increment_calls
        assert "recommendation.spindle.image.error" in increment_calls

    @pytest.mark.asyncio
    async def test_non_2xx_emits_status_metric_and_returns_none(self):
        """A 500 should be recorded with its status code and not populate the cache."""
        http_client = MagicMock(spec=AsyncClient)
        http_client.post = AsyncMock(
            return_value=Response(
                status_code=500, json={"error": "x"}, request=Request("POST", "http://x/")
            )
        )
        metrics = MagicMock(spec=aiodogstatsd.Client)
        backend = _make_backend(http_client, metrics_client=metrics)

        await backend.refresh_duplicate_item_info([_item("a")], SurfaceId.NEW_TAB_EN_US)

        increment_calls = [c.args[0] for c in metrics.increment.call_args_list]
        assert "recommendation.spindle.text.status_codes.500" in increment_calls
        assert backend.get_similar_stories_text(SurfaceId.NEW_TAB_EN_US) is None


class TestDummySpindleBackend:
    """DummySpindleBackend always returns None."""

    @pytest.mark.asyncio
    async def test_returns_none_and_does_not_raise(self):
        """All operations on the dummy should be safely no-ops."""
        backend = DummySpindleBackend()
        await backend.refresh_duplicate_item_info([_item("a")], SurfaceId.NEW_TAB_EN_US)
        assert backend.get_similar_stories_text(SurfaceId.NEW_TAB_EN_US) is None
        assert backend.get_similar_stories_image(SurfaceId.NEW_TAB_EN_US) is None
