"""Tests loading engagement data from Google Cloud Storage."""

import asyncio
import base64
import logging
import time
from typing import Callable

import pytest
from aiodogstatsd import Client as StatsdClient
from google.cloud.storage import Client, Bucket

from merino.configs import settings
from merino.curated_recommendations.ml_backends.gcs_interest_cohort_model import (
    GcsInterestCohortModel,
)
from merino.utils.synced_gcs_blob import SyncedGcsBlob

MODEL_BASE64 = "AAIAAAAAAAB7Il9fbWV0YWRhdGFfXyI6eyJtb2RlbF9uYW1lIjoiSW50ZXJlc3RDb2hvcnRNb2RlbCIsIm1vZGVsX2lkIjoiaW5mZXJyZWQtdjMtbW9kZWwiLCJudW1faW50ZXJlc3RfYml0cyI6IjMyIiwidHJhaW5pbmdfcnVuX2lkIjoiYXJnby1wcm9zcGVjdGluZy5wcm9kLmluZmVycmVkaW50ZXJlc3RzdXNlcmZsb3ctanBoamcifSwiaW50ZXJlc3RfbGF5ZXIuMC5iaWFzIjp7ImR0eXBlIjoiRjMyIiwic2hhcGUiOlsxNl0sImRhdGFfb2Zmc2V0cyI6WzAsNjRdfSwiaW50ZXJlc3RfbGF5ZXIuMC53ZWlnaHQiOnsiZHR5cGUiOiJGMzIiLCJzaGFwZSI6WzE2LDMyXSwiZGF0YV9vZmZzZXRzIjpbNjQsMjExMl19LCJpbnRlcmVzdF9sYXllci4yLmJpYXMiOnsiZHR5cGUiOiJGMzIiLCJzaGFwZSI6WzEwXSwiZGF0YV9vZmZzZXRzIjpbMjExMiwyMTUyXX0sImludGVyZXN0X2xheWVyLjIud2VpZ2h0Ijp7ImR0eXBlIjoiRjMyIiwic2hhcGUiOlsxMCwxNl0sImRhdGFfb2Zmc2V0cyI6WzIxNTIsMjc5Ml19fSAgICAgINs+lL6DW0A+eLGNPuI4RL7OFPG9z2MNPoQjZD4VqKY9oguMPhKvS72zThM/2hvTPzXVoL3Zow8/JCcJvp4BuD16BiG/7CmZP7rNoj9a/Po+cmeRPqqslz8Ea44/rguYP1sUGL85w6I/lUEAwEC40T96q4U+MNOaP+4tjT+0v+e/Z1iNPzjSAcAxxJU/uFLJv7cqeT/h96Y/GEiUP445kj/d0Y8+hOufP9nIqT8SoJs/yJV9P31Tjj+Mqp0/IyiAP2M6Z78D74e/pZurv5ez7j+LCc8+EYGUv07Pcb8Cj4O/PEI+v1zzj7/DPbM/RZBqP5/+iT7Ai5e/iTp+v7sOzT+Dmu4/8czEP9jugr+v5sA/F0LmP+7GUb/z+mq/mWlhv6wOPT40zn6/e8KUv9IMer+akts/RU2Pv0gpmb+E7oq/ck3HPsWHWT9ST4g/UFq5v1cxy7xXbmY/jDxrP/X2Zj/PboY+5ndXPxgeOj8blNS+u2FHPmm9Yj+gZVk/LEFGPxXyX72H4jc/RTZUP+t1OT8ycZi9DbdgP7irbj+zQ2o/CUxQPqPLcj91QmM/dKJgP8wtzL03xHE/lYhmP3FxRz+npQG/njZ0P0Cofj/TERK/Wu7mPfjaQD9rVBU/4EUdPyEXD787HyI/fOXwvwQpDj9vHHc+ZgJgP4UoaT9l7M2/D9gfP6Jivb87g2Q/C3LPv7bSQD+tzog/ErB/PyBnRT9LeHM+glNtPyCiUT9Wvjw/yAgfPwhYdj+bU1s/9+tkPyfLgz7Ig24/L0KFP/Xnpr/Jvhk+CIhUPy4LYz/ygoA/4oi5PS6AKj8P70e/jd4IvweaET4toHA/GApYPysARr9cYI49zMFTvymUjD8oJF2/dm/+Pciohj9oUHc/diGQPz5dsby8e2s/jgyDP9L8ij/luz4+lqd5P8KdZD89b34/sXrRPZB+qjzyEDw/1dRLvdb7yz1azgU/6lQlP4xD8T2IVo0+6hw7vRV80zzFpXY/BBsUvVvPuT2eN60+25RNvV7dQL5kHPu94lUXP1xPT73Okru8cjSBu66ziL0lkpe9U5/CvQrYBL3MCsK91t1qvWi5xT2bKjA/fAaDvQBCJT/k4qW9ptaPPz+isj/kggTAdKeKPlwOhj+OdJE/mFWMP005sz1REY0/1V7fv0UXa7+cngM+wGagP92woT/Yuei/e5sXP78u3r9KdZc/sDbsv890Hj9r550/GImbP202pz+GqpA8zD6YP52Nnz+5hKI/LTYPPyA4rz8c66E/bMGQPwKD1D7ecBI/S31XPwURfL9aTx89aiBLP8N4Uz9yaQ4/fZDPPrl+KD8Wjw0/rfkQvw9Tcj5CLyA/lHD+PkcWDz+qNpw8C80hP5vKJD/TrUg/2RMdvSArVT9n01Q/bAdAPwKCSD6zn0c/hnFKP40TUT9xoV++zU9WP3CGGD8SygQ/7ePbvhyAhb9Xlt++iAaav38SCT5/hxu/nQ42v4CXDr+KPaW+A/F8v1+tbb3+xe+/rd8BPp/cMr9vBh+/QHpRPuWDHz/hTO49ZnN5v9D+pz5hze0+68t9v/4di7/AIHO/LZ8GPoobab/7/Bu/+MNvvyTeDj+mt4e/i8FFv3cxhb8+tzA+bLUEP18ALT/b5o+/2G21Pe6vHz9jP+o+f/X3PrCT4bzv2rg+gWibP6EhMr8Js4I+48DvPp7ZBj9Az4g/y8UrPsM4hz/8sig/hyBvP8x6pT4GriE/GY0gPwRgQT+noAW9tKkCP1biEz/MzN4+UnwYPgmNDz+SUwE/aKcwP+Aidz9zX9C+7bQmvyImKb/ByKk+z2Auv9pc577VE+++okV0P6esNb+XCec/ZFOjvwQVlz4oxkC/ATw1v/wp2T83OAG/BLLcP+OEC7+LW8s/Jat6vkKU5r7Bozu/4MY4v9rKmj7xuum+MBkBvyGr/L6gk8a+fDD8vuy5Fb/HjC2/nmUHQANt1L8jj7S/BpuRPyu8BD/u2sq/1LDmvzgK3r+ZqBBA+gXhvwzt0r/7wxA+zv20Posayb8OMdu/+I3Ev/LClb9Cft6/xejOv81Y3L+rFKS/MuHCv7DWrL8GUs2/ae+fPnJB3L/ZQte/VP3cvwaTqL+a9L+/FbnMv4j52b8hI8g9ROrfPpe7/D5S+UC/QA7JPUURCT9fZKE+52h8Ppc3gz5ebMw94VWtP0HHS7+PLvI9eQatPvTvBj/v4qk//T5pPmqTrD+mLN4+ffi9Pxrtez4h8wE/hb3xPrAFkj4aXTI+FPOmPgmufj5TTUg+m7H+PR3uAj9AH94+txuAPshz4z84tLg/fBHHP8TRnr/V3oQ+EGOyP+PrtD+fk7w/eobgP5D0lj80Iee/KCCAPmWZtj4vmZ8/dlmxP0/Y0L/3Mxi//nHPvy42mj/X59+/Q1VZv1mapj+SM6g/jCKcP1P9oD4+u7U/SLmkP8vztD98UFC/BEybP7rLvz/oH58/KVCxPauu6D7vb6g+IMmxP1hwRz6YtCA/W88YP0nWtT7lenU+YX8CP150w74Kynw/IksRPmrvkT7i6Pg+usc0O6OsTT7l0yK+wPjsPphi2b4iLFc+X5a2Pl1j7D5s/98+UOCmPSS15D4VreY+2t2pPlmeBL7xOPM+XrgDP2xNAT/mryI+kAotP4/kcj85v7m/pupqPmYAOT9urzI/bExJP86+BT7wBBE/yLHMP4tRk7825ro9bjdDP37wMj/go7Y/BN+SPWV9rD/UMC8/qI20P97+Jz5Jt0c/jWJSP8LHOz+IsaE+eVVEP/b5KT9Wq0Y/jC/BProGVD9/EFA/X4Y9P8hKerwrO9M9/qUzvtcjrzyy3b+9N8osPU4Y6Tw4LG09FV+mPo0HJr7+F70+ZWC4P4zyaL93GZY/DLxJvusil7+tiDU/Eo4Wv86eBEDA81s+iWuRvzCvMb/uU0q+/ufpv5VyBL+FNKE8HPOvvuX1oj44PTq+fCcgvkV+Nz3zbUg+q1eevmiNAj70slI+6OSkvs8X6bwOXjI/hZmlvQiwTT3VZE8852xavv2evj/xCry/HniMPwquhj+5III/Rvj9Pppvvz9DGxg/lYKlvx5WMT+Oy4K/P8Lmv8RnTD1SYrQ/EuBzPocRQD9AIuE/lhTjPzxBuL+DEQ0/atV7v52u4T3TBeO/v0hcv+xx47+icZK/yansvzCT3z+zqGu/RH4Tv3WWQj/QFNC/PqamvoeXLr+RS3k+DqDAvTdm2D1xS969V18fvToNGj66mCm9O84VPexqnr2HdSa+3BhJPkbASD0dgmI+WRyGPv0OuL/rF8k/DzwYP9ZpSL+XU32+rte+vJ6N2r+tUak+kr9PPSdoVj8Bu9E/fEa5v8k1Pj+Qeoq/YTVGvfC+pT+VFZo8EQzjPtBWmLwYgwc+9bWUvqEttbwqERa/5ErMPRbBzz3e3Em+kLkDvuCJWT9iyaO93xMGvba/Zb4BwRC+Bm7hvo87aD/cKxG+ydooviSwob2N+eA9oHG2Prq0Q76LgQg/D5tUvh/OkD4x4KM/dMuMPemeSz2eUpu+NNtevq6wCcCVFce/OWxOPVk/j79u5YG+sT4dvcRqMr6Xvbw+zZufvQwcAr9fedc/zaNYQKOgur7SbJc/I6S1viKV5b5gyrC+QdvzPqi+Uj3bhtK9/2HZvYLhyDv0DPa+V5JNPa0Xvb3KEAm9ye+GvQNygT9LMwk9rx2Ovnpx8z1YKoO+"


