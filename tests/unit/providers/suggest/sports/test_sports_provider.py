"""Unit tests for the Merino v1 suggest API for the Sports provider"""

import pytest

from datetime import datetime, timedelta, timezone
from unittest.mock import patch

# from merino.configs import settings
from merino.providers.suggest.sports import utc_time_from_now, init_logs

# from tests.unit.types import SuggestionRequestFixture


@pytest.mark.asyncio
async def test_sports_ttl_from_now():
    """Test that we get a valid UTC time for tomorrow"""
    result = utc_time_from_now(timedelta(days=1))
    tomorrow = int((datetime.now(tz=timezone.utc) + timedelta(days=1)).timestamp())
    # Use a window because of clock skew.
    assert tomorrow - 1 <= result <= tomorrow + 1


@pytest.mark.asyncio
async def test_sports_init_logger():
    """Test that we are generating the correct level for logs."""
    with patch("logging.basicConfig") as logger:
        # Note, dummy out the `getLogger` call as well to prevent accidental changes.
        with patch("logging.getLogger") as _log2:
            # pass in the argument for testing because `os.getenv` is defined before
            # mock can patch it.
            init_logs("DEBUG")
            logger.assert_called_with(level=10)
            logger.reset_mock()
            init_logs("warning")
            logger.assert_called_with(level=30)
