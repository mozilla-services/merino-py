# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

"""Unit tests for the Manifest backend module."""

from unittest.mock import patch
import pytest
from merino.providers.manifest.backends.protocol import (
    GetManifestResultCode,
    ManifestFetchResult,
)
from merino.providers.manifest.backends.manifest import ManifestBackend


@pytest.mark.asyncio
async def test_fetch_manifest_data(backend: ManifestBackend, fixture_filemanager) -> None:
    """Verify that the fetch_manifest_data method returns manifest data on success"""
    # Since we only initialize ManifestRemoteFilemanager inside the fetch_manifest_data function,
    # we will have to patch the actual path for ManifestRemoteFilemanager class with our fixture

    with patch(
        "merino.providers.manifest.backends.manifest.ManifestRemoteFilemanager",
        return_value=fixture_filemanager,
    ):
        result = await backend.fetch_manifest_data()

        assert result.code is GetManifestResultCode.SUCCESS
        assert result.data is not None
        assert result.data.domains is not None
        assert len(result.data.domains) == 5
        assert result.data.domains[1].domain == "microsoft"
        assert result.etag == "42"


@pytest.mark.asyncio
async def test_fetch_manifest_data_fail(backend: ManifestBackend, fixture_filemanager) -> None:
    """Verify that the fetch_manifest_data method returns FAIL code when an error occurs"""
    with patch(
        "merino.providers.manifest.backends.manifest.ManifestRemoteFilemanager",
        return_value=fixture_filemanager,
    ):
        with patch.object(
            fixture_filemanager,
            "get_file",
            return_value=ManifestFetchResult(code=GetManifestResultCode.FAIL, data=None),
        ) as mock_get_file:
            result = await backend.fetch_manifest_data()

            assert result.code is GetManifestResultCode.FAIL
            assert result.data is None
            assert result.etag is None

            mock_get_file.assert_called_once()


@pytest.mark.asyncio
async def test_fetch(backend: ManifestBackend, fixture_filemanager) -> None:
    """Verify that the fetch method returns manifest data"""
    with patch(
        "merino.providers.manifest.backends.manifest.ManifestRemoteFilemanager",
        return_value=fixture_filemanager,
    ):
        result = await backend.fetch()

        assert result.code is GetManifestResultCode.SUCCESS
        assert result.data is not None
        assert result.data.domains is not None
        assert len(result.data.domains) == 5
        assert result.data.domains[2].domain == "facebook"
        assert result.etag == "42"
