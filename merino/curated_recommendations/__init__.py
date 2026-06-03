"""Module dedicated to providing curated recommendations to New Tab."""

# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.
import logging
import random

from merino.configs import settings
from merino.curated_recommendations.corpus_backends.protocol import SurfaceId
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
from merino.curated_recommendations.ml_backends.lints_interest_model import (
    EmptyLinTSInterestBackend,
    LinTSInterestBackend,
)
from merino.curated_recommendations.ml_backends.tz_feature_model import (
    EmptyTZFeatureBackend,
    TZFeatureBackend,
)

from merino.curated_recommendations.ml_backends.gcs_local_model import GCSLocalModel
from merino.curated_recommendations.ml_backends.protocol import (
    NUM_ML_RECS_BACKEND_FILES,
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


def init_ml_recommendations_backend(num_files=NUM_ML_RECS_BACKEND_FILES) -> MLRecsBackend:
    """Initialize the ML Recommendations GCS Backend which falls back to an empty
    recommendation set if GCS cannot be initialized. This is handled downstream
    by falling by to Thompson Sampling.
    """
    """ Pick a random blob name from a set of possible files to increase diversity.
    Because there are so merino servers, we don't need to rotate files in a particular
    instance"""

    synced_gcs_blobs: dict[SurfaceId, SyncedGcsBlob] = {}
    surface_blob_names: dict[SurfaceId, str] = {
        SurfaceId.NEW_TAB_EN_US: settings.ml_recommendations.gcs.blob_name,
        SurfaceId.NEW_TAB_EN_CA: settings.ml_recommendations.gcs.blob_name_ca,
    }
    metrics_namespaces: dict[SurfaceId, str] = {
        SurfaceId.NEW_TAB_EN_US: "recommendation.ml.contextual",
        SurfaceId.NEW_TAB_EN_CA: "recommendation.ml.contextual_ca",
    }
    for surface_id, blob_name in surface_blob_names.items():
        try:
            synced_gcs_blob = SyncedGcsBlob(
                storage_client=initialize_storage_client(
                    destination_gcp_project=settings.ml_recommendations.gcs.gcp_project
                ),
                metrics_client=get_metrics_client(),
                metrics_namespace=metrics_namespaces[surface_id],
                bucket_name=settings.ml_recommendations.gcs.bucket_name,
                blob_name=blob_name,
                max_size=settings.ml_recommendations.gcs.max_size,
                cron_interval_seconds=settings.ml_recommendations.gcs.cron_interval_seconds,
                cron_job_name="fetch_ml_contextual_recs",
            )
            synced_gcs_blob.initialize()
            synced_gcs_blobs[surface_id] = synced_gcs_blob
        except Exception as e:
            logger.error(f"Failed to initialize GCS ML Recs Backend for {surface_id}: {e}")

    if not synced_gcs_blobs:
        # Fall back to an empty recommendation set if no surface could be initialized.
        # This happens in contract tests or when the developer isn't logged in with gcloud auth.
        return EmptyMLRecs()
    return GcsMLRecs(synced_gcs_blobs=synced_gcs_blobs)


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


def init_lints_interest_backend() -> LinTSInterestBackend | EmptyLinTSInterestBackend:
    """Initialize the LinTS-interest backend.

    Two layers of off-switch:
      - The ``lints_interest.enabled`` config flag (kill switch). If false,
        we skip GCS entirely and return an empty stub regardless of bucket
        state.
      - Failure to construct the ``SyncedGcsBlob`` (e.g. dev env without
        gcloud auth) also falls back to the empty stub.

    The empty stub returns ``False`` from ``is_valid()`` so the request flow
    naturally falls through to the cohort or vanilla TS ranker.

    US-only for the initial experiment. Adding ``NEW_TAB_EN_CA`` later is a
    one-line wiring change here — the backend is already per-``SurfaceId``.
    """
    if not settings.contextual_interest.enabled:
        logger.info("LinTS interest backend disabled by config; using empty stub.")
        return EmptyLinTSInterestBackend()

    try:
        synced_gcs_blob = SyncedGcsBlob(
            storage_client=initialize_storage_client(
                destination_gcp_project=settings.contextual_interest.gcs.gcp_project
            ),
            metrics_client=get_metrics_client(),
            metrics_namespace="recommendation.ml.lints_interest",
            bucket_name=settings.contextual_interest.gcs.bucket_name,
            blob_name=settings.contextual_interest.gcs.blob_name,
            max_size=settings.contextual_interest.gcs.max_size,
            cron_interval_seconds=settings.contextual_interest.gcs.cron_interval_seconds,
            cron_job_name="fetch_lints_interest_model",
            is_bytes=True,
        )
        synced_gcs_blob.initialize()
        return LinTSInterestBackend(synced_gcs_blobs={SurfaceId.NEW_TAB_EN_US: synced_gcs_blob})
    except Exception as e:
        logger.error(f"Failed to initialize LinTS interest backend: {e}")
        return EmptyLinTSInterestBackend()


def init_tz_feature_backend() -> TZFeatureBackend | EmptyTZFeatureBackend:
    """Initialize the CTR-timezone feature backend (kill-switched + boot-safe)."""
    if not settings.tz_feature.enabled:
        logger.info("TZ feature backend disabled by config; using empty stub.")
        return EmptyTZFeatureBackend()

    try:
        synced_gcs_blob = SyncedGcsBlob(
            storage_client=initialize_storage_client(
                destination_gcp_project=settings.tz_feature.gcs.gcp_project
            ),
            metrics_client=get_metrics_client(),
            metrics_namespace="recommendation.ml.tz_feature",
            bucket_name=settings.tz_feature.gcs.bucket_name,
            blob_name=settings.tz_feature.gcs.blob_name,
            max_size=settings.tz_feature.gcs.max_size,
            cron_interval_seconds=settings.tz_feature.gcs.cron_interval_seconds,
            cron_job_name="fetch_tz_feature_ratios",
            is_bytes=True,
        )
        synced_gcs_blob.initialize()
        return TZFeatureBackend(synced_gcs_blobs={SurfaceId.NEW_TAB_EN_US: synced_gcs_blob})
    except Exception as e:
        logger.error(f"Failed to initialize TZ feature backend: {e}")
        return EmptyTZFeatureBackend()


def init_provider() -> None:
    """Initialize the curated recommendations' provider."""
    global _provider
    global _legacy_provider

    engagement_backend = init_engagement_backend()
    local_model_backend = init_local_model_backend()
    ml_recommendations_backend = init_ml_recommendations_backend()
    cohort_model_backend = init_ml_cohort_model_backend()
    lints_interest_backend = init_lints_interest_backend()
    tz_feature_backend = init_tz_feature_backend()

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
        lints_interest_backend=lints_interest_backend,
        tz_feature_backend=tz_feature_backend,
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
