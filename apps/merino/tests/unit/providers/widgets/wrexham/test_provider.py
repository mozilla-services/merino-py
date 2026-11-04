# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

"""Unit tests for the Wrexham widget provider."""

import pytest
from pytest_mock import MockerFixture

from merino.cache.protocol import CacheAdapter
from merino.providers.widgets.wrexham.provider import WrexhamProvider


@pytest.mark.asyncio
async def test_get_matches_applies_limit_to_previous_and_upcoming() -> None:
    """`limit` caps previous and upcoming matches but not current ones."""
    provider = WrexhamProvider(mock_data_enabled=True)

    matches = await provider.get_matches(limit=2)

    assert len(matches.previous) == 2
    assert len(matches.upcoming) == 2
    assert len(matches.current) == 1


@pytest.mark.asyncio
async def test_get_matches_keeps_the_closest_matches_when_limited() -> None:
    """Limiting keeps the most recent results and the next fixtures."""
    provider = WrexhamProvider(mock_data_enabled=True)

    full = await provider.get_matches(limit=50)
    limited = await provider.get_matches(limit=1)

    assert [match.id for match in limited.previous] == [full.previous[0].id]
    assert [match.id for match in limited.upcoming] == [full.upcoming[0].id]


@pytest.mark.asyncio
async def test_get_matches_returns_empty_groups_when_mock_data_disabled() -> None:
    """Returns empty match groups when mock data is disabled."""
    provider = WrexhamProvider(mock_data_enabled=False)

    matches = await provider.get_matches(limit=5)

    assert matches.previous == []
    assert matches.current == []
    assert matches.upcoming == []


@pytest.mark.asyncio
async def test_get_standings_returns_the_table() -> None:
    """Returns the full Championship table when mock data is enabled."""
    provider = WrexhamProvider(mock_data_enabled=True)

    standings = await provider.get_standings()

    assert len(standings.standings) == 24


@pytest.mark.asyncio
async def test_get_standings_returns_empty_table_when_mock_data_disabled() -> None:
    """Returns the Championship with an empty table when mock data is disabled."""
    provider = WrexhamProvider(mock_data_enabled=False)

    standings = await provider.get_standings()

    assert standings.competition.name == "EFL Championship"
    assert standings.standings == []


@pytest.mark.asyncio
async def test_shutdown_without_cache_is_a_noop() -> None:
    """Shutdown does nothing when no cache is configured."""
    provider = WrexhamProvider(mock_data_enabled=True)

    await provider.shutdown()


@pytest.mark.asyncio
async def test_shutdown_closes_cache(mocker: MockerFixture) -> None:
    """Shutdown closes the Redis cache connection when one is configured."""
    cache = mocker.AsyncMock(spec=CacheAdapter)
    provider = WrexhamProvider(mock_data_enabled=False, cache=cache)

    await provider.shutdown()

    cache.close.assert_awaited_once()
