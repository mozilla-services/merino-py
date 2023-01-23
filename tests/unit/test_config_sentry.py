# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

"""Unit tests for the config_sentry.py module."""
import pathlib

import pytest

from merino.utils.version import fetch_app_version

# NOTE: project_root argument is defined in the project_root fixture in
# conftest.py, at the root of this directory.


def test_fetch_app_version(project_root) -> None:
    """Test that the 'version.json' file in the root merino directory
    can be read to capture the SHA hash of the current main HEAD value
    accessed via the 'commit' key. This is the method implemented in the
    staging and production environments as there is no populated version.json
    file in dev. It defaults to 'TBD' in source control.
    """
    commit_hash = fetch_app_version(project_root)
    assert commit_hash == "TBD"


def test_fetch_app_version_invalid_path(project_root) -> None:
    """Test that the 'version.json' file in the root merino directory
    can be read to capture the SHA hash of the current main HEAD.
    This is the method implemented in the staging and production
    environments as there is no populated version.json file in dev.
    """
    with pytest.raises(FileNotFoundError):
        fetch_app_version(pathlib.Path(project_root) / "invalid" / "wrong.json")
