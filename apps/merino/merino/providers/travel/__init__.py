"""Initialize travel providers."""

from merino.configs import settings
from merino.providers.travel.kayak.backends.kayak import KayakBackend
from merino.providers.travel.kayak.provider import Provider
from merino.utils.metrics import get_metrics_client
from merino_common.utils.http_client import create_http_client

_travel_provider: Provider | None = None

# Module-level variables as looking up from settings each time is expensive.
_enabled = settings.travel_providers.kayak.enabled
_connect_timeout = settings.travel_providers.kayak.connect_timeout_sec
_api_key = settings.kayak.api_key
_url_base = settings.kayak.url_base
_url_autocomplete_path = settings.kayak.url_autocomplete_path


async def init_providers() -> None:
    """Initialize travel providers - currently only Kayak"""
    init_travel_provider()


def init_travel_provider() -> None:
    """Initialize the travel provider."""
    global _travel_provider

    metrics_client = get_metrics_client()

    _travel_provider = Provider(
        backend=KayakBackend(
            api_key=_api_key,
            http_client=create_http_client(connect_timeout=_connect_timeout),
            url_base=_url_base,
            url_autocomplete_path=_url_autocomplete_path,
            metrics_client=metrics_client,
        ),
        metrics_client=metrics_client,
        name="Travel Provider",
        enabled=_enabled,
    )


async def shutdown_providers() -> None:
    """Shut down the travel provider.

    This should only be called once at the shutdown of the application.
    """
    if _travel_provider is not None:
        await _travel_provider.shutdown()


def get_travel_provider() -> Provider:
    """Return the travel provider"""
    if _travel_provider is None:
        raise ValueError("Travel provider has not been initialized.")

    return _travel_provider
