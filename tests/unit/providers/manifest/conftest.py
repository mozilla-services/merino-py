# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

"""Module for test configurations for the Manifest provider unit test directory."""

import json
from typing import Any
from unittest.mock import patch

import pytest
from merino.configs import settings
from merino.providers.manifest.backends.filemanager import ManifestRemoteFilemanager
from merino.providers.manifest.backends.manifest import ManifestBackend
from merino.providers.manifest.provider import Provider


@pytest.fixture(name="manifest_remote_filemanager_parameters")
def fixture_manifest_remote_filemanager_parameters() -> dict[str, Any]:
    """Define ManifestRemoteFilemanager parameters for test."""
    # These settings read from testing.toml, not default.toml.
    return {
        "gcs_project_path": settings.manifest.gcs_project,
        "gcs_bucket_path": settings.manifest.gcs_bucket,
        "blob_name": settings.manifest.gcs_blob_name,
    }


@pytest.fixture(name="manifest_remote_filemanager")
def fixture_manifest_remote_filemanager(
    manifest_remote_filemanager_parameters: dict[str, Any], gcs_client_mock
) -> ManifestRemoteFilemanager:
    """Create a ManifestRemoteFilemanager object for test."""
    with patch("merino.providers.manifest.backends.filemanager.Client") as mock_client:
        mock_client.return_value = gcs_client_mock
        return ManifestRemoteFilemanager(**manifest_remote_filemanager_parameters)


@pytest.fixture(name="backend")
def fixture_backend() -> ManifestBackend:
    """Create a Manifest backend object for test."""
    backend = ManifestBackend()
    return backend


@pytest.fixture(name="manifest_parameters")
def fixture_manifest_parameters() -> dict[str, Any]:
    """Define Manifest provider parameters for test."""
    return {
        "resync_interval_sec": settings.manifest.resync_interval_sec,
        "cron_interval_sec": settings.manifest.cron_interval_sec,
    }


@pytest.fixture(name="manifest_provider")
def fixture_top_picks(backend: ManifestBackend, manifest_parameters: dict[str, Any]) -> Provider:
    """Create Manifest Provider for test."""
    return Provider(backend=backend, **manifest_parameters)


@pytest.fixture(name="blob_json")
def fixture_blob_json() -> str:
    """Return a JSON string for mocking."""
    return json.dumps(
        {
            "domains": [
                {
                    "rank": 1,
                    "domain": "google",
                    "categories": ["Search Engines"],
                    "serp_categories": [0],
                    "url": "https://www.google.com/",
                    "title": "Google",
                    "icon": "chrome://activity-stream/content/data/content/tippytop/images/google-com@2x.png",
                },
                {
                    "rank": 2,
                    "domain": "microsoft",
                    "categories": ["Business", "Information Technology"],
                    "serp_categories": [0],
                    "url": "https://www.microsoft.com/",
                    "title": "Microsoft – AI, Cloud, Productivity, Computing, Gaming & Apps",
                    "icon": "https://merino-images.services.mozilla.com/favicons/90cdaf487716184e4034000935c605d1633926d348116d198f355a98b8c6cd21_17174.oct",
                },
                {
                    "rank": 3,
                    "domain": "facebook",
                    "categories": ["Social Networks"],
                    "serp_categories": [0],
                    "url": "https://www.facebook.com/",
                    "title": "Log in to Facebook",
                    "icon": "https://merino-images.services.mozilla.com/favicons/e673f8818103a583c9a98ee38aa7892d58969ec2a8387deaa46ef6d94e8a3796_4535.png",
                },
            ]
        }
    )
