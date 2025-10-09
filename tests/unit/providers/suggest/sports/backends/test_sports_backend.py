"""Test Gauntlet for SportsData.io"""

import pytest
import json
from datetime import timedelta


from unittest.mock import patch
import httpx

# from merino.configs import settings
from merino.providers.suggest.sports.backends import get_data

VALID_TEST_RESPONSE: dict = {}


@pytest.mark.asyncio
async def test_get_data():
    """Simple test for the `get_data` caching fetcher."""
    ttl = timedelta(seconds=5)
    with patch.object(
        httpx.AsyncClient,
        "get",
        return_value=httpx.Response(status_code=200, json=dict(foo="bar")),
    ) as mock_client:
        with patch.object(json, "dump") as mock_json:
            await get_data(
                client=mock_client,
                url="http://example.org",
                ttl=ttl,
                cache_dir="/tmp",
            )
            # was the URL called?
            mock_client.get.assert_called_with("http://example.org")
            # see if it tried to write the file to the cache dir...
            assert (
                mock_json.call_args_list[0].args[1].buffer.name
                == "/tmp/ff7c1f10ab54968058fdcfaadf1b2457cd5d1a3f.json"
            )
            # TODO: check for TTL.


@pytest.mark.asyncio
async def test_build_suggestion():
    """Simple test that the suggestion can be built from a sample event response"""
