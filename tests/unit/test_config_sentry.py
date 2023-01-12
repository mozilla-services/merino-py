# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.

"""Unit tests for the config_sentry.py module."""
import os
from subprocess import check_output  # nosec

import pytest

from merino.config_sentry import (
    check_git_packed_refs,
    fetch_git_sha,
    fetch_sha_hash_from_version_file,
    read_git_head_file,
)
from merino.exceptions import InvalidGitRepository

# project_root is defined in the project_root fixture in
# conftest.py in this directory.


def test_read_git_head_file(project_root) -> None:  # nosec
    """Test to read the git head file to acquire refs/heads pointer."""
    result = read_git_head_file(project_root)
    assert result is not None
    # Add back the start of the string 'ref: ' contained in HEAD file.
    result = f"ref: {result}"
    assert result == (
        check_output("cat .git/HEAD", shell=True, cwd=project_root)
        .decode("utf-8")
        .strip()
    )


def test_read_git_head_file_fails(project_root) -> None:  # nosec
    """Test that ensures invalid directory results in exception."""
    with pytest.raises(InvalidGitRepository):
        fetch_git_sha(f"{project_root}/merino")
    with pytest.raises(Exception):
        fetch_git_sha(f"{project_root}/merino")


@pytest.mark.has_git_requirements
def test_fetch_git_sha(project_root) -> None:  # nosec
    """Test that checks that the git SHA can be accessed in the Merino
    directory.
    """
    result = fetch_git_sha(project_root)
    assert result is not None
    assert len(result) == 40
    assert (
        result
        == check_output("git rev-parse --verify HEAD", shell=True, cwd=project_root)
        .decode("utf-8")
        .strip()
    )


def test_fetch_git_sha_invalid_directory(project_root) -> None:  # nosec
    """Test that ensures invalid directory results in exception."""
    with pytest.raises(InvalidGitRepository):
        fetch_git_sha(os.path.join(project_root, "wrong"))


def test_has_git_requirements(project_root) -> None:
    """Ensure that a valid path in the .git directory exists."""
    assert os.path.exists(os.path.join(project_root, ".git", "refs", "heads", "main"))


def test_check_packed_refs(project_root) -> None:
    """Test to verify call of possible packed refs."""
    pass


def test_check_packed_refs_fails(project_root) -> None:
    """Test packed refs fails when passed invalid path."""
    invalid_head_path = f"{project_root}/merino"
    result = check_git_packed_refs(invalid_head_path)
    assert result is None


def test_fetch_sha_hash_from_version_file(project_root) -> None:
    """Test that the 'version.json' file in the root merino directory
    can be read to capture the SHA hash of the current main HEAD.
    This is the method implemented in the staging and produciton
    environments as there is no git directory created when service deployed.
    """
    hash = fetch_sha_hash_from_version_file(project_root)
    assert hash == "TBD"


def test_fetch_sha_hash_from_version_file_invalid_path(project_root) -> None:
    """Test that the 'version.json' file in the root merino directory
    can be read to capture the SHA hash of the current main HEAD.
    This is the method implemented in the staging and produciton
    environments as there is no git directory created when service deployed.
    """
    with pytest.raises(FileNotFoundError):
        fetch_sha_hash_from_version_file(f"{project_root}/wrong")
