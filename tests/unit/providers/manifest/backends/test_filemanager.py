# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

"""Unit tests for the manifest backend filemanager module."""

import json
from unittest.mock import patch, MagicMock
from pydantic import ValidationError
from merino.providers.manifest.backends.filemanager import ManifestRemoteFilemanager
from merino.providers.manifest.backends.protocol import GetManifestResultCode, ManifestData


def test_get_file(
    manifest_remote_filemanager: ManifestRemoteFilemanager,
    gcs_client_mock,
    gcs_bucket_mock,
    gcs_blob_mock,
    blob_json,
) -> None:
    """Test that the get_file method returns manifest data."""
    manifest_remote_filemanager.gcs_client = MagicMock()
    manifest_remote_filemanager.gcs_client.get_file_by_name.return_value = gcs_blob_mock

    get_file_result_code, result = manifest_remote_filemanager.get_file()

    assert isinstance(result, ManifestData)
    assert result.domains
    assert len(result.domains) == 3
    assert result.domains[0].domain == "google"


def test_get_file_skip(
    manifest_remote_filemanager: ManifestRemoteFilemanager,
    gcs_client_mock,
    gcs_bucket_mock,
) -> None:
    """Test that the get_file method returns the SKIP code when there's no new generation."""
    manifest_remote_filemanager.gcs_client = MagicMock()
    manifest_remote_filemanager.gcs_client.get_file_by_name.return_value = None

    get_file_result_code, result = manifest_remote_filemanager.get_file()

    assert get_file_result_code is GetManifestResultCode.SKIP
    assert result is None


def test_get_file_fail(
    manifest_remote_filemanager: ManifestRemoteFilemanager,
    gcs_client_mock,
    gcs_bucket_mock,
) -> None:
    """Test that the get_file method returns the FAIL code on failure."""
    gcs_client_mock.get_bucket.side_effect = Exception("Test error")

    get_file_result_code, result = manifest_remote_filemanager.get_file()

    assert get_file_result_code is GetManifestResultCode.FAIL
    assert result is None


def test_get_file_fail_validation_error(
    manifest_remote_filemanager: ManifestRemoteFilemanager,
    gcs_client_mock,
    gcs_bucket_mock,
    gcs_blob_mock,
    blob_json,
) -> None:
    """Test that the get_file method returns the FAIL code when a validation error occurs."""
    mock_blob = gcs_blob_mock(blob_json, "manifest.json")

    gcs_bucket_mock.get_blob.return_value = mock_blob
    gcs_client_mock.get_bucket.return_value = gcs_bucket_mock

    mock_blob.download_as_text.return_value = '{"invalid": "data"}'

    with patch(
        "merino.providers.manifest.backends.filemanager.ManifestData.model_validate",
        side_effect=ValidationError,
    ):
        get_file_result_code, result = manifest_remote_filemanager.get_file()

    assert get_file_result_code is GetManifestResultCode.FAIL
    assert result is None


def test_get_file_fail_json_decoder_error(
    manifest_remote_filemanager: ManifestRemoteFilemanager,
    gcs_client_mock,
    gcs_bucket_mock,
    gcs_blob_mock,
    blob_json,
) -> None:
    """Test that the get_file method returns the FAIL code when a JSON decoder occurs."""
    gcs_bucket_mock.get_blob.return_value = gcs_blob_mock(blob_json, "manifest.json")
    gcs_client_mock.get_bucket.return_value = gcs_bucket_mock

    with patch(
        "merino.providers.manifest.backends.filemanager.json.loads",
        side_effect=json.JSONDecodeError,
    ):
        get_file_result_code, result = manifest_remote_filemanager.get_file()

    assert get_file_result_code is GetManifestResultCode.FAIL
    assert result is None
