# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

"""Unit tests for the Manifest backend module."""

from unittest.mock import patch, MagicMock
import pytest
from merino.providers.manifest.backends.filemanager import ManifestRemoteFilemanager
from merino.providers.manifest.backends.protocol import GetManifestResultCode
from merino.providers.manifest.backends.manifest import ManifestBackend


def test_fetch_manifest_data(
    manifest_remote_filemanager: ManifestRemoteFilemanager,
    backend: ManifestBackend,
    gcs_client_mock,
    gcs_bucket_mock,
    gcs_blob_mock,
    blob_json,
) -> None:
    """Verify that the fetch_manifest_data method returns manifest data on success"""
    manifest_remote_filemanager.gcs_client = MagicMock()
    manifest_remote_filemanager.gcs_client.get_file_by_name.return_value = gcs_blob_mock

    with patch(
        "merino.providers.manifest.backends.manifest.ManifestRemoteFilemanager",
        return_value=manifest_remote_filemanager,
    ):
        get_file_result_code, result = backend.fetch_manifest_data()

        assert get_file_result_code is GetManifestResultCode.SUCCESS
        assert result is not None
        assert result.domains is not None
        assert len(result.domains) == 3
        assert result.domains[1].domain == "microsoft"


def test_fetch_manifest_data_skip(
    manifest_remote_filemanager: ManifestRemoteFilemanager,
    gcs_client_mock,
    gcs_bucket_mock,
    gcs_blob_mock,
    backend: ManifestBackend,
) -> None:
    """Verify that the fetch_manifest_data method returns SKIP code for no new blob generation"""
    manifest_remote_filemanager.gcs_client = MagicMock()
    manifest_remote_filemanager.gcs_client.get_file_by_name.return_value = None

    with patch(
        "merino.providers.manifest.backends.manifest.ManifestRemoteFilemanager",
        return_value=manifest_remote_filemanager,
    ):
        get_file_result_code, result = backend.fetch_manifest_data()

        assert get_file_result_code is GetManifestResultCode.SKIP
        assert result is None


def test_fetch_manifest_data_fail(
    manifest_remote_filemanager: ManifestRemoteFilemanager,
    gcs_client_mock,
    gcs_bucket_mock,
    backend: ManifestBackend,
) -> None:
    """Verify that the fetch_manifest_data method returns FAIL code when an error occurs"""
    manifest_remote_filemanager.gcs_client = MagicMock()
    manifest_remote_filemanager.gcs_client.get_file_by_name.return_value = None

    with patch(
        "merino.providers.manifest.backends.manifest.ManifestRemoteFilemanager",
        return_value=manifest_remote_filemanager,
    ):
        with patch.object(
            manifest_remote_filemanager,
            "get_file",
            return_value=(GetManifestResultCode.FAIL, None),
        ) as mock_get_file:
            get_file_result_code, result = backend.fetch_manifest_data()

            assert get_file_result_code is GetManifestResultCode.FAIL
            assert result is None

            mock_get_file.assert_called_once()


@pytest.mark.asyncio
async def test_fetch(
    manifest_remote_filemanager: ManifestRemoteFilemanager,
    backend: ManifestBackend,
    gcs_client_mock,
    gcs_bucket_mock,
    gcs_blob_mock,
    blob_json,
) -> None:
    """Verify that the fetch method returns manifest data"""
    manifest_remote_filemanager.gcs_client = MagicMock()
    manifest_remote_filemanager.gcs_client.get_file_by_name.return_value = gcs_blob_mock

    with patch(
        "merino.providers.manifest.backends.manifest.ManifestRemoteFilemanager",
        return_value=manifest_remote_filemanager,
    ):
        get_file_result_code, result = await backend.fetch()

        assert get_file_result_code is GetManifestResultCode.SUCCESS
        assert result is not None
        assert result.domains is not None
        assert len(result.domains) == 3
        assert result.domains[2].domain == "facebook"
