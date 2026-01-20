"""Module dedicated to providing curated recommendations to New Tab."""

# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.
import logging

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
from merino.curated_recommendations.ml_backends.empty_ml_recs import EmptyMLRecs
from merino.curated_recommendations.ml_backends.static_local_model import SuperInferredModel
from merino.curated_recommendations.ml_backends.gcs_ml_recs import GcsMLRecs
from merino.curated_recommendations.ml_backends.gcs_interest_cohort_model import (
    EmptyCohortModel,
    GcsInterestCohortModel,
)

from merino.curated_recommendations.ml_backends.gcs_local_model import GCSLocalModel
from merino.curated_recommendations.ml_backends.protocol import (
    CohortModelBackend,
    LocalModelBackend,
    MLRecsBackend,
)
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


def init_local_model_backend() -> LocalModelBackend:
    """Initialize the Local Model Backend. This will be repaced with GCSLocal model
    prior to production launch so we can dynamically update models.
    """
    return SuperInferredModel()


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


def init_ml_recommendations_backend() -> MLRecsBackend:
    """Initialize the ML Recommendations GCS Backend which falls back to an empty
    recommendation set if GCS cannot be initialized. This is handled downstream
    by falling by to Thompson Sampling.
    """
    try:
        synced_gcs_blob = SyncedGcsBlob(
            storage_client=initialize_storage_client(
                destination_gcp_project=settings.ml_recommendations.gcs.gcp_project
            ),
            metrics_client=get_metrics_client(),
            metrics_namespace="recommendation.ml.contextual",
            bucket_name=settings.ml_recommendations.gcs.bucket_name,
            blob_name=settings.ml_recommendations.gcs.blob_name,
            max_size=settings.ml_recommendations.gcs.max_size,
            cron_interval_seconds=settings.ml_recommendations.gcs.cron_interval_seconds,
            cron_job_name="fetch_ml_contextual_recs",
        )
        synced_gcs_blob.initialize()
        return GcsMLRecs(synced_gcs_blob=synced_gcs_blob)
    except Exception as e:
        logger.error(f"Failed to initialize GCS ML Recs Backend: {e}")
        # Fall back to a empty recommendation set if GCS cannot be initialized.
        # This happens in contract tests or when the developer isn't logged in with gcloud auth.
        return EmptyMLRecs()


def init_ml_cohort_model_backend() -> CohortModelBackend:
    """Initialize the ML Cohort Model GCS Backend which falls back to an empty
    if GCS cannot be initialized.
    """
    try:
        synced_gcs_blob = SyncedGcsBlob(
            storage_client=initialize_storage_client(
                destination_gcp_project=settings.interest_cohort_model.gcs.gcp_project
            ),
            metrics_client=get_metrics_client(),
            metrics_namespace="recommendation.ml.interest_cohort_model",
            bucket_name=settings.interest_cohort_model.gcs.bucket_name,
            blob_name=settings.interest_cohort_model.gcs.blob_name,
            max_size=settings.interest_cohort_model.gcs.max_size,
            cron_interval_seconds=settings.interest_cohort_model.gcs.cron_interval_seconds,
            cron_job_name="fetch_ml_interest_cohort_model",
            is_bytes=True,
        )
        synced_gcs_blob.initialize()
        return GcsInterestCohortModel(synced_gcs_blob=synced_gcs_blob)
    except Exception as e:
        logger.error(f"Failed to initialize GCS cohort model Backend: {e}")
        # Fall back to a Null model if GCS cannot be initialized.
        return EmptyCohortModel()


def init_provider() -> None:
    """Initialize the curated recommendations' provider."""
    global _provider
    global _legacy_provider

    engagement_backend = init_engagement_backend()
    local_model_backend = init_local_model_backend()
    ml_recommendations_backend = init_ml_recommendations_backend()
    cohort_model_backend = init_ml_cohort_model_backend()

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
        local_model_backend=local_model_backend,
        ml_recommendations_backend=ml_recommendations_backend,
        cohort_model_backend=cohort_model_backend,
    )
    _legacy_provider = LegacyCuratedRecommendationsProvider()


def get_provider() -> CuratedRecommendationsProvider:
    """Return the curated recommendations provider."""
    global _provider
    return _provider


def get_legacy_provider() -> LegacyCuratedRecommendationsProvider:
    """Return the legacy curated recommendations provider"""
    global _legacy_provider
    return _legacy_provider
