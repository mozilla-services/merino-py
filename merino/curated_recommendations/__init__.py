"""Module dedicated to providing curated recommendations to New Tab."""

# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.
import logging
import random

from merino.cache.redis import RedisAdapter, create_redis_clients
from merino.configs import settings
from merino.curated_recommendations.corpus_backends.protocol import (
    ScheduledSurfaceProtocol,
    SectionsProtocol,
)
from merino.curated_recommendations.corpus_backends.redis_cache import (
    CorpusCacheConfig,
    RedisCachedScheduledSurface,
    RedisCachedSections,
)
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

    blob_name = settings.ml_recommendations.gcs.blob_name
    try:
        synced_gcs_blob = SyncedGcsBlob(
            storage_client=initialize_storage_client(
                destination_gcp_project=settings.ml_recommendations.gcs.gcp_project
            ),
            metrics_client=get_metrics_client(),
            metrics_namespace="recommendation.ml.contextual",
            bucket_name=settings.ml_recommendations.gcs.bucket_name,
            blob_name=blob_name,
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


def _init_corpus_cache(
    scheduled_surface_backend: ScheduledSurfaceProtocol,
    sections_backend: SectionsProtocol,
) -> tuple[ScheduledSurfaceProtocol, SectionsProtocol, RedisAdapter | None]:
    """Optionally wrap corpus backends with a Redis L2 cache layer.

    Returns the backends (possibly wrapped) and the Redis adapter (if created).
    The caller owns the adapter and is responsible for closing it on shutdown.
    """
    cache_settings = settings.curated_recommendations.corpus_cache
    if cache_settings.cache != "redis":
        return scheduled_surface_backend, sections_backend, None

    try:
        logger.info("Initializing Redis L2 cache for corpus backends")
        adapter = RedisAdapter(
            *create_redis_clients(
                primary=settings.redis.server,
                replica=settings.redis.replica,
                max_connections=settings.redis.max_connections,
                socket_connect_timeout=settings.redis.socket_connect_timeout_sec,
                socket_timeout=settings.redis.socket_timeout_sec,
            )
        )
        config = CorpusCacheConfig(
            soft_ttl_sec=cache_settings.soft_ttl_sec,
            hard_ttl_sec=cache_settings.hard_ttl_sec,
            lock_ttl_sec=cache_settings.lock_ttl_sec,
            key_prefix=cache_settings.key_prefix,
        )
        return (
            RedisCachedScheduledSurface(scheduled_surface_backend, adapter, config),
            RedisCachedSections(sections_backend, adapter, config),
            adapter,
        )
    except Exception as e:
        logger.error("Failed to initialize Redis corpus cache, proceeding without it: %s", e)
        return scheduled_surface_backend, sections_backend, None


def init_provider() -> None:
    """Initialize the curated recommendations' provider."""
    global _provider
    global _legacy_provider

    engagement_backend = init_engagement_backend()
    local_model_backend = init_local_model_backend()
    ml_recommendations_backend = init_ml_recommendations_backend()
    cohort_model_backend = init_ml_cohort_model_backend()

    scheduled_surface_backend: ScheduledSurfaceProtocol = ScheduledSurfaceBackend(
        http_client=create_http_client(base_url=""),
        graph_config=CorpusApiGraphConfig(),
        metrics_client=get_metrics_client(),
        manifest_provider=get_manifest_provider(),
    )

    sections_backend: SectionsProtocol = SectionsBackend(
        http_client=create_http_client(base_url=""),
        graph_config=CorpusApiGraphConfig(),
        metrics_client=get_metrics_client(),
        manifest_provider=get_manifest_provider(),
    )

    scheduled_surface_backend, sections_backend, cache_adapter = _init_corpus_cache(
        scheduled_surface_backend, sections_backend
    )

    _provider = CuratedRecommendationsProvider(
        scheduled_surface_backend=scheduled_surface_backend,
        engagement_backend=engagement_backend,
        prior_backend=init_prior_backend(),
        sections_backend=sections_backend,
        local_model_backend=local_model_backend,
        ml_recommendations_backend=ml_recommendations_backend,
        cohort_model_backend=cohort_model_backend,
        cache_adapter=cache_adapter,
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


async def shutdown() -> None:
    """Clean up resources used by curated recommendations."""
    try:
        await _provider.shutdown()
    except NameError:
        pass
