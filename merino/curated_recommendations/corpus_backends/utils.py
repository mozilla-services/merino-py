"""Utility functions for corpus backends."""

from urllib.parse import urlparse, urlencode, parse_qsl

from merino.curated_recommendations.corpus_backends.protocol import (
    SurfaceId,
    Topic,
    CorpusItem,
)
from merino.exceptions import BackendError
from merino.providers.manifest import Provider as ManifestProvider
from merino.utils.version import fetch_app_version_from_file


def map_corpus_topic_to_serp_topic(topic: str) -> Topic | None:
    """Map a corpus topic to a SERP topic."""
    mapping = {
        "BUSINESS": Topic.BUSINESS,
        "CAREER": Topic.CAREER,
        "EDUCATION": Topic.EDUCATION,
        "ENTERTAINMENT": Topic.ARTS,
        "FOOD": Topic.FOOD,
        "GAMING": Topic.GAMING,
        "HEALTH_FITNESS": Topic.HEALTH_FITNESS,
        "HOME": Topic.HOME,
        "PARENTING": Topic.PARENTING,
        "PERSONAL_FINANCE": Topic.PERSONAL_FINANCE,
        "POLITICS": Topic.POLITICS,
        "SCIENCE": Topic.SCIENCE,
        "SELF_IMPROVEMENT": Topic.SELF_IMPROVEMENT,
        "SPORTS": Topic.SPORTS,
        "TECHNOLOGY": Topic.TECHNOLOGY,
        "TRAVEL": Topic.TRAVEL,
    }
    return mapping.get(topic.upper())


def get_utm_source(surface_id: SurfaceId) -> str | None:
    """Return the utm_source for the given scheduled surface id."""
    utm_mapping = {
        SurfaceId.NEW_TAB_EN_US: "firefox-newtab-en-us",
        SurfaceId.NEW_TAB_EN_GB: "firefox-newtab-en-gb",
        SurfaceId.NEW_TAB_EN_CA: "firefox-newtab-en-ca",
        SurfaceId.NEW_TAB_EN_INTL: "firefox-newtab-en-intl",
        SurfaceId.NEW_TAB_DE_DE: "firefox-newtab-de-de",
        SurfaceId.NEW_TAB_ES_ES: "firefox-newtab-es-es",
        SurfaceId.NEW_TAB_FR_FR: "firefox-newtab-fr-fr",
        SurfaceId.NEW_TAB_IT_IT: "firefox-newtab-it-it",
    }
    return utm_mapping.get(surface_id)


def update_url_utm_source(url: str, utm_source: str) -> str:
    """Update the URL by adding or replacing the utm_source query parameter."""
    parsed_url = urlparse(url)
    query = dict(parse_qsl(parsed_url.query))
    query["utm_source"] = utm_source
    return parsed_url._replace(query=urlencode(query)).geturl()


class CorpusGraphQLError(BackendError):
    """Error during interaction with the corpus GraphQL API."""


class CorpusApiGraphConfig:
    """Graph configuration for the Corpus Sections API."""

    CORPUS_API_PROD_ENDPOINT = "https://client-api.getpocket.com"
    CORPUS_API_DEV_ENDPOINT = "https://client-api.getpocket.dev"

    def __init__(self) -> None:
        self._app_version = fetch_app_version_from_file().commit

    @property
    def endpoint(self) -> str:
        """Return the GraphQL endpoint URL."""
        return self.CORPUS_API_PROD_ENDPOINT

    @property
    def headers(self) -> dict[str, str]:
        """Return the GraphQL client headers."""
        return {
            "apollographql-client-name": "merino-py",
            "apollographql-client-version": self._app_version,
        }


def build_corpus_item(
    corpus_item: dict, manifest_provider: ManifestProvider, utm_source: str | None
) -> CorpusItem:
    """Construct a CorpusItem from a GraphQL corpus item dictionary.

    This function maps the corpus topic, updates the URL with the utm_source if provided,
    and adds an icon URL from the manifest provider if available.

    Args:
        corpus_item: The dictionary representing the corpus item from GraphQL.
        utm_source: Optional utm_source string.
        manifest_provider: The manifest provider to obtain the icon URL.

    Returns:
        CorpusItem: The constructed CorpusItem.
    """
    url = corpus_item["url"]
    if utm_source is not None:
        url = update_url_utm_source(corpus_item["url"], utm_source)

    return CorpusItem(
        corpusItemId=corpus_item["id"],
        title=corpus_item["title"],
        excerpt=corpus_item["excerpt"],
        topic=map_corpus_topic_to_serp_topic(corpus_item["topic"]),
        publisher=corpus_item["publisher"],
        isTimeSensitive=corpus_item["isTimeSensitive"],
        imageUrl=corpus_item["imageUrl"],
        iconUrl=manifest_provider.get_icon_url(url),
        url=url,
    )
