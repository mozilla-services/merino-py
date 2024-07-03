"""Corpus API backend for making GRAPHQL requests"""

from datetime import datetime, timedelta
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError
import logging

from httpx import AsyncClient

from merino.curated_recommendations.corpus_backends.protocol import (
    CorpusBackend,
    CorpusItem,
    Topic,
    ScheduledSurfaceId,
)
from merino.utils.version import fetch_app_version_from_file

logger = logging.getLogger(__name__)


class CorpusApiGraphConfig:
    """Corpus API Graph Config."""

    CORPUS_API_PROD_ENDPOINT = "https://client-api.getpocket.com"
    CORPUS_API_DEV_ENDPOINT = "https://client-api.getpocket.dev"
    CLIENT_NAME = "merino-py"
    CLIENT_VERSION = fetch_app_version_from_file().commit
    HEADERS = {
        "apollographql-client-name": CLIENT_NAME,
        "apollographql-client-version": CLIENT_VERSION,
    }


"""
Map Corpus topic to a SERP topic.
Note: Not all Corpus topics map to a SERP topic. For unmapped topics, null is returned.
See: https://mozilla-hub.atlassian.net/wiki/spaces/MozSocial/pages/735248385/Topic+Selection+Tech+Spec+Draft#Topics  # noqa
"""
CORPUS_TOPIC_TO_SERP_TOPIC_MAPPING = {
    "entertainment": Topic.ARTS.value,
    "food": Topic.FOOD.value,
    "science": Topic.EDUCATION.value,
    "health_fitness": Topic.HEALTH.value,
    "personal_finance": Topic.FINANCE.value,
    "politics": Topic.GOVERNMENT.value,
    "self_improvement": Topic.SOCIETY.value,
    "technology": Topic.TECH.value,
    "business": Topic.BUSINESS.value,
    "travel": Topic.TRAVEL.value,
    "sports": Topic.SPORTS.value,
}


def map_corpus_topic_to_serp_topic(topic: str) -> tuple[str] | None:
    """Map the corpus topic to the SERP topic."""
    return CORPUS_TOPIC_TO_SERP_TOPIC_MAPPING.get(topic.lower())


class CorpusApiBackend(CorpusBackend):
    """Corpus API Backend hitting the curated corpus api
    & returning recommendations for current date & locale/region.
    """

    http_client: AsyncClient

    def __init__(self, http_client: AsyncClient):
        self.http_client = http_client

    @staticmethod
    def get_surface_timezone(scheduled_surface_id: str) -> ZoneInfo:
        """Return the correct timezone for a scheduled surface id.
        If no timezone is found, gracefully return timezone in UTC.
        https://github.com/Pocket/recommendation-api/blob/main/app/data_providers/corpus/corpus_api_client.py#L98 # noqa
        """
        zones = {
            "NEW_TAB_EN_US": "America/New_York",
            "NEW_TAB_EN_GB": "Europe/London",
            "NEW_TAB_EN_INTL": "Asia/Kolkata",  # Note: en-Intl is poorly named. Only India is currently eligible.
            "NEW_TAB_DE_DE": "Europe/Berlin",
            "NEW_TAB_ES_ES": "Europe/Madrid",
            "NEW_TAB_FR_FR": "Europe/Paris",
            "NEW_TAB_IT_IT": "Europe/Rome",
        }

        try:
            return ZoneInfo(zones[scheduled_surface_id])
        except (KeyError, ZoneInfoNotFoundError) as e:
            # Graceful degradation: continue to serve recommendations if timezone cannot be obtained for the surface.
            default_tz = ZoneInfo("UTC")
            logging.error(
                f"Failed to get timezone for {scheduled_surface_id}, so defaulting to {default_tz}: {e}"
            )
            return default_tz

    @staticmethod
    def get_scheduled_surface_date(surface_timezone: ZoneInfo) -> datetime:
        """Return scheduled surface date based on timezone."""
        return datetime.now(tz=surface_timezone) - timedelta(hours=3)

    async def fetch(self, surface_id: ScheduledSurfaceId) -> list[CorpusItem]:
        """Issue a scheduledSurface query"""
        query = """
            query ScheduledSurface($scheduledSurfaceId: ID!, $date: Date!) {
              scheduledSurface(id: $scheduledSurfaceId) {
                items: items(date: $date) {
                  id
                  corpusItem {
                    url
                    title
                    excerpt
                    topic
                    publisher
                    imageUrl
                  }
                }
              }
            }
        """

        # The date is supposed to progress at 3am local time,
        # where 'local time' is based on the timezone associated with the scheduled surface.
        # This requirement is documented in the NewTab slate spec:
        # https://getpocket.atlassian.net/wiki/spaces/PE/pages/2927100008/Fx+NewTab+Slate+spec
        today = self.get_scheduled_surface_date(self.get_surface_timezone(surface_id))

        body = {
            "query": query,
            "variables": {
                "scheduledSurfaceId": surface_id,
                "date": today.strftime("%Y-%m-%d"),
            },
        }

        """Echoing the query as the single suggestion."""
        res = await self.http_client.post(
            CorpusApiGraphConfig.CORPUS_API_PROD_ENDPOINT,
            json=body,
            headers=CorpusApiGraphConfig.HEADERS,
        )

        data = res.json()

        # Map Corpus topic to SERP topic
        for item in data["data"]["scheduledSurface"]["items"]:
            item["corpusItem"]["topic"] = map_corpus_topic_to_serp_topic(
                item["corpusItem"]["topic"]
            )

        curated_recommendations = [
            CorpusItem(**item["corpusItem"], scheduledCorpusItemId=item["id"])
            for item in data["data"]["scheduledSurface"]["items"]
        ]
        return curated_recommendations
