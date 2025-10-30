"""Unit tests for the Merino v1 suggest API for the Sports provider"""

import pytest

from datetime import datetime, timedelta, timezone
from unittest.mock import patch
from httpx import AsyncClient
from typing import cast

from pydantic import HttpUrl
from pytest_mock import MockerFixture
from unittest.mock import AsyncMock

from merino.middleware.geolocation import Location
from merino.providers.suggest.custom_details import CustomDetails
from merino.utils.domain_categories.models import Category
from merino.utils.metrics import get_metrics_client
from merino.providers.suggest.base import SuggestionRequest, BaseSuggestion
from merino.providers.suggest.sports import (
    utc_time_from_now,
    init_logs,
    IGNORED_SUGGESTION_URL,
    PROVIDER_ID,
    BASE_SUGGEST_SCORE,
)
from merino.providers.suggest.sports.provider import SportsDataProvider
from merino.providers.suggest.sports.backends.sportsdata.backend import (
    SportsDataBackend,
)
from merino.providers.suggest.sports.backends.sportsdata.protocol import (
    SportEventDetail,
    SportTeamDetail,
    SportSummary,
    SportEventDetails,
)


@pytest.fixture
def mock_client(mocker: MockerFixture) -> AsyncClient:
    """Mock Async Client."""
    return cast(AsyncClient, mocker.Mock(spec=AsyncClient))


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


@pytest.mark.asyncio
async def test_sports_provider(mock_client: AsyncClient):
    """Test the sports data provider"""
    # we already test the backend.
    home_team = SportTeamDetail(
        key="HOM", name="Home Team", colors=["000000"], score=None
    )
    away_team = SportTeamDetail(
        key="AWY", name="Away Team", colors=["FFFFFF"], score=None
    )
    event = SportEventDetail(
        sport="test",
        query="test query",
        date="2025-10-01T00:00:00+00:00",
        home_team=home_team,
        away_team=away_team,
        event_status="Final",
        status="final",
    )
    summary = [SportSummary(sport="test", values=[event])]
    backend = AsyncMock(spec=SportsDataBackend)
    backend.base_score = 0
    backend.query = AsyncMock(side_effect=[summary])
    provider = SportsDataProvider(
        metrics_client=get_metrics_client(),
        backend=backend,
        enabled_by_default=True,
        trigger_words=["test"],
    )
    sreq = SuggestionRequest(query="test game jets", geolocation=Location())
    res = await provider.query(sreq=sreq)
    assert len(res) == 1
    sum = res[0]
    assert sum.custom_details.sports  # type: ignore
    assert len(sum.custom_details.sports.values) == 1  # type: ignore
    assert sum == BaseSuggestion(
        title="All Sport",
        description="All Sport report for test game jets",
        url=HttpUrl(IGNORED_SUGGESTION_URL),
        provider=PROVIDER_ID,
        is_sponsored=False,
        custom_details=CustomDetails(
            sports=SportEventDetails(summary=SportSummary(sport="test", values=[event]))
        ),
        categories=[Category.Sports],
        score=BASE_SUGGEST_SCORE,
    )


@pytest.mark.asyncio
async def test_provider_query_non_trigger_word():
    """Test non-trigger word returns no suggestions."""
    backend = AsyncMock(spec=SportsDataBackend)
    provider = SportsDataProvider(
        metrics_client=get_metrics_client(),
        backend=backend,
        enabled_by_default=True,
        trigger_words=["trigger word"],
    )
    backend.query.return_value = []
    sreq = SuggestionRequest(query="something else", geolocation=Location())
    res = await provider.query(sreq=sreq)
    assert len(res) == 0


@pytest.mark.asyncio
async def test_provider_normalize_query():
    backend = AsyncMock(spec=SportsDataBackend)
    provider = SportsDataProvider(
        metrics_client=get_metrics_client(),
        backend=backend,
        enabled_by_default=True,
        trigger_words=["trigger", "word"],
    )
    success = "Trigger is my horse"
    fail = "Hi-ho Silver!"
    assert provider.normalize_query(success) == success
    assert provider.normalize_query(fail) == ""
