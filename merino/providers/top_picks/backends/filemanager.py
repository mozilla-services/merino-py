"""A Filemanager to acquire data for the Top Picks Backend."""
import json
import logging
from enum import Enum
from json import JSONDecodeError
from typing import Any

from google.cloud.storage import Bucket, Client

from merino.exceptions import FilemanagerError

logger = logging.getLogger(__name__)


class DomainDataSource(str, Enum):
    """Source enum for domain data source."""

    REMOTE = "remote"
    LOCAL = "local"


class GetFileResultCode(Enum):
    """Enum to capture the result of getting domain file."""

    SUCCESS = 0
    FAIL = 1
    SKIP = 2


class TopPicksFilemanagerError(FilemanagerError):
    """Error during interaction with Top Picks data."""


class TopPicksLocalFilemanager:
    """Filemanager for processing local Top Picks data."""

    static_file_path: str

    def __init__(self, static_file_path: str) -> None:
        self.static_file_path = static_file_path

    def get_file(self) -> dict[str, Any]:
        """Read local domain list file.

        Raises:
            TopPicksFilemanagerError: If the top picks file path cannot be opened or decoded.
        """
        try:
            with open(self.static_file_path, "r") as readfile:
                domain_list: dict = json.load(readfile)
                return domain_list
        except OSError as os_error:
            raise TopPicksFilemanagerError(
                f"Cannot open file '{self.static_file_path}'"
            ) from os_error
        except JSONDecodeError as json_error:
            raise TopPicksFilemanagerError(
                f"Cannot decode file '{self.static_file_path}'"
            ) from json_error


class TopPicksRemoteFilemanager:
    """Filemanager for processing local Top Picks data."""

    client: Client
    gcs_project_path: str
    gcs_bucket_path: str
    blob_generation: int

    def __init__(
        self,
        gcs_project_path: str,
        gcs_bucket_path: str,
    ) -> None:
        self.gcs_project_path = gcs_project_path
        self.gcs_bucket_path = gcs_bucket_path
        self.blob_generation = 0

    def create_gcs_client(self) -> Client:
        """Initialize the GCS Client connection."""
        return Client(self.gcs_project_path)

    def get_file(self, client: Client) -> tuple[Enum, dict[str, Any] | None]:
        """Read remote domain list file.

        Raises:
            TopPicksFilemanagerError: If the top picks file cannot be accessed.
        Returns:
            Dictionary containing domain list
        """
        try:
            bucket: Bucket = client.get_bucket(self.gcs_bucket_path)
            if (
                blob := bucket.get_blob(
                    "top_picks_latest.json",
                    if_generation_not_match=self.blob_generation,
                )
            ) is not None:
                self.blob_generation = blob.generation
                blob_data = blob.download_as_text()
                file_contents: dict = json.loads(blob_data)
                logger.info("Successfully loaded remote domain file.")
                return (GetFileResultCode.SUCCESS, file_contents)
            return (GetFileResultCode.SKIP, None)
        except Exception as e:
            logger.error(f"Error with getting remote domain file. {e}")
            return (GetFileResultCode.FAIL, None)
