"""Module dedicated to providing curated recommendations to New Tab."""

# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.
from merino.curated_recommendations.corpus_backends.corpus_api_backend import (
    CorpusApiBackend,
    CorpusApiGraphConfig,
)
from merino.curated_recommendations.provider import CuratedRecommendationsProvider
from merino.utils.http_client import create_http_client

_provider: CuratedRecommendationsProvider


def init_provider() -> None:
    """Initialize the curated recommendations provider."""
    global _provider
    _provider = CuratedRecommendationsProvider(
        corpus_backend=CorpusApiBackend(
            http_client=create_http_client(base_url=""),
            graph_config=CorpusApiGraphConfig(),
        )
    )


def get_provider() -> CuratedRecommendationsProvider:
    """Return the curated recommendations provider."""
    global _provider
    return _provider
