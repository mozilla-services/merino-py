"""Merino provider manager."""

from enum import Enum, unique

from dynaconf.base import Settings
from redis.asyncio import Redis

from merino.cache.none import NoCacheAdapter
from merino.cache.redis import RedisAdapter
from merino.config import settings
from merino.exceptions import InvalidProviderError
from merino.metrics import get_metrics_client
from merino.providers.adm.backends.fake_backends import FakeAdmBackend
from merino.providers.adm.backends.remotesettings import RemoteSettingsBackend
from merino.providers.adm.provider import Provider as AdmProvider
from merino.providers.amo.addons_data import ADDON_KEYWORDS as ADDON_KEYWORDS
from merino.providers.amo.backends.dynamic import DynamicAmoBackend
from merino.providers.amo.backends.static import StaticAmoBackend
from merino.providers.amo.provider import Provider as AmoProvider
from merino.providers.base import BaseProvider
from merino.providers.geolocation.provider import Provider as GeolocationProvider
from merino.providers.top_picks.backends.top_picks import TopPicksBackend
from merino.providers.top_picks.provider import Provider as TopPicksProvider
from merino.providers.weather.backends.accuweather import AccuweatherBackend
from merino.providers.weather.backends.fake_backends import FakeWeatherBackend
from merino.providers.weather.provider import Provider as WeatherProvider
from merino.providers.wikipedia.backends.elastic import ElasticBackend
from merino.providers.wikipedia.backends.fake_backends import FakeWikipediaBackend
from merino.providers.wikipedia.provider import Provider as WikipediaProvider
from merino.utils.blocklists import TOP_PICKS_BLOCKLIST, WIKIPEDIA_TITLE_BLOCKLIST
from merino.utils.http_client import create_http_client


@unique
class ProviderType(str, Enum):
    """Enum for provider type."""

    ACCUWEATHER = "accuweather"
    AMO = "amo"
    ADM = "adm"
    GEOLOCATION = "geolocation"
    TOP_PICKS = "top_picks"
    WIKIPEDIA = "wikipedia"


def _create_provider(provider_id: str, setting: Settings) -> BaseProvider:
    """Create a provider for a given type and settings.

    Exceptions:
      - `InvalidProviderError` if the provider type is unknown.
    """
    match setting.type:
        case ProviderType.ACCUWEATHER:
            cache = (
                RedisAdapter(Redis.from_url(settings.redis.server))
                if setting.cache == "redis"
                else NoCacheAdapter()
            )
            return WeatherProvider(
                backend=AccuweatherBackend(
                    api_key=settings.accuweather.api_key,
                    cache=cache,  # type: ignore [arg-type]
                    cached_location_key_ttl_sec=setting.cache_ttls.location_key_ttl_sec,
                    cached_current_condition_ttl_sec=setting.cache_ttls.current_condition_ttl_sec,
                    cached_forecast_ttl_sec=setting.cache_ttls.forecast_ttl_sec,
                    metrics_client=get_metrics_client(),
                    http_client=create_http_client(
                        base_url=settings.accuweather.url_base
                    ),
                    url_param_api_key=settings.accuweather.url_param_api_key,
                    url_postalcodes_path=settings.accuweather.url_postalcodes_path,
                    url_postalcodes_param_query=settings.accuweather.url_postalcodes_param_query,
                    url_current_conditions_path=settings.accuweather.url_current_conditions_path,
                    url_forecasts_path=settings.accuweather.url_forecasts_path,
                    url_location_key_placeholder=settings.accuweather.url_location_key_placeholder,
                )
                if setting.backend == "accuweather"
                else FakeWeatherBackend(),
                metrics_client=get_metrics_client(),
                score=setting.score,
                name=provider_id,
                query_timeout_sec=setting.query_timeout_sec,
                enabled_by_default=setting.enabled_by_default,
            )
        case ProviderType.AMO:
            return AmoProvider(
                backend=DynamicAmoBackend(
                    api_url=settings.amo.dynamic.api_url
                )  # type: ignore [arg-type]
                if setting.backend == "dynamic"
                else StaticAmoBackend(),
                score=setting.score,
                name=provider_id,
                min_chars=settings.providers.amo.min_chars,
                keywords=ADDON_KEYWORDS,
                enabled_by_default=setting.enabled_by_default,
            )
        case ProviderType.ADM:
            return AdmProvider(
                backend=(
                    RemoteSettingsBackend(
                        server=settings.remote_settings.server,
                        collection=settings.remote_settings.collection,
                        bucket=settings.remote_settings.bucket,
                    )  # type: ignore [arg-type]
                    if setting.backend == "remote-settings"
                    else FakeAdmBackend()
                ),
                score=setting.score,
                name=provider_id,
                resync_interval_sec=setting.resync_interval_sec,
                cron_interval_sec=setting.cron_interval_sec,
                enabled_by_default=setting.enabled_by_default,
            )
        case ProviderType.GEOLOCATION:
            return GeolocationProvider(
                name=provider_id,
                enabled_by_default=setting.enabled_by_default,
            )
        case ProviderType.TOP_PICKS:
            return TopPicksProvider(
                backend=TopPicksBackend(
                    top_picks_file_path=setting.top_picks_file_path,
                    query_char_limit=setting.query_char_limit,
                    firefox_char_limit=setting.firefox_char_limit,
                    domain_blocklist=TOP_PICKS_BLOCKLIST,
                ),  # type: ignore [arg-type]
                score=setting.score,
                name=provider_id,
                enabled_by_default=setting.enabled_by_default,
            )
        case ProviderType.WIKIPEDIA:
            return WikipediaProvider(
                backend=(
                    ElasticBackend(
                        api_key=setting.es_api_key,
                        url=setting.es_url,
                    )
                )  # type: ignore [arg-type]
                if setting.backend == "elasticsearch"
                else FakeWikipediaBackend(),
                title_block_list=WIKIPEDIA_TITLE_BLOCKLIST,
                name=provider_id,
                query_timeout_sec=setting.query_timeout_sec,
                enabled_by_default=setting.enabled_by_default,
            )
        case _:
            raise InvalidProviderError(f"Unknown provider type: {setting.type}")


def load_providers(disabled_providers_list: list[str]) -> dict[str, BaseProvider]:
    """Load providers from configurations.

    Exceptions:
      - `InvalidProviderError` if the provider type is unknown.
    """
    providers: dict[str, BaseProvider] = {}
    for provider_id, setting in settings.providers.items():
        # Do not initialize provider if disabled in config.
        if provider_id.lower() not in disabled_providers_list:
            providers[provider_id] = _create_provider(provider_id, setting)
    return providers
