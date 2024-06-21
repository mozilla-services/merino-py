"""Module dedicated to providing curated recommendations to New Tab."""
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.
from merino.curated_recommendations.corpus_backends.corpus_api_backend import CorpusApiBackend
from merino.curated_recommendations.provider import CuratedRecommendationsProvider
from merino.utils.http_client import create_http_client

corpus_api_provider: dict[str, CuratedRecommendationsProvider] = {}


async def init_providers():
    """initialize providers"""
    corpus_api_provider['corpus_provider'] = CuratedRecommendationsProvider(
        corpus_backend=CorpusApiBackend(create_http_client(base_url="")))


def get_providers():
    return corpus_api_provider['corpus_provider']
