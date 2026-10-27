"""Initialize travel providers."""

from merino.configs import settings
from merino.providers.travel.kayak.backends.kayak import KayakBackend
from merino.providers.travel.kayak.provider import Provider
from merino.utils.metrics import get_metrics_client

_travel_provider: Provider | None = None

# Module-level variables as looking up from settings each time is expensive.
_enabled = settings.travel_providers.kayak.enabled
_api_key = settings.kayak.api_key
_url_base = settings.kayak.url_base


async def init_providers() -> None:
    """Initialize travel providers - currently only Kayak"""
    init_travel_provider()


def init_travel_provider() -> None:
    """Initialize the travel provider."""
    global _travel_provider

    _travel_provider = Provider(
        backend=KayakBackend(api_key=_api_key, url_base=_url_base),
        metrics_client=get_metrics_client(),
        name="Travel Provider",
        enabled=_enabled,
    )


def get_travel_provider() -> Provider:
    """Return the travel provider"""
    if _travel_provider is None:
        raise ValueError("Travel provider has not been initialized.")

    return _travel_provider
