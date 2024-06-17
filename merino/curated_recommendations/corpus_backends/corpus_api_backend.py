"""Test backends"""
from datetime import datetime

from merino.curated_recommendations.corpus_backends.protocol import (
    CorpusBackend,
    CorpusItem,
)
from merino.utils.http_client import create_http_client


CORPUS_API_PROD_ENDPOINT = 'https://client-api.getpocket.com'
CLIENT_NAME = 'merino-py'
CLIENT_VERSION = '0.1.0' # TODO: get this from pyproject.tml


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

        headers = {
            'apollographql-client-name': CLIENT_NAME,
            'apollographql-client-version': CLIENT_VERSION,
        }

        """Echoing the query as the single suggestion."""
        async with create_http_client(base_url="") as client:
            res = await client.post(CORPUS_API_PROD_ENDPOINT, json=body, headers=headers)

            data = res.json()
            return [
                CorpusItem(
                    **item['corpusItem'],
                    scheduledCorpusItemId=item['id']
                ) for item in data['data']['scheduledSurface']['items']
            ]
