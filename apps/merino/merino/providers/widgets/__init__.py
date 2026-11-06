"""Initialize widget providers."""

from datetime import timedelta

from merino.cache.redis import RedisAdapter, create_redis_clients
from merino.configs import settings
from merino.providers.widgets.iframed.provider import Provider as IframedWidgetsProvider
from merino.providers.widgets.travel.kayak.backends.kayak import KayakBackend
from merino.providers.widgets.travel.kayak.provider import Provider as TravelProvider
from merino.providers.widgets.wrexham.provider import WrexhamProvider
from merino.providers.widgets.wrexham.store import WrexhamStore
from merino.utils.metrics import get_metrics_client
from merino_common.utils.http_client import create_http_client

_wrexham_provider: WrexhamProvider | None = None
_wrexham_mock_data_enabled = settings.widgets.providers.wrexham.mock_data_enabled
_wrexham_cache_ttls = settings.widgets.providers.wrexham.cache_ttls

_iframed_widgets_provider: IframedWidgetsProvider | None = None
_iframed_widgets_provider_enabled = settings.widget_providers.iframed.enabled

_travel_provider: TravelProvider | None = None
_travel_enabled = settings.widgets.providers.travel.kayak.enabled
_travel_connect_timeout = settings.widgets.providers.travel.kayak.connect_timeout_sec
_kayak_api_key = settings.kayak.api_key
_kayak_url_base = settings.kayak.url_base
_kayak_url_autocomplete_path = settings.kayak.url_autocomplete_path


async def init_providers() -> None:
    """Initialize widget providers."""
    init_wrexham_provider()
    init_widget_provider()
    init_travel_provider()


def init_wrexham_provider() -> None:
    """Initialize the Wrexham widget provider."""
    global _wrexham_provider

    store = WrexhamStore(
        cache=RedisAdapter(
            *create_redis_clients(
                settings.redis.widgets_server,
                settings.redis.widgets_replica,
                settings.redis.max_connections,
                settings.redis.socket_connect_timeout_sec,
                settings.redis.socket_timeout_sec,
            )
        ),
        fixtures_ttl=timedelta(seconds=_wrexham_cache_ttls.fixtures_ttl_sec),
        live_matches_ttl=timedelta(seconds=_wrexham_cache_ttls.live_matches_ttl_sec),
        standings_ttl=timedelta(seconds=_wrexham_cache_ttls.standings_ttl_sec),
    )
    _wrexham_provider = WrexhamProvider(
        store=store,
        metrics_client=get_metrics_client(),
        mock_data_enabled=_wrexham_mock_data_enabled,
    )


async def shutdown_providers() -> None:
    """Shut down widget providers.

    This should only be called once at the shutdown of the application.
    """
    global _wrexham_provider, _travel_provider

    if _wrexham_provider is not None:
        await _wrexham_provider.shutdown()
        _wrexham_provider = None

    if _travel_provider is not None:
        await _travel_provider.shutdown()
        _travel_provider = None


def get_wrexham_provider() -> WrexhamProvider:
    """Return the Wrexham widget provider."""
    if _wrexham_provider is None:
        raise ValueError("Wrexham widget provider has not been initialized.")

    return _wrexham_provider


def init_widget_provider() -> None:
    """Initialize the iframed widgets provider."""
    global _iframed_widgets_provider

    _iframed_widgets_provider = IframedWidgetsProvider(
        metrics_client=get_metrics_client(),
        name="iframed Widgets Provider",
        enabled=_iframed_widgets_provider_enabled,
    )


def get_iframed_widgets_provider() -> IframedWidgetsProvider:
    """Return the iframed widgets provider"""
    if _iframed_widgets_provider is None:
        raise ValueError("iframed widgets provider has not been initialized.")

    return _iframed_widgets_provider


def init_travel_provider() -> None:
    """Initialize the travel widget provider (currently backed by Kayak)."""
    global _travel_provider

    metrics_client = get_metrics_client()

    _travel_provider = TravelProvider(
        backend=KayakBackend(
            api_key=_kayak_api_key,
            http_client=create_http_client(connect_timeout=_travel_connect_timeout),
            url_base=_kayak_url_base,
            url_autocomplete_path=_kayak_url_autocomplete_path,
            metrics_client=metrics_client,
        ),
        metrics_client=metrics_client,
        name="Travel Provider",
        enabled=_travel_enabled,
    )


def get_travel_provider() -> TravelProvider:
    """Return the travel widget provider."""
    if _travel_provider is None:
        raise ValueError("Travel provider has not been initialized.")

    return _travel_provider
