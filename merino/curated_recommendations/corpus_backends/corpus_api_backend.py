"""Corpus API backend for making GRAPHQL requests"""
from datetime import datetime

from merino.curated_recommendations.corpus_backends.protocol import (
    CorpusBackend,
    CorpusItem,
    Topic,
)
from merino.utils.http_client import create_http_client

CORPUS_API_PROD_ENDPOINT = 'https://client-api.getpocket.com'
CLIENT_NAME = 'merino-py'
CLIENT_VERSION = '0.1.0'  # TODO: get this from pyproject.tml
HEADERS = {
            'apollographql-client-name': CLIENT_NAME,
            'apollographql-client-version': CLIENT_VERSION,
}


def map_corpus_topic_to_serp_topic(topic: str) -> Topic:
    """Maps Corpus topic to a SERP topic. See:
    https://mozilla-hub.atlassian.net/wiki/spaces/MozSocial/pages/735248385/Topic+Selection+Tech+Spec+Draft#Topics"""

    if topic == 'entertainment':
        topic = Topic.ARTS.value
    elif topic == 'science':
        topic = Topic.EDUCATION.value
    elif topic == 'health_fitness':
        topic = Topic.HEALTH.value
    elif topic == 'personal_finance':
        topic = Topic.FINANCE.value
    elif topic == 'politics':
        topic = Topic.GOVERNMENT.value
    elif topic == 'self_improvement':
        topic = Topic.SOCIETY.value
    elif topic == 'technology':
        topic = Topic.TECH.value

    # after topic mapping, if topic is not found in SERP Topic enum, don't return it
    if topic not in Topic.values():
        topic = None
    return topic


class CorpusApiBackend(CorpusBackend):
    """A fake backend that returns static content."""

    async def fetch(self) -> list[CorpusItem]:
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

        # The date is supposed to progress at 3am local time, where 'local time' is based on the timezone associated
        # with the scheduled surface. This requirement is documented in the NewTab slate spec:
        # https://getpocket.atlassian.net/wiki/spaces/PE/pages/2927100008/Fx+NewTab+Slate+spec
        today = datetime.now()

        body = {
            'query': query,
            'variables': {
                'scheduledSurfaceId': 'NEW_TAB_EN_US',
                'date': today.strftime('%Y-%m-%d'),
            }
        }

        """Echoing the query as the single suggestion."""
        async with create_http_client(base_url="") as client:
            res = await client.post(CORPUS_API_PROD_ENDPOINT, json=body, headers=HEADERS)

            data = res.json()

            # Map Corpus topic to SERP topic
            for item in data['data']['scheduledSurface']['items']:
                item['corpusItem']['topic'] = map_corpus_topic_to_serp_topic(item['corpusItem']['topic'].lower())

            return [
                CorpusItem(
                    **item['corpusItem'],
                    scheduledCorpusItemId=item['id']
                ) for item in data['data']['scheduledSurface']['items']
            ]
