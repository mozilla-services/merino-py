"""Merino provider manager."""

from enum import Enum, unique

from dynaconf.base import Settings

from merino.cache.none import NoCacheAdapter
from merino.cache.redis import RedisAdapter, create_redis_clients
from merino.configs import settings
from merino.exceptions import InvalidProviderError
from merino.providers.suggest.finance.backends.polygon.backend import PolygonBackend
from merino.utils.gcs.gcs_uploader import GcsUploader
from merino.utils.metrics import get_metrics_client
from merino.providers.suggest.adm.backends.fake_backends import FakeAdmBackend
from merino.providers.suggest.adm.backends.remotesettings import RemoteSettingsBackend
from merino.providers.suggest.adm.provider import Provider as AdmProvider
from merino.providers.suggest.amo.addons_data import ADDON_KEYWORDS as ADDON_KEYWORDS
from merino.providers.suggest.amo.backends.dynamic import DynamicAmoBackend
from merino.providers.suggest.amo.backends.static import StaticAmoBackend
from merino.providers.suggest.amo.provider import Provider as AmoProvider
from merino.providers.suggest.base import BaseProvider
from merino.providers.suggest.geolocation.provider import (
    Provider as GeolocationProvider,
)
from merino.providers.suggest.top_picks.backends.top_picks import TopPicksBackend
from merino.providers.suggest.top_picks.provider import Provider as TopPicksProvider
from merino.providers.suggest.weather.backends.accuweather import AccuweatherBackend
from merino.providers.suggest.weather.backends.fake_backends import FakeWeatherBackend
from merino.providers.suggest.weather.provider import Provider as WeatherProvider
from merino.providers.suggest.wikipedia.backends.elastic import ElasticBackend
from merino.providers.suggest.wikipedia.backends.fake_backends import (
    FakeWikipediaBackend,
)
from merino.providers.suggest.wikipedia.provider import Provider as WikipediaProvider
from merino.providers.suggest.finance.provider import Provider as PolygonProvider
from merino.providers.suggest.yelp.provider import Provider as YelpProvider
from merino.providers.suggest.flightaware.provider import (
    Provider as FlightAwareProvider,
)
from merino.providers.suggest.flightaware.backends.flightaware import FlightAwareBackend
from merino.providers.suggest.sports.provider import SportsDataProvider
from merino.providers.suggest.sports.backends.sportsdata.backend import (
    SportsDataBackend,
)
from merino.providers.suggest.yelp.backends.yelp import YelpBackend
from merino.providers.suggest.google_suggest.provider import (
    Provider as GoogleSuggestProvider,
)
from merino.providers.suggest.google_suggest.backends.google_suggest import (
    GoogleSuggestBackend,
)
from merino.utils.blocklists import TOP_PICKS_BLOCKLIST, WIKIPEDIA_TITLE_BLOCKLIST
from merino.utils.http_client import create_http_client
from merino.utils.icon_processor import IconProcessor


@unique
class ProviderType(str, Enum):
    """Enum for provider type."""

    ACCUWEATHER = "accuweather"
    AMO = "amo"
    ADM = "adm"
    GEOLOCATION = "geolocation"
    TOP_PICKS = "top_picks"
    WIKIPEDIA = "wikipedia"
    POLYGON = "polygon"
    YELP = "yelp"
    FLIGHTAWARE = "flightaware"
    GOOGLE_SUGGEST = "google_suggest"
    SPORTS = "sports"


