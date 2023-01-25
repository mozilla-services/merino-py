"""Versioning utility module"""
import json
import logging
import pathlib

from pydantic import BaseModel, HttpUrl

logger = logging.getLogger(__name__)


class Version(BaseModel):
    """Model for version.json data"""

    source: HttpUrl
    version: str
    commit: str
    build: str


def fetch_app_version_file(
    merino_root_path: pathlib.Path = pathlib.Path.cwd(),
) -> Version:
    """Fetch the content of the version.json file, which contains the SHA-1 hash
    commit value, repo source url, version, and CI build values .
    During deployment, this file is written and values are populated for
    the current version of Merino in production and staging.
    """
    version_file: pathlib.Path = merino_root_path / "version.json"

    # pathlib has the 'read_text()' function that opens the file, reads it
    # and closes the file like a context manager. Uses built-in open() function.
    version_file_content: dict = json.loads(version_file.read_text())
    return Version(**version_file_content)
