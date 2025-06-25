"""Tests loading local model data from Google Cloud Storage."""

import asyncio
import json
import time
from typing import Callable

import pytest
from aiodogstatsd import Client as StatsdClient
from google.cloud.storage import Client, Bucket

from merino.configs import settings
from merino.curated_recommendations import GCSLocalModel
from merino.curated_recommendations.ml_backends.protocol import (
    InferredLocalModel,
    ModelData,
    ModelType,
    DayTimeWeightingConfig,
)
from merino.utils.synced_gcs_blob import SyncedGcsBlob

TEST_SURFACE_ID = "AA"
TEST_MODEL_ID = "BB"


@pytest.fixture(scope="function")
def gcs_bucket(gcs_storage_client):
    """Create a test bucket in the fake GCS server."""
    bucket = gcs_storage_client.create_bucket(settings.curated_recommendations.gcs.bucket_name)
    yield bucket
    bucket.delete(force=True)


def create_gcs_local_model(
    gcs_storage_client: Client, gcs_bucket: Bucket, metrics_client: StatsdClient
) -> GCSLocalModel:
    """Return an initialized GcsEngagement instance using the fake GCS server."""
    synced_gcs_blob = SyncedGcsBlob(
        storage_client=gcs_storage_client,
        bucket_name=gcs_bucket.name,
        blob_name=settings.curated_recommendations.gcs.local_model.blob_name,
        metrics_client=metrics_client,
        metrics_namespace="recommendation.local_model",
        max_size=settings.curated_recommendations.gcs.local_model.max_size,
        cron_interval_seconds=0.01,
        cron_job_name="fetch_local_model",
    )
    # Call initialize to start the cron job in the same event loop
    synced_gcs_blob.initialize()

    return GCSLocalModel(synced_gcs_blob=synced_gcs_blob)


def create_blob(bucket, data):
    """Create a blob with given data."""
    blob = bucket.blob(settings.curated_recommendations.gcs.local_model.blob_name)
    blob.upload_from_string(json.dumps(data))
    return blob


async def wait(until: Callable[[], bool]):
    """Wait for some time to pass, until the given condition is true."""
    max_wait_time_sec = 2
    start_time = time.time()
    while time.time() - start_time < max_wait_time_sec:
        if until():
            break
        await asyncio.sleep(0.01)  # sleep for 10ms


async def wait_until_engagement_is_updated(backend: GCSLocalModel):
    """Wait for some time to pass to update engagement."""
    await wait(until=lambda: backend.update_count > 0)


@pytest.fixture
def blob(gcs_bucket):
    """Create a blob with region data."""
    return create_blob(
        gcs_bucket,
        [
            {
                "surface_id": TEST_SURFACE_ID,
                "model_id": TEST_MODEL_ID,
                "model_version": 0,
                "model_data": {
                    "model_type": ModelType.CTR,
                    "rescale": True,
                    "day_time_weighting": {"days": [], "relative_weight": []},
                    "interest_vector": {},
                },
            }
        ],
    )


@pytest.fixture(params=["stage", "prod", "dev"])
def setting_environment(request):
    """Fixture to run a test in the staging, production, and development environment."""
    original_env = settings.current_env

    # Set the desired environment.
    settings.configure(FORCE_ENV_FOR_DYNACONF=request.param)
    yield request.param  # Yield to run the test

    # Reset to the original environment after the test
    settings.configure(FORCE_ENV_FOR_DYNACONF=original_env)


@pytest.mark.asyncio
async def test_gcs_local_model_returns_none_for_missing_keys(
    gcs_storage_client, gcs_bucket, metrics_client
):
    """Test that the backend returns None for keys not in the GCS blobs."""
    gcs_engagement = create_gcs_local_model(gcs_storage_client, gcs_bucket, metrics_client)
    assert gcs_engagement.get("missing_key") is None


@pytest.mark.asyncio
async def test_gcs_local_model_fetches_data(gcs_storage_client, gcs_bucket, metrics_client, blob):
    """Test that the backend fetches data from GCS and returns engagement data."""
    local_model = create_gcs_local_model(gcs_storage_client, gcs_bucket, metrics_client)
    await wait_until_engagement_is_updated(local_model)
    model_data = ModelData(
        model_type=ModelType.CTR,
        rescale=True,
        day_time_weighting=DayTimeWeightingConfig(
            days=[3, 14, 45],
            relative_weight=[1, 1, 1],
        ),
        interest_vector={},
    )

    assert (
        local_model.get(TEST_SURFACE_ID).model_id
        == InferredLocalModel(
            surface_id=TEST_SURFACE_ID,
            model_version=0,
            model_id=TEST_MODEL_ID,
            model_data=model_data,
        ).model_id
    )
