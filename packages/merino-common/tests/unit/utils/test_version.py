# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

"""Unit tests for the version.py utility module."""

import json
import pathlib

import pytest
from pydantic import ValidationError

from merino_common.utils.version import Version, fetch_app_version_from_file


VALID_VERSION_PAYLOAD = {
    "source": "https://github.com/mozilla-services/merino-py",
    "version": "dev",
    "commit": "TBD",
    "build": "TBD",
}


@pytest.fixture(name="dir_with_valid_version_file")
def fixture_dir_with_valid_version_file(tmp_path: pathlib.Path) -> pathlib.Path:
    """Create a directory containing a valid version.json file."""
    (tmp_path / "version.json").write_text(json.dumps(VALID_VERSION_PAYLOAD))
    return tmp_path


def test_fetch_app_version_from_file(dir_with_valid_version_file: pathlib.Path) -> None:
    """Happy path: a valid version.json parses into a Version model."""
    version: Version = fetch_app_version_from_file(merino_root_path=dir_with_valid_version_file)

    assert str(version.source) == "https://github.com/mozilla-services/merino-py"
    assert version.version == "dev"
    assert version.commit == "TBD"
    assert version.build == "TBD"


def test_fetch_app_version_from_file_default_cwd(
    dir_with_valid_version_file: pathlib.Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Default argument resolves version.json relative to the current working directory."""
    monkeypatch.chdir(dir_with_valid_version_file)

    version: Version = fetch_app_version_from_file()

    assert version.version == "dev"


def test_fetch_app_version_from_file_invalid_path() -> None:
    """An invalid path raises FileNotFoundError."""
    with pytest.raises(FileNotFoundError) as excinfo:
        fetch_app_version_from_file(pathlib.Path("invalid"))

    assert "No such file or directory: 'invalid/version.json'" in str(excinfo.value)


def test_fetch_app_version_from_file_extra_forbid(tmp_path: pathlib.Path) -> None:
    """A version.json with extra keys triggers a ValidationError (extra='forbid')."""
    payload = {**VALID_VERSION_PAYLOAD, "incorrect": "this should not be here"}
    (tmp_path / "version.json").write_text(json.dumps(payload))

    with pytest.raises(ValidationError):
        fetch_app_version_from_file(merino_root_path=tmp_path)


def test_fetch_app_version_from_file_missing_field(tmp_path: pathlib.Path) -> None:
    """A version.json missing required fields triggers a ValidationError."""
    payload = {k: v for k, v in VALID_VERSION_PAYLOAD.items() if k != "commit"}
    (tmp_path / "version.json").write_text(json.dumps(payload))

    with pytest.raises(ValidationError):
        fetch_app_version_from_file(merino_root_path=tmp_path)


def test_fetch_app_version_from_file_invalid_source_url(tmp_path: pathlib.Path) -> None:
    """A non-URL `source` value triggers a ValidationError via the HttpUrl field."""
    payload = {**VALID_VERSION_PAYLOAD, "source": "not-a-url"}
    (tmp_path / "version.json").write_text(json.dumps(payload))

    with pytest.raises(ValidationError):
        fetch_app_version_from_file(merino_root_path=tmp_path)
