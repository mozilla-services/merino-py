# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

"""Unit tests for the version.py utility module."""
import pathlib

import pytest

from merino.utils.version import Version, fetch_app_version_file

# NOTE: project_root argument is defined in the project_root fixture in
# conftest.py, at the root of this directory.


@pytest.mark.parametrize("attribute", ["source", "version", "commit", "build"])
def test_fetch_app_version(project_root: pathlib.Path, attribute: str) -> None:
    """Test that the 'version.json' file in the root merino directory
    can be read. Used to populate values in __version__ endpoint and to
    access the individual values held within the json file.
    This is the method implemented in the staging and production environments
    as there is no populated version.json file in dev.
    """
    version_file = fetch_app_version_file(project_root)
    assert version_file
    assert type(version_file) == Version
    assert hasattr(version_file, attribute)


def test_fetch_app_version_get_commit_attribute(project_root) -> None:
    """Test that the 'version.json' file in the root merino directory
    can be read and the commit attribute can be accessed to populate
    the SHA hash of the current main HEAD value.
    It defaults to 'TBD' in source control.
    """
    version_file = fetch_app_version_file(project_root)
    commit_hash = version_file.commit
    assert commit_hash == "TBD"


def test_fetch_app_version_invalid_path(project_root) -> None:
    """Test that the 'version.json' file cannot be read when provided
    an invalid path, raising a FileNotFoundError.
    """
    with pytest.raises(FileNotFoundError):
        fetch_app_version_file(pathlib.Path(project_root) / "invalid" / "wrong.json")
