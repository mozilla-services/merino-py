# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

"""Shared fixtures for the Wrexham widget unit tests."""

from datetime import UTC, datetime, timedelta
from typing import Callable

import pytest

from merino.cache.none import NoCacheAdapter
from merino.providers.widgets.wrexham.protocol import (
    Competition,
    Match,
    MatchPeriod,
    MatchStatus,
    Standing,
    Team,
)
from merino.providers.widgets.wrexham.store import WrexhamStore

# Statuses of matches that have kicked off, so they have a period and a score.
_STARTED_STATUSES = frozenset(
    {MatchStatus.InProgress, MatchStatus.Break, MatchStatus.Suspended, MatchStatus.Final}
)

MakeMatch = Callable[..., Match]
MakeStanding = Callable[[int], Standing]


class FakeCache(NoCacheAdapter):
    """In-memory stand-in for a cache adapter that records expiry times."""

    def __init__(self) -> None:
        self.values: dict[str, bytes] = {}
        self.ttls: dict[str, timedelta | None] = {}

    async def get(self, key: str) -> bytes | None:
        """Return the stored value, or None."""
        return self.values.get(key)

    async def set(
        self, key: str, value: bytes | str, ttl: timedelta | None = None, nx: bool = False
    ) -> None:
        """Store a value and record its expiry."""
        self.values[key] = value.encode() if isinstance(value, str) else value
        self.ttls[key] = ttl


def _team(team_id: int) -> Team:
    """Build a team for tests."""
    return Team(id=team_id, name=f"Team {team_id}", logo_url="https://example.com/logo.png")


@pytest.fixture(name="fake_cache")
def fixture_fake_cache() -> FakeCache:
    """Return an empty in-memory cache."""
    return FakeCache()


@pytest.fixture(name="store")
def fixture_store(fake_cache: FakeCache) -> WrexhamStore:
    """Return a store backed by the in-memory cache."""
    return WrexhamStore(
        cache=fake_cache,
        fixtures_ttl=timedelta(hours=3),
        live_matches_ttl=timedelta(minutes=10),
        standings_ttl=timedelta(hours=6),
    )


@pytest.fixture(name="make_match")
def fixture_make_match() -> MakeMatch:
    """Return a function that builds a match for tests."""

    def make_match(
        match_id: int,
        status: MatchStatus = MatchStatus.Final,
        competition_id: int = 34,
        kickoff: datetime = datetime(2026, 10, 31, 15, tzinfo=UTC),
        updated_at: datetime | None = None,
    ) -> Match:
        started = status in _STARTED_STATUSES
        return Match(
            id=match_id,
            competition=Competition(id=competition_id, name=f"Competition {competition_id}"),
            kickoff=kickoff,
            home_team=_team(1),
            away_team=_team(2),
            period=MatchPeriod.Regular if started else None,
            status=status,
            clock="60" if status == MatchStatus.InProgress else None,
            home_score=1 if started else None,
            away_score=0 if started else None,
            home_penalty_score=None,
            away_penalty_score=None,
            updated_at=updated_at or kickoff,
        )

    return make_match


@pytest.fixture(name="make_standing")
def fixture_make_standing() -> MakeStanding:
    """Return a function that builds a table row for tests."""

    def make_standing(position: int) -> Standing:
        return Standing(
            position=position, team=_team(position), played=14, goal_difference=0, points=20
        )

    return make_standing
