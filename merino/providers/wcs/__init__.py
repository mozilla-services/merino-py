"""Module dedicated to providing World Cup Soccer match data to New Tab."""

from merino.cache.none import NoCacheAdapter
from merino.cache.redis import RedisAdapter, create_redis_clients
from merino.configs import settings
from merino.providers.suggest.sports.backends.sportsdata.common.sports import WCS
from merino.providers.wcs.provider import WcsProvider

_sport: WCS | None = None
_provider: WcsProvider | None = None


def _cache() -> RedisAdapter | NoCacheAdapter:
    """Build the cache adapter used by the WCS API provider."""
    if settings.providers.sports.get("cache") != "redis":
        return NoCacheAdapter()
    return RedisAdapter(
        *create_redis_clients(
            settings.redis.wcs_server,
            settings.redis.wcs_replica,
            settings.redis.max_connections,
            settings.redis.socket_connect_timeout_sec,
            settings.redis.socket_timeout_sec,
        )
    )


def _build_provider() -> WcsProvider:
    """Build the singleton WCS API provider."""
    global _sport
    _sport = WCS(settings.providers.sports, cache=_cache())
    return WcsProvider(sport=_sport)


async def init_provider() -> None:
    """Initialize the singleton WCS provider during app startup."""
    get_provider()


async def shutdown_provider() -> None:
    """Close the WCS cache adapter and clear the singleton provider."""
    global _provider, _sport
    if _sport is not None:
        await _sport.cache.close()
    _provider = None
    _sport = None


def get_provider() -> WcsProvider:
    """Return the singleton WCS provider for FastAPI's `Depends`."""
    global _provider
    if _provider is None:
        _provider = _build_provider()
    return _provider