def _create_provider(provider_id: str, setting: Settings) -> BaseProvider:
    """Create a provider for a given type and settings.

    Exceptions:
      - `InvalidProviderError` if the provider type is unknown.
    """
    match setting.type:
        case ProviderType.ACCUWEATHER:
            cache = (
                RedisAdapter(
                    *create_redis_clients(
                        settings.redis.server,
                        settings.redis.replica,
                        settings.redis.max_connections,
                        settings.redis.socket_connect_timeout_sec,
                        settings.redis.socket_timeout_sec,
                    )
                )
                if setting.cache == "redis"
                else NoCacheAdapter()
            )
            return WeatherProvider(
                backend=(
                    AccuweatherBackend(
                        api_key=settings.accuweather.api_key,
                        cache=cache,  # type: ignore [arg-type]
                        cached_location_key_ttl_sec=setting.cache_ttls.location_key_ttl_sec,
                        cached_current_condition_ttl_sec=(
                            setting.cache_ttls.current_condition_ttl_sec
                        ),
                        cached_forecast_ttl_sec=setting.cache_ttls.forecast_ttl_sec,
                        metrics_client=get_metrics_client(),
                        metrics_sample_rate=settings.accuweather.metrics_sampling_rate,
                        http_client=create_http_client(
                            base_url=settings.accuweather.url_base,
                            connect_timeout=settings.providers.accuweather.connect_timeout_sec,
                        ),
                        url_param_api_key=settings.accuweather.url_param_api_key,
                        url_cities_admin_path=settings.accuweather.url_cities_admin_path,
                        url_cities_path=settings.accuweather.url_cities_path,
                        url_cities_param_query=settings.accuweather.url_cities_param_query,
                        url_current_conditions_path=(
                            settings.accuweather.url_current_conditions_path
                        ),
                        url_forecasts_path=settings.accuweather.url_forecasts_path,
                        url_location_completion_path=(
                            settings.accuweather.url_location_completion_path
                        ),
                        url_location_key_placeholder=(
                            settings.accuweather.url_location_key_placeholder
                        ),
                    )
                    if setting.backend == "accuweather"
                    else FakeWeatherBackend()
                ),
                metrics_client=get_metrics_client(),
                score=setting.score,
                name=provider_id,
                query_timeout_sec=setting.query_timeout_sec,
                enabled_by_default=setting.enabled_by_default,
                cron_interval_sec=setting.cron_interval_sec,
            )
        case ProviderType.AMO:
            return AmoProvider(
                backend=(
                    DynamicAmoBackend(api_url=settings.amo.dynamic.api_url)
                    if setting.backend == "dynamic"
                    else StaticAmoBackend()
                ),
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
                        collection=settings.remote_settings.collection_amp,
                        bucket=settings.remote_settings.bucket,
                        icon_processor=IconProcessor(
                            gcs_project=settings.image_gcs.gcs_project,
                            gcs_bucket=settings.image_gcs.gcs_bucket,
                            cdn_hostname=settings.image_gcs.cdn_hostname,
                            http_client=create_http_client(
                                request_timeout=settings.icon.http_timeout,
                            ),
                        ),
                    )
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
                    (
                        ElasticBackend(
                            api_key=setting.es_api_key,
                            url=setting.es_url,
                        )
                    )
                    if setting.backend == "elasticsearch"
                    else FakeWikipediaBackend()
                ),
                title_block_list=WIKIPEDIA_TITLE_BLOCKLIST,
                name=provider_id,
                query_timeout_sec=setting.query_timeout_sec,
                enabled_by_default=setting.enabled_by_default,
            )
        case ProviderType.POLYGON:
            cache = (
                RedisAdapter(
                    *create_redis_clients(
                        settings.redis.server,
                        settings.redis.replica,
                        settings.redis.max_connections,
                        settings.redis.socket_connect_timeout_sec,
                        settings.redis.socket_timeout_sec,
                        settings.providers.polygon.cache_db,
                    )
                )
                if setting.cache == "redis"
                else NoCacheAdapter()
            )
            return PolygonProvider(
                backend=PolygonBackend(
                    api_key=settings.polygon.api_key,
                    metrics_client=get_metrics_client(),
                    metrics_sample_rate=settings.polygon.metrics_sampling_rate,
                    http_client=create_http_client(
                        base_url=settings.polygon.url_base,
                        connect_timeout=settings.providers.polygon.connect_timeout_sec,
                    ),
                    url_param_api_key=settings.polygon.url_param_api_key,
                    url_single_ticker_snapshot=settings.polygon.url_single_ticker_snapshot,
                    url_single_ticker_overview=settings.polygon.url_single_ticker_overview,
                    gcs_uploader=GcsUploader(
                        settings.image_gcs.gcs_project,
                        settings.image_gcs.gcs_bucket,
                        settings.image_gcs.cdn_hostname,
                    ),
                    ticker_ttl_sec=settings.providers.polygon.cache_ttls.ticker_ttl_sec,
                    cache=cache,
                ),
                metrics_client=get_metrics_client(),
                score=setting.score,
                name=provider_id,
                query_timeout_sec=setting.query_timeout_sec,
                enabled_by_default=setting.enabled_by_default,
                resync_interval_sec=setting.resync_interval_sec,
                cron_interval_sec=setting.cron_interval_sec,
            )
        case ProviderType.YELP:
            cache = (
                RedisAdapter(
                    *create_redis_clients(
                        settings.redis.server,
                        settings.redis.replica,
                        settings.redis.max_connections,
                        settings.redis.socket_connect_timeout_sec,
                        settings.redis.socket_timeout_sec,
                    )
                )
                if setting.cache == "redis"
                else NoCacheAdapter()
            )

            return YelpProvider(
                backend=YelpBackend(
                    api_key=settings.yelp.api_key,
                    http_client=create_http_client(
                        base_url=settings.yelp.url_base,
                        connect_timeout=settings.providers.yelp.connect_timeout_sec,
                    ),
                    url_business_search=settings.yelp.url_business_search,
                    cache_ttl_sec=setting.cache_ttls.business_search_ttl_sec,
                    metrics_client=get_metrics_client(),
                    cache=cache,
                ),
                metrics_client=get_metrics_client(),
                score=setting.score,
                name=provider_id,
                query_timeout_sec=setting.query_timeout_sec,
                enabled_by_default=setting.enabled_by_default,
            )
        case ProviderType.GOOGLE_SUGGEST:
            return GoogleSuggestProvider(
                backend=GoogleSuggestBackend(
                    http_client=create_http_client(
                        base_url=settings.google_suggest.url_base,
                        proxy=(
                            settings.google_suggest.proxy_url
                            if settings.google_suggest.proxy_url
                            else None  # no proxying
                        ),
                    ),
                    url_suggest_path=settings.google_suggest.url_suggest_path,
                    metrics_client=get_metrics_client(),
                ),
                score=setting.score,
                name=provider_id,
                enabled_by_default=setting.enabled_by_default,
            )
        case ProviderType.FLIGHTAWARE:
            return FlightAwareProvider(
                backend=FlightAwareBackend(
                    api_key=settings.flightaware.api_key,
                    http_client=create_http_client(base_url=settings.flightaware.base_url),
                    ident_url=settings.flightaware.ident_url_path,
                ),
                metrics_client=get_metrics_client(),
                score=setting.score,
                name=provider_id,
                query_timeout_sec=setting.query_timeout_sec,
                enabled_by_default=setting.enabled_by_default,
            )
        case ProviderType.SPORTS:
            return SportsDataProvider(
                backend=SportsDataBackend(settings=settings),
                metrics_client=get_metrics_client(),
                score=setting.score,
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
