"""Redis keys and read/write helpers for Wrexham widget data."""

import logging
from datetime import UTC, datetime, timedelta
from typing import TypeVar

import orjson
from pydantic import TypeAdapter

from merino.cache.protocol import CacheAdapter
from merino.providers.widgets.wrexham.protocol import Match, Standing

logger = logging.getLogger(__name__)

T = TypeVar("T")  # Type of the data being written or read

KEY_PREFIX = "wrexham:v1"
LIVE_MATCHES_KEY = f"{KEY_PREFIX}:live"
STANDINGS_KEY = f"{KEY_PREFIX}:standings"

_MATCHES = TypeAdapter(list[Match])
_STANDINGS = TypeAdapter(list[Standing])


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
        await self._write(fixtures_key(competition_id), matches, _MATCHES, self.fixtures_ttl)

    async def read_fixtures(self, competition_id: int) -> tuple[list[Match], datetime] | None:
        """Read a competition's Wrexham fixtures and their fetch time, or None if none are
        stored.
        """
        return await self._read(fixtures_key(competition_id), _MATCHES)

    async def write_live_matches(self, matches: list[Match]) -> None:
        """Write today's live Wrexham match data."""
        await self._write(LIVE_MATCHES_KEY, matches, _MATCHES, self.live_matches_ttl)

    async def read_live_matches(self) -> tuple[list[Match], datetime] | None:
        """Read today's live Wrexham match data and its fetch time, or None if none is
        stored.
        """
        return await self._read(LIVE_MATCHES_KEY, _MATCHES)

    async def write_standings(self, standings: list[Standing]) -> None:
        """Write the EFL Championship table."""
        await self._write(STANDINGS_KEY, standings, _STANDINGS, self.standings_ttl)

    async def read_standings(self) -> tuple[list[Standing], datetime] | None:
        """Read the EFL Championship table."""
        return await self._read(STANDINGS_KEY, _STANDINGS)

    async def _write(self, key: str, data: T, adapter: TypeAdapter[T], ttl: timedelta) -> None:
        """Write data to cache."""
        payload = {
            "fetched_at": datetime.now(UTC).isoformat(),
            "data": adapter.dump_python(data, mode="json"),
        }
        await self.cache.set(key, orjson.dumps(payload), ttl=ttl)

    async def _read(self, key: str, adapter: TypeAdapter[T]) -> tuple[T, datetime] | None:
        """Read data from cahe. Returns None if it's missing or can't be parsed."""
        raw = await self.cache.get(key)
        if raw is None:
            return None

        try:
            payload = orjson.loads(raw)
            fetched_at = datetime.fromisoformat(payload["fetched_at"])
            data = adapter.validate_python(payload["data"])
        except (KeyError, TypeError, ValueError) as ex:
            logger.warning(
                "Could not parse stored Wrexham data",
                extra={"key": key, "error": str(ex)},
            )
            return None

        return data, fetched_at
