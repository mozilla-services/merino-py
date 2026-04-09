# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

"""Test configurations for the logos provider unit tests."""

import pytest
import pytest_asyncio
from unittest.mock import AsyncMock, MagicMock

from gcloud.aio.storage import Storage

from merino.providers.suggest.logos.provider import Provider


@pytest_asyncio.fixture
async def fixture_logos_bucket() -> AsyncMock:
    """Return a mocked async GCS bucket."""
    bucket = AsyncMock()
    bucket.name = "test_gcp_uploader_bucket"
    bucket.blob_exists.return_value = True
    return bucket


@pytest.fixture(name="logos_provider")
def fixture_logos_provider(statsd_mock, fixture_logos_bucket) -> Provider:
    """Return a Provider instance with mocked GCS bucket."""
    provider = Provider(
        metrics_client=statsd_mock,
        storage_client=MagicMock(spec=Storage),
    )
    provider._bucket = fixture_logos_bucket
    return provider