@pytest.fixture(scope="function")
def gcs_bucket(gcs_storage_client):
    """Create a test bucket in the fake GCS server."""
    bucket = gcs_storage_client.create_bucket(settings.interest_cohort_model.gcs.bucket_name)
    yield bucket
    bucket.delete(force=True)


def create_cohort_model(
    gcs_storage_client: Client, gcs_bucket: Bucket, metrics_client: StatsdClient
) -> GcsInterestCohortModel:
    """Return an initialized GcsInterestCohortModel instance using the fake GCS server."""
    synced_gcs_blob = SyncedGcsBlob(
        storage_client=gcs_storage_client,
        bucket_name=gcs_bucket.name,
        blob_name=settings.interest_cohort_model.gcs.blob_name,
        metrics_client=metrics_client,
        metrics_namespace="recommendation.ml.interest_cohort_model",
        max_size=settings.interest_cohort_model.gcs.max_size,
        cron_interval_seconds=0.01,
        cron_job_name="fetch_ml_cohort_model",
        is_bytes=True,
    )
    # Call initialize to start the cron job in the same event loop
    synced_gcs_blob.initialize()

    return GcsInterestCohortModel(synced_gcs_blob=synced_gcs_blob)


def create_blob(bucket, data):
    """Create a blob with given data."""
    blob = bucket.blob(settings.interest_cohort_model.gcs.blob_name)
    blob.upload_from_string(data=data, content_type="application/octet-stream")
    return blob


