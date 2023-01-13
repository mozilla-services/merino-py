# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

"""Unit tests for the config_sentry.py module."""
import os

import pytest

from merino.config_sentry import fetch_sha_hash_from_version_file

# NOTE: project_root argument is defined in the project_root fixture in
# conftest.py, at the root of this directory.


def test_fetch_sha_hash_from_version_file(project_root) -> None:
    """Test that the 'version.json' file in the root merino directory
    can be read to capture the SHA hash of the current main HEAD.
    This is the method implemented in the staging and produciton
    environments as there is no populated version.json file in dev.
    """
    hash = fetch_sha_hash_from_version_file(project_root)
    assert hash == "TBD"


def test_fetch_sha_hash_from_version_file_invalid_path(project_root) -> None:
    """Test that the 'version.json' file in the root merino directory
    can be read to capture the SHA hash of the current main HEAD.
    This is the method implemented in the staging and produciton
    environments as there is no populated version.json file in dev.
    """
    with pytest.raises(FileNotFoundError):
        fetch_sha_hash_from_version_file(os.path.join(project_root, "wrong"))
