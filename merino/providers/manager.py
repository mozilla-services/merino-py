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
from merino.providers.top_picks.backends.top_picks import TopPicksBackend
from merino.providers.top_picks.provider import Provider as TopPicksProvider
from merino.providers.weather.backends.accuweather import AccuweatherBackend
from merino.providers.weather.backends.fake_backends import FakeWeatherBackend
from merino.providers.weather.provider import Provider as WeatherProvider
from merino.providers.wiki_fruit import WikiFruitProvider
from merino.providers.wikipedia.backends.elastic import ElasticBackend
from merino.providers.wikipedia.backends.fake_backends import FakeWikipediaBackend
from merino.providers.wikipedia.provider import Provider as WikipediaProvider
from merino.utils.blocklist import TITLE_BLOCKLIST


@unique
class ProviderType(str, Enum):
    """Enum for provider type."""

    ACCUWEATHER = "accuweather"
    AMO = "amo"
    ADM = "adm"
    TOP_PICKS = "top_picks"
    WIKI_FRUIT = "wiki_fruit"
    WIKIPEDIA = "wikipedia"


def _create_provider(provider_id: str, setting: Settings) -> BaseProvider:
    """Create a provider for a given type and settings.

    Exceptions:
      - `InvalidProviderError` if the provider type is unknown.
    """
    match setting.type:
        case ProviderType.ACCUWEATHER:
            return WeatherProvider(
                backend=AccuweatherBackend(
                    api_key=settings.accuweather.api_key,
                    cache=RedisAdapter(
                        Redis.from_url(settings.redis.server)
                    )  # type: ignore [arg-type]
                    if setting.cache == "redis"
                    else NoCacheAdapter(),
                    cached_report_ttl_sec=setting.cached_report_ttl_sec,
                    metrics_client=get_metrics_client(),
                    url_base=settings.accuweather.url_base,
                    url_param_api_key=settings.accuweather.url_param_api_key,
                    url_postalcodes_path=settings.accuweather.url_postalcodes_path,
                    url_postalcodes_param_query=settings.accuweather.url_postalcodes_param_query,
                    url_current_conditions_path=settings.accuweather.url_current_conditions_path,
                    url_forecasts_path=settings.accuweather.url_forecasts_path,
                    url_param_partner_code=settings.accuweather.get(
                        "url_param_partner_code"
                    ),
                    partner_code=settings.accuweather.get("partner_code"),
                )
                if setting.backend == "accuweather"
                else FakeWeatherBackend(),
                cache=RedisAdapter(
                    Redis.from_url(settings.redis.server)
                )  # type: ignore [arg-type]
                if setting.cache == "redis"
                else NoCacheAdapter(),
                metrics_client=get_metrics_client(),
                score=setting.score,
                name=provider_id,
                query_timeout_sec=setting.query_timeout_sec,
                cached_report_ttl_sec=setting.cached_report_ttl_sec,
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
        case ProviderType.TOP_PICKS:
            return TopPicksProvider(
                backend=TopPicksBackend(
                    top_picks_file_path=setting.top_picks_file_path,
                    query_char_limit=setting.query_char_limit,
                    firefox_char_limit=setting.firefox_char_limit,
                ),
                score=setting.score,
                name=provider_id,
                enabled_by_default=setting.enabled_by_default,
            )
        case ProviderType.WIKI_FRUIT:
            return WikiFruitProvider(
                name=provider_id, enabled_by_default=setting.enabled_by_default
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
                title_block_list=TITLE_BLOCKLIST,
                name=provider_id,
                query_timeout_sec=setting.query_timeout_sec,
                enabled_by_default=setting.enabled_by_default,
            )
        case _:
            raise InvalidProviderError(f"Unknown provider type: {setting.type}")


def load_providers() -> dict[str, BaseProvider]:
    """Load providers from configurations.

    Exceptions:
      - `InvalidProviderError` if the provider type is unknown.
    """
    providers: dict[str, BaseProvider] = {}

    for provider_id, setting in settings.providers.items():
        providers[provider_id] = _create_provider(provider_id, setting)

    return providers
