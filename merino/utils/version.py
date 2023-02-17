"""Versioning utility module"""
import json
import pathlib

from pydantic import BaseModel, Extra, HttpUrl


class Version(BaseModel, extra=Extra.forbid):
    """Model for version.json data"""

    source: HttpUrl
    version: str
    commit: str
    build: str


def fetch_app_version_from_file(
    merino_root_path: pathlib.Path = pathlib.Path.cwd(),
) -> Version:
    """Fetch the content of the version.json file, which contains the SHA-1 hash
    commit value, repo source url, version, and CI build values .
    During deployment, this file is written and values are populated for
    the current version of Merino in production and staging.

    Errors are not handled here as the desired behavior is for merino to crash.
    The following exceptions can possibly be raised.
    Raises:
        FileNotFoundError if file cannot be found.
        JSONDecodeError if the file cannot be processed.
        ValidationError if Pydantic model validation for Version fails.
    """
    version_file: pathlib.Path = merino_root_path / "version.json"

    # pathlib has the 'read_text()' function that opens the file, reads it
    # and closes the file like a context manager. Uses built-in open() function.
    version_file_content: dict = json.loads(version_file.read_text())
    return Version(**version_file_content)


def check_version(
    merino_root_path: pathlib.Path = pathlib.Path.cwd(),
) -> bool:
    """Check the instance of version.json file at merino startup.
    If an exception is raised, merino will not initialize.

    Calls on fetch_app_version_from_file() for check. Possible exceptions
    defined in that function definition.
    """
    return True if fetch_app_version_from_file(merino_root_path) else False
