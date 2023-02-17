# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

"""Unit tests for the version.py utility module."""
import json
import pathlib

import pytest
from pydantic import ValidationError

from merino.utils.version import check_version, fetch_app_version_from_file


@pytest.fixture(name="expected_version_data")
def fixture_expected_version_data() -> dict:
    """Version file data."""
    expected_data = {
        "source": "https://github.com/mozilla-services/merino-py",
        "version": "dev",
        "commit": "TBD",
        "build": "TBD",
    }
    return expected_data


def test_fetch_app_version_from_file(expected_version_data: dict) -> None:
    """Happy path test for fetch_app_version_from_file()."""
    version = fetch_app_version_from_file()
    assert version.dict() == expected_version_data


def test_fetch_app_version_from_file_file_not_found() -> None:
    """Test that the 'version.json' file cannot be read when provided
    an invalid path, raising a FileNotFoundError.
    """
    with pytest.raises(FileNotFoundError):
        fetch_app_version_from_file(pathlib.Path("invalid"))


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


@pytest.fixture(name="dir_containing_corrupted_file")
def fixture_dir_containing_corrupted_file(tmp_path: pathlib.Path) -> pathlib.Path:
    """Create a version.json file that does not match the Version model."""
    version_file = tmp_path / "version.json"
    version_file.write_text(
        json.dumps(
            {
                "source": "https://github.com/mozilla-services/merino-py",
                "version": "dev",
                "commit": "TBD",
                "build": "TBD",
            }
        )
    )
    version_file.write_text(",")
    return tmp_path


def test_version_invalid_json_forbid(
    dir_containing_corrupted_file: pathlib.Path,
) -> None:
    """Test that fetch_app_version_from_file raises an error for incorrect files."""
    with pytest.raises(json.JSONDecodeError):
        fetch_app_version_from_file(merino_root_path=dir_containing_corrupted_file)


def test_check_version() -> None:
    """Test that test_check_version returns True, indicating successful
    lookup and validation of version.json file.
    """
    assert check_version() is True
