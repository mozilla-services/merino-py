"""Redis keys and read/write helpers for Wrexham widget data."""

import logging
from datetime import UTC, datetime, timedelta
from typing import Generic, TypeVar

from pydantic import AwareDatetime, BaseModel, ValidationError

from merino.cache.protocol import CacheAdapter
from merino.providers.widgets.wrexham.protocol import Match, Standing

logger = logging.getLogger(__name__)

T = TypeVar("T")  # Type of the data being written or read

KEY_PREFIX = "wrexham:v1"
LIVE_MATCHES_KEY = f"{KEY_PREFIX}:live"
STANDINGS_KEY = f"{KEY_PREFIX}:standings"


class _Stored(BaseModel, Generic[T]):
    """Stored value: the data and the time it was fetched."""

    fetched_at: AwareDatetime
    data: T


_StoredMatches = _Stored[list[Match]]
_StoredStandings = _Stored[list[Standing]]


def fixtures_key(competition_id: int) -> str:
    """Return the Redis key for a competition's Wrexham fixtures."""
    return f"{KEY_PREFIX}:fixtures:{competition_id}"


class WrexhamStore:
    """Writes and reads Wrexham widget data in Redis."""

    cache: CacheAdapter
    fixtures_ttl: timedelta
    live_matches_ttl: timedelta
    standings_ttl: timedelta

    def __init__(
        self,
        cache: CacheAdapter,
        fixtures_ttl: timedelta,
        live_matches_ttl: timedelta,
        standings_ttl: timedelta,
    ) -> None:
        self.cache = cache
        self.fixtures_ttl = fixtures_ttl
        self.live_matches_ttl = live_matches_ttl
        self.standings_ttl = standings_ttl

    async def write_fixtures(self, competition_id: int, matches: list[Match]) -> None:
        """Write a competition's Wrexham fixtures."""
        await self._write(fixtures_key(competition_id), _StoredMatches, matches, self.fixtures_ttl)

    async def read_fixtures(self, competition_id: int) -> tuple[list[Match], datetime] | None:
        """Read a competition's Wrexham fixtures and their fetch time, or None if none are
        stored.
        """
        return await self._read(fixtures_key(competition_id), _StoredMatches)

    async def write_live_matches(self, matches: list[Match]) -> None:
        """Write today's live Wrexham match data."""
        await self._write(LIVE_MATCHES_KEY, _StoredMatches, matches, self.live_matches_ttl)

    async def read_live_matches(self) -> tuple[list[Match], datetime] | None:
        """Read today's live Wrexham match data and its fetch time, or None if none is
        stored.
        """
        return await self._read(LIVE_MATCHES_KEY, _StoredMatches)

    async def write_standings(self, standings: list[Standing]) -> None:
        """Write the EFL Championship table."""
        await self._write(STANDINGS_KEY, _StoredStandings, standings, self.standings_ttl)

    async def read_standings(self) -> tuple[list[Standing], datetime] | None:
        """Read the EFL Championship table."""
        return await self._read(STANDINGS_KEY, _StoredStandings)

    async def _write(self, key: str, model: type[_Stored[T]], data: T, ttl: timedelta) -> None:
        """Write data to cache with the current time as its fetch time."""
        value = model(fetched_at=datetime.now(UTC), data=data)
        await self.cache.set(key, value.model_dump_json().encode(), ttl=ttl)

    async def _read(self, key: str, model: type[_Stored[T]]) -> tuple[T, datetime] | None:
        """Read data from cache. Returns None if it's missing or can't be parsed."""
        raw = await self.cache.get(key)
        if raw is None:
            return None

        try:
            stored = model.model_validate_json(raw)
        except ValidationError as ex:
            logger.warning(
                "Could not parse stored Wrexham data",
                extra={"key": key, "error": str(ex)},
            )
            return None

        return stored.data, stored.fetched_at
