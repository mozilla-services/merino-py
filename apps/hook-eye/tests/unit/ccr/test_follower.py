"""Unit tests for merino_hook_eye.ccr.follower."""

from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

from merino_hook_eye.ccr import follower
from merino_hook_eye.ccr import metrics as ccr_metrics
from merino_hook_eye.ccr.stats import parse_ccr_stats


@pytest.mark.parametrize(
    ("api_key", "expected_header"),
    [("", None), ("c2VjcmV0", "ApiKey c2VjcmV0")],
    ids=["no-key", "with-key"],
)
@pytest.mark.asyncio
async def test_build_client(
    monkeypatch: pytest.MonkeyPatch, api_key: str, expected_header: str | None
) -> None:
    """The client targets the configured follower and only authenticates with a key."""
    # `setitem`, not `setattr`: undoing `setattr` on the Dynaconf box deletes the key.
    monkeypatch.setitem(follower.settings.ccr_follower, "api_key", api_key)

    client = follower.build_client()
    try:
        node = next(iter(client.transport.node_pool.all()))
        assert node.base_url == "http://test-es-follower:9200"
        assert client._headers.get("authorization") == expected_header
    finally:
        await client.close()


@pytest.mark.asyncio
async def test_start_runs_and_cleans_up(
    monkeypatch: pytest.MonkeyPatch, ccr_stats_body: dict[str, Any]
) -> None:
    """The check runs on the configured interval, then clears its snapshot and closes the
    client on exit.
    """
    client = MagicMock()
    client.ccr.stats = AsyncMock(return_value=MagicMock(body=ccr_stats_body))
    client.close = AsyncMock()
    monkeypatch.setattr(follower, "build_client", lambda: client)

    async with follower.start() as check:
        assert check.name == "ccr_follower"
        assert check.interval_sec == float(follower.settings.ccr_follower.interval_sec)
        ccr_metrics.publish(parse_ccr_stats(ccr_stats_body, ["*"]))

    assert ccr_metrics.latest() is None
    client.close.assert_awaited_once_with()
