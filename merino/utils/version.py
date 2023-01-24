"""Versioning utility module"""
import json
import logging
import pathlib

logger = logging.getLogger(__name__)


def fetch_app_version_file(
    merino_root_path: pathlib.Path = pathlib.Path.cwd(),
) -> dict:
    """Fetch the SHA hash from commit value in the version.json file.
    During deployment, this file is written and values are
    populated for the current version of Merino in production and staging.
    """
    version_file: pathlib.Path = merino_root_path / "version.json"

    # pathlib has the 'read_text()' function that opens the file, reads it
    # and closes the file like a context manager. Uses built-in open() function.
    version_file_content: dict = json.loads(version_file.read_text())
    return version_file_content
