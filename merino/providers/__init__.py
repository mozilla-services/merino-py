"""Initialize all Providers."""
import asyncio
import logging
from enum import Enum, unique
from timeit import default_timer as timer

from merino import metrics
from merino.config import settings
from merino.exceptions import InvalidProviderError
from merino.providers.adm.backends.fake_backends import FakeAdmBackend
from merino.providers.adm.backends.remotesettings import RemoteSettingsBackend
from merino.providers.adm.provider import Provider as AdmProvider
from merino.providers.base import BaseProvider
from merino.providers.top_picks import Provider as TopPicksProvider
from merino.providers.weather.backends.accuweather import AccuweatherBackend
from merino.providers.weather.provider import Provider as WeatherProvider
from merino.providers.wiki_fruit import WikiFruitProvider
from merino.providers.wikipedia.backends.elastic import ElasticBackend
from merino.providers.wikipedia.backends.fake_backends import FakeWikipediaBackend
from merino.providers.wikipedia.provider import Provider as WikipediaProvider

providers: dict[str, BaseProvider] = {}
default_providers: list[BaseProvider] = []

logger = logging.getLogger(__name__)


@unique
class ProviderType(str, Enum):
    """Enum for provider type."""

    ACCUWEATHER = "accuweather"
    ADM = "adm"
    TOP_PICKS = "top_picks"
    WIKI_FRUIT = "wiki_fruit"
    WIKIPEDIA = "wikipedia"


async def init_providers() -> None:
    """Initialize all suggestion providers.

    This should only be called once at the startup of application.
    """
    start = timer()

    # register providers
    for provider_type, setting in settings.providers.items():
        match provider_type:
            case ProviderType.ACCUWEATHER:
                providers["accuweather"] = WeatherProvider(
                    backend=AccuweatherBackend(
                        api_key=setting.api_key,
                        url_base=setting.url_base,
                        url_param_api_key=setting.url_param_api_key,
                        url_postalcodes_path=setting.url_postalcodes_path,
                        url_postalcodes_param_query=setting.url_postalcodes_param_query,
                        url_current_conditions_path=setting.url_current_conditions_path,
                        url_forecasts_path=setting.url_forecasts_path,
                    ),
                    score=setting.score,
                    name=provider_type,
                    query_timeout_sec=setting.query_timeout_sec,
                    enabled_by_default=setting.enabled_by_default,
                )
            case ProviderType.ADM:
                providers["adm"] = AdmProvider(
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
                    score_wikipedia=setting.score_wikipedia,
                    name=provider_type,
                    resync_interval_sec=setting.resync_interval_sec,
                    enabled_by_default=setting.enabled_by_default,
                )
            case ProviderType.TOP_PICKS:
                providers["top_picks"] = TopPicksProvider(
                    name=provider_type,
                    enabled_by_default=setting.enabled_by_default,
                )
            case ProviderType.WIKI_FRUIT:
                providers["wiki_fruit"] = WikiFruitProvider(
                    name=provider_type, enabled_by_default=setting.enabled_by_default
                )
            case ProviderType.WIKIPEDIA:
                providers["wikipedia"] = WikipediaProvider(
                    backend=(
                        ElasticBackend(
                            api_key=setting.es_api_key,
                            cloud_id=setting.es_cloud_id,
                        )
                    )  # type: ignore [arg-type]
                    if setting.backend == "elasticsearch"
                    else FakeWikipediaBackend(),
                    name=provider_type,
                    query_timeout_sec=setting.query_timeout_sec,
                    enabled_by_default=setting.enabled_by_default,
                )
            case _:
                raise InvalidProviderError(f"Unknown provider type: {provider_type}")

    # initialize providers and record time
    init_metric = "providers.initialize"
    client = metrics.get_metrics_client()
    with client.timeit(init_metric):
        wrapped_tasks = [
            client.timeit_task(p.initialize(), f"{init_metric}.{provider_name}")
            for provider_name, p in providers.items()
        ]
        await asyncio.gather(*wrapped_tasks)
        default_providers.extend(
            [p for p in providers.values() if p.enabled_by_default]
        )
        logger.info(
            "Provider initialization completed",
            extra={"providers": [*providers.keys()], "elapsed": timer() - start},
        )


async def shutdown_providers() -> None:
    """Shut down all suggestion providers.

    This should only be called once at the shutdown of application.
    """
    start = timer()

    for provider in providers.values():
        await provider.shutdown()
    logger.info(
        "Provider shutdown completed",
        extra={"providers": [*providers.keys()], "elapsed": timer() - start},
    )


def get_providers() -> tuple[dict[str, BaseProvider], list[BaseProvider]]:
    """Return a tuple of all the providers and default providers."""
    return providers, default_providers
