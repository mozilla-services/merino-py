"""Protocol for the Manifest provider backend."""

from enum import Enum
from typing import NamedTuple, Protocol

from pydantic import BaseModel, HttpUrl
from merino.exceptions import BackendError


class ManifestBackendError(BackendError):
    """Manifest Specific Errors"""

    pass


class GetManifestResultCode(Enum):
    """Enum to capture the result of getting manifest file."""

    SUCCESS = 0
    FAIL = 1


class Domain(BaseModel):
    """Model for a domain within a manifest."""

    rank: int
    domain: str
    categories: list[str]
    serp_categories: list[int]
    url: HttpUrl
    title: str
    icon: str


class ManifestData(BaseModel):
    """Model for manifest file content"""

    domains: list[Domain]
    partners: list[dict[str, str]]


class ManifestFetchResult(NamedTuple):
    """Result of fetching the manifest from its backing store.

    The ``etag`` field carries the stringified GCS ``blob.generation`` on a
    successful fetch. It is surfaced to the HTTP layer so the ``/manifest``
    endpoint can answer conditional ``If-None-Match`` requests with a
    ``304 Not Modified`` instead of the full body. It is ``None`` on any
    failure path and for backends that do not provide a validator.
    """

    code: GetManifestResultCode
    data: ManifestData | None
    etag: str | None = None


class ManifestBackend(Protocol):
    """Protocol for the Manifest backend that the provider depends on."""

    async def fetch(self) -> ManifestFetchResult:
        """Fetch the manifest from storage.

        Raises:
            ManifestBackendError: If the manifest is unavailable or there is an error reading it.
        """
        ...
