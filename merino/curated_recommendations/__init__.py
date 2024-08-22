"""Module dedicated to providing curated recommendations to New Tab."""

# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.
from google.cloud.storage import Client

from merino.config import settings
from merino.curated_recommendations.corpus_backends.corpus_api_backend import (
    CorpusApiBackend,
    CorpusApiGraphConfig,
)
from merino.curated_recommendations.engagement_backends.gcs_engagement import GcsEngagement
from merino.curated_recommendations.provider import CuratedRecommendationsProvider
from merino.metrics import get_metrics_client
from merino.utils.http_client import create_http_client

_provider: CuratedRecommendationsProvider


def init_provider() -> None:
    """Initialize the curated recommendations provider."""
    global _provider

    # Initialize GCS Engagement Backend
    gcs_engagement_backend = GcsEngagement(
        storage_client=Client(settings.curated_recommendations.gcs_engagement.gcp_project),
        metrics_client=get_metrics_client(),
        bucket_name=settings.curated_recommendations.gcs_engagement.bucket_name,
        blob_prefix=settings.curated_recommendations.gcs_engagement.blob_prefix,
        max_size=settings.curated_recommendations.gcs_engagement.max_size,
        cron_interval_seconds=settings.curated_recommendations.gcs_engagement.cron_interval_seconds,
    )
    gcs_engagement_backend.initialize()

    # Create the recommendations provider.
    _provider = CuratedRecommendationsProvider(
        corpus_backend=CorpusApiBackend(
            http_client=create_http_client(base_url=""),
            graph_config=CorpusApiGraphConfig(),
            metrics_client=get_metrics_client(),
        ),
        engagement_backend=gcs_engagement_backend,
    )


def get_provider() -> CuratedRecommendationsProvider:
    """Return the curated recommendations provider."""
    global _provider
    return _provider
