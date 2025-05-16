"""Module dedicated to providing curated recommendations to New Tab."""

# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.
import logging

from google.cloud.storage import Client

from merino.configs import settings
from merino.curated_recommendations.corpus_backends.scheduled_surface_backend import (
    ScheduledSurfaceBackend,
    CorpusApiGraphConfig,
)
from merino.curated_recommendations.corpus_backends.sections_backend import (
    SectionsBackend,
)
from merino.curated_recommendations.engagement_backends.fake_engagement import FakeEngagement
from merino.curated_recommendations.engagement_backends.gcs_engagement import GcsEngagement
from merino.curated_recommendations.engagement_backends.protocol import EngagementBackend
from merino.curated_recommendations.prior_backends.gcs_prior import GcsPrior
from merino.curated_recommendations.prior_backends.constant_prior import ConstantPrior
from merino.curated_recommendations.prior_backends.protocol import PriorBackend
from merino.curated_recommendations.provider import CuratedRecommendationsProvider
from merino.curated_recommendations.legacy.provider import LegacyCuratedRecommendationsProvider
from merino.utils.metrics import get_metrics_client
from merino.utils.http_client import create_http_client
from merino.utils.synced_gcs_blob import SyncedGcsBlob

from merino.providers.manifest import get_provider as get_manifest_provider
from merino.utils.gcs import initialize_storage_client

logger = logging.getLogger(__name__)

_provider: CuratedRecommendationsProvider
_legacy_provider: LegacyCuratedRecommendationsProvider


def init_engagement_backend() -> EngagementBackend:
    """Initialize the GCS Engagement Backend."""
    try:
        metrics_namespace = "recommendation.engagement"
        synced_gcs_blob = SyncedGcsBlob(
            storage_client=initialize_storage_client(
                destination_gcp_project=settings.curated_recommendations.gcs.gcp_project
            ),
            metrics_client=get_metrics_client(),
            metrics_namespace=metrics_namespace,
            bucket_name=settings.curated_recommendations.gcs.bucket_name,
            blob_name=settings.curated_recommendations.gcs.engagement.blob_name,
            max_size=settings.curated_recommendations.gcs.engagement.max_size,
            cron_interval_seconds=settings.curated_recommendations.gcs.engagement.cron_interval_seconds,
            cron_job_name="fetch_recommendation_engagement",
        )
        synced_gcs_blob.initialize()

        return GcsEngagement(
            synced_gcs_blob=synced_gcs_blob,
            metrics_client=get_metrics_client(),
            metrics_namespace=metrics_namespace,
        )
    except Exception as e:
        logger.error(f"Failed to initialize GCS Engagement Backend: {e}")
        # Engagement data enhances the experience but can be gracefully degraded if unavailable.
        # This applies in contract tests or when the developer isn't logged in with gcloud auth.
        return FakeEngagement()


def init_prior_backend() -> PriorBackend:
    """Initialize the GCS Prior Backend, falling back to ConstantPrior if GCS Prior cannot be initialized."""
    try:
        synced_gcs_blob = SyncedGcsBlob(
            storage_client=initialize_storage_client(
                destination_gcp_project=settings.curated_recommendations.gcs.gcp_project
            ),
            metrics_client=get_metrics_client(),
            metrics_namespace="recommendation.prior",
            bucket_name=settings.curated_recommendations.gcs.bucket_name,
            blob_name=settings.curated_recommendations.gcs.prior.blob_name,
            max_size=settings.curated_recommendations.gcs.prior.max_size,
            cron_interval_seconds=settings.curated_recommendations.gcs.prior.cron_interval_seconds,
            cron_job_name="fetch_recommendation_engagement",
        )
        synced_gcs_blob.initialize()
        return GcsPrior(synced_gcs_blob=synced_gcs_blob)
    except Exception as e:
        logger.error(f"Failed to initialize GCS Prior Backend: {e}")
        # Fall back to a constant prior if GCS prior cannot be initialized.
        # This happens in contract tests or when the developer isn't logged in with gcloud auth.
        return ConstantPrior()


def init_provider() -> None:
    """Initialize the curated recommendations provider."""
    global _provider
    global _legacy_provider

    engagement_backend = init_engagement_backend()

    scheduled_surface_backend = ScheduledSurfaceBackend(
        http_client=create_http_client(base_url=""),
        graph_config=CorpusApiGraphConfig(),
        metrics_client=get_metrics_client(),
        manifest_provider=get_manifest_provider(),
    )

    sections_backend = SectionsBackend(
        http_client=create_http_client(base_url=""),
        graph_config=CorpusApiGraphConfig(),
        metrics_client=get_metrics_client(),
        manifest_provider=get_manifest_provider(),
    )

    _provider = CuratedRecommendationsProvider(
        scheduled_surface_backend=scheduled_surface_backend,
        engagement_backend=engagement_backend,
        prior_backend=init_prior_backend(),
        sections_backend=sections_backend,
    )
    _legacy_provider = LegacyCuratedRecommendationsProvider(
        scheduled_surface_backend=scheduled_surface_backend,
        engagement_backend=engagement_backend,
        prior_backend=init_prior_backend(),
        sections_backend=sections_backend,
    )


def get_provider() -> CuratedRecommendationsProvider:
    """Return the curated recommendations provider."""
    global _provider
    return _provider


def get_legacy_provider() -> LegacyCuratedRecommendationsProvider:
    """TODO"""
    global _legacy_provider
    return _legacy_provider