async def wait(until: Callable[[], bool]):
    """Wait for some time to pass, until the given condition is true."""
    max_wait_time_sec = 2
    start_time = time.time()
    while time.time() - start_time < max_wait_time_sec:
        if until():
            break
        await asyncio.sleep(0.01)  # sleep for 10ms


async def wait_until_model_is_updated(backend: GcsInterestCohortModel):
    """Wait for some time to pass to update engagement."""
    await wait(until=lambda: backend.update_count > 0)


@pytest.fixture
def blob(gcs_bucket):
    """Create a blob with region data."""
    return create_blob(
        gcs_bucket,
        base64.b64decode(MODEL_BASE64),
    )


@pytest.fixture
def old_blob(gcs_bucket):
    """Create a blob with region data."""
    return create_blob(
        gcs_bucket,
        base64.b64decode(MODEL_BASE64),
    )


@pytest.fixture
def large_blob(gcs_bucket):
    """Create a large blob in the fake GCS server."""
    return create_blob(
        gcs_bucket,
        "a" * (settings.interest_cohort_model.gcs.max_size + 1),
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
async def test_cohort_model_works(gcs_storage_client, gcs_bucket, metrics_client, blob):
    """Test that the backend parses model."""
    model_provider = create_cohort_model(gcs_storage_client, gcs_bucket, metrics_client)
    await wait_until_model_is_updated(model_provider)
    result = model_provider.get_cohort_for_interests(
        model_id="inferred-v3-model", interests="1" * model_provider._num_bits
    )
    assert result is not None
    int_result: int | None = None
    try:
        int_result = int(result)
    except ValueError:
        int_result = None
    assert int_result is not None
    assert int_result >= 0
    assert int_result < 20


@pytest.mark.asyncio
async def test_cohort_model_skips_due_to_mismatch(
    gcs_storage_client, gcs_bucket, metrics_client, blob
):
    """Test that graceful failures due to various mismatched parameters."""
    model_provider = create_cohort_model(gcs_storage_client, gcs_bucket, metrics_client)
    await wait_until_model_is_updated(model_provider)

    result = model_provider.get_cohort_for_interests(
        model_id="inferred-othermodel", interests="1" * model_provider._num_bits
    )
    assert result is None

    result = model_provider.get_cohort_for_interests(
        model_id="inferred-othermodel", interests="1" * (model_provider._num_bits - 1)
    )
    assert result is None

    result = model_provider.get_cohort_for_interests(
        model_id="inferred-v3-model",
        interests="1" * model_provider._num_bits,
        training_run_id="different-run-id",
    )
    assert result is None


@pytest.mark.asyncio
async def test_gcs_engagement_logs_error_for_large_blob(
    gcs_storage_client, gcs_bucket, metrics_client, large_blob, caplog
):
    """Test that the backend logs an error if the blob size exceeds the max size."""
    model_provider = create_cohort_model(gcs_storage_client, gcs_bucket, metrics_client)
    caplog.set_level(logging.ERROR)

    await wait_until_model_is_updated(model_provider)

    max_size = settings.interest_cohort_model.gcs.max_size
    assert f"Blob '{large_blob.name}' size {max_size + 1} exceeds {max_size}" in caplog.text


@pytest.mark.asyncio
async def test_gcs_cohort_logs_error_for_missing_blob(
    gcs_storage_client, gcs_bucket, metrics_client, caplog, setting_environment
):
    """Test that the backend logs an error if the blob does not exist, outside 'stage'."""
    # Set the environment for each test case
    caplog.set_level(logging.INFO)
    create_cohort_model(gcs_storage_client, gcs_bucket, metrics_client)

    def expected_message_is_logged():
        # Filter log records to only those with the expected log level
        expected_level_name = "INFO" if setting_environment == "stage" else "ERROR"
        log_records = [
            record for record in caplog.records if record.levelname == expected_level_name
        ]
        # Assert that the expected message appears with the expected log level
        expected_message = "Blob 'contextual_ts/cohort_model.safetensors' not found."
        return any(expected_message in record.message for record in log_records)

    # Ensure that this test runs quickly, by waiting only until the expected message is logged.
    await wait(until=expected_message_is_logged)

    assert expected_message_is_logged()


@pytest.mark.asyncio
async def test_gcs_cohort_model_metrics(gcs_storage_client, gcs_bucket, metrics_client, blob):
    """Test that the backend records the correct metrics."""
    model_provider = create_cohort_model(gcs_storage_client, gcs_bucket, metrics_client)
    await wait_until_model_is_updated(model_provider)
    # Check the last_updated gauge value shows that the data was updated just now.
    assert any(
        call[0][0] == "recommendation.ml.interest_cohort_model.last_updated"
        and 0 <= call[1]["value"] <= 10
        for call in metrics_client.gauge.call_args_list
    ), "The gauge recommendation.ml.interest_cohort_model.last_updated was not called with value between 0 and 10"
