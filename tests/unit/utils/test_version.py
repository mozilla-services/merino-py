# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

"""Unit tests for the version.py utility module."""

import json
import pathlib

import pytest
from pydantic import ValidationError

from merino.utils.version import Version, fetch_app_version_from_file


def test_fetch_app_version_from_file() -> None:
    """Happy path test for fetch_app_version_from_file()."""
    expected_information: dict = {
        "source": "https://github.com/mozilla-services/merino-py",
        "version": "dev",
        "commit": "TBD",
        "build": "TBD",
    }

    version: Version = fetch_app_version_from_file()
    assert version.model_dump() == expected_information


def test_fetch_app_version_from_file_invalid_path() -> None:
    """Test that the 'version.json' file cannot be read when provided
    an invalid path, raising a FileNotFoundError.
    """
    with pytest.raises(FileNotFoundError) as excinfo:
        fetch_app_version_from_file(pathlib.Path("invalid"))

    assert "No such file or directory: 'invalid/version.json'" in str(excinfo.value)


@pytest.fixture(name="dir_containing_incorrect_file")
def fixture_dir_containing_incorrect_file(tmp_path: pathlib.Path) -> pathlib.Path:
    """Create a version.json file that does not match the Version model."""
    version_file = tmp_path / "version.json"
    version_file.write_text(
        json.dumps(
            {
                "source": "https://github.com/mozilla-services/merino-py",
                "version": "dev",
                "commit": "TBD",
                "build": "TBD",
                "incorrect": "this should not be here",
            }
        )
    )
    return tmp_path


def test_version_extra_forbid(dir_containing_incorrect_file: pathlib.Path) -> None:
    """Test that fetch_app_version_from_file raises an error for incorrect files."""
    with pytest.raises(ValidationError):
        fetch_app_version_from_file(merino_root_path=dir_containing_incorrect_file)
