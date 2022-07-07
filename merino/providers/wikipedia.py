from asyncio import wait_for
from asyncio.exceptions import TimeoutError
from typing import Dict
from urllib.parse import quote
from elasticsearch import AsyncElasticsearch
from sanic.log import logger

from merino.providers.base import DefaultProvider

ES_HOST = "http://35.192.164.92:9200/"

class Provider(DefaultProvider):

    def __init__(self):
        self.es_client = AsyncElasticsearch(hosts=[ES_HOST], sniff_on_start=True)

    async def query(self, q: str):
        output = []
        try:
            res = await wait_for(self.es_client.search(index="enwiki", query=self.get_query(q), size=2), 0.50)
            if 'hits' in res:
                for doc in res['hits']['hits']:
                    output.append(self.format_suggestion(doc))
        except TimeoutError:
            logger.info("cancelled due to es request timeout")
            pass
        return output

    def format_suggestion(self, doc: Dict):
        source = doc['_source']
        title = str(source['title'])
        return {
          "block_id": int(doc.get("_id", '')),
          "full_keyword": title.lower(),
          "title": title,
          "url": "https://en.wikipedia.org/wiki/" + quote(title.replace(' ', '_')),
          "impression_url": "",
          "click_url": "",
          "provider": "wiki",
          "advertiser": "",
          "is_sponsored": False,
          "icon": "",
          "score": 0.5,
      }
        
    def get_query(self, q: str):
        return {
            "bool": {
                "must": [
                    {
                        "term": {
                            "title.prefix": q
                        }
                    }
                ],
                "should": [
                    {
                        "rank_feature": {
                            "field": "incoming_links.rank"
                        }
                    },
                    {
                        "rank_feature": {
                            "field": "popularity_score.rank",
                            "boost": 100000
                        }
                    },
                    {
                        "rank_feature": {
                            "field": "title_length"
                        }
                    }
                ]
            }
        }

